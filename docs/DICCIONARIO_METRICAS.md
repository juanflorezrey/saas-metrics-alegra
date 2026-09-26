# Diccionario de métricas

Cada métrica lista su fórmula exacta, la vista que la calcula y las decisiones de
diseño que la hacen correcta (no solo "una forma de calcularla", sino la forma que no
se presta a errores comunes). Todos los montos están en COP; los eventos en USD se
convierten con la tasa de cambio del mes del evento (`dim_tasa_cambio`).

---

## MRR (Monthly Recurring Revenue)

Suma del ingreso mensual recurrente de todos los clientes activos al cierre del mes.

```
MRR(mes) = Σ monto_mensual_cop de cada cliente activo al cierre de "mes"
```

**Vista:** `gold_v_arr_mrr` (columna `mrr_total`), derivada de `gold_v_estado_cliente_mensual`
(el estado de cada cliente se deriva del *último* evento de suscripción con
`id_periodo <= mes`; persiste entre meses hasta el siguiente evento).

## ARR (Annual Recurring Revenue)

```
ARR(mes) = MRR(mes) × 12
```

**Vista:** `gold_v_arr_mrr`, columna `arr_total`. Es una proyección anualizada del MRR
del mes, no una suma de 12 meses reales — así se define en toda la industria SaaS.

## MRR Movements (el "waterfall")

El cambio de MRR mes a mes se descompone en 5 categorías, calculadas **directamente
de los eventos del mes** (no por diferencia de estados, que se presta a errores de
redondeo y no distingue causas):

| Movimiento | Fórmula |
|---|---|
| **Nuevo** | Σ monto de eventos `nueva_suscripcion` del mes |
| **Expansión** | Σ (monto nuevo − monto anterior) de eventos `upgrade` del mes |
| **Contracción** | Σ (monto anterior − monto nuevo) de eventos `downgrade` del mes |
| **Reactivación** | Σ monto de eventos `reactivacion` del mes |
| **Churn** | Σ monto de eventos `cancelacion` del mes (lo que se pierde) |

`MRR(mes) = MRR(mes−1) + Nuevo + Expansión + Reactivación − Contracción − Churn`

**Vista:** `gold_v_mrr_movements`.

## NRR (Net Revenue Retention)

```
NRR(mes) = (MRR_inicio_mes + Expansión + Reactivación − Contracción − Churn) / MRR_inicio_mes  × 100
```

**El detalle que no se puede saltar:** el numerador **excluye el MRR de clientes
nuevos** (`Nuevo`) del mes. Si se incluyera, NRR dejaría de medir *retención* de la
base existente y empezaría a medir *crecimiento* — son dos preguntas de negocio
distintas, y confundirlas es el error más común al calcular esta métrica.

**Ejemplo numérico:** si el MRR de inicio de mes es 40.000.000, hay 3.000.000 de
expansión, 1.000.000 de contracción y 500.000 de churn (sin nuevos clientes en el
cálculo), NRR = (40.000.000 + 3.000.000 − 1.000.000 − 500.000) / 40.000.000 = **104,5%**.
Un NRR > 100% significa que la base existente crece por sí sola, sin necesidad de
vender a clientes nuevos.

**Convención declarada:** las reactivaciones (clientes que habían cancelado y vuelven)
**sí** suman en el numerador, como recuperación de ingreso ya ganado, aunque no estaban
en la base al inicio del mes. En 2024 pesan poco (149.000 COP en todo el año: el NRR
promedio pasa de 100,0% a 99,96% si se excluyen), pero conviene saberlo al comparar con
otra definición.

**Vista:** `gold_v_nrr_mensual`.

## Churn

Dos versiones, porque cuentan historias distintas (un cliente pequeño que se va pesa
igual en logos, pero casi nada en ingreso):

```
Churn de logos (%)   = clientes que cancelaron en el mes / clientes activos al inicio del mes × 100
Churn de ingreso (%) = MRR cancelado en el mes / MRR al inicio del mes × 100
```

**Vista:** `gold_v_churn`.

## Cohortes de retención

Para cada cohorte (mes de alta) y cada mes calendario posterior, qué porcentaje del
MRR inicial de esa cohorte específica sigue activo (incluye la expansión propia de
esos mismos clientes, no clientes nuevos de otros meses):

