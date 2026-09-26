# =====================================================================================
# Generador de datos sinteticos - SaaS Metrics (Reto Alegra)
#
# Simula un SaaS ficticio (no son datos reales de Alegra ni de ningun cliente) con cuatro
# fuentes que NO cruzan limpio a proposito:
#
#   CRM (estilo HubSpot)        -> data/raw/crm/crm_hubspot_export.csv
#   Billing (estilo Stripe)     -> data/raw/billing/billing_stripe_export.csv
#   Contratos (formal, Excel)   -> data/raw/contratos/contratos.xlsx
#   Marketing (gasto por canal) -> data/raw/marketing/gasto_canales.csv
#
# El script primero simula la "verdad" (que cliente existe, que plan tiene cada mes,
# cuando entra y cuando se va) y SOLO DESPUES la deforma para producir los archivos de
# origen. La verdad queda guardada en data/control_totales.json: sirve para verificar,
# al final del pipeline ETL, que la reconstruccion desde los archivos sucios llega a
# los mismos numeros.
#
# Reproducible: semilla fija (SEED). Volver a correr este script borra y regenera todo.
# =====================================================================================

import json
import random
import string
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib_comun import normaliza  # noqa: E402  (compartida con el ETL, ver lib_comun.py)

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
fake = Faker("es_CO")
Faker.seed(SEED)

ROOT = Path(__file__).parent
RAW = ROOT / "raw"
SEEDS = ROOT / "seeds"

MESES = [f"2024{m:02d}" for m in range(1, 13)]  # id_periodo AAAAMM, 12 meses de historia
ID_PERIODOS = [int(m) for m in MESES]

# -------------------------------------------------------------------------------------
# Config canonica (esto SI es config de referencia, no algo por "detectar")
# -------------------------------------------------------------------------------------
PLANES = {
    "Starter":  {"precio_cop": 149_000, "precio_usd": 38},
    "Pro":      {"precio_cop": 349_000, "precio_usd": 89},
    "Business": {"precio_cop": 899_000, "precio_usd": 230},
}
PLAN_PESOS = {"Starter": 0.50, "Pro": 0.35, "Business": 0.15}

CANALES = {
    "Organico":     {"peso": 0.22, "gasto_base": 2_000_000, "gasto_var_por_cliente": 0},
    "Pago-Google":  {"peso": 0.24, "gasto_base": 1_500_000, "gasto_var_por_cliente": 380_000},
    "Pago-Meta":    {"peso": 0.20, "gasto_base": 1_200_000, "gasto_var_por_cliente": 300_000},
    "Referido":     {"peso": 0.16, "gasto_base": 300_000,   "gasto_var_por_cliente": 60_000},
    "Partner":      {"peso": 0.10, "gasto_base": 900_000,   "gasto_var_por_cliente": 180_000},
    "Outbound":     {"peso": 0.08, "gasto_base": 7_500_000, "gasto_var_por_cliente": 250_000},
}

# Tasa de cambio USD->COP por mes (ficticia, con variacion realista)
TASA_BASE = 3950
TASA_CAMBIO = {p: int(TASA_BASE + np.random.normal(0, 60)) for p in ID_PERIODOS}

N_CLIENTES_PAGOS = 180     # empresas que sí llegan a ser clientes de pago
N_LEADS_TRIAL = 55         # leads/trials que solo existen en el CRM, nunca facturan

CHURN_MENSUAL_BASE = {"Starter": 0.045, "Pro": 0.025, "Business": 0.012}
PROB_UPGRADE_MES = 0.05
PROB_DOWNGRADE_MES = 0.02
PROB_REACTIVACION_TRAS_BAJA = 0.15

PLAN_ORDEN = ["Starter", "Pro", "Business"]


# =====================================================================================
# PASO 1 - Simular la "verdad": una empresa por cliente, con su ciclo de vida completo
# =====================================================================================

def nombre_empresa_base():
    return fake.company()


def elegir_ponderado(pesos: dict):
    claves = list(pesos.keys())
    p = np.array([pesos[k] for k in claves])
    p = p / p.sum()
    return np.random.choice(claves, p=p)


clientes = []  # lista de dicts: verdad de cada cliente

