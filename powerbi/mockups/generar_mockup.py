# =====================================================================================
# Inyecta los datos de la capa gold en el mockup HTML del tablero ejecutivo.
# Lee los mismos CSV que consume el modelo de Power BI (powerbi/*.csv) y escribe el JSON
# entre los marcadores /*DATOS_INICIO*/ ... /*DATOS_FIN*/ de tablero_ejecutivo.html.
# Asi el mockup es un solo archivo y ninguna cifra queda escrita a mano.
# Correr desde la raiz del repo:  python powerbi/mockups/generar_mockup.py
# =====================================================================================

import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "powerbi"
HTML = Path(__file__).resolve().parent / "tablero_ejecutivo.html"


def filas(nombre):
    df = pd.read_csv(CSV / f"{nombre}.csv", encoding="utf-8")
    return json.loads(df.to_json(orient="records", force_ascii=False))


control = json.loads((ROOT / "data" / "control_totales.json").read_text(encoding="utf-8"))

datos = {
    "generado": date.today().isoformat(),
    "resumen": filas("gold_v_resumen_ejecutivo"),
    "cac": filas("gold_v_cac_por_canal"),
    "cohortes": filas("gold_v_cohortes"),
    "ltv": filas("gold_v_ltv"),
    "ltv_cac": filas("gold_v_ltv_cac_por_canal"),
    "calidad_clientes": filas("gold_v_calidad_clientes"),
    "resumen_calidad": filas("gold_v_resumen_calidad"),
    "cuarentena": filas("gold_v_calidad_cuarentena"),
    "canales": filas("dim_canal"),
    "planes": filas("dim_plan"),
    # MRR de la verdad de control (antes de ensuciar los datos), solo para la conciliacion.
    "control_mrr": {p: v["mrr_cop"] for p, v in control["mensual"].items()},
}

html = HTML.read_text(encoding="utf-8")
bloque = "/*DATOS_INICIO*/" + json.dumps(datos, ensure_ascii=False, separators=(",", ":")) + "/*DATOS_FIN*/"
nuevo, n = re.subn(r"/\*DATOS_INICIO\*/.*?/\*DATOS_FIN\*/", lambda _: bloque, html, flags=re.S)
assert n == 1, "No se encontraron los marcadores /*DATOS_INICIO*/ ... /*DATOS_FIN*/ en el HTML"
HTML.write_text(nuevo, encoding="utf-8")

print(f"Datos inyectados en {HTML.relative_to(ROOT).as_posix()}:")
for clave, valor in datos.items():
    if isinstance(valor, list):
        print(f"  {clave}: {len(valor)} filas")
