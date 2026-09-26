-- =====================================================================================
-- CAPA GOLD - vistas de consumo. Power BI y los notebooks leen SOLO de aqui.
-- Ninguna regla de negocio de metricas SaaS vive en el dashboard, vive aqui.
--
-- Requiere que Silver ya este poblado (correr cargar_datos.py primero).
-- Horizonte de datos: 202401-202412 (dim_periodo esta sembrado hasta 2025 para cuando
-- haya carga real de meses futuros, pero estas vistas acotan al horizonte actual).
-- =====================================================================================

DROP VIEW IF EXISTS gold_v_eventos_detalle;
DROP VIEW IF EXISTS gold_v_resumen_ejecutivo;
DROP VIEW IF EXISTS gold_v_calidad_cuarentena;
DROP VIEW IF EXISTS gold_v_resumen_calidad;
DROP VIEW IF EXISTS gold_v_calidad_clientes;
DROP VIEW IF EXISTS gold_v_ltv;
DROP VIEW IF EXISTS gold_v_cac_por_canal;
DROP VIEW IF EXISTS gold_v_churn;
DROP VIEW IF EXISTS gold_v_cohortes;
DROP VIEW IF EXISTS gold_v_nrr_mensual;
DROP VIEW IF EXISTS gold_v_arr_mrr;
DROP VIEW IF EXISTS gold_v_mrr_movements;
DROP VIEW IF EXISTS gold_v_estado_cliente_mensual;

-- ------------------------------------------------------------------------------------
-- Base: estado de cada cliente al CIERRE de cada mes (plan activo, MRR, o inactivo).
-- Se deriva del ULTIMO evento de ese cliente con id_periodo <= el mes en cuestion -
-- el estado persiste entre meses hasta el siguiente evento (alta/cambio/baja).
-- Todas las demas vistas de metricas parten de esta.
-- ------------------------------------------------------------------------------------
CREATE VIEW gold_v_estado_cliente_mensual AS
WITH clientes_con_eventos AS (
    SELECT DISTINCT id_cliente FROM fact_evento_suscripcion
),
universo AS (
    SELECT c.id_cliente, p.id_periodo
    FROM clientes_con_eventos c
    CROSS JOIN dim_periodo p
    WHERE p.id_periodo BETWEEN 202401 AND 202412
),
ultimo_evento AS (
    SELECT u.id_cliente, u.id_periodo,
        (SELECT e.id_evento FROM fact_evento_suscripcion e
         WHERE e.id_cliente = u.id_cliente AND e.id_periodo <= u.id_periodo
         ORDER BY e.id_periodo DESC, e.id_evento DESC LIMIT 1) AS id_evento_vigente
    FROM universo u
)
SELECT
    ue.id_cliente,
    ue.id_periodo,
    ev.tipo_evento                                                AS ultimo_tipo_evento,
    CASE WHEN ev.tipo_evento = 'cancelacion' THEN NULL ELSE ev.id_plan END        AS id_plan_activo,
    CASE WHEN ev.tipo_evento = 'cancelacion' THEN 0 ELSE ev.monto_mensual_cop END AS mrr_cliente,
    CASE WHEN ev.tipo_evento = 'cancelacion' THEN 0 ELSE 1 END      AS activo
FROM ultimo_evento ue
JOIN fact_evento_suscripcion ev ON ev.id_evento = ue.id_evento_vigente;

