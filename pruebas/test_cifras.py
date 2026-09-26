# =====================================================================================
# Cifras publicadas vs. base de datos - sin LLM.
# Cada cifra que citan README, docs/INFORME.md y pruebas/preguntas_demo.md se afirma
# aqui contra db/saas_metrics.db: si el pipeline cambia, la documentacion no puede
# quedar desalineada sin que esta prueba falle.
# Correr desde la raiz del repo:  python pruebas/test_cifras.py
# =====================================================================================

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
con = sqlite3.connect(f"{(ROOT / 'db' / 'saas_metrics.db').as_uri()}?mode=ro", uri=True)
control = json.loads((ROOT / "data" / "control_totales.json").read_text(encoding="utf-8"))

resultados = []


def q(sql):
    return con.execute(sql).fetchall()


def uno(sql):
    return q(sql)[0][0]


def caso(nombre, funcion):
    try:
        funcion()
        resultados.append((nombre, True, ""))
    except AssertionError as e:
        resultados.append((nombre, False, str(e)))
    except Exception as e:
        resultados.append((nombre, False, f"{type(e).__name__}: {e}"))


def igual(obtenido, esperado, tolerancia=0.0):
    ok = abs(obtenido - esperado) <= tolerancia if isinstance(esperado, (int, float)) else obtenido == esperado
    assert ok, f"esperado {esperado}, obtenido {obtenido}"


# --- Metricas principales ------------------------------------------------------------
def _cierre():
    mrr, arr, activos = q("SELECT mrr_total, arr_total, clientes_activos FROM gold_v_arr_mrr WHERE id_periodo = 202412")[0]
    igual(mrr, 57_201_326)
    igual(arr, 686_415_912)
    igual(activos, 144)
    igual(uno("SELECT mrr_total FROM gold_v_arr_mrr WHERE id_periodo = 202401"), 8_254_340)
    igual(uno("SELECT mrr_total FROM gold_v_arr_mrr WHERE id_periodo = 202409"), 59_979_290)

caso("MRR/ARR/activos a diciembre, enero y pico de septiembre", _cierre)


def _nrr():
    prom, minimo, maximo = q("SELECT ROUND(AVG(nrr_pct), 1), MIN(nrr_pct), MAX(nrr_pct) FROM gold_v_nrr_mensual")[0]
    igual((prom, minimo, maximo), (100.0, 94.3, 106.7))
    bajo_100 = [m for (m,) in q("SELECT nombre_mes FROM gold_v_nrr_mensual WHERE nrr_pct < 100 ORDER BY id_periodo")]
    igual(bajo_100, ["Marzo", "Abril", "Julio", "Septiembre", "Octubre", "Noviembre"])
    igual(uno("SELECT nrr_pct FROM gold_v_nrr_mensual WHERE id_periodo = 202412"), 101.2)

caso("NRR: promedio 100,0 %, rango 94,3-106,7, 6 meses bajo 100", _nrr)


def _churn():
    igual(q("SELECT ROUND(AVG(churn_logos_pct), 2), ROUND(AVG(churn_ingreso_pct), 2) FROM gold_v_churn")[0], (2.71, 1.87))
    igual(uno("SELECT COUNT(*) FROM gold_v_churn WHERE churn_ingreso_pct < churn_logos_pct"), 10)
    igual(uno("SELECT COUNT(*) FROM gold_v_churn"), 11)

caso("Churn promedio 2,71 % logos / 1,87 % ingreso; ingreso < logos en 10 de 11 meses", _churn)


def _caida_oct_nov():
    delta = dict(q("""SELECT a.id_periodo, a.mrr_total - b.mrr_total FROM gold_v_arr_mrr a
                      JOIN gold_v_arr_mrr b ON b.id_periodo = a.id_periodo - 1 WHERE a.id_periodo IN (202410, 202411)"""))
    igual(delta, {202410: -758_682, 202411: -2_671_282})
    nov = q("""SELECT m.mrr_nuevo, m.mrr_expansion, m.mrr_contraccion, m.mrr_churn, m.clientes_bajas, c.churn_logos_pct
               FROM gold_v_mrr_movements m JOIN gold_v_churn c USING (id_periodo) WHERE id_periodo = 202411""")[0]
    igual(nov, (0, 2_600_000, 2_066_112, 3_192_060, 11, 7.01))
    por_plan = dict(q("SELECT plan, COUNT(*) FROM gold_v_eventos_detalle WHERE id_periodo = 202411 AND tipo_evento = 'cancelacion' GROUP BY plan"))
    igual(por_plan, {"Starter": 6, "Pro": 4, "Business": 1})

caso("Caida de octubre y noviembre (preguntas 2 y 3)", _caida_oct_nov)


def _cac():
    cac = dict(q("SELECT nombre_canal, ROUND(SUM(gasto_cop) * 1.0 / SUM(clientes_nuevos)) FROM gold_v_cac_por_canal GROUP BY nombre_canal"))
    igual(cac, {"Referido": 173_171, "Organico": 661_622, "Pago-Meta": 687_528,
                "Pago-Google": 870_654, "Partner": 983_303, "Outbound": 6_257_989})
    igual(uno("SELECT SUM(clientes_nuevos) FROM gold_v_cac_por_canal"), 172)
    igual(uno("SELECT COUNT(*) FROM gold_v_eventos_detalle WHERE tipo_evento = 'nueva_suscripcion'"), 177)

caso("CAC anual por canal (gasto total / clientes) y 172 de 177 altas con canal", _cac)


def _ltv():
    filas = {p: (round(l), s, round(ls), b) for p, l, s, ls, b in
             q("SELECT nombre_plan, ltv_cop, churn_ingreso_plan_pct, ltv_cop_churn_plan, bajas_plan FROM gold_v_ltv")}
    igual(filas, {"Starter": (7_967_914, 3.94, 3_777_150, 20),
                  "Pro": (18_671_632, 3.05, 11_452_314, 14),
                  "Business": (48_391_345, 0.5, 181_606_737, 1)})

