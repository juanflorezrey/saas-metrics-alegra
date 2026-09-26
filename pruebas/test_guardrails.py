# =====================================================================================
# Pruebas de los guardrails del agente - sin LLM, directo contra el motor.
# Correr desde la raiz del repo:  python pruebas/test_guardrails.py
# =====================================================================================

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agente import guardrails as g  # noqa: E402
from agente.catalogo import describir_modelo  # noqa: E402

resultados = []


def caso(nombre, funcion):
    try:
        funcion()
        resultados.append((nombre, True, ""))
    except AssertionError as e:
        resultados.append((nombre, False, str(e)))
    except Exception as e:  # un error inesperado tambien es una falla
        resultados.append((nombre, False, f"{type(e).__name__}: {e}"))


def debe_permitir(sql):
    return g.ejecutar_consulta(sql, motivo="prueba")


def debe_bloquear(sql):
    try:
        g.ejecutar_consulta(sql, motivo="prueba")
    except g.ConsultaBloqueada:
        return
    raise AssertionError(f"NO se bloqueo: {sql}")


def lineas_bitacora():
    return g.BITACORA.read_text(encoding="utf-8").count("\n") if g.BITACORA.exists() else 0


eventos_antes = sqlite3.connect(g.DB_PATH).execute("SELECT COUNT(*) FROM fact_evento_suscripcion").fetchone()[0]
bitacora_antes = lineas_bitacora()

# --- Lo que SI debe poder hacer el agente -------------------------------------------
def _mrr_diciembre():
    r = debe_permitir("SELECT mrr_total FROM gold_v_arr_mrr WHERE id_periodo = 202412")
    assert r["filas"][0][0] == 57201326.0, f"MRR dic esperado 57201326, llego {r['filas'][0][0]}"

caso("SELECT a vista gold (MRR dic = 57.201.326)", _mrr_diciembre)
caso("Vista gold de detalle (construida sobre silver, publicada materializada)",
     lambda: debe_permitir("SELECT COUNT(*) FROM gold_v_eventos_detalle WHERE tipo_evento = 'cancelacion'"))
caso("Vista gold anidada (resumen_ejecutivo usa otras vistas gold)",
     lambda: debe_permitir("SELECT * FROM gold_v_resumen_ejecutivo"))
caso("SELECT a dimension permitida (dim_cliente)",
     lambda: debe_permitir("SELECT COUNT(*) FROM dim_cliente"))
caso("JOIN entre vista gold y dimension",
     lambda: debe_permitir("SELECT p.nombre_mes, a.mrr_total FROM gold_v_arr_mrr a JOIN dim_periodo p USING (id_periodo)"))
caso("CTE propio sobre vistas gold",
     lambda: debe_permitir("WITH t AS (SELECT * FROM gold_v_churn) SELECT MAX(churn_logos_pct) FROM t"))

def _truncado():
    r = debe_permitir("SELECT * FROM gold_v_estado_cliente_mensual")
    assert r["truncado"] and r["n_filas"] == g.MAX_FILAS, f"esperaba truncado a {g.MAX_FILAS}: {r['n_filas']}, {r['truncado']}"

caso(f"Mas de {g.MAX_FILAS} filas -> truncado y avisado", _truncado)

# --- Lo que NO debe poder hacer ------------------------------------------------------
caso("Lectura directa de bronze",  lambda: debe_bloquear("SELECT * FROM bronze_crm"))
caso("Lectura directa de silver",  lambda: debe_bloquear("SELECT * FROM fact_evento_suscripcion"))
caso("Lectura directa de control", lambda: debe_bloquear("SELECT * FROM err_registro_rechazado"))
caso("Lectura de sqlite_master",   lambda: debe_bloquear("SELECT * FROM sqlite_master"))
caso("Silver escondido en subconsulta",
     lambda: debe_bloquear("SELECT * FROM gold_v_arr_mrr WHERE id_periodo IN (SELECT id_periodo FROM fact_evento_suscripcion)"))
caso("CTE disfrazado de vista gold (nombre inventado)",
     lambda: debe_bloquear("WITH gold_v_truco AS (SELECT * FROM bronze_crm) SELECT * FROM gold_v_truco"))
caso("CTE que suplanta una vista gold real",
     lambda: debe_bloquear("WITH gold_v_arr_mrr AS (SELECT * FROM bronze_billing) SELECT * FROM gold_v_arr_mrr"))
caso("INSERT", lambda: debe_bloquear("INSERT INTO dim_canal (id_canal, nombre_canal) VALUES (99, 'x')"))
caso("UPDATE", lambda: debe_bloquear("UPDATE dim_cliente SET activo = 0"))
caso("DELETE", lambda: debe_bloquear("DELETE FROM dim_cliente"))
caso("DROP",   lambda: debe_bloquear("DROP VIEW gold_v_arr_mrr"))
caso("CREATE", lambda: debe_bloquear("CREATE TABLE x (a INT)"))
caso("ATTACH", lambda: debe_bloquear("ATTACH DATABASE 'otra.db' AS otra"))
caso("PRAGMA", lambda: debe_bloquear("PRAGMA table_info(bronze_crm)"))
caso("Dos sentencias en una llamada",
     lambda: debe_bloquear("SELECT 1 FROM gold_v_arr_mrr; DELETE FROM dim_cliente"))
