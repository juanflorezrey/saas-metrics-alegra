# SaaS Metrics — proyecto ficticio construido con Claude Code

**Reto Alegra, Actividad 1 ("Construye con IA").** Todos los datos son sintéticos
(generados con `Faker`, semilla fija). Ninguna cifra corresponde a Alegra ni a un
cliente real.

## El problema

Un SaaS ficticio que factura desde **Stripe**, gestiona su embudo comercial en un
**CRM** estilo HubSpot y firma **contratos** formales para sus cuentas grandes — sin
que los tres sistemas compartan un identificador común. La pregunta de negocio:
**¿cuál es el MRR real, y por qué no cuadra entre sistemas?**

## Qué hay aquí

| Carpeta | Contenido |
|---|---|
| `data/` | Generador de datos sintéticos (`generar_datos.py`) + seeds + verdad de control |
| `sql/` | DDL de 4 capas (bronze/silver/control) + vistas gold de métricas SaaS |
| `notebooks/` | 4 notebooks ejecutados de principio a fin: arquitectura → generar datos → carga y calidad → métricas |
| `powerbi/` | Proyecto Power BI (`.pbip`/TMDL) + CSV exportados + instrucciones |
| `docs/` | Informe, diccionario de métricas, guion del video |
| `db/` | `saas_metrics.db` (SQLite poblado y verificado) |
| `cargar_datos.py`, `exportar_csv.py`, `lib_comun.py` | El ETL y utilidades, en la raíz |

## El hallazgo que no estaba planeado

Al generar los datos sintéticos, `Faker` produjo por azar el **mismo nombre de
empresa para dos clientes distintos**, tres veces. Resolver identidad solo por nombre
normalizado habría fusionado esas empresas reales por error. La solución — anclar cada
sistema por su propio identificador estable, y neutralizar cualquier nombre ambiguo en
vez de asignarlo arbitrariamente — es el corazón de este proyecto. Detalle completo en
[`docs/INFORME.md`](docs/INFORME.md).

## Cómo reproducirlo

```powershell
python data/generar_datos.py   # genera los 4 archivos de origen sucios
python cargar_datos.py         # ETL: bronze -> silver, resuelve identidad y alias
# aplicar sql/02_vistas_gold.sql contra db/saas_metrics.db (ver notebooks/03)
python exportar_csv.py         # exporta las vistas gold a powerbi/*.csv
```

O simplemente abre y corre los notebooks en orden (`01` → `04`); cada uno llama a los
scripts de arriba y narra lo que va encontrando.

## Métricas clave (diciembre 2024)

| MRR | ARR | Clientes activos | NRR promedio | Churn de ingreso promedio |
|---:|---:|---:|---:|---:|
| 57.201.326 COP | 686.415.912 COP | 144 | 100,0% | 1,87% mensual |

Diccionario completo de fórmulas en [`docs/DICCIONARIO_METRICAS.md`](docs/DICCIONARIO_METRICAS.md).

## Stack

Python (pandas, Faker, matplotlib) · SQLite · Jupyter · Power BI Desktop (PBIP/TMDL) ·
Claude Code como copiloto en cada etapa.

## Video

Guion en [`docs/video_storyboard.md`](docs/video_storyboard.md). Link al video: *(agregar aquí)*.

---

Construido por Juan Pablo Florez Rey, con Claude Code, para el proceso de selección de
Business Intelligence & Analytics Partner en Alegra.
