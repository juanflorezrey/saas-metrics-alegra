# =====================================================================================
# Catalogo de negocio de lo que el agente puede leer, y contexto de la simulacion.
# Las descripciones estan alineadas con docs/DICCIONARIO_METRICAS.md: le dicen al
# agente el GRANO de cada vista y como usarla bien (p.ej. no promediar CAC mensuales).
# =====================================================================================

from agente.guardrails import capa_publicada

DESCRIPCIONES = {
    "gold_v_resumen_ejecutivo": (
        "PUNTO DE ENTRADA. Una fila por mes (202401-202412): MRR y ARR al cierre, clientes activos, "
        "NRR %, churn de logos % y de ingreso %, y los 5 movimientos de MRR del mes. NRR y churn son "
        "NULL en enero (no hay mes anterior)."
    ),
    "gold_v_mrr_movements": (
        "Una fila por mes: MRR nuevo, expansion, contraccion, reactivacion y churn (flujos del mes, "
        "calculados desde los eventos) + clientes_altas y clientes_bajas. "
        "MRR(mes) = MRR(mes-1) + nuevo + expansion + reactivacion - contraccion - churn."
    ),
    "gold_v_arr_mrr": "Una fila por mes: mrr_total, arr_total (= MRR x 12) y clientes_activos al cierre del mes.",
    "gold_v_nrr_mensual": (
        "Una fila por mes desde febrero: MRR al inicio del mes y nrr_pct. El NRR EXCLUYE el MRR de "
        "clientes nuevos (mide retencion de la base existente, no crecimiento)."
    ),
    "gold_v_churn": (
        "Una fila por mes desde febrero: clientes y MRR al inicio del mes, bajas, MRR perdido, "
        "churn_logos_pct y churn_ingreso_pct."
    ),
    "gold_v_cohortes": (
        "Una fila por cohorte (mes de alta) x mes calendario: clientes de la cohorte, MRR inicial, MRR "
        "retenido y pct_retencion (puede superar 100% por expansion de la propia cohorte)."
    ),
    "gold_v_estado_cliente_mensual": (
        "Una fila por cliente x mes: si estaba activo al cierre, su plan activo (id_plan_activo) y su "
        "MRR. Base de las demas metricas; util para contar clientes por plan en un mes dado."
    ),
    "gold_v_cac_por_canal": (
        "Una fila por canal x mes: gasto de adquisicion (COP), clientes_nuevos y cac_cop. Para el CAC "
        "de un periodo largo, SUMAR gasto y clientes y dividir; NO promediar los CAC mensuales. Las altas "
        "de clientes huerfanos no tienen canal y no cuentan en ningun canal."
    ),
    "gold_v_ltv": (
        "Una fila por plan. ltv_cop = ARPA / churn de ingreso mensual promedio de TODA la compania (cifra "
        "principal). Sensibilidad: churn_ingreso_plan_pct y ltv_cop_churn_plan usan el churn propio de cada "
        "plan; bajas_plan es la muestra (con pocas bajas, como Business, esa sensibilidad no es confiable). "
        "Ninguna descuenta margen."
    ),
    "gold_v_ltv_cac_por_canal": (
        "Una fila por canal: gasto y clientes nuevos del anio, CAC (gasto total / clientes), altas por "
        "plan (la mezcla REAL con la que entro el canal), LTV ponderado por esa mezcla y ltv_cac. "
        "ltv_cac_churn_plan es la sensibilidad con churn por plan. Referencia: LTV:CAC >= 3."
    ),
    "gold_v_calidad_clientes": (
        "Una fila por empresa de dim_cliente con su estado_calidad: OK (cliente de pago resuelto), "
        "REBRANDING (resuelto por el id del CRM), HUERFANO_O_AMBIGUO (sin contraparte confiable; revision "
        "manual), CLIENTE_SIN_EVENTOS_VALIDOS (cliente del CRM cuya facturacion quedo en cuarentena: su MRR "
        "no esta contado) y LEAD_SIN_FACTURACION (lead/trial, no es un error). Incluye nota y MRR inicial."
    ),
    "gold_v_resumen_calidad": "Una fila por estado de calidad: numero de clientes y MRR inicial involucrado.",
    "gold_v_calidad_cuarentena": "Una fila por fuente de datos: filas rechazadas a cuarentena en la carga y su motivo.",
    "gold_v_eventos_detalle": (
        "DETALLE. Una fila por evento de suscripcion (nueva_suscripcion, upgrade, downgrade, cancelacion, "
        "reactivacion) con cliente, estado de calidad, canal, plan, plan anterior, moneda de origen y "
        "montos en COP. Para preguntas de detalle ('que clientes...', 'cuantos facturan en USD')."
    ),
    "dim_periodo": "Calendario mensual 2024-2025 (id_periodo = AAAAMM). Solo 2024 tiene datos.",
    "dim_plan": "Planes Starter, Pro y Business con su precio de lista mensual en COP y en USD.",
    "dim_canal": "Canales de adquisicion: Organico, Pago-Google, Pago-Meta, Referido, Partner, Outbound.",
    "dim_cliente": (
        "Una fila por empresa, INCLUYE 55 leads/trials que nunca pagaron y los registros huerfanos. "
        "activo = 1 si estaba activo al cierre del ultimo mes. moneda_principal = moneda de su ultimo "
        "evento de facturacion (NULL si nunca facturo). etapa_crm = Cliente, Lead, Trial o Perdido "
        "(NULL si la empresa no existe en el CRM)."
    ),
}

