# =====================================================================================
# ETL - carga los 4 archivos de origen sucios a SQLite, resolviendo en el camino:
#
#   1. Identidad de cliente entre CRM / Billing / Contratos (map_alias_cliente)
#   2. Alias de plan y de canal (map_alias_plan, map_alias_canal)
#   3. Formatos de fecha, moneda y monto inconsistentes
#   4. Cuarentena de filas que no se pueden tipificar (err_registro_rechazado)
#
# Bronze = ingesta literal con linaje. Silver = dim_/fact_ ya resueltos. Gold
# (sql/02_vistas_gold.sql) se aplica al final, una vez Silver esta poblado.
#
# Reproducible: correr `python cargar_datos.py` reconstruye la base completa desde cero.
# =====================================================================================

import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

from lib_comun import normaliza

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DB_PATH = ROOT / "db" / "saas_metrics.db"
SQL_DIR = ROOT / "sql"

HOY = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def hash_fila(*valores) -> str:
    return hashlib.sha256("||".join(str(v) for v in valores).encode("utf-8")).hexdigest()[:16]


def hash_archivo(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def parsear_fecha_crm(valor: str):
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(valor).strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


# =====================================================================================
# 0. Reconstruir la base desde el DDL
# =====================================================================================
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
if DB_PATH.exists():
    DB_PATH.unlink()

con = sqlite3.connect(DB_PATH)
con.executescript((SQL_DIR / "01_ddl_sqlite.sql").read_text(encoding="utf-8"))
# El orden de carga de este script inserta hechos antes de que dim_cliente este
# completo (los clientes huerfanos solo se conocen al resolver Billing/Contrato).
# Se desactiva la validacion de FK durante la carga; PRAGMA foreign_key_check al
# final (paso 11) sigue verificando la integridad completa igual, sin depender de
# este interruptor.
con.execute("PRAGMA foreign_keys = OFF")

reporte = {"quarantine": [], "alias_cliente_dificiles": [], "hallazgos": []}


# =====================================================================================
# 1. Seeds: dim_periodo, dim_plan, dim_canal, dim_tasa_cambio
# =====================================================================================
NOMBRES_MES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
               "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

periodos = []
for anio in (2024, 2025):
    for mes in range(1, 13):
        id_periodo = anio * 100 + mes
        ultimo_dia = 31 if mes in (1, 3, 5, 7, 8, 10, 12) else (29 if (mes == 2 and anio % 4 == 0) else (28 if mes == 2 else 30))
        periodos.append((id_periodo, anio, mes, NOMBRES_MES[mes - 1],
                          f"{anio}-{mes:02d}-01", f"{anio}-{mes:02d}-{ultimo_dia}"))
con.executemany(
    "INSERT INTO dim_periodo (id_periodo, anio, mes, nombre_mes, fecha_inicio, fecha_fin) VALUES (?,?,?,?,?,?)",
    periodos,
)

df_planes = pd.read_csv(DATA / "seeds" / "planes.csv")
for i, row in df_planes.iterrows():
    con.execute(
        "INSERT INTO dim_plan (id_plan, nombre_plan, precio_cop_mensual, precio_usd_mensual, orden) VALUES (?,?,?,?,?)",
        (int(row.id_plan), row.nombre_plan, float(row.precio_cop_mensual), float(row.precio_usd_mensual), i),
    )

df_canales = pd.read_csv(DATA / "seeds" / "canales.csv")
for _, row in df_canales.iterrows():
    con.execute("INSERT INTO dim_canal (id_canal, nombre_canal) VALUES (?,?)", (int(row.id_canal), row.nombre_canal))

df_tasa = pd.read_csv(DATA / "seeds" / "tasa_cambio.csv")
for _, row in df_tasa.iterrows():
    con.execute("INSERT INTO dim_tasa_cambio (id_periodo, tasa_usd_cop) VALUES (?,?)",
                (int(row.id_periodo), float(row.tasa_usd_cop)))
TASA = dict(zip(df_tasa.id_periodo.astype(int), df_tasa.tasa_usd_cop.astype(float)))

con.commit()


# =====================================================================================
# 2. Registrar cargas (ctl_carga) y volcar a Bronze (literal, con linaje)
# =====================================================================================
def registrar_carga(archivo: Path, formato: str, contenido: str) -> int:
    cur = con.execute(
        "INSERT INTO ctl_carga (archivo_origen, hash_archivo, formato, contenido, fecha_carga) VALUES (?,?,?,?,?)",
        (archivo.relative_to(ROOT).as_posix(), hash_archivo(archivo), formato, contenido, HOY),
    )
    return cur.lastrowid


def cerrar_carga(id_carga: int, leidas: int, aceptadas: int, rechazadas: int) -> None:
    con.execute(
        "UPDATE ctl_carga SET filas_leidas = ?, filas_aceptadas = ?, filas_rechazadas = ? WHERE id_carga = ?",
        (leidas, aceptadas, rechazadas, id_carga),
    )


path_crm = DATA / "raw" / "crm" / "crm_hubspot_export.csv"
path_billing = DATA / "raw" / "billing" / "billing_stripe_export.csv"
path_contrato = DATA / "raw" / "contratos" / "contratos.xlsx"
path_mkt = DATA / "raw" / "marketing" / "gasto_canales.csv"

df_crm_raw = pd.read_csv(path_crm, dtype=str)
df_billing_raw = pd.read_csv(path_billing, dtype=str)
df_contrato_raw = pd.read_excel(path_contrato)          # aqui SI se permite tipo mixto (bug real de Excel)
df_mkt_raw = pd.read_csv(path_mkt, dtype=str)

id_carga_crm = registrar_carga(path_crm, "CSV", "CRM")
id_carga_billing = registrar_carga(path_billing, "CSV", "BILLING")
id_carga_contrato = registrar_carga(path_contrato, "XLSX", "CONTRATO")
id_carga_mkt = registrar_carga(path_mkt, "CSV", "MARKETING")

for i, r in df_crm_raw.iterrows():
    con.execute(
        "INSERT INTO bronze_crm (id_carga, numero_linea, id_contacto_crm, nombre_empresa, nombre_contacto, "
        "email, telefono, canal_adquisicion, fecha_alta_lead, etapa, hash_fila) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (id_carga_crm, i + 2, r.id_contacto_crm, r.nombre_empresa, r.nombre_contacto, r.email, r.telefono,
         r.canal_adquisicion, r.fecha_alta_lead, r.etapa, hash_fila(*r.values)),
    )