-- ------------------------------------------------------------------------------------
-- MRR waterfall: nuevo / expansion / contraccion / churn / reactivacion, por mes.
-- Se calcula DIRECTO de los eventos del mes (no por diferencia de estados), que es
-- la forma correcta y estandar de construir un waterfall de MRR.
-- ------------------------------------------------------------------------------------
CREATE VIEW gold_v_mrr_movements AS
SELECT
    per.id_periodo,
    per.anio,
    per.nombre_mes,
    ROUND(SUM(CASE WHEN e.tipo_evento = 'nueva_suscripcion' THEN e.monto_mensual_cop ELSE 0 END), 2) AS mrr_nuevo,
    ROUND(SUM(CASE WHEN e.tipo_evento = 'reactivacion' THEN e.monto_mensual_cop ELSE 0 END), 2)      AS mrr_reactivacion,
    ROUND(SUM(CASE WHEN e.tipo_evento = 'upgrade' THEN e.monto_mensual_cop - e.monto_anterior_cop ELSE 0 END), 2)   AS mrr_expansion,
    ROUND(SUM(CASE WHEN e.tipo_evento = 'downgrade' THEN e.monto_anterior_cop - e.monto_mensual_cop ELSE 0 END), 2) AS mrr_contraccion,
    ROUND(SUM(CASE WHEN e.tipo_evento = 'cancelacion' THEN e.monto_mensual_cop ELSE 0 END), 2)       AS mrr_churn,
    COUNT(DISTINCT CASE WHEN e.tipo_evento IN ('nueva_suscripcion','reactivacion') THEN e.id_cliente END) AS clientes_altas,
    COUNT(DISTINCT CASE WHEN e.tipo_evento = 'cancelacion' THEN e.id_cliente END)                        AS clientes_bajas
FROM fact_evento_suscripcion e
JOIN dim_periodo per ON per.id_periodo = e.id_periodo
WHERE e.id_periodo BETWEEN 202401 AND 202412
GROUP BY per.id_periodo, per.anio, per.nombre_mes;

-- ------------------------------------------------------------------------------------
-- ARR / MRR totales al cierre de cada mes (para la tarjeta de resumen ejecutivo).
-- ------------------------------------------------------------------------------------
CREATE VIEW gold_v_arr_mrr AS
SELECT
    id_periodo,
    ROUND(SUM(mrr_cliente), 2) AS mrr_total,
    ROUND(SUM(mrr_cliente) * 12, 2) AS arr_total,
    SUM(activo) AS clientes_activos
FROM gold_v_estado_cliente_mensual
GROUP BY id_periodo;

-- ------------------------------------------------------------------------------------
-- NRR mensual (Net Revenue Retention): que porcentaje del MRR con el que arranco el
-- mes se conserva al cierre, contando expansion/contraccion/churn/reactivacion pero
-- EXCLUYENDO el MRR de clientes nuevos (new-logo). Excluir clientes nuevos es la parte
-- que mas se olvida al calcular NRR - si se incluyeran, NRR dejaria de medir retencion
-- y empezaria a medir crecimiento, que es una pregunta distinta (esa es gross/net
-- revenue GROWTH, no retention).
-- ------------------------------------------------------------------------------------
CREATE VIEW gold_v_nrr_mensual AS
SELECT
    per.id_periodo,
    per.nombre_mes,
    mrr_prev.mrr_total AS mrr_inicio_mes,
    mv.mrr_expansion,
    mv.mrr_contraccion,
    mv.mrr_churn,
    mv.mrr_reactivacion,
    ROUND(
        (mrr_prev.mrr_total + mv.mrr_expansion + mv.mrr_reactivacion - mv.mrr_contraccion - mv.mrr_churn)
        * 100.0 / NULLIF(mrr_prev.mrr_total, 0), 1
    ) AS nrr_pct
FROM dim_periodo per
JOIN gold_v_mrr_movements mv ON mv.id_periodo = per.id_periodo
JOIN gold_v_arr_mrr mrr_prev ON mrr_prev.id_periodo = (
    SELECT MAX(id_periodo) FROM gold_v_arr_mrr WHERE id_periodo < per.id_periodo
)
WHERE per.id_periodo BETWEEN 202402 AND 202412;

