# Informe — SaaS Metrics (proyecto ficticio, Reto Alegra)

## Qué es esto y qué no es

Un SaaS ficticio, con datos 100% sintéticos generados con semilla fija (reproducibles).
Ninguna cifra de este informe corresponde a Alegra ni a ningún cliente real. Construido
para la Actividad 1 del proceso de selección de Business Intelligence & Analytics
Partner, con Claude Code como copiloto en cada etapa — de la generación de datos a las
vistas SQL, los notebooks y este mismo informe.

**El problema que resuelve:** un SaaS que factura desde Stripe, gestiona su embudo en
un CRM estilo HubSpot y firma contratos formales para sus cuentas grandes, sin que los
tres sistemas compartan un identificador común. La pregunta de negocio — *¿cuál es el
MRR real, y por qué no cuadra entre sistemas?* — exige resolver esa identidad antes de
poder confiar en cualquier métrica.

---

## Arquitectura

Cuatro capas sobre SQLite (raw → bronze → silver → gold): un origen nuevo solo agrega un
lector hacia Bronze, sin tocar Silver ni Gold. Detalle completo en
`notebooks/01_arquitectura_y_modelo.ipynb`.

---

## Lo que encontró el pipeline al integrar los 3 sistemas

| Categoría | Clientes | MRR inicial involucrado | Resolución |
|---|---:|---:|---|
| OK | 219 | 52.935.830 | Cruce automático por normalización de nombre |
| Rebranding | 16 | 4.140.050 | Automática — CRM ancla la identidad por su propio ID, no por nombre |
| Huérfano / ambiguo | 12 | 1.145.000 | **Sin resolución automática** — ver abajo |

**El hallazgo más interesante no estaba planeado:** al generar los datos sintéticos,
`Faker` produjo por azar el mismo nombre de empresa para dos clientes distintos, tres
veces ("Rivera Group", "Castillo LLC", "Gomez-Quintero"). Resolver identidad solo por
nombre normalizado habría fusionado esas 6 empresas reales en 3, silenciosamente. La
solución fue anclar Billing por `id_customer_stripe` (el identificador estable de ese
sistema, igual que CRM se ancla por `id_contacto_crm`) y neutralizar cualquier nombre
reclamado por más de una empresa distinta en vez de asignarlo arbitrariamente al
primero que apareció. El costo de esa honestidad: 6 clientes quedan como huérfanos en
vez de fusionados por error — y **eso es exactamente lo correcto.**

Los otros 6 huérfanos son contratos con errores de digitación demasiado severos para
la normalización automática (ej. `"LOA IZA , ESPINOSA A ND SOLA NO S.A.S."`) — se
marcan para revisión manual en lugar de forzar un match.

**Cuarentena:** 3 filas de Billing llegaron con `tipo_evento` vacío (perdido en el
origen) y se aislaron en `err_registro_rechazado` en vez de descartarse en silencio o
adivinar su clasificación.

---

## Métricas SaaS — 2024

| Métrica | Valor |
|---|---:|
| MRR (diciembre) | **57.201.326 COP** |
| ARR (diciembre) | **686.415.912 COP** |
| Clientes activos (diciembre) | **144** |
| NRR promedio | **100,0%** (rango 94,3% – 106,7%) |
| Churn de logos promedio | **2,71% mensual** |
| Churn de ingreso promedio | **1,87% mensual** |

**Churn de ingreso consistentemente menor que churn de logos** en los 11 meses con
dato: los clientes que se van tienden a ser los de plan Starter, no los de mayor MRR —
la base de ingresos es más resiliente de lo que sugeriría solo contar clientes
perdidos.

### CAC por canal (promedio anual)

| Canal | CAC (COP) |
|---|---:|
| Referido | **173.171** |
| Organico | 661.622 |
| Pago-Meta | 687.528 |
| Pago-Google | 870.655 |
| Partner | 983.303 |
| **Outbound** | **6.257.989** |

**Outbound cuesta 36 veces más que Referido por cliente adquirido.** Con un LTV de
Business de ~48,4M COP, Outbound sigue siendo rentable para ese plan — pero para
Starter (LTV ~8,0M) el CAC de Outbound superaría el valor del cliente. Es la primera
pregunta que le haría al equipo de Growth: ¿Outbound se está usando para cerrar cuentas
grandes, o se está prospectando indiscriminadamente?

### LTV por plan

| Plan | ARPA (COP) | LTV (COP) |
|---|---:|---:|
| Starter | 149.000 | 7.967.914 |
| Pro | 349.160 | 18.671.632 |
| Business | 904.918 | 48.391.345 |

*(LTV = ARPA / churn de ingreso promedio de la compañía — simplificación declarada en
`docs/DICCIONARIO_METRICAS.md`.)*

---

## Advertencia metodológica: por qué la reconciliación no da 100% exacto (y por qué eso es correcto)

Al comparar el pipeline reconstruido contra la verdad de control (`data/control_totales.json`,
calculada *antes* de ensuciar los datos), 8 de 12 meses cuadran exacto. El resto tiene
un desvío de **~1% del MRR** a diciembre. La causa está completamente identificada: las
3 filas de Billing en cuarentena (tipo de evento perdido) no solo faltan ellas mismas —
si una de esas filas era el evento de alta de un cliente, cualquier upgrade/downgrade
posterior de ese mismo cliente pierde su "plan anterior" y no se puede clasificar como
expansión o contracción. Es un efecto en cascada real, no un error del pipeline.

**No se forzó una reconciliación perfecta artificial.** Un pipeline que "cuadra
siempre" sobre datos con pérdida real de información está adivinando en algún punto.
El detalle completo, con las cifras exactas mes a mes, está en
`notebooks/03_carga_y_calidad.ipynb`.

---

## Verificaciones ejecutadas

| Verificación | Resultado |
|---|---|
| `PRAGMA foreign_key_check` | Sin violaciones |
| Reconciliación mensual contra `control_totales.json` | 8/12 meses exactos; el resto explicado (ver arriba) |
| Los 4 notebooks ejecutan de principio a fin | Verificado con `nbclient` |
| Filas rechazadas van a cuarentena, no se descartan en silencio | 3 filas, motivo exacto registrado |
| Clientes con identidad ambigua no se fusionan por error | 3 colisiones de nombre detectadas y separadas |

---

## Contenido del repositorio

```
Alegra/
  data/           generador de datos sinteticos + seeds + control de verdad
  sql/            DDL (bronze/silver/control) + vistas gold
  notebooks/      01 arquitectura · 02 generar datos · 03 carga y calidad · 04 metricas
  powerbi/        vistas gold exportadas a CSV + proyecto .pbip
  docs/           este informe, el diccionario de metricas, el guion del video
  db/             saas_metrics.db (SQLite poblado y verificado)
  cargar_datos.py · exportar_csv.py · lib_comun.py
```

---

Construido con **Claude Code** como copiloto de principio a fin — desde el diseño de
la arquitectura hasta la detección de la colisión de nombres que ningún plan original
contemplaba.