caso("LTV por plan y sensibilidad con churn por plan", _ltv)


def _ltv_cac():
    filas = {c: (a, s) for c, a, s in q("SELECT nombre_canal, ltv_cac, ltv_cac_churn_plan FROM gold_v_ltv_cac_por_canal")}
    igual(filas["Outbound"], (2.5, 3.07))
    igual(filas["Referido"], (84.09, 127.25))
    igual([c for (c,) in q("SELECT nombre_canal FROM gold_v_ltv_cac_por_canal WHERE ltv_cac < 3")], ["Outbound"])

caso("LTV:CAC por canal: Outbound es el unico bajo 3:1", _ltv_cac)


# --- Calidad de datos ----------------------------------------------------------------
def _calidad():
    igual(dict(q("SELECT estado_calidad, num_clientes FROM gold_v_resumen_calidad")),
          {"OK": 157, "REBRANDING": 16, "HUERFANO_O_AMBIGUO": 17,
           "CLIENTE_SIN_EVENTOS_VALIDOS": 2, "LEAD_SIN_FACTURACION": 55})
    igual(uno("SELECT mrr_inicial_cop FROM gold_v_resumen_calidad WHERE estado_calidad = 'HUERFANO_O_AMBIGUO'"), 1_145_000)
    huerfanos = dict(q("SELECT origen_sistema, COUNT(*) FROM map_alias_cliente WHERE metodo = 'ALIAS_MANUAL' GROUP BY 1"))
    igual(huerfanos, {"BILLING": 5, "CONTRATO": 7})
    igual(uno("SELECT filas_rechazadas FROM gold_v_calidad_cuarentena WHERE fuente = 'BILLING'"), 3)
    igual(uno("SELECT COUNT(DISTINCT id_cliente) FROM gold_v_eventos_detalle WHERE moneda_origen = 'USD'"), 11)
    activos = dict(q("""SELECT p.nombre_plan, COUNT(*) FROM gold_v_estado_cliente_mensual e
                        JOIN dim_plan p ON p.id_plan = e.id_plan_activo WHERE e.id_periodo = 202412 AND e.activo = 1 GROUP BY 1"""))
    igual(activos, {"Pro": 58, "Starter": 54, "Business": 32})

caso("Calidad: 157 OK / 16 rebranding / 17 huerfanos (5 Billing + 7 Contratos) / 2 sin eventos / 55 leads", _calidad)


def _reconciliacion():
    mrr_dic = uno("SELECT mrr_total FROM gold_v_arr_mrr WHERE id_periodo = 202412")
    igual(round(mrr_dic - control["mensual"]["202412"]["mrr_cop"]), -574_210)
    exactos = 0
    for p, altas, nuevo in q("SELECT id_periodo, clientes_altas, mrr_nuevo FROM gold_v_mrr_movements"):
        v = control["mensual"][str(p)]
        exactos += altas == v["altas"] and abs(nuevo - v["mrr_nuevo"]) < 0.5
    igual(exactos, 10)
    brechas = dict(q("""SELECT a.id_periodo, ROUND((a.mrr_total - b.mrr_total) - (m.mrr_nuevo + m.mrr_expansion
                        + m.mrr_reactivacion - m.mrr_contraccion - m.mrr_churn))
                        FROM gold_v_arr_mrr a JOIN gold_v_arr_mrr b ON b.id_periodo = a.id_periodo - 1
                        JOIN gold_v_mrr_movements m ON m.id_periodo = a.id_periodo"""))
    igual({p: v for p, v in brechas.items() if v}, {202407: 4_984, 202408: 349_000, 202411: -13_110})

caso("Reconciliacion con la verdad: -574.210 a diciembre, 10/12 meses exactos, brechas explicadas", _reconciliacion)


# --- Silver: bugs corregidos no vuelven ----------------------------------------------
def _silver():
    igual(uno("SELECT COUNT(*) FROM fact_contrato WHERE valor_mensual_cop < 100000"), 0)
    igual(uno("""SELECT COUNT(*) FROM dim_cliente c JOIN (SELECT id_cliente, MIN(id_periodo) p FROM fact_evento_suscripcion
                 WHERE tipo_evento = 'nueva_suscripcion' GROUP BY id_cliente) f USING (id_cliente)
                 WHERE CAST(REPLACE(SUBSTR(c.fecha_alta, 1, 7), '-', '') AS INTEGER) > f.p"""), 0)
    for archivo, leidas, aceptadas, rechazadas in q("SELECT archivo_origen, filas_leidas, filas_aceptadas, filas_rechazadas FROM ctl_carga"):
        assert leidas > 0 and leidas == aceptadas + rechazadas, f"ctl_carga incoherente en {archivo}"
        assert "\\" not in archivo, f"ruta con backslash en ctl_carga: {archivo}"
    igual(uno("SELECT COUNT(*) FROM err_registro_rechazado WHERE numero_linea IS NULL"), 0)
    igual(uno("SELECT COUNT(*) FROM dim_cliente WHERE moneda_principal = 'USD'"), 11)

caso("Silver: contratos USD convertidos, fecha_alta coherente, ctl_carga lleno, linaje en cuarentena", _silver)


fallas = [r for r in resultados if not r[1]]
for nombre, ok, detalle in resultados:
    print(f"[{'OK' if ok else 'FALLA'}] {nombre}" + (f"  -> {detalle}" if detalle else ""))
print(f"\n{len(resultados) - len(fallas)}/{len(resultados)} pruebas OK")
sys.exit(1 if fallas else 0)