for i in range(1, N_CLIENTES_PAGOS + 1):
    nombre_real = nombre_empresa_base()
    plan_inicial = elegir_ponderado(PLAN_PESOS)
    canal = elegir_ponderado({k: v["peso"] for k, v in CANALES.items()})
    moneda = "USD" if (plan_inicial == "Business" and np.random.rand() < 0.35) else "COP"

    # Meses 1-9 tienen más peso para que existan cohortes maduras (NRR, churn)
    mes_alta_idx = np.random.choice(range(9), p=[0.16, 0.14, 0.13, 0.11, 0.10, 0.09, 0.09, 0.09, 0.09])
    mes_alta = ID_PERIODOS[mes_alta_idx]

    # Caso dificil de integrar: ~8% de las empresas cambian de nombre a mitad de año
    # (fusion / rebranding). La normalizacion no los junta: el ETL debe resolverlos por el
    # identificador estable del CRM (id_contacto_crm), no por el nombre.
    caso_dificil = np.random.rand() < 0.08
    nombre_post_rebrand = nombre_empresa_base() if caso_dificil else None
    mes_rebrand = ID_PERIODOS[np.random.randint(mes_alta_idx + 1, 12)] if caso_dificil and mes_alta_idx < 11 else None

    # Ciclo de vida mes a mes
    plan_actual = plan_inicial
    activo = True
    eventos = [{"tipo": "nueva_suscripcion", "id_periodo": mes_alta, "plan": plan_actual}]
    mes_baja = None
    reactivado = False

    idx_inicio = ID_PERIODOS.index(mes_alta)
    for idx in range(idx_inicio + 1, 12):
        periodo = ID_PERIODOS[idx]
        if not activo:
            # La reactivacion (si ocurre) se decide aparte, despues de este bucle,
            # para poder fijar el mes exacto en que el cliente vuelve.
            continue
        r = np.random.rand()
        churn_p = CHURN_MENSUAL_BASE[plan_actual]
        if r < churn_p:
            eventos.append({"tipo": "cancelacion", "id_periodo": periodo, "plan": plan_actual})
            activo = False
            mes_baja = periodo
        elif r < churn_p + PROB_UPGRADE_MES and PLAN_ORDEN.index(plan_actual) < 2:
            nuevo_plan = PLAN_ORDEN[PLAN_ORDEN.index(plan_actual) + 1]
            eventos.append({"tipo": "upgrade", "id_periodo": periodo, "plan": nuevo_plan, "plan_anterior": plan_actual})
            plan_actual = nuevo_plan
        elif r < churn_p + PROB_UPGRADE_MES + PROB_DOWNGRADE_MES and PLAN_ORDEN.index(plan_actual) > 0:
            nuevo_plan = PLAN_ORDEN[PLAN_ORDEN.index(plan_actual) - 1]
            eventos.append({"tipo": "downgrade", "id_periodo": periodo, "plan": nuevo_plan, "plan_anterior": plan_actual})
            plan_actual = nuevo_plan

    # Reactivacion: si se dio de baja y no fue en los ultimos 2 meses del horizonte,
    # probabilidad de volver 2-3 meses despues con el mismo plan.
    if mes_baja is not None:
        idx_baja = ID_PERIODOS.index(mes_baja)
        if idx_baja < 9 and np.random.rand() < PROB_REACTIVACION_TRAS_BAJA:
            idx_reactivacion = min(idx_baja + np.random.randint(2, 4), 11)
            periodo_reac = ID_PERIODOS[idx_reactivacion]
            eventos.append({"tipo": "reactivacion", "id_periodo": periodo_reac, "plan": plan_actual})
            activo = True

    clientes.append({
        "cliente_id_verdad": i,
        "nombre_real": nombre_real,
        "nombre_post_rebrand": nombre_post_rebrand,
        "mes_rebrand": mes_rebrand,
        "moneda": moneda,
        "canal": canal,
        "eventos": eventos,
    })

# =====================================================================================
# PASO 2 - Calcular control_totales.json (la verdad, antes de ensuciar nada)
# =====================================================================================

def precio_cop(plan, moneda, periodo):
    """Equivalente en COP - para la verdad de control (MRR total de la compania en una
    sola moneda). NO es lo que se escribe en los archivos de origen."""
    if moneda == "COP":
        return PLANES[plan]["precio_cop"]
    return PLANES[plan]["precio_usd"] * TASA_CAMBIO[periodo]


