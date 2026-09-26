# Resumen ejecutivo — Métricas SaaS 2024

> **Datos sintéticos.** Generados con `Faker` (semilla fija) para el reto de Alegra: ninguna cifra
> corresponde a Alegra ni a un cliente real. Cada cifra de este documento sale de la capa gold y
> la verifica `pruebas/test_cifras.py`. Tablero interactivo:
> [`powerbi/mockups/tablero_ejecutivo.html`](../powerbi/mockups/tablero_ejecutivo.html).

## En 30 segundos

- **El negocio creció 6,9x en MRR (de 8,3 M a 57,2 M COP), pero su base instalada no crece
  sola.** El NRR promedio es 100,0% y queda bajo 100% en 6 de 11 meses. Todo el crecimiento viene
  de adquirir clientes nuevos.
- **La mitad del presupuesto de adquisición rinde poco.** Outbound se lleva el **48,2% del gasto**
  y trae el **8,7% de las altas**. Es el único canal con LTV:CAC bajo 3:1 (2,5x).
- **Hay espacio para crecer más con el mismo dinero.** Referido, Pago-Meta y Orgánico adquieren a
  un CAC entre 9 y 36 veces menor que Outbound, con LTV:CAC entre 27,8x y 84,1x. Además, un
  identificador común entre sistemas permitiría medir el CAC sin trabajo manual.

## Cifras clave (diciembre 2024)

| MRR | ARR | Clientes activos | NRR promedio | Churn de ingreso prom. | CAC combinado 2024 |
|---:|---:|---:|---:|---:|---:|
| 57.201.326 COP | 686.415.912 COP | 144 | 100,0% | 1,87% mensual | 1.131.771 COP |

---

## Insights

### 1. El crecimiento depende de la adquisición: la base instalada solo se sostiene

- El MRR pasó de **8.254.340** (enero) a **57.201.326** (diciembre), con un pico de
  **59.979.290** en septiembre.
- En el año, el MRR nuevo aportó **58,2 M** frente a **17,9 M** de expansión. Las pérdidas
  sumaron **19,4 M**: 10,6 M de contracción y 8,8 M de churn.
- En el Q4, la expansión (**7,25 M**) cubrió solo el **72%** de las pérdidas (**10,01 M**). Sin
  altas, el MRR cae: diciembre cierra **4,6% bajo el pico**.

**Por qué importa:** con un NRR de 100%, cada peso de crecimiento hay que comprarlo con
adquisición. Por eso la eficiencia del gasto en adquisición es la palanca principal.

> *Hallazgo vs. supuesto:* que no haya altas desde octubre es un **supuesto de la simulación**,
> no una caída comercial. Lo que sí es hallazgo es que, sin altas, la expansión no compensa las
> pérdidas.

### 2. Outbound es el canal ineficiente: consume la mitad del gasto y solo se paga con Business

| Canal | % del gasto | % de las altas | CAC (COP) | LTV:CAC |
|---|---:|---:|---:|---:|
| **Outbound** | **48,2%** | **8,7%** | **6.257.989** | **2,5x** |
| Pago-Google | 16,1% | 20,9% | 870.654 | 20,7x |
| Pago-Meta | 13,8% | 22,7% | 687.528 | 31,5x |
| Orgánico | 11,9% | 20,3% | 661.622 | 27,8x |
| Partner | 7,1% | 8,1% | 983.303 | 14,2x |
| Referido | 2,9% | 19,2% | 173.171 | 84,1x |

- Outbound invirtió **93,9 M** para traer **15 clientes**: cada uno le cuesta **36,1 veces** más
  que uno de Referido.
- El problema es **a quién trae**. A su CAC, un cliente Starter rinde **1,3x** (y **0,6x** con el
  churn propio de Starter: no recupera lo que costó), un Pro rinde **2,98x** (justo bajo 3:1) y un Business
  **7,7x**. Aun así, **7 de sus 15 altas son Starter** y solo 1 es Business.

**Por qué importa:** con este CAC, Outbound solo tiene sentido para cuentas Business. Hoy se está
usando para prospectar sin filtro.

### 3. Referido y Pago-Meta son los canales que conviene escalar

- **Referido** trae el **19,2% de las altas con el 2,9% del gasto** (CAC 173.171, LTV:CAC 84,1x).
- **Pago-Meta** tiene la mejor mezcla de valor: **9 de sus 39 altas son Business (23%)**, con un
  LTV:CAC de 31,5x.
- Sin Outbound, el resto de los canales adquirió **157 clientes con 100,8 M**, un CAC combinado
  de **642.005**.

**Por qué importa:** son los canales con más retorno por peso. Falta probar cuánto aguantan al
subir la inversión, porque el CAC marginal crece con la escala.

### 4. La retención del plan Starter es el punto débil del LTV

| Plan | ARPA (COP) | Churn propio del plan | LTV con churn del plan | Bajas en el año |
|---|---:|---:|---:|---:|
| Starter | 149.000 | 3,94% | 3.777.150 | 20 |
| Pro | 349.160 | 3,05% | 11.452.314 | 14 |
| Business | 904.918 | 0,50% | 181.606.737 ⚠ | 1 |