-- ------------------------------------------------------------------------------------
-- Cohortes de retencion: por cada mes de alta (cohorte) y cada mes calendario
-- posterior, que fraccion del MRR inicial de esa cohorte sigue activa (incluye
-- expansion propia de la cohorte, no clientes nuevos de otros meses).
-- ------------------------------------------------------------------------------------
CREATE VIEW gold_v_cohortes AS
WITH primera_alta AS (
    SELECT id_cliente, MIN(id_periodo) AS id_periodo_cohorte
    FROM fact_evento_suscripcion
    WHERE tipo_evento = 'nueva_suscripcion'
    GROUP BY id_cliente
),
mrr_inicial AS (
    SELECT pa.id_cliente, pa.id_periodo_cohorte, e.monto_mensual_cop AS mrr_inicial_cop
    FROM primera_alta pa
    JOIN fact_evento_suscripcion e
      ON e.id_cliente = pa.id_cliente AND e.id_periodo = pa.id_periodo_cohorte
     AND e.tipo_evento = 'nueva_suscripcion'
)
SELECT
    mi.id_periodo_cohorte,
    per_c.nombre_mes                                      AS mes_cohorte,
    per.id_periodo,
    (per.anio - per_c.anio) * 12 + (per.mes - per_c.mes)  AS meses_desde_alta,
    COUNT(DISTINCT mi.id_cliente)                         AS clientes_en_cohorte,
    ROUND(SUM(mi.mrr_inicial_cop), 2)                     AS mrr_inicial_cohorte,
    ROUND(SUM(COALESCE(ec.mrr_cliente, 0)), 2)            AS mrr_retenido_cop,
    ROUND(SUM(COALESCE(ec.mrr_cliente, 0)) * 100.0 / NULLIF(SUM(mi.mrr_inicial_cop), 0), 1) AS pct_retencion
FROM mrr_inicial mi
JOIN dim_periodo per_c ON per_c.id_periodo = mi.id_periodo_cohorte
CROSS JOIN dim_periodo per
LEFT JOIN gold_v_estado_cliente_mensual ec
       ON ec.id_cliente = mi.id_cliente AND ec.id_periodo = per.id_periodo
WHERE per.id_periodo >= mi.id_periodo_cohorte AND per.id_periodo <= 202412
GROUP BY mi.id_periodo_cohorte, per_c.nombre_mes, per.id_periodo, per_c.anio, per_c.mes, per.anio, per.mes
ORDER BY mi.id_periodo_cohorte, per.id_periodo;

-- ------------------------------------------------------------------------------------
-- Churn de logos (% clientes) y de ingreso (% MRR), mensual.
-- ------------------------------------------------------------------------------------
CREATE VIEW gold_v_churn AS
SELECT
    per.id_periodo,
    per.nombre_mes,
    activos_inicio.clientes_activos AS clientes_inicio_mes,
    activos_inicio.mrr_total        AS mrr_inicio_mes,
    mv.clientes_bajas,
    mv.mrr_churn,
    ROUND(mv.clientes_bajas * 100.0 / NULLIF(activos_inicio.clientes_activos, 0), 2) AS churn_logos_pct,
    ROUND(mv.mrr_churn * 100.0 / NULLIF(activos_inicio.mrr_total, 0), 2)             AS churn_ingreso_pct
FROM dim_periodo per
JOIN gold_v_mrr_movements mv ON mv.id_periodo = per.id_periodo
JOIN gold_v_arr_mrr activos_inicio ON activos_inicio.id_periodo = (
    SELECT MAX(id_periodo) FROM gold_v_arr_mrr WHERE id_periodo < per.id_periodo
)
WHERE per.id_periodo BETWEEN 202402 AND 202412;

-- ------------------------------------------------------------------------------------
-- CAC por canal y mes: gasto de adquisicion del canal ese mes / clientes nuevos que
-- ese canal aporto ese mes (el canal de adquisicion vive en dim_cliente, asignado en
-- el momento de la carga a partir del CRM).
-- ------------------------------------------------------------------------------------
CREATE VIEW gold_v_cac_por_canal AS
SELECT
    ga.id_periodo,
    per.nombre_mes,
    c.nombre_canal,
    ga.gasto_cop,
    COUNT(DISTINCT CASE WHEN e.tipo_evento = 'nueva_suscripcion' THEN cli.id_cliente END) AS clientes_nuevos,
    ROUND(
        ga.gasto_cop / NULLIF(COUNT(DISTINCT CASE WHEN e.tipo_evento = 'nueva_suscripcion' THEN cli.id_cliente END), 0),
        2
    ) AS cac_cop