def precio_moneda_nativa(plan, moneda):
    """El monto en la moneda propia del cliente - esto SI es lo que se escribe en
    billing/contratos. Si es USD, el ETL debe convertirlo el con la tasa del mes;
    si aqui ya se entregara convertido a COP, la conversion en el ETL duplicaria el
    ajuste de tasa de cambio."""
    if moneda == "COP":
        return PLANES[plan]["precio_cop"]
    return PLANES[plan]["precio_usd"]


control_mensual = {p: {"mrr_cop": 0.0, "altas": 0, "bajas": 0, "clientes_activos": 0,
                       "mrr_nuevo": 0.0, "mrr_expansion": 0.0, "mrr_contraccion": 0.0,
                       "mrr_churn": 0.0, "mrr_reactivacion": 0.0}
                   for p in ID_PERIODOS}

estado_cliente = {}  # cliente_id_verdad -> plan actual o None si inactivo

for periodo in ID_PERIODOS:
    for c in clientes:
        cid = c["cliente_id_verdad"]
        ev_mes = [e for e in c["eventos"] if e["id_periodo"] == periodo]
        for e in ev_mes:
            if e["tipo"] == "nueva_suscripcion":
                p_nuevo = precio_cop(e["plan"], c["moneda"], periodo)
                control_mensual[periodo]["mrr_nuevo"] += p_nuevo
                control_mensual[periodo]["altas"] += 1
                estado_cliente[cid] = e["plan"]
            elif e["tipo"] == "upgrade":
                delta = precio_cop(e["plan"], c["moneda"], periodo) - precio_cop(e["plan_anterior"], c["moneda"], periodo)
                control_mensual[periodo]["mrr_expansion"] += delta
                estado_cliente[cid] = e["plan"]
            elif e["tipo"] == "downgrade":
                delta = precio_cop(e["plan_anterior"], c["moneda"], periodo) - precio_cop(e["plan"], c["moneda"], periodo)
                control_mensual[periodo]["mrr_contraccion"] += delta
                estado_cliente[cid] = e["plan"]
            elif e["tipo"] == "cancelacion":
                control_mensual[periodo]["mrr_churn"] += precio_cop(e["plan"], c["moneda"], periodo)
                control_mensual[periodo]["bajas"] += 1
                estado_cliente[cid] = None
            elif e["tipo"] == "reactivacion":
                control_mensual[periodo]["mrr_reactivacion"] += precio_cop(e["plan"], c["moneda"], periodo)
                control_mensual[periodo]["altas"] += 1
                estado_cliente[cid] = e["plan"]

    mrr_total = 0.0
    activos = 0
    for cid, plan in estado_cliente.items():
        if plan is not None:
            cli = next(c for c in clientes if c["cliente_id_verdad"] == cid)
            mrr_total += precio_cop(plan, cli["moneda"], periodo)
            activos += 1
    control_mensual[periodo]["mrr_cop"] = round(mrr_total, 2)
    control_mensual[periodo]["clientes_activos"] = activos

control_totales = {
    "seed": SEED,
    "num_clientes_pagos_verdad": N_CLIENTES_PAGOS,
    "num_leads_trial_verdad": N_LEADS_TRIAL,
    "num_casos_dificiles_rebrand": sum(1 for c in clientes if c["nombre_post_rebrand"]),
    "tasa_cambio_por_periodo": TASA_CAMBIO,
    "mensual": control_mensual,
}

SEEDS.mkdir(parents=True, exist_ok=True)
with open(ROOT / "control_totales.json", "w", encoding="utf-8") as f:
    json.dump(control_totales, f, ensure_ascii=False, indent=2)

print(f"Control de verdad calculado: {N_CLIENTES_PAGOS} clientes de pago, "
      f"{control_totales['num_casos_dificiles_rebrand']} casos dificiles de rebranding.")
print(f"MRR verdad diciembre 2024: {control_mensual[ID_PERIODOS[-1]]['mrr_cop']:,.0f} COP")

# =====================================================================================
# PASO 3 - Deformar la verdad para producir los 4 archivos de origen sucios
# =====================================================================================