for i, r in df_billing_raw.iterrows():
    con.execute(
        "INSERT INTO bronze_billing (id_carga, numero_linea, id_customer_stripe, nombre_cliente_facturacion, "
        "email_facturacion, plan_contratado, moneda, monto, fecha_evento, tipo_evento, id_periodo, hash_fila) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (id_carga_billing, i + 2, r.id_customer_stripe, r.nombre_cliente_facturacion, r.email_facturacion,
         r.plan_contratado, r.moneda, r.monto, r.fecha_evento, r.tipo_evento, r.id_periodo, hash_fila(*r.values)),
    )

for i, r in df_contrato_raw.iterrows():
    con.execute(
        "INSERT INTO bronze_contrato (id_carga, numero_linea, razon_social, nit, plan_contratado, "
        "valor_mensual_contrato, moneda, fecha_firma, vigencia_meses, hash_fila) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (id_carga_contrato, i + 2, r.razon_social, r.nit, r.plan_contratado, str(r.valor_mensual_contrato),
         r.moneda, str(r.fecha_firma), str(r.vigencia_meses), hash_fila(*r.values)),
    )

for i, r in df_mkt_raw.iterrows():
    con.execute(
        "INSERT INTO bronze_marketing (id_carga, numero_linea, canal, mes, gasto_cop, hash_fila) VALUES (?,?,?,?,?,?)",
        (id_carga_mkt, i + 2, r.canal, r.mes, r.gasto_cop, hash_fila(*r.values)),
    )