- Con su propio churn, un Starter vale **menos de la mitad** del LTV principal (7.967.914).
- El churn de ingreso queda por debajo del de logos en **10 de 11 meses**: se van sobre todo
  clientes pequeños. Noviembre tuvo el pico: **11 bajas**, churn de logos de **7,01%** y
  **3.192.060 COP** perdidos.
- ⚠ El LTV de Business con churn propio se basa en **una sola baja**: no es confiable.

> *Hallazgo vs. supuesto:* que Starter tenga más churn que Business viene del generador (churn
> base por plan). La magnitud observada y su efecto sobre el LTV:CAC de cada canal sí son
> resultado del pipeline.

### 5. La calidad de los datos limita que la medición escale

- **17 clientes huérfanos o ambiguos** (1.145.000 COP de MRR inicial) y **5 altas sin canal**: el
  CAC por canal cuenta 172 de 177 altas.
- **3 filas en cuarentena** y un MRR a diciembre **574.210 COP (−1,0%)** por debajo de la verdad
  de control. La diferencia está explicada: cuarentena en cascada y convención de tipo de cambio.
- La causa de fondo: Stripe, el CRM y los contratos **no comparten un identificador**.

**Por qué importa:** cada canal nuevo o cada punto de escala suma trabajo manual de conciliación.
Si no se resuelve, el CAC por canal pierde precisión justo cuando más decisiones dependen de él.

---

## Accionables priorizados

| # | Acción | Responsable | KPI de éxito | Horizonte |
|---|---|---|---|---|
| 1 | **Reasignar la mitad del presupuesto de Outbound** a Referido, Pago-Meta y Orgánico, por tramos y midiendo el CAC marginal. | CMO / Growth | CAC combinado ↓, altas por mes ↑ | 1 trimestre |
| 2 | **Limitar Outbound a cuentas con perfil Business**, con calificación antes del contacto comercial. | Ventas / SDR | ≥ 50% de altas Business en Outbound; LTV:CAC ≥ 3x | 1 trimestre |
| 3 | **Escalar el programa de referidos**: incentivo al que refiere y al referido, y un flujo dentro del producto. | Growth / Producto | Altas por referido al mes; CAC Referido ≤ 2x el actual | 2 trimestres |
| 4 | **Optimizar paid media por valor, no por volumen**: enviar a Meta y Google la conversión por plan (puja por valor). | Performance | % de altas Pro/Business en paid; LTV ponderado por canal | 1 trimestre |
| 5 | **Ruta Starter → Pro**: onboarding guiado, activación en los primeros 30 días e invitaciones a subir de plan. | Producto / CS | Churn Starter < 3%; expansión neta > 0 cada mes | 2 trimestres |
| 6 | **Alerta temprana de churn**: aviso cuando el churn de logos del mes supere el 4% (noviembre llegó a 7,01%). | BI / CS | Alertas atendidas en < 5 días | 1 mes |
| 7 | **Identificador común y atribución obligatoria**: `id_customer_stripe` en el CRM y en los contratos, y el canal como campo requerido en el alta. | Data / RevOps | 100% de altas con canal; 0 huérfanos; conciliación < 0,5% | 1 trimestre |
| 8 | **Regla de gasto sin conversión**: pausar y revisar cualquier canal con 30 días de gasto sin altas. | Growth / Finanzas | Gasto sin altas = 0 | 1 mes |

### Escenario ilustrativo del accionable 1 (no es un pronóstico)

La mitad del gasto de Outbound son **46,9 M COP**:

| Supuesto | Altas estimadas con esos 46,9 M |
|---|---:|
| Quedarse en Outbound (CAC 6.257.989) | **7,5** |
| Moverlos al CAC combinado del resto de canales (642.005) | **73** |
| Moverlos con el CAC **duplicado** por saturación (1.284.010) | **37** |

Aun con un CAC al doble, la reasignación multiplica por **~5** las altas de ese tramo. Es un
cálculo lineal para dimensionar la oportunidad. Antes de mover todo el presupuesto hay que
validarlo con pruebas por tramos, porque los rendimientos de cada canal son decrecientes.

> Nota sobre la regla 8: en los datos, el Q4 muestra **39,9 M COP de gasto sin ninguna alta**.
> Ese gasto es un artefacto de la simulación (no se generaron altas desde octubre), pero es
> justo el caso que la regla debe detectar en la operación real.

---

## Riesgos y supuestos que hay que tener presentes

- **Datos sintéticos:** las tasas de churn, upgrade y reactivación son parámetros del generador. Las
  conclusiones valen como método; las magnitudes, solo como ilustración.
- **LTV sin margen bruto:** ambos LTV miden ingreso, no contribución. Con el margen real, todos los
  LTV:CAC bajan y Outbound queda todavía más lejos de 3:1.
- **Muestras pequeñas:** Business tiene 1 baja en el año y Outbound 1 alta Business. Esas cifras no
  deben sostener una decisión por sí solas.
- **CAC marginal:** el CAC promedio de un canal subestima lo que costaría escalarlo.

## Próximos pasos

1. Presentar el accionable 1 con un piloto de reasignación del 25% durante 6 semanas.
2. Cargar el margen bruto por plan para pasar a LTV de contribución.
3. Implementar el identificador común (accionable 7) antes de sumar canales nuevos.
4. Montar las 5 páginas del tablero en Power BI Desktop usando el mockup como guía visual
   (ver `powerbi/INSTRUCCIONES_POWERBI.md`).