def variante_nombre(nombre: str, sistema: str) -> str:
    """Introduce variantes de escritura tipicas entre sistemas (no rompe la clave normalizada,
    salvo para los casos de rebranding que se manejan aparte)."""
    n = nombre
    r = np.random.rand()
    if sistema == "crm":
        if r < 0.25:
            n = n.upper()
        elif r < 0.35:
            n = n.replace("S.A.S.", "SAS").replace("S.A.", "SA")
    elif sistema == "billing":
        if r < 0.20:
            n = n.replace(" S.A.S.", "").replace(" SAS", "")  # Stripe a veces solo guarda el nombre comercial
        if r < 0.10:
            n = n + "  "  # espacio doble al final (typo de digitacion)
    elif sistema == "contrato":
        if r < 0.15:
            n = n.replace("a", "a ").strip()  # typo de digitacion: rompe el cruce por nombre normalizado
    return n


def telefono_variante():
    base = fake.msisdn()[-10:]
    r = np.random.rand()
    if r < 0.25:
        return f"+57 {base[:3]} {base[3:6]}{base[6:]}"
    if r < 0.5:
        return f"({base[:3]}) {base[3:6]}-{base[6:]}"
    if r < 0.75:
        return base
    return f"{base[:3]}-{base[3:6]}-{base[6:]}"


def email_variante(nombre_empresa: str):
    primera_palabra = normaliza(nombre_empresa).split(" ")[0]
    primera_palabra = "".join(ch for ch in primera_palabra if ch.isalnum())
    dominio = primera_palabra.lower() + ".com"
    usuario = fake.first_name().lower()
    correo = f"{usuario}@{dominio}"
    if np.random.rand() < 0.15:
        correo = correo.upper()
    return correo


def fecha_variante_texto(id_periodo: int, sistema: str):
    dia = np.random.randint(1, 28)
    anio = int(str(id_periodo)[:4])
    mes = int(str(id_periodo)[4:])
    if sistema == "crm" and np.random.rand() < 0.3:
        return f"{dia:02d}/{mes:02d}/{anio}"       # formato DD/MM/AAAA colado entre los ISO
    return f"{anio}-{mes:02d}-{dia:02d}"            # ISO, el formato dominante


CANAL_TEXTO_CRM = {
    "Organico": ["Organico", "organico", "SEO"],
    "Pago-Google": ["Google Ads", "google ads", "SEM", "Pago-Google"],
    "Pago-Meta": ["Meta Ads", "Facebook Ads", "meta ads"],
    "Referido": ["Referido", "referido cliente", "Referral"],
    "Partner": ["Partner", "Canal Partner", "alianza"],
    "Outbound": ["Outbound", "SDR", "prospeccion en frio"],
}

CANAL_TEXTO_MKT = {
    "Organico": "Organico / Contenido",
    "Pago-Google": "Google Ads",
    "Pago-Meta": "Meta Ads",
    "Referido": "Programa de Referidos",
    "Partner": "Partners",
    "Outbound": "Outbound / SDR",
}

PLAN_TEXTO_BILLING = {
    "Starter": ["Starter", "starter_monthly", "STARTER"],
    "Pro": ["Pro", "pro_monthly", "PRO-M"],
    "Business": ["Business", "business_monthly", "BUSINESS-ENT"],
}

# ---------------------------------------------------------------------------
# 3a. CRM (HubSpot-like): un registro por empresa (clientes de pago + leads/trial)
# ---------------------------------------------------------------------------
filas_crm = []
for c in clientes:
    cid = c["cliente_id_verdad"]
    idc = f"CRM-{cid:06d}"
    nombre = variante_nombre(c["nombre_real"], "crm")
    idx_alta = ID_PERIODOS.index(c["eventos"][0]["id_periodo"])
    fila = {
        "id_contacto_crm": idc,
        "nombre_empresa": nombre,
        "nombre_contacto": fake.name(),
        "email": email_variante(c["nombre_real"]),
        "telefono": telefono_variante(),
        "canal_adquisicion": random.choice(CANAL_TEXTO_CRM[c["canal"]]),
        "fecha_alta_lead": fecha_variante_texto(c["eventos"][0]["id_periodo"], "crm"),
        "etapa": "Cliente",
    }
    filas_crm.append(fila)
    # Rebranding: una segunda fila con el nombre nuevo a partir del mes de rebrand,
    # como si el CRM hubiera actualizado el registro (mismo id_contacto_crm).
    if c["nombre_post_rebrand"]:
        fila2 = dict(fila)
        fila2["nombre_empresa"] = variante_nombre(c["nombre_post_rebrand"], "crm")
        fila2["fecha_alta_lead"] = fecha_variante_texto(c["mes_rebrand"], "crm")
        filas_crm.append(fila2)