# CRM no rechaza filas: todas quedan en Bronze y alimentan la resolucion de identidad.
cerrar_carga(id_carga_crm, len(df_crm_raw), len(df_crm_raw), 0)
con.commit()
print(f"Bronze cargado: CRM {len(df_crm_raw)} | Billing {len(df_billing_raw)} | "
      f"Contratos {len(df_contrato_raw)} | Marketing {len(df_mkt_raw)}")


# =====================================================================================
# 3. Resolver identidad de cliente (dim_cliente + map_alias_cliente)
#
#    CRM es el sistema de referencia para identidad: id_contacto_crm es estable aunque
#    el nombre de la empresa cambie (rebranding). Se construye primero el diccionario
#    de alias que CRM ya conoce de si mismo, y CONTRA ESE diccionario se resuelven
#    Billing y Contratos - no al reves.
# =====================================================================================
crm_por_id = df_crm_raw.groupby("id_contacto_crm")

id_cliente_por_crm = {}       # id_contacto_crm -> id_cliente
alias_normalizado_a_cliente = {}  # nombre_normalizado -> id_cliente  (semilla: nombres que CRM conoce de si mismo)
cliente_info = {}             # id_cliente -> {nombre_canonico, fecha_alta, canal, etapa}

siguiente_id_cliente = 1
alias_rows = []  # filas para map_alias_cliente

claves_ambiguas = set()  # nombres normalizados reclamados por mas de un id_cliente distinto en CRM

for id_contacto, grupo in crm_por_id:
    id_cliente = siguiente_id_cliente
    siguiente_id_cliente += 1
    id_cliente_por_crm[id_contacto] = id_cliente

    nombres_vistos = grupo["nombre_empresa"].drop_duplicates().tolist()
    nombre_canonico = nombres_vistos[-1]  # el mas reciente (post-rebrand si aplica)
    # Parsear ANTES de comparar: el min() sobre texto mezcla ISO con DD/MM/AAAA y escoge mal.
    fechas = [f for f in grupo["fecha_alta_lead"].map(parsear_fecha_crm) if f]
    fecha_alta = min(fechas) if fechas else None
    etapa = grupo["etapa"].iloc[-1]

    for nombre in nombres_vistos:
        key = normaliza(nombre)
        if key in alias_normalizado_a_cliente and alias_normalizado_a_cliente[key] != id_cliente:
            claves_ambiguas.add(key)
            reporte["hallazgos"].append(
                f"Nombre '{key}' usado por mas de una empresa distinta en CRM (id_cliente "
                f"{alias_normalizado_a_cliente[key]} y {id_cliente}): se marca AMBIGUO y NO se "
                f"cruza automaticamente contra Billing/Contratos - cada lado se resuelve por su "
                f"identificador propio (id_customer_stripe / fila de contrato), nunca por este nombre"
            )
            continue
        alias_normalizado_a_cliente[key] = id_cliente
        alias_rows.append((key, "CRM", id_cliente, "NORMALIZACION", None))

    if len(nombres_vistos) > 1:
        reporte["alias_cliente_dificiles"].append({
            "id_contacto_crm": id_contacto, "id_cliente": id_cliente, "nombres": nombres_vistos,
        })

    cliente_info[id_cliente] = {
        "nombre_canonico": nombre_canonico, "fecha_alta": fecha_alta, "etapa": etapa,
    }

# Neutralizar toda clave ambigua: ninguna referencia a ella debe quedar utilizable para
# cruzar Billing/Contratos por nombre (evita fusionar por error los movimientos de dos
# empresas reales distintas que solo coinciden en como se escribe su razon social).
for key in claves_ambiguas:
    alias_normalizado_a_cliente.pop(key, None)
