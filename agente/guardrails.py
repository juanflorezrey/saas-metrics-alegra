# =====================================================================================
# Acceso gobernado a la base del SaaS para el agente conversacional.
#
# El agente escribe SQL libre, asi que las reglas NO pueden vivir solo en el prompt:
# las hace cumplir el motor de SQLite.
#
#   1. Capa publicada    el agente NUNCA se conecta a db/saas_metrics.db. Al arrancar se
#                        publica una copia EN MEMORIA que contiene SOLO las vistas gold
#                        (materializadas) y las dimensiones. Bronze, silver y control no
#                        existen en esa conexion: no hay nada que evadir.
#   2. Solo lectura      la fuente se adjunta con mode=ro solo para copiar; la copia queda
#                        con PRAGMA query_only y un authorizer que niega todo lo que no sea
#                        leer las tablas publicadas.
#   3. Una sentencia     sqlite3.execute ya rechaza sentencias multiples.
#   4. Limites           maximo MAX_FILAS filas devueltas y MAX_SEGUNDOS por consulta.
#   5. Bitacora          cada llamada queda en salidas/auditoria_consultas.jsonl.
#
# Por que una copia y no un allowlist sobre la base real: el authorizer de SQLite reporta
# como "origen" de una lectura tanto la vista como un CTE, asi que un CTE con el nombre de
# una vista gold podia colarse hasta bronze (lo detecto pruebas/test_guardrails.py).
# Publicar solo lo permitido elimina esa clase entera de evasiones.
#
# Mismo principio que el resto del proyecto: "Power BI y los notebooks leen SOLO de gold".
# =====================================================================================

import json
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "saas_metrics.db"
SALIDAS = ROOT / "salidas"
BITACORA = SALIDAS / "auditoria_consultas.jsonl"

MAX_FILAS = 200
MAX_SEGUNDOS = 5.0

PREFIJO_GOLD = "gold_v_"
DIMENSIONES_PERMITIDAS = ("dim_periodo", "dim_plan", "dim_canal", "dim_cliente")

MENSAJE_GOBERNANZA = (
    "Bloqueado por gobernanza: el agente solo puede LEER las vistas gold_v_* y las dimensiones "
    "(dim_periodo, dim_plan, dim_canal, dim_cliente). Las capas bronze/silver/control no estan "
    "publicadas para el agente y no se permite ninguna escritura."
)

_SQLITE_FUNCTION = getattr(sqlite3, "SQLITE_FUNCTION", 31)
_SQLITE_RECURSIVE = getattr(sqlite3, "SQLITE_RECURSIVE", 33)


class ErrorConsulta(Exception):
    """La consulta no se pudo ejecutar (SQL invalido, columna inexistente, etc.)."""


class ConsultaBloqueada(ErrorConsulta):
    """La consulta viola una regla de gobernanza."""


# -------------------------------------------------------------------------------------
# Capa publicada (copia en memoria de gold + dimensiones)
# -------------------------------------------------------------------------------------
_lock = threading.Lock()
_estado = {"con": None, "mtime": None, "publicadas": (), "no_publicadas": frozenset()}


def _construir_capa_publicada():
    con = sqlite3.connect(":memory:", uri=True, check_same_thread=False)
    con.execute("ATTACH DATABASE ? AS fuente", (DB_PATH.resolve().as_uri() + "?mode=ro",))
    objetos_fuente = {n for (n,) in con.execute("SELECT name FROM fuente.sqlite_master WHERE type IN ('table', 'view')")}
    vistas_gold = sorted(n for n in objetos_fuente if n.startswith(PREFIJO_GOLD))
    publicadas = tuple(vistas_gold) + tuple(d for d in DIMENSIONES_PERMITIDAS if d in objetos_fuente)
    for nombre in publicadas:
        con.execute(f'CREATE TABLE main."{nombre}" AS SELECT * FROM fuente."{nombre}"')
    con.commit()
    con.execute("DETACH DATABASE fuente")
    con.execute("PRAGMA query_only = ON")

    permitidas = frozenset(publicadas)

    def autorizador(accion, arg1, arg2, nombre_db, origen):
        if accion in (sqlite3.SQLITE_SELECT, _SQLITE_FUNCTION, _SQLITE_RECURSIVE):
            return sqlite3.SQLITE_OK
        if accion == sqlite3.SQLITE_READ and arg1 in permitidas:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    con.set_authorizer(autorizador)
    return con, publicadas, frozenset(objetos_fuente - permitidas)