# Leads / trials que nunca facturan (no deben contar en MRR)
for i in range(N_LEADS_TRIAL):
    cid = 9000 + i
    filas_crm.append({
        "id_contacto_crm": f"CRM-{cid:06d}",
        "nombre_empresa": nombre_empresa_base(),
        "nombre_contacto": fake.name(),
        "email": f"{fake.first_name().lower()}@{fake.domain_name()}",
        "telefono": telefono_variante(),
        "canal_adquisicion": random.choice(list(CANAL_TEXTO_CRM.keys())),
        "fecha_alta_lead": fecha_variante_texto(random.choice(ID_PERIODOS), "crm"),
        "etapa": random.choice(["Lead", "Trial", "Perdido"]),
    })

df_crm = pd.DataFrame(filas_crm)

# Duplicados por reintento de sincronizacion (~4% de filas repetidas exactas)
dup_idx = df_crm.sample(frac=0.04, random_state=SEED).index
df_crm = pd.concat([df_crm, df_crm.loc[dup_idx]], ignore_index=True)
df_crm = df_crm.sample(frac=1, random_state=SEED).reset_index(drop=True)  # mezclar orden

# ---------------------------------------------------------------------------
# 3b. Billing (Stripe-like): un evento por fila
# ---------------------------------------------------------------------------
filas_billing = []
for c in clientes:
    nombre_facturacion = variante_nombre(
        c["nombre_post_rebrand"] if (c["nombre_post_rebrand"] and c["mes_rebrand"] and
                                      ID_PERIODOS.index(c["mes_rebrand"]) <= 0) else c["nombre_real"],
        "billing"
    )
    cus_id = "cus_" + "".join(random.choices(string.hexdigits.lower()[:16], k=14))
    for e in c["eventos"]:
        # si el rebrand ya ocurrio para este evento, usa el nombre nuevo en billing
        nombre_evt = nombre_facturacion
        if c["nombre_post_rebrand"] and c["mes_rebrand"] and e["id_periodo"] >= c["mes_rebrand"]:
            nombre_evt = variante_nombre(c["nombre_post_rebrand"], "billing")

        plan_evt = e["plan"]
        monto = precio_moneda_nativa(plan_evt, c["moneda"])
        monto_txt = monto
        # Un puñado de montos con separador de miles ("$149.000"): el ETL debe leerlos como
        # 149000 y no como 149.0
        if np.random.rand() < 0.015:
            monto_txt = f"${monto:,.0f}".replace(",", ".")  # formato con puntos de miles, sin decimales claros

        filas_billing.append({
            "id_customer_stripe": cus_id,
            "nombre_cliente_facturacion": nombre_evt,
            "email_facturacion": email_variante(c["nombre_real"]),
            "plan_contratado": random.choice(PLAN_TEXTO_BILLING[plan_evt]),
            "moneda": c["moneda"],
            "monto": monto_txt,
            "fecha_evento": fecha_variante_texto(e["id_periodo"], "billing"),
            "tipo_evento": e["tipo"],
            "id_periodo": e["id_periodo"],
        })

df_billing = pd.DataFrame(filas_billing)
# Un par de filas con tipo_evento vacio (registro corrupto -> cuarentena)
corrupt_idx = df_billing.sample(n=3, random_state=SEED).index
df_billing.loc[corrupt_idx, "tipo_evento"] = None