CONTEXTO_SIMULACION = """\
Contexto de la simulacion (supuestos del generador data/generar_datos.py, semilla 42):

- Todos los datos son SINTETICOS. Ninguna cifra corresponde a Alegra ni a un cliente real.
- 180 empresas llegan a ser clientes de pago; 55 leads/trials adicionales existen solo en el CRM
  y nunca facturan (por eso no aportan MRR).
- Las ALTAS se simularon solo de enero a septiembre de 2024, a proposito, para tener cohortes
  maduras que medir. Por eso octubre, noviembre y diciembre muestran MRR nuevo = 0: es un supuesto
  de la simulacion, no un hallazgo de negocio. No inventes causas comerciales para eso.
- Churn mensual base por plan: Starter 4,5%, Pro 2,5%, Business 1,2%. Probabilidad mensual de
  upgrade 5% y de downgrade 2%; 15% de los que cancelan se reactivan 2-3 meses despues.
- Planes: Starter 149.000 COP, Pro 349.000 COP, Business 899.000 COP al mes. ~35% de los clientes
  Business facturan en USD (38 / 89 / 230 USD) y se convierten a COP con la tasa del mes.
- 17 empresas cambiaron de razon social a mitad de anio (rebranding): se resolvieron
  automaticamente porque el CRM conserva el mismo id de contacto. 16 quedan marcadas REBRANDING;
  la otra ("Leal Inc", renombrada "Rivera Group") tomo un nombre que ya usaba otra empresa, asi
  que ese nombre quedo neutralizado y figura como OK.
- Por azar, 3 nombres quedaron compartidos por dos empresas distintas del CRM ("Rivera Group",
  "Castillo LLC", "Gomez-Quintero"). El pipeline NO las fusiono: esos nombres no se usan para
  cruzar, y la facturacion de 5 de esas empresas quedo en 5 clientes huerfanos de Billing (cada
  uno anclado por su id_customer_stripe) para revision manual. Del lado del CRM, esas mismas 5
  empresas figuran como HUERFANO_O_AMBIGUO sin facturacion.
- 7 contratos no encontraron contraparte en el CRM: 5 por un error de digitacion que la
  normalizacion no corrige (espacios dentro del nombre) y 2 por nombre ambiguo.
- 3 filas de facturacion llegaron sin tipo de evento y se aislaron en cuarentena: la unica alta
  de "Uribe and Sons" y de "Gonzalez-Rodriguez" (esos 2 clientes no aparecen en el MRR; quedan
  como CLIENTE_SIN_EVENTOS_VALIDOS) y el alta de "Mena PLC", que en agosto hizo upgrade. Por eso
  la reconstruccion difiere ~1% del MRR de la "verdad" de la simulacion a diciembre.
- 5 altas de clientes huerfanos (1.145.000 COP de MRR inicial) no tienen canal de adquisicion:
  el CAC por canal cuenta 172 de las 177 altas.

Por que el waterfall no siempre suma exacto a la variacion del MRR (dos efectos conocidos):
- Tipo de cambio: el MRR de un cliente en USD se registra a la tasa del mes de su ULTIMO evento,
  pero su baja o cambio de plan se valora a la tasa del mes en que ocurre. Ejemplo: en noviembre
  un cliente Business en USD cancelo; el MRR lo traia en 915.170 COP y el churn lo valoro en
  902.060 COP -> 13.110 COP de diferencia (julio: 4.984 COP por el mismo efecto).
- Cuarentena en cascada: en agosto un cliente cuya alta quedo en cuarentena aparece por primera
  vez con un upgrade sin "monto anterior"; entra al MRR (349.000 COP, un plan Pro) sin contar
  como expansion.
"""


def describir_modelo() -> str:
    """Markdown con cada objeto que el agente puede leer: descripcion, filas y columnas.
    Lee la capa publicada, asi que describe exactamente lo que consultar_sql puede ver."""
    with capa_publicada() as (con, publicadas):
        # Punto de entrada y detalle primero; luego el resto de vistas gold; dimensiones al final.
        primero = [n for n in ("gold_v_resumen_ejecutivo", "gold_v_eventos_detalle") if n in publicadas]
        gold = sorted(n for n in publicadas if n.startswith("gold_v_") and n not in primero)
        dims = [n for n in publicadas if n.startswith("dim_")]
        bloques = [
            "# Modelo disponible para el agente (solo lectura)\n",
            "Solo se pueden consultar estos objetos. Montos en COP. id_periodo = AAAAMM (ej. 202412).\n",
        ]
        # Solo lecturas que el propio authorizer ya permite (sin PRAGMA): una sola regla
        # de seguridad, definida en guardrails.py.
        for nombre in primero + gold + dims:
            cur = con.execute(f'SELECT * FROM "{nombre}" LIMIT 0')
            columnas = [d[0] for d in cur.description]
            cur.close()
            n = con.execute(f'SELECT COUNT(*) FROM "{nombre}"').fetchone()[0]
            bloques.append(
                f"## {nombre}  ({n} filas)\n{DESCRIPCIONES.get(nombre, '(sin descripcion)')}\n"
                f"Columnas: {', '.join(columnas)}\n"
            )
        return "\n".join(bloques)