alias_rows[:] = [row for row in alias_rows if row[0] not in claves_ambiguas]

print(f"dim_cliente: {len(cliente_info)} empresas resueltas desde CRM "
      f"({len(reporte['alias_cliente_dificiles'])} con mas de un nombre historico, "
      f"{len(claves_ambiguas)} nombres ambiguos entre empresas distintas)")

alias_vistos = set((a[0], a[1]) for a in alias_rows)
cliente_por_stripe = {}  # id_customer_stripe -> id_cliente (ancla identidad dentro de Billing)


def resolver_cliente_por_nombre(nombre_origen: str, origen_sistema: str):
    """Busca contra el diccionario CONFIABLE que ya conoce CRM (sin nombres ambiguos).
    Devuelve None si no hay match; el llamador decide como crear el huerfano."""
    key = normaliza(nombre_origen)
    if key in alias_normalizado_a_cliente:
        cid = alias_normalizado_a_cliente[key]
        if (key, origen_sistema) not in alias_vistos:
            alias_rows.append((key, origen_sistema, cid, "NORMALIZACION", None))
            alias_vistos.add((key, origen_sistema))
        return cid
    return None


def crear_huerfano(nombre_origen: str, origen_sistema: str, nota: str):
    """Cliente sin contraparte confiable en CRM (nombre ambiguo o sin match). Se registra
    con una clave UNICA por cliente (no por texto) para que dos huerfanos que compartan
    el mismo nombre nunca se fusionen entre si por accidente."""
    global siguiente_id_cliente
    cid = siguiente_id_cliente
    siguiente_id_cliente += 1
    cliente_info[cid] = {"nombre_canonico": nombre_origen, "fecha_alta": None, "etapa": None}
    reporte["hallazgos"].append(f"SIN MATCH confiable en {origen_sistema}: '{nombre_origen}' -> {nota}")
    alias_rows.append((f"{normaliza(nombre_origen)}#{cid}", origen_sistema, cid, "ALIAS_MANUAL", nota))
    return cid


def resolver_cliente_billing(id_stripe: str, nombre_origen: str):
    """Ancla la identidad en Billing por id_customer_stripe - el mismo criterio que CRM
    usa id_contacto_crm: la primera resolucion de un id_customer_stripe fija su id_cliente
    para todas sus filas. Asi un nombre ambiguo nunca fusiona dos clientes Stripe
    distintos, y un cambio de nombre posterior nunca parte a uno solo en dos."""
    if id_stripe in cliente_por_stripe:
        cid = cliente_por_stripe[id_stripe]
        if alias_normalizado_a_cliente.get(normaliza(nombre_origen)) == cid:
            resolver_cliente_por_nombre(nombre_origen, "BILLING")  # registra la variante como alias
        return cid
    cid = resolver_cliente_por_nombre(nombre_origen, "BILLING")
    if cid is None:
        cid = crear_huerfano(nombre_origen, "BILLING",
                              f"sin contraparte confiable en CRM (id_customer_stripe={id_stripe})")
    cliente_por_stripe[id_stripe] = cid
    return cid


def resolver_cliente_contrato(nombre_origen: str):
    cid = resolver_cliente_por_nombre(nombre_origen, "CONTRATO")
    if cid is None:
        cid = crear_huerfano(nombre_origen, "CONTRATO", "sin contraparte confiable en CRM")
    return cid


# Canal e email de referencia por id_cliente (para dim_cliente y luego map_alias_canal)
canal_texto_por_crm = df_crm_raw.set_index("id_contacto_crm")["canal_adquisicion"].groupby(level=0).last()
email_por_crm = df_crm_raw.set_index("id_contacto_crm")["email"].groupby(level=0).last()