FROM fact_gasto_adquisicion ga
JOIN dim_canal c    ON c.id_canal = ga.id_canal
JOIN dim_periodo per ON per.id_periodo = ga.id_periodo
LEFT JOIN dim_cliente cli ON cli.id_canal = ga.id_canal
LEFT JOIN fact_evento_suscripcion e
       ON e.id_cliente = cli.id_cliente AND e.id_periodo = ga.id_periodo AND e.tipo_evento = 'nueva_suscripcion'
GROUP BY ga.id_periodo, per.nombre_mes, c.nombre_canal, ga.gasto_cop
ORDER BY ga.id_periodo, c.nombre_canal;

-- ------------------------------------------------------------------------------------
-- LTV por plan: ARPA (ingreso promedio por cuenta activa) / churn mensual de ingreso.
-- SIMPLIFICACION DECLARADA: usa el churn de ingreso PROMEDIO de toda la compania, no
-- uno especifico por plan (requeriria trackear churn por plan mes a mes), y no
-- descuenta margen bruto - ver docs/DICCIONARIO_METRICAS.md.
-- ------------------------------------------------------------------------------------
CREATE VIEW gold_v_ltv AS
WITH arpa AS (
    SELECT dp.nombre_plan, AVG(ec.mrr_cliente) AS arpa_cop
    FROM gold_v_estado_cliente_mensual ec
    JOIN dim_plan dp ON dp.id_plan = ec.id_plan_activo
    WHERE ec.activo = 1
    GROUP BY dp.nombre_plan
),
churn_prom AS (
    SELECT AVG(churn_ingreso_pct) / 100.0 AS churn_mensual_promedio FROM gold_v_churn
)
SELECT
    a.nombre_plan,
    ROUND(a.arpa_cop, 2)               AS arpa_cop,
    ROUND(c.churn_mensual_promedio * 100, 2) AS churn_mensual_promedio_pct,
    ROUND(a.arpa_cop / NULLIF(c.churn_mensual_promedio, 0), 2) AS ltv_cop
FROM arpa a CROSS JOIN churn_prom c;

-- ------------------------------------------------------------------------------------
-- Calidad de datos: estado de cada cliente segun como se resolvio su identidad.
-- REBRANDING: CRM conoce mas de un nombre para el mismo id_contacto_crm (resuelto
--             automaticamente via el ancla estable).
-- HUERFANO_O_AMBIGUO: no hubo una contraparte confiable en CRM (nombre ambiguo entre
--             dos empresas reales, o typo de digitacion demasiado severo) - requiere
--             revision manual, no se adivino.
-- ------------------------------------------------------------------------------------
CREATE VIEW gold_v_calidad_clientes AS
SELECT
    dc.id_cliente,
    dc.nombre_canonico,
    dc.activo,
    CASE
        WHEN EXISTS (SELECT 1 FROM map_alias_cliente m WHERE m.id_cliente = dc.id_cliente AND m.metodo = 'ALIAS_MANUAL')
            THEN 'HUERFANO_O_AMBIGUO'
        WHEN (SELECT COUNT(*) FROM map_alias_cliente m2 WHERE m2.id_cliente = dc.id_cliente AND m2.origen_sistema = 'CRM') > 1
            THEN 'REBRANDING'
        ELSE 'OK'
    END AS estado_calidad,
    (SELECT GROUP_CONCAT(DISTINCT origen_sistema) FROM map_alias_cliente m3 WHERE m3.id_cliente = dc.id_cliente) AS sistemas_confirmados,
    (SELECT nota FROM map_alias_cliente m4 WHERE m4.id_cliente = dc.id_cliente AND m4.metodo = 'ALIAS_MANUAL' LIMIT 1) AS nota_calidad,
    (SELECT SUM(monto_mensual_cop) FROM fact_evento_suscripcion e
      WHERE e.id_cliente = dc.id_cliente AND e.tipo_evento = 'nueva_suscripcion') AS mrr_inicial_cop