# ---------------------------------------------------------------------------
# 3c. Contratos (Excel formal): solo clientes Business + 40% de Pro (los que exigen
#     contrato firmado). Fecha con un bug clasico de Excel: la columna
#     de Excel mezcla fechas reales (Timestamp) y texto DD/MM/AAAA en la misma columna.
# ---------------------------------------------------------------------------
filas_contrato = []
for c in clientes:
    plan_inicial = c["eventos"][0]["plan"]
    incluye_contrato = plan_inicial == "Business" or (plan_inicial == "Pro" and np.random.rand() < 0.4)
    if not incluye_contrato:
        continue
    nombre_legal = variante_nombre(c["nombre_real"], "contrato").upper() + random.choice([" S.A.S.", " SAS"])
    fecha_alta = c["eventos"][0]["id_periodo"]
    anio = int(str(fecha_alta)[:4]); mes = int(str(fecha_alta)[4:]); dia = np.random.randint(1, 28)
    fecha_valor = pd.Timestamp(year=anio, month=mes, day=dia) if np.random.rand() < 0.5 else f"{dia:02d}/{mes:02d}/{anio}"
    filas_contrato.append({
        "razon_social": nombre_legal,
        "nit": fake.numerify("###.###.###") + "-" + str(np.random.randint(0, 9)),
        "plan_contratado": plan_inicial,
        "valor_mensual_contrato": precio_moneda_nativa(plan_inicial, c["moneda"]),
        "moneda": c["moneda"],
        "fecha_firma": fecha_valor,
        "vigencia_meses": random.choice([12, 24]),
    })

df_contratos = pd.DataFrame(filas_contrato)

# ---------------------------------------------------------------------------
# 3d. Marketing: gasto por canal y mes (con texto de canal inconsistente)
# ---------------------------------------------------------------------------
altas_por_canal_mes = {}
for c in clientes:
    periodo_alta = c["eventos"][0]["id_periodo"]
    altas_por_canal_mes.setdefault((c["canal"], periodo_alta), 0)
    altas_por_canal_mes[(c["canal"], periodo_alta)] += 1

filas_mkt = []
for periodo in ID_PERIODOS:
    for canal, cfg in CANALES.items():
        n_altas = altas_por_canal_mes.get((canal, periodo), 0)
        gasto = cfg["gasto_base"] + cfg["gasto_var_por_cliente"] * n_altas
        gasto = gasto * (1 + np.random.normal(0, 0.08))
        filas_mkt.append({
            "canal": CANAL_TEXTO_MKT[canal],
            "mes": f"{str(periodo)[:4]}-{str(periodo)[4:]}",
            "gasto_cop": round(gasto, 0),
        })

df_mkt = pd.DataFrame(filas_mkt)

# =====================================================================================
# PASO 4 - Escribir archivos de origen
# =====================================================================================
(RAW / "crm").mkdir(parents=True, exist_ok=True)
(RAW / "billing").mkdir(parents=True, exist_ok=True)
(RAW / "contratos").mkdir(parents=True, exist_ok=True)
(RAW / "marketing").mkdir(parents=True, exist_ok=True)

df_crm.to_csv(RAW / "crm" / "crm_hubspot_export.csv", index=False, encoding="utf-8")
df_billing.to_csv(RAW / "billing" / "billing_stripe_export.csv", index=False, encoding="utf-8")
df_contratos.to_excel(RAW / "contratos" / "contratos.xlsx", index=False)
df_mkt.to_csv(RAW / "marketing" / "gasto_canales.csv", index=False, encoding="utf-8")

# Seeds de configuracion (referencia, no algo por "detectar")
pd.DataFrame(
    [{"id_plan": i + 1, "nombre_plan": k, "precio_cop_mensual": v["precio_cop"], "precio_usd_mensual": v["precio_usd"]}
     for i, (k, v) in enumerate(PLANES.items())]
).to_csv(SEEDS / "planes.csv", index=False, encoding="utf-8")

pd.DataFrame(
    [{"id_canal": i + 1, "nombre_canal": k} for i, k in enumerate(CANALES.keys())]
).to_csv(SEEDS / "canales.csv", index=False, encoding="utf-8")

pd.DataFrame(
    [{"id_periodo": p, "tasa_usd_cop": TASA_CAMBIO[p]} for p in ID_PERIODOS]
).to_csv(SEEDS / "tasa_cambio.csv", index=False, encoding="utf-8")

print("\nArchivos generados:")
print(f"  CRM:        {len(df_crm)} filas -> data/raw/crm/crm_hubspot_export.csv")
print(f"  Billing:    {len(df_billing)} filas -> data/raw/billing/billing_stripe_export.csv")
print(f"  Contratos:  {len(df_contratos)} filas -> data/raw/contratos/contratos.xlsx")
print(f"  Marketing:  {len(df_mkt)} filas -> data/raw/marketing/gasto_canales.csv")
print(f"  Seeds:      planes.csv, canales.csv, tasa_cambio.csv")
print(f"  Control:    data/control_totales.json")
