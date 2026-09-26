# =====================================================================================
# Prueba de humo del servidor MCP con el protocolo real (stdio), sin LLM:
# levanta agente/servidor_mcp.py igual que lo haria Claude Code y llama cada herramienta.
# Correr desde la raiz del repo:  python pruebas/smoke_mcp.py
# =====================================================================================

import asyncio
import sys
import time
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parent.parent
ESPERADAS = ["consultar_sql", "describir_modelo", "graficar", "leer_documentacion"]

resultados = []


def verificar(nombre, condicion, detalle=""):
    resultados.append((nombre, bool(condicion), "" if condicion else detalle))


def texto(res) -> str:
    return "\n".join(getattr(c, "text", "") for c in res.content)


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "agente" / "servidor_mcp.py")],
        env={"PYTHONUTF8": "1"},
        cwd=str(ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as sesion:
            await sesion.initialize()

            herramientas = await sesion.list_tools()
            nombres = sorted(t.name for t in herramientas.tools)
            verificar("Expone exactamente las 4 herramientas", nombres == ESPERADAS, f"expone {nombres}")

            t0 = time.monotonic()
            r = await sesion.call_tool("describir_modelo", {})
            verificar("describir_modelo responde (primera llamada publica la capa gold)",
                      not r.is_error and "gold_v_resumen_ejecutivo" in texto(r), texto(r)[:300])
            print(f"  primera llamada (publicacion de la capa gold): {time.monotonic() - t0:.2f} s")

            r = await sesion.call_tool("consultar_sql", {
                "sql": "SELECT mrr_total FROM gold_v_arr_mrr WHERE id_periodo = 202412",
                "motivo": "smoke: MRR de diciembre"})
            verificar("consultar_sql: MRR dic = 57.201.326", not r.is_error and "57201326" in texto(r), texto(r))

            r = await sesion.call_tool("consultar_sql", {"sql": "SELECT * FROM bronze_billing", "motivo": "smoke: intento a bronze"})
            verificar("consultar_sql a bronze -> error de gobernanza", r.is_error and "gobernanza" in texto(r), texto(r))

            r = await sesion.call_tool("consultar_sql", {"sql": "DELETE FROM dim_cliente", "motivo": "smoke: intento de borrado"})
            verificar("consultar_sql DELETE -> error de gobernanza", r.is_error and "gobernanza" in texto(r), texto(r))

            r = await sesion.call_tool("consultar_sql", {
                "sql": "SELECT DISTINCT cliente FROM gold_v_eventos_detalle WHERE cliente LIKE 'D%az-Burgos'",
                "motivo": "smoke: tildes por stdio"})
            verificar("El servidor sigue vivo tras los errores y las tildes viajan bien (Díaz-Burgos)",
                      not r.is_error and "Díaz-Burgos" in texto(r), texto(r))

            r = await sesion.call_tool("leer_documentacion", {"documento": "contexto_simulacion"})
            verificar("leer_documentacion: contexto de simulacion", not r.is_error and "SINTETICOS" in texto(r), texto(r)[:200])

            r = await sesion.call_tool("leer_documentacion", {"documento": "diccionario_metricas"})
            verificar("leer_documentacion: diccionario de metricas", not r.is_error and "NRR" in texto(r), texto(r)[:200])

            r = await sesion.call_tool("graficar", {
                "sql": "SELECT nombre_mes, nrr_pct FROM gold_v_nrr_mensual ORDER BY id_periodo",
                "tipo": "linea", "x": "nombre_mes", "y": ["nrr_pct"], "titulo": "NRR mensual 2024 (smoke)",
                "linea_referencia": 100})
            imagenes = [c for c in r.content if getattr(c, "type", "") == "image"]
            ruta = next((linea.split(": ", 1)[1] for linea in texto(r).splitlines() if linea.startswith("Grafico guardado en")), None)
            verificar("graficar: devuelve imagen y crea el PNG",
                      not r.is_error and imagenes and ruta and Path(ruta).exists(), texto(r))

            r = await sesion.call_tool("graficar", {
                "sql": "SELECT nombre_canal, SUM(gasto_cop) * 1.0 / SUM(clientes_nuevos) AS cac FROM gold_v_cac_por_canal GROUP BY nombre_canal ORDER BY cac",
                "tipo": "barras_h", "x": "nombre_canal", "y": ["cac"], "titulo": "CAC por canal 2024 (smoke)"})
            verificar("graficar: barras horizontales (CAC por canal)", not r.is_error, texto(r))


asyncio.run(main())

fallas = [r for r in resultados if not r[1]]
for nombre, ok, detalle in resultados:
    print(f"[{'OK' if ok else 'FALLA'}] {nombre}" + (f"\n        -> {detalle}" if detalle else ""))
print(f"\n{len(resultados) - len(fallas)}/{len(resultados)} verificaciones OK")
sys.exit(1 if fallas else 0)