```
% retención(cohorte, mes) = MRR retenido de la cohorte en "mes" / MRR inicial de la cohorte × 100
```

Un valor por encima de 100% es normal y deseable: significa que la expansión de la
cohorte superó su propio churn+contracción.

**Vista:** `gold_v_cohortes`.

## CAC (Customer Acquisition Cost)

```
CAC(canal, mes) = gasto de adquisición del canal en el mes / clientes nuevos adquiridos por ese canal en el mes
```

**CAC de un periodo largo** (el año, un trimestre):

```
CAC(canal, periodo) = Σ gasto del canal en el periodo / Σ clientes nuevos del canal en el periodo
```

**Nunca** el promedio de los CAC mensuales: pesaría igual un mes con 1 alta que uno con
10, y los meses sin altas (CAC indefinido) se perderían del cálculo.

**Vista:** `gold_v_cac_por_canal`. El canal de adquisición de cada cliente se fija en
el momento de la carga (viene del CRM, resuelto contra `map_alias_canal`). Los clientes
huérfanos de Billing no tienen canal conocido: sus altas no entran en ningún canal.

## LTV (Lifetime Value)

```
LTV(plan)             = ARPA(plan) / churn_mensual_de_ingreso_promedio_de_la_compañía
LTV_churn_plan(plan)  = ARPA(plan) / churn_mensual_de_ingreso_del_plan
```

Donde ARPA (Average Revenue Per Account) es el MRR promedio de los clientes activos
de ese plan, y el churn de ingreso del plan es el MRR cancelado del plan sobre el MRR del
plan al inicio de cada mes, acumulado en el año.

**Dos lecturas, lado a lado, a propósito:**
1. `ltv_cop` (cifra principal) usa el churn **promedio de toda la compañía**. Es estable,
   pero trata igual a planes que se van a ritmos muy distintos: la diferencia de LTV entre
   planes sale solo del ARPA.
2. `ltv_cop_churn_plan` (sensibilidad) usa el churn **propio de cada plan**. Refleja mejor
   el comportamiento de cada plan, pero con 12 meses de historia la muestra es chica:
   `bajas_plan` dice cuántas bajas la sostienen (Business tiene una sola, así que su cifra
   no es confiable).

Ninguna descuenta margen bruto ni costo de servicio: es LTV de *ingreso*, no de
*utilidad*.

**Vista:** `gold_v_ltv`.

## LTV:CAC

El CAC vive por canal y el LTV por plan. Para cruzarlos no se supone un plan típico: se
usa la mezcla **real** de planes con la que entró cada canal.

```
LTV ponderado(canal) = Σ (altas del canal en el plan × LTV del plan) / altas del canal
LTV:CAC(canal)       = LTV ponderado(canal) / CAC anual(canal)
```

Referencia de la industria: LTV:CAC ≥ 3. La vista trae también la versión con el LTV por
plan (`ltv_cac_churn_plan`).

**Vista:** `gold_v_ltv_cac_por_canal`.

---

## Calidad de datos (no son "métricas de negocio", pero condicionan la confianza en
## todas las de arriba)

- **`gold_v_calidad_clientes`** / **`gold_v_resumen_calidad`**: clasifica cada empresa
  de `dim_cliente` en:
  - `OK`: cliente de pago cruzado automáticamente entre sistemas.
  - `REBRANDING`: el CRM conoce más de un nombre para el mismo contacto; resuelto
    automáticamente por el ID del CRM.
  - `HUERFANO_O_AMBIGUO`: sin contraparte confiable entre sistemas (registro creado desde
    Billing o Contratos sin match, o empresa del CRM con un nombre compartido que se
    neutralizó). Requiere revisión manual; nunca se fuerza un match.
  - `CLIENTE_SIN_EVENTOS_VALIDOS`: cliente del CRM sin ningún evento de facturación válido
    (su alta cayó en cuarentena). Su MRR no está contado.
  - `LEAD_SIN_FACTURACION`: lead o trial que nunca pagó. No es un error.
- **`gold_v_calidad_cuarentena`**: filas rechazadas por fuente y motivo. Cero filas en
  cuarentena silenciosamente descartadas: cada una queda en `err_registro_rechazado`
  con su motivo exacto.