FROM dim_cliente dc;

CREATE VIEW gold_v_resumen_calidad AS
SELECT estado_calidad, COUNT(*) AS num_clientes, ROUND(SUM(COALESCE(mrr_inicial_cop, 0)), 2) AS mrr_inicial_cop
FROM gold_v_calidad_clientes
GROUP BY estado_calidad;

CREATE VIEW gold_v_calidad_cuarentena AS
SELECT c.contenido AS fuente, COUNT(*) AS filas_rechazadas, GROUP_CONCAT(DISTINCT e.motivo) AS motivos
FROM err_registro_rechazado e
JOIN ctl_carga c ON c.id_carga = e.id_carga
GROUP BY c.contenido;

-- ------------------------------------------------------------------------------------
-- Resumen ejecutivo: una fila por mes con todo lo que va en la pagina de tarjetas.
-- ------------------------------------------------------------------------------------
CREATE VIEW gold_v_resumen_ejecutivo AS
SELECT
    am.id_periodo, per.nombre_mes, per.anio,
    am.mrr_total, am.arr_total, am.clientes_activos,
    nrr.nrr_pct,
    ch.churn_logos_pct, ch.churn_ingreso_pct,
    mv.mrr_nuevo, mv.mrr_expansion, mv.mrr_contraccion, mv.mrr_churn, mv.mrr_reactivacion
FROM gold_v_arr_mrr am
JOIN dim_periodo per ON per.id_periodo = am.id_periodo
LEFT JOIN gold_v_nrr_mensual nrr ON nrr.id_periodo = am.id_periodo
LEFT JOIN gold_v_churn ch        ON ch.id_periodo = am.id_periodo
LEFT JOIN gold_v_mrr_movements mv ON mv.id_periodo = am.id_periodo
ORDER BY am.id_periodo;

-- ------------------------------------------------------------------------------------
-- Detalle plano de eventos (una fila por evento de suscripcion), ya resuelto contra
-- las dimensiones: es la forma gobernada de bajar al detalle por cliente sin que ningun consumidor
-- (Power BI, notebooks, el agente conversacional) tenga que leer la capa silver.
-- ------------------------------------------------------------------------------------
CREATE VIEW gold_v_eventos_detalle AS
SELECT
    e.id_evento,
    e.fecha_evento,
    per.id_periodo,
    per.nombre_mes,
    per.anio,
    c.id_cliente,
    c.nombre_canonico                  AS cliente,
    COALESCE(gc.estado_calidad, 'OK')  AS estado_calidad_cliente,
    ca.nombre_canal                    AS canal_adquisicion,
    e.tipo_evento,
    p.nombre_plan                      AS plan,
    pa.nombre_plan                     AS plan_anterior,
    e.moneda_origen,
    ROUND(e.monto_mensual_cop, 2)      AS monto_mensual_cop,
    ROUND(e.monto_anterior_cop, 2)     AS monto_anterior_cop
FROM fact_evento_suscripcion e
JOIN dim_periodo  per ON per.id_periodo = e.id_periodo
JOIN dim_cliente  c   ON c.id_cliente   = e.id_cliente
JOIN dim_plan     p   ON p.id_plan      = e.id_plan
LEFT JOIN dim_plan    pa ON pa.id_plan    = e.id_plan_anterior
LEFT JOIN dim_canal   ca ON ca.id_canal   = c.id_canal
LEFT JOIN gold_v_calidad_clientes gc ON gc.id_cliente = c.id_cliente;