# =====================================================================================
# 4. Resolver alias de plan y de canal (reglas, no diccionario del generador)
# =====================================================================================
def resolver_plan(texto: str) -> str | None:
    t = re.sub(r"[^A-Z]", "", str(texto).upper())
    if "STARTER" in t:
        return "Starter"
    if "PRO" in t and "PROFESIONAL" not in t:
        return "Pro"
    if "PROFESIONAL" in t:
        return "Pro"
    if "BUSINESS" in t or "EMPRESARIAL" in t:
        return "Business"
    return None


def resolver_canal(texto: str) -> str | None:
    t = normaliza(texto)
    if any(k in t for k in ["ORGANIC", "SEO", "CONTENIDO"]):
        return "Organico"
    if any(k in t for k in ["GOOGLE", "SEM"]):
        return "Pago-Google"
    if any(k in t for k in ["META", "FACEBOOK"]):
        return "Pago-Meta"
    if "REFER" in t:
        return "Referido"
    if any(k in t for k in ["PARTNER", "ALIANZA"]):
        return "Partner"
    if any(k in t for k in ["OUTBOUND", "SDR", "PROSPECCION"]):
        return "Outbound"
    return None


nombre_a_id_plan = dict(zip(df_planes.nombre_plan, df_planes.id_plan.astype(int)))
nombre_a_id_canal = dict(zip(df_canales.nombre_canal, df_canales.id_canal.astype(int)))

alias_plan_rows, alias_plan_vistos = [], set()
alias_canal_rows, alias_canal_vistos = [], set()


def id_plan_de(texto_origen: str, origen_sistema: str):
    plan = resolver_plan(texto_origen)
    if plan is None:
        reporte["hallazgos"].append(f"Plan no reconocido en {origen_sistema}: '{texto_origen}'")
        return None
    key = (str(texto_origen), origen_sistema)
    if key not in alias_plan_vistos:
        alias_plan_rows.append((str(texto_origen), origen_sistema, nombre_a_id_plan[plan]))
        alias_plan_vistos.add(key)
    return nombre_a_id_plan[plan]


def id_canal_de(texto_origen: str, origen_sistema: str):
    canal = resolver_canal(texto_origen)
    if canal is None:
        reporte["hallazgos"].append(f"Canal no reconocido en {origen_sistema}: '{texto_origen}'")
        return None
    key = (str(texto_origen), origen_sistema)
    if key not in alias_canal_vistos:
        alias_canal_rows.append((str(texto_origen), origen_sistema, nombre_a_id_canal[canal]))
        alias_canal_vistos.add(key)
    return nombre_a_id_canal[canal]


