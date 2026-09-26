# Cómo armar el dashboard en Power BI

---

## Ruta rápida — el modelo ya está generado

El modelo semántico completo (tablas, relaciones, 12 medidas DAX) **ya está hecho** en
`saas_metrics.pbip`, formato TMDL (texto, versionable en git). Las 5 páginas del reporte
están creadas y nombradas, pero **vacías**: la maquetación de visuales es la única parte que Power BI Desktop
tiene que generar internamente al abrir el archivo, y por eso se deja para hacer en
Desktop en vez de escribirla a mano (el JSON de un visual es frágil; un `.pbip` que "no
abre" es peor que uno sin gráficos).

## Qué hacer

1. **Doble clic en `saas_metrics.pbip`.** Abre en Power BI Desktop y construye el modelo.
2. **Apunta el parámetro `RutaDatos` a esta carpeta.** Si clonaste el repo en otra ruta:
   `Inicio > Transformar datos > Editar parámetros > RutaDatos` = ruta absoluta de la
   carpeta `powerbi` de tu copia (por ejemplo `C:\repos\saas-metrics-alegra\powerbi`).
   Power BI no admite rutas relativas en orígenes de archivo.
3. **`Inicio > Actualizar`.** Lee los 9 CSV de esta carpeta y llena las tablas.
4. **Comprueba las cifras de control** (abajo). Si cuadran, el modelo está bien.
5. **Arrastra los visuales** en cada página (detalle en el *Paso 5* más abajo). Son
   ~30-40 minutos para las 5 páginas.
6. **`Archivo > Guardar como` → `.pbix`** (opcional, para tener también el binario).

## Cifras de control

Pon una tarjeta con `[MRR]` y otra con `[Clientes Activos]` (sin ningún segmentador —
las medidas ya toman el último mes con `LASTNONBLANK`):

| Medida | Valor esperado (diciembre 2024) |
|---|---:|
| `[MRR]` | **57.201.326** |
| `[ARR]` | 686.415.912 |
| `[Clientes Activos]` | **144** |
| `[NRR %]` | 101,2% |
| `[CAC]` (sin segmentador: todo el año) | 1.131.771 |

Conteo de filas esperado: `dim_periodo` 24 · `gold_v_resumen_ejecutivo` 12 ·
`gold_v_cohortes` 72 · `gold_v_cac_por_canal` 72 · `gold_v_ltv` 3 · `gold_v_ltv_cac_por_canal` 6 ·
`gold_v_calidad_clientes` 247 · `gold_v_resumen_calidad` 5 · `gold_v_calidad_cuarentena` 1.

> **Si el proyecto no abre**, anota el mensaje de error exacto y usa la *Ruta manual*
> de abajo: construye el mismo modelo paso a paso.

---

## Ruta manual — paso a paso desde cero

Úsala si prefieres construirlo tú, o si la ruta rápida falla. Tiempo estimado:
**30-40 minutos**. No hace falta escribir DAX de negocio: toda la lógica de negocio ya
está resuelta en las vistas `gold_v_*` — Power BI solo agrega y visualiza.

## Paso 0 · Por qué CSV y no ODBC

SQLite no trae driver ODBC en Windows: la ruta CSV funciona sin instalar nada, se
re-exporta en segundos con `python exportar_csv.py`, y publica sin depender de un
gateway on-premises.

## Paso 1 · Importar las tablas

`Inicio > Obtener datos > Texto/CSV`, y carga estos 9 archivos de esta misma carpeta:

| Archivo | Grano | Filas |
|---|---|---:|
| `dim_periodo.csv` | Un mes (24 meses sembrados, 2024-2025) | 24 |
| `gold_v_resumen_ejecutivo.csv` | Un mes | 12 |
| `gold_v_cohortes.csv` | Cohorte × mes de seguimiento | 72 |
| `gold_v_cac_por_canal.csv` | Canal × mes | 72 |
| `gold_v_ltv.csv` | Un plan | 3 |
| `gold_v_ltv_cac_por_canal.csv` | Un canal | 6 |
| `gold_v_calidad_clientes.csv` | Un cliente | 247 |
| `gold_v_resumen_calidad.csv` | Un estado de calidad | 5 |
| `gold_v_calidad_cuarentena.csv` | Una fuente de datos | 1 |

> Si ves tildes rotas, en *Origen de archivo* elige **65001: Unicode (UTF-8)**.
> Verifica que `mrr_total`, `arr_total`, `cac_cop`, `ltv_cop` y las columnas `*_pct`
> queden como **Número decimal**, no texto.

## Paso 2 · Relaciones

Vista **Modelo**, dos relaciones **uno a muchos**, dirección simple:

```
dim_periodo[id_periodo]  1 ──► *  gold_v_resumen_ejecutivo[id_periodo]
dim_periodo[id_periodo]  1 ──► *  gold_v_cac_por_canal[id_periodo]
```

`gold_v_cohortes`, `gold_v_ltv` y las tablas de `gold_v_calidad_*` quedan **sin
relación** a propósito: cada una alimenta su propia página con su propio grano (una
matriz de cohortes no se relaciona con un calendario mensual sin duplicar filas).

Marca `dim_periodo` como tabla de fechas: selecciónala, `Herramientas de tabla > Marcar
como tabla de fechas`, columna `fecha_inicio`.

## Paso 3 · Medidas DAX

Ya vienen en la tabla `Medidas` si usaste la ruta rápida. Si las escribes a mano:

```dax
MRR = CALCULATE(SUM(gold_v_resumen_ejecutivo[mrr_total]), LASTNONBLANK(gold_v_resumen_ejecutivo[id_periodo], 1))
ARR = CALCULATE(SUM(gold_v_resumen_ejecutivo[arr_total]), LASTNONBLANK(gold_v_resumen_ejecutivo[id_periodo], 1))
Clientes Activos = CALCULATE(SUM(gold_v_resumen_ejecutivo[clientes_activos]), LASTNONBLANK(gold_v_resumen_ejecutivo[id_periodo], 1))
NRR % = CALCULATE(AVERAGE(gold_v_resumen_ejecutivo[nrr_pct]), LASTNONBLANK(gold_v_resumen_ejecutivo[id_periodo], 1))
Churn Logos % = CALCULATE(AVERAGE(gold_v_resumen_ejecutivo[churn_logos_pct]), LASTNONBLANK(gold_v_resumen_ejecutivo[id_periodo], 1))
Churn Ingreso % = CALCULATE(AVERAGE(gold_v_resumen_ejecutivo[churn_ingreso_pct]), LASTNONBLANK(gold_v_resumen_ejecutivo[id_periodo], 1))
MRR Nuevo = SUM(gold_v_resumen_ejecutivo[mrr_nuevo])
MRR Expansion = SUM(gold_v_resumen_ejecutivo[mrr_expansion])
MRR Contraccion = SUM(gold_v_resumen_ejecutivo[mrr_contraccion])
MRR Churn = SUM(gold_v_resumen_ejecutivo[mrr_churn])
MRR Reactivacion = SUM(gold_v_resumen_ejecutivo[mrr_reactivacion])
CAC = DIVIDE(SUM(gold_v_cac_por_canal[gasto_cop]), SUM(gold_v_cac_por_canal[clientes_nuevos]))
```

### El detalle que no te puedes saltar

`MRR`, `ARR`, `Clientes Activos` y los `*%` usan **`LASTNONBLANK`** — son medidas de
**estado** (una foto al cierre del mes), no se suman entre meses. Sin ese patrón, quitar
el segmentador de mes sumaría los 12 meses y el MRR anual saldría absurdo (más de
500 millones). `MRR Nuevo/Expansion/Contraccion/Churn/Reactivacion` sí son aditivas
(son flujos del mes, no una foto) — por eso son un `SUM` simple. `CAC` divide sumas
(gasto total / clientes nuevos) en cualquier contexto: nunca promedia CAC mensuales.

## Paso 4 · Comprobar el modelo

Antes de maquetar nada, una tarjeta con `[MRR]` y otra con `[Clientes Activos]`, **sin
ningún segmentador aplicado**, debe dar exactamente 57.201.326 y 144 — son diciembre
2024, el último mes con datos, gracias al `LASTNONBLANK`.

## Paso 5 · Las 5 páginas

### 1. Resumen ejecutivo
- 5 tarjetas: `[MRR]`, `[ARR]`, `[Clientes Activos]`, `[NRR %]`, `[Churn Ingreso %]`.
- Gráfico de líneas: eje `gold_v_resumen_ejecutivo[nombre_mes]`, valores `mrr_total` y
  `arr_total` (en dos visuales separados — nunca doble eje).
- Segmentador de `dim_periodo[nombre_mes]`, sincronizado con la página 2.

### 2. MRR Waterfall
- Un visual de **cascada** (*Waterfall*): categoría = las 5 columnas de movimiento
  (`mrr_nuevo`, `mrr_expansion`, `mrr_reactivacion`, `mrr_contraccion` en negativo,
  `mrr_churn` en negativo), para el mes seleccionado en el segmentador.
- Alternativa si no tienes el visual de cascada: columnas apiladas con `MRR
  Nuevo/Expansion/Contraccion/Churn/Reactivacion` como series, coloreadas verde
  (aumentos) / rojo (disminuciones).

### 3. Cohortes y NRR
- **Matriz**: filas `gold_v_cohortes[mes_cohorte]`, columnas
  `gold_v_cohortes[meses_desde_alta]`, valores `gold_v_cohortes[pct_retencion]`.
  Formato condicional: escala de color (rojo bajo → verde alto, centro en 100%).
- Gráfico de líneas: `[NRR %]` por `dim_periodo[nombre_mes]`, con una línea de
  referencia en 100%.

### 4. CAC y LTV
- Barras horizontales: eje `gold_v_cac_por_canal[nombre_canal]`, valor `[CAC]`. **No uses
  `AVERAGE(cac_cop)`**: promediar CAC mensuales contradice el diccionario de métricas.
  Ordena de menor a mayor — Referido debe quedar primero (173.171), Outbound último
  (6.257.989).
- Barras: eje `gold_v_ltv[nombre_plan]`, valores `ltv_cop` y `ltv_cop_churn_plan` (la
  sensibilidad con churn por plan; muestra también `bajas_plan` en el tooltip).
- Tabla de `gold_v_ltv_cac_por_canal`: `nombre_canal`, `cac_cop`, altas por plan,
  `ltv_cac` y `ltv_cac_churn_plan`, con formato condicional en rojo bajo 3. Outbound debe
  ser el único bajo 3 (2,5).

### 5. Calidad de datos
- **Donut o barras**: `gold_v_resumen_calidad[estado_calidad]` vs
  `gold_v_resumen_calidad[num_clientes]` — muestra de un vistazo los 5 estados (OK 157,
  Rebranding 16, Huérfano/ambiguo 17, Cliente sin eventos válidos 2, Lead sin
  facturación 55).
- **Tabla**: `gold_v_calidad_clientes` filtrada a `estado_calidad` distinto de `OK` y de
  `LEAD_SIN_FACTURACION` (los leads no son un problema de calidad), columnas
  `nombre_canonico`, `estado_calidad`, `nota_calidad`, `mrr_inicial_cop`.
- Tarjeta con el total de `gold_v_calidad_cuarentena[filas_rechazadas]`.

## Paso 6 · Guardar

`Archivo > Guardar como` → `saas_metrics.pbix` en esta misma carpeta (opcional, además
del `.pbip`).

---

## Si prefieres la ruta corta

Si el tiempo aprieta, monta solo la página 1 (Resumen ejecutivo) y la página 5
(Calidad de datos) — son las dos que más conectan directo con lo que pide la vacante
(métricas SaaS + auditoría de datos) y no necesitan el visual de cascada ni la matriz
de cohortes. Es más rápido, pero muestra menos superficie de modelado.