caso(f"Consulta infinita cortada a los {g.MAX_SEGUNDOS:.0f} s",
     lambda: debe_bloquear("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c"))
# Destino en memoria: aunque la regla fallara, la prueba no escribe archivos.
caso("VACUUM INTO (copiar la base a otro destino)",
     lambda: debe_bloquear("VACUUM INTO 'file:prueba_vacuum?mode=memory'"))
caso("load_extension (cargar codigo nativo)", lambda: debe_bloquear("SELECT load_extension('x')"))
caso("Funcion-tabla pragma_table_list (listar el esquema)", lambda: debe_bloquear("SELECT * FROM pragma_table_list"))

SETLIMIT = hasattr(sqlite3.Connection, "setlimit")  # Python 3.11+


def _valor_gigante():
    # Segun la funcion, SQLite lo rechaza ("too big") o devuelve NULL; en ningun caso llega.
    try:
        texto = g.a_markdown(g.ejecutar_consulta("SELECT printf('%.*c', 50000000, 'x')", motivo="prueba"))
    except g.ConsultaBloqueada:
        return
    assert len(texto) <= g.MAX_CARACTERES_RESPUESTA + 500, f"respuesta de {len(texto)} caracteres"

caso("Valor gigante (50 MB de texto) no llega al agente", _valor_gigante)
if SETLIMIT:
    caso("Blob gigante en memoria (300 MB)", lambda: debe_bloquear("SELECT length(randomblob(300000000))"))
    caso("Texto gigante agregado (group_concat)",
         lambda: debe_bloquear("SELECT group_concat(printf('%.*c', 900000, 'x')) FROM gold_v_arr_mrr"))


def _respuesta_acotada():
    r = debe_permitir("SELECT printf('%.*c', 900, 'x') AS relleno, id_cliente FROM gold_v_estado_cliente_mensual")
    texto = g.a_markdown(r)
    assert len(texto) <= g.MAX_CARACTERES_RESPUESTA + 500, f"respuesta de {len(texto)} caracteres"
    assert "Se muestran" in texto, "no avisa que recorto filas"
    assert "x" * (g.MAX_CARACTERES_CELDA + 1) not in texto, "no recorto la celda larga"

caso(f"Respuesta al agente acotada a {g.MAX_CARACTERES_RESPUESTA:,} caracteres y avisada", _respuesta_acotada)

# --- Errores de SQL: se reportan como error corregible, no como bloqueo ---------------
def _columna_inexistente():
    try:
        g.ejecutar_consulta("SELECT columna_que_no_existe FROM gold_v_arr_mrr", motivo="prueba")
    except g.ConsultaBloqueada as e:
        raise AssertionError(f"se reporto como bloqueo en vez de error de SQL: {e}")
    except g.ErrorConsulta:
        return
    raise AssertionError("no fallo")

caso("Columna inexistente -> ErrorConsulta (el agente puede corregir su SQL)", _columna_inexistente)

# --- Catalogo, bitacora e integridad --------------------------------------------------
def _catalogo():
    texto = describir_modelo()
    assert "gold_v_resumen_ejecutivo" in texto and "gold_v_eventos_detalle" in texto
    assert "bronze_" not in texto and "fact_evento_suscripcion" not in texto.split("Columnas")[0], "el catalogo expone capas no permitidas"
    assert "(sin descripcion)" not in texto, "hay vistas sin descripcion en catalogo.py"

caso("describir_modelo lista solo lo permitido, todo con descripcion", _catalogo)

def _bitacora():
    nuevas = lineas_bitacora() - bitacora_antes
    assert nuevas >= 20, f"la bitacora solo registro {nuevas} lineas"

caso("La bitacora registra cada llamada", _bitacora)

def _integridad():
    despues = sqlite3.connect(g.DB_PATH).execute("SELECT COUNT(*) FROM fact_evento_suscripcion").fetchone()[0]
    assert despues == eventos_antes, f"la base cambio: {eventos_antes} -> {despues}"

caso("La base quedo intacta", _integridad)

# --- Reporte -------------------------------------------------------------------------
fallas = [r for r in resultados if not r[1]]
for nombre, ok, detalle in resultados:
    print(f"[{'OK' if ok else 'FALLA'}] {nombre}" + (f"  -> {detalle}" if detalle else ""))
print(f"\n{len(resultados) - len(fallas)}/{len(resultados)} pruebas OK")
sys.exit(1 if fallas else 0)