# =====================================================================================
# 5. Parsear monto y fecha sucios
# =====================================================================================
def parsear_monto(valor) -> float | None:
    """OJO con el orden: '149.000' es ambiguo (¿149 mil, o 149 con tres decimales?).
    En estos datos los precios siempre son enteros, asi que el patron de miles con
    punto (3 digitos exactos tras el punto, sin coma) SIEMPRE es separador de miles y
    debe resolverse ANTES de intentar un float() directo - si no, "149.000" se leeria
    como 149.0 y el monto quedaria mil veces mas chico, en silencio, sin ir a cuarentena."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    s2 = str(valor).replace("$", "").strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s2):          # "149.000" -> separador de miles
        return float(s2.replace(".", ""))
    if re.fullmatch(r"\d{1,3}(\.\d{3})*,\d{1,2}", s2):  # "1.234.567,89" -> miles+decimal europeo
        return float(s2.replace(".", "").replace(",", "."))
    try:
        return float(s2)                                # "89", "149000.0", etc.
    except ValueError:
        return None


def parsear_fecha_contrato(valor):
    """Bug clasico de Excel: la misma columna trae a veces una
    fecha real y a veces texto DD/MM/AAAA. pandas/openpyxl devuelve las celdas-fecha
    como datetime.datetime nativo (no pd.Timestamp) - isinstance(x, pd.Timestamp) NO
    las detecta porque pd.Timestamp es subclase de datetime, no al reves. Hay que
    comprobar contra datetime (la clase base), que cubre ambos casos."""
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%d")
    return parsear_fecha_crm(valor)


# =====================================================================================
# 6. Cargar fact_evento_suscripcion (orden secuencial por cliente para calcular
#    monto_anterior_cop en upgrade/downgrade)
# =====================================================================================
df_billing_raw["id_cliente"] = df_billing_raw.apply(
    lambda r: resolver_cliente_billing(r.id_customer_stripe, r.nombre_cliente_facturacion), axis=1
)
df_billing_raw["monto_parseado"] = df_billing_raw["monto"].apply(parsear_monto)
df_billing_raw["id_plan_resuelto"] = df_billing_raw.apply(
    lambda r: id_plan_de(r.plan_contratado, "BILLING"), axis=1
)

n_evento = 1
n_rechazadas_billing = 0
estado_por_cliente = {}  # id_cliente -> (monto_cop, id_plan) o None si inactivo
moneda_por_cliente = {}  # id_cliente -> moneda de su ultimo evento valido

df_billing_raw["orden_fecha"] = pd.to_datetime(df_billing_raw["fecha_evento"], errors="coerce")
df_billing_ordenado = df_billing_raw.sort_values(["id_cliente", "id_periodo", "orden_fecha"])

# El indice del DataFrame se conserva al ordenar: indice + 2 = linea del CSV (1 = encabezado).
for idx, r in df_billing_ordenado.iterrows():
    tipo = r.tipo_evento
    motivo_rechazo = None
    if pd.isna(tipo):
        motivo_rechazo = "tipo_evento vacio"
    elif tipo not in ("nueva_suscripcion", "upgrade", "downgrade", "cancelacion", "reactivacion"):
        motivo_rechazo = f"tipo_evento invalido: '{tipo}'"
    elif r.monto_parseado is None:
        motivo_rechazo = f"monto no parseable: '{r.monto}'"
    elif r.id_plan_resuelto is None:
        motivo_rechazo = f"plan no reconocido: '{r.plan_contratado}'"
    elif r.moneda not in ("COP", "USD"):
        motivo_rechazo = f"moneda invalida: '{r.moneda}'"

    if motivo_rechazo:
        con.execute(
            "INSERT INTO err_registro_rechazado (id_carga, numero_linea, fila_cruda, motivo, fecha_registro) "
            "VALUES (?,?,?,?,?)",
            (id_carga_billing, idx + 2, json.dumps(r.to_dict(), default=str, ensure_ascii=False), motivo_rechazo, HOY),
        )
        n_rechazadas_billing += 1
        continue

    monto_cop = r.monto_parseado if r.moneda == "COP" else r.monto_parseado * TASA[int(r.id_periodo)]
    cid = r.id_cliente
    estado_previo = estado_por_cliente.get(cid)

    monto_anterior_cop, id_plan_anterior = None, None
    if tipo in ("upgrade", "downgrade") and estado_previo is not None:
        monto_anterior_cop, id_plan_anterior = estado_previo

    fecha_evt = r.fecha_evento  # ya viene ISO en billing (ver generador)

    con.execute(
        "INSERT INTO fact_evento_suscripcion (id_carga, id_cliente, id_periodo, id_plan, id_plan_anterior, "
        "tipo_evento, moneda_origen, monto_mensual_cop, monto_anterior_cop, fecha_evento, numero_linea, hash_fila) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (id_carga_billing, cid, int(r.id_periodo), r.id_plan_resuelto, id_plan_anterior, tipo, r.moneda,
         round(monto_cop, 2), monto_anterior_cop, fecha_evt, idx + 2,
         hash_fila(r.id_customer_stripe, r.fecha_evento, tipo)),
    )
    n_evento += 1

    estado_por_cliente[cid] = None if tipo == "cancelacion" else (round(monto_cop, 2), r.id_plan_resuelto)
    moneda_por_cliente[cid] = r.moneda

cerrar_carga(id_carga_billing, len(df_billing_raw), n_evento - 1, n_rechazadas_billing)
con.commit()
print(f"fact_evento_suscripcion: {n_evento - 1} eventos cargados, {n_rechazadas_billing} rechazados a cuarentena")


# =====================================================================================
# 7. Cargar fact_contrato
# =====================================================================================
n_contrato, n_contrato_rechazado = 0, 0
for idx, r in df_contrato_raw.iterrows():
    cid = resolver_cliente_contrato(r.razon_social)
    id_plan = id_plan_de(r.plan_contratado, "CONTRATO")
    fecha = parsear_fecha_contrato(r.fecha_firma)
    periodo_firma = int(fecha[:4] + fecha[5:7]) if fecha else None
    motivo_rechazo = None
    if id_plan is None or fecha is None:
        motivo_rechazo = "plan o fecha_firma no reconocidos"
    elif r.moneda not in ("COP", "USD") or (r.moneda == "USD" and periodo_firma not in TASA):
        motivo_rechazo = f"moneda invalida o sin tasa de cambio: '{r.moneda}' ({periodo_firma})"
    if motivo_rechazo:
        con.execute(
            "INSERT INTO err_registro_rechazado (id_carga, numero_linea, fila_cruda, motivo, fecha_registro) "
            "VALUES (?,?,?,?,?)",
            (id_carga_contrato, idx + 2, json.dumps(r.to_dict(), default=str, ensure_ascii=False),
             motivo_rechazo, HOY),
        )
        n_contrato_rechazado += 1
        continue
    # El contrato trae el valor en la moneda propia del cliente: USD se convierte con la
    # tasa del mes de la firma, igual que Billing usa la tasa del mes del evento.
    valor = float(r.valor_mensual_contrato)
    valor_cop = valor * TASA[periodo_firma] if r.moneda == "USD" else valor
    con.execute(
        "INSERT INTO fact_contrato (id_carga, id_cliente, id_plan, valor_mensual_cop, fecha_firma, vigencia_meses) "
        "VALUES (?,?,?,?,?,?)",
        (id_carga_contrato, cid, id_plan, round(valor_cop, 2), fecha, int(r.vigencia_meses)),
    )
    n_contrato += 1

cerrar_carga(id_carga_contrato, len(df_contrato_raw), n_contrato, n_contrato_rechazado)
con.commit()
print(f"fact_contrato: {n_contrato} contratos cargados, {n_contrato_rechazado} rechazados")


# =====================================================================================
# 8. Cargar fact_gasto_adquisicion
# =====================================================================================
n_gasto, n_gasto_rechazado = 0, 0
for idx, r in df_mkt_raw.iterrows():
    id_canal = id_canal_de(r.canal, "MARKETING")
    anio, mes = r.mes.split("-")
    id_periodo = int(anio) * 100 + int(mes)
    if id_canal is None:
        con.execute(
            "INSERT INTO err_registro_rechazado (id_carga, numero_linea, fila_cruda, motivo, fecha_registro) "
            "VALUES (?,?,?,?,?)",
            (id_carga_mkt, idx + 2, json.dumps(r.to_dict(), default=str, ensure_ascii=False),
             f"canal no reconocido: '{r.canal}'", HOY),
        )
        n_gasto_rechazado += 1
        continue
    con.execute(
        "INSERT INTO fact_gasto_adquisicion (id_carga, id_canal, id_periodo, gasto_cop) VALUES (?,?,?,?)",
        (id_carga_mkt, id_canal, id_periodo, float(r.gasto_cop)),
    )
    n_gasto += 1

cerrar_carga(id_carga_mkt, len(df_mkt_raw), n_gasto, n_gasto_rechazado)
con.commit()
print(f"fact_gasto_adquisicion: {n_gasto} filas cargadas, {n_gasto_rechazado} rechazadas")


# =====================================================================================
# 9. Insertar dim_cliente y las tablas de alias ya resueltas
# =====================================================================================
canal_por_cliente = {}
for id_contacto, cid in id_cliente_por_crm.items():
    canal_texto = canal_texto_por_crm.get(id_contacto)
    canal_por_cliente[cid] = id_canal_de(canal_texto, "CRM") if canal_texto is not None else None

for cid, info in cliente_info.items():
    con.execute(
        "INSERT INTO dim_cliente (id_cliente, nombre_canonico, fecha_alta, id_canal, moneda_principal, activo, etapa_crm) "
        "VALUES (?,?,?,?,?,?,?)",
        (cid, info["nombre_canonico"], info["fecha_alta"], canal_por_cliente.get(cid),
         moneda_por_cliente.get(cid), 1 if estado_por_cliente.get(cid) else 0, info["etapa"]),
    )

for row in alias_rows:
    con.execute(
        "INSERT OR IGNORE INTO map_alias_cliente (texto_origen, origen_sistema, id_cliente, metodo, nota) "
        "VALUES (?,?,?,?,?)", row,
    )
for row in alias_plan_rows:
    con.execute("INSERT OR IGNORE INTO map_alias_plan (texto_origen, origen_sistema, id_plan) VALUES (?,?,?)", row)
for row in alias_canal_rows:
    con.execute("INSERT OR IGNORE INTO map_alias_canal (texto_origen, origen_sistema, id_canal) VALUES (?,?,?)", row)

con.commit()

# NOTA: fact_evento_suscripcion / fact_contrato se insertaron ANTES de existir las
# filas de dim_cliente (FK deshabilitadas via PRAGMA por simplicidad de orden de carga
# en este script; se valida integridad referencial al final, paso 11).


# =====================================================================================
# 10. Guardar seeds derivados (para reproducibilidad)
# =====================================================================================
pd.DataFrame(alias_rows, columns=["texto_origen", "origen_sistema", "id_cliente", "metodo", "nota"]).to_csv(
    DATA / "seeds" / "map_alias_cliente.csv", index=False, encoding="utf-8"
)
pd.DataFrame(alias_plan_rows, columns=["texto_origen", "origen_sistema", "id_plan"]).to_csv(
    DATA / "seeds" / "map_alias_plan.csv", index=False, encoding="utf-8"
)
pd.DataFrame(alias_canal_rows, columns=["texto_origen", "origen_sistema", "id_canal"]).to_csv(
    DATA / "seeds" / "map_alias_canal.csv", index=False, encoding="utf-8"
)

with open(ROOT / "reporte_calidad.json", "w", encoding="utf-8") as f:
    json.dump(reporte, f, ensure_ascii=False, indent=2, default=str)

# =====================================================================================
# 11. Verificacion de integridad referencial
# =====================================================================================
violaciones = con.execute("PRAGMA foreign_key_check").fetchall()
print(f"\nPRAGMA foreign_key_check: {len(violaciones)} violaciones" + (" -> OK" if not violaciones else " -> REVISAR"))
if violaciones:
    print(violaciones[:10])

print(f"Hallazgos de calidad: {len(reporte['hallazgos'])} (detalle en reporte_calidad.json)")
print(f"Clientes con mas de un nombre historico (rebranding detectado): {len(reporte['alias_cliente_dificiles'])}")

# =====================================================================================
# 12. Capa Gold: vistas de consumo
# =====================================================================================
con.executescript((SQL_DIR / "02_vistas_gold.sql").read_text(encoding="utf-8"))
n_vistas = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'view' AND name LIKE 'gold_v_%'").fetchone()[0]
print(f"Vistas gold aplicadas: {n_vistas}")

con.close()
print("\nCarga completa. Base: db/saas_metrics.db")
