# =====================================================================================
# Exporta dimensiones + vistas gold a CSV para Power BI (ruta CSV, no ODBC: Windows no
# trae driver ODBC de SQLite, y los tipos se fijan explicitamente en Power Query).
#
# Correr despues de cargar_datos.py. Se puede volver a correr en cualquier momento
# para refrescar los CSV tras un cambio en los datos de origen.
# =====================================================================================

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
DB_PATH = ROOT / "db" / "saas_metrics.db"
OUT = ROOT / "powerbi"
OUT.mkdir(parents=True, exist_ok=True)

TABLAS_Y_VISTAS = [
    # dimensiones (para relaciones y segmentadores en Power BI)
    "dim_periodo", "dim_cliente", "dim_plan", "dim_canal",
    # detalle (por si se necesita bajar de nivel)
    "fact_evento_suscripcion",
    # gold: metricas listas para consumo
    "gold_v_resumen_ejecutivo",
    "gold_v_mrr_movements",
    "gold_v_arr_mrr",
    "gold_v_nrr_mensual",
    "gold_v_churn",
    "gold_v_cohortes",
    "gold_v_cac_por_canal",
    "gold_v_ltv",
    "gold_v_calidad_clientes",
    "gold_v_resumen_calidad",
    "gold_v_calidad_cuarentena",
]

con = sqlite3.connect(DB_PATH)
for nombre in TABLAS_Y_VISTAS:
    df = pd.read_sql_query(f"SELECT * FROM {nombre}", con)
    df.to_csv(OUT / f"{nombre}.csv", index=False, encoding="utf-8")
    print(f"  {nombre}.csv: {len(df)} filas")

con.close()
print(f"\n{len(TABLAS_Y_VISTAS)} archivos exportados a {OUT}")