@contextmanager
def capa_publicada():
    """Entrega (conexion, objetos_publicados) bajo lock. Re-publica si la base cambio
    (p.ej. se volvio a correr el ETL con el servidor encendido)."""
    with _lock:
        mtime = DB_PATH.stat().st_mtime
        if _estado["con"] is None or _estado["mtime"] != mtime:
            if _estado["con"] is not None:
                _estado["con"].close()
            con, publicadas, no_publicadas = _construir_capa_publicada()
            _estado.update(con=con, mtime=mtime, publicadas=publicadas, no_publicadas=no_publicadas)
        yield _estado["con"], _estado["publicadas"]


# -------------------------------------------------------------------------------------
# Ejecucion de consultas del agente
# -------------------------------------------------------------------------------------
def _registrar(motivo: str, sql: str, estado: str, filas: int | None, ms: float, detalle: str | None) -> None:
    SALIDAS.mkdir(parents=True, exist_ok=True)
    entrada = {
        "fecha_hora": datetime.now().isoformat(timespec="seconds"),
        "motivo": motivo,
        "sql": sql,
        "estado": estado,
        "filas": filas,
        "ms": round(ms, 1),
        "detalle": detalle,
    }
    with open(BITACORA, "a", encoding="utf-8") as f:
        f.write(json.dumps(entrada, ensure_ascii=False) + "\n")


def _clasificar_error(e: sqlite3.Error) -> ErrorConsulta:
    texto = str(e)
    if isinstance(e, sqlite3.ProgrammingError) and "one statement" in texto:
        return ConsultaBloqueada("Solo se permite UNA sentencia SELECT por llamada.")
    if "prohibited" in texto or "not authorized" in texto or "readonly" in texto or "query_only" in texto:
        return ConsultaBloqueada(MENSAJE_GOBERNANZA)
    if "interrupted" in texto:
        return ConsultaBloqueada(f"La consulta supero el limite de {MAX_SEGUNDOS:.0f} s y se cancelo.")
    tabla = re.search(r"no such table: (?:\w+\.)?(\w+)", texto)
    if tabla and tabla.group(1) in _estado["no_publicadas"]:
        # Existe en la base real pero no esta publicada para el agente (bronze/silver/control).
        return ConsultaBloqueada(MENSAJE_GOBERNANZA)
    if tabla:
        return ErrorConsulta(f"Error de SQL: {texto}. Usa describir_modelo para ver las vistas disponibles.")
    return ErrorConsulta(f"Error de SQL: {texto}")


def ejecutar_consulta(sql: str, motivo: str) -> dict:
    """Ejecuta una consulta del agente bajo todas las reglas de gobernanza.

    Devuelve {"columnas", "filas", "n_filas", "truncado", "ms"}.
    Lanza ConsultaBloqueada (regla de gobernanza) o ErrorConsulta (SQL invalido)."""
    inicio = time.monotonic()
    limite = inicio + MAX_SEGUNDOS
    with capa_publicada() as (con, _publicadas):
        con.set_progress_handler(lambda: 1 if time.monotonic() > limite else 0, 10_000)
        try:
            cur = con.execute(sql)
            filas = cur.fetchmany(MAX_FILAS + 1)
            columnas = [d[0] for d in (cur.description or [])]
            cur.close()
        except sqlite3.Error as e:
            error = _clasificar_error(e)
            estado = "bloqueada" if isinstance(error, ConsultaBloqueada) else "error"
            _registrar(motivo, sql, estado, None, (time.monotonic() - inicio) * 1000, str(e))
            raise error from e
        finally:
            con.set_progress_handler(None, 0)

    truncado = len(filas) > MAX_FILAS
    filas = filas[:MAX_FILAS]
    ms = (time.monotonic() - inicio) * 1000
    _registrar(motivo, sql, "permitida", len(filas), ms, "truncado" if truncado else None)
    return {"columnas": columnas, "filas": filas, "n_filas": len(filas), "truncado": truncado, "ms": round(ms, 1)}


def _celda(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).replace("|", "\\|")


def a_markdown(resultado: dict) -> str:
    """Tabla markdown + pie con filas, truncado y duracion."""
    columnas, filas = resultado["columnas"], resultado["filas"]
    if not columnas:
        return "(la consulta no devolvio columnas)"
    lineas = ["| " + " | ".join(columnas) + " |", "|" + "---|" * len(columnas)]
    lineas += ["| " + " | ".join(_celda(v) for v in fila) + " |" for fila in filas]
    pie = f"\n{resultado['n_filas']} fila(s) en {resultado['ms']} ms."
    if resultado["truncado"]:
        pie += f" RESULTADO TRUNCADO a {MAX_FILAS} filas: agrega o filtra si necesitas el total."
    return "\n".join(lineas) + pie
