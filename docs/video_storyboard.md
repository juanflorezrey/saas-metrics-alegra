# Guion del video (≤ 5 minutos) — Actividad 1, Reto Alegra

Objetivo del video según el reto: mostrar **qué problema resolviste, cómo lo
abordaste, qué herramientas usaste y qué resultado obtuviste** — no una solución
perfecta, sino el proceso. Este guion está armado sobre los artefactos ya construidos;
grábalo siguiendo la pantalla, no leyendo un libreto.

| Min | Qué mostrar | Qué decir |
|---|---|---|
| **0:00–0:25** | Tu cara / pantalla en blanco | "Simulé un SaaS con datos de CRM, Facturación y Contratos que no cruzan entre sí — el problema real que describe la vacante de Alegra. La pregunta: ¿cuál es el MRR real, y por qué no cuadra entre sistemas?" |
| **0:25–1:00** | `notebooks/01_arquitectura_y_modelo.ipynb` (el diagrama de capas) | "Usé Claude Code de principio a fin: para diseñar la arquitectura de 4 capas, generar datos sintéticos con mugre intencional, escribir el ETL, y llegar a las métricas." |
| **1:00–2:30** | `notebooks/03_carga_y_calidad.ipynb` — la celda de hallazgos (colisiones, rebranding, cuarentena) | **El momento central.** "Al generar los datos, por azar dos empresas distintas terminaron con el mismo nombre. Si resuelves identidad solo por nombre, las fusionas por error — así lo detecté con Claude Code, y así lo corregimos: anclar cada sistema por su propio ID estable, y cuando un nombre es ambiguo, no adivinar, sino marcarlo para revisión manual." (Muestra el bloque de `hallazgos` con las 3 colisiones impresas.) |
| **2:30–3:15** | `notebooks/04_metricas_saas.ipynb` — el MRR waterfall y el gráfico de cohortes | "Con la identidad resuelta, esto ya se puede confiar: MRR de diciembre, NRR promedio de 100%, y la cascada de nuevo/expansión/contracción/churn mes a mes." |
| **3:15–4:00** | Dashboard Power BI (`powerbi/saas_metrics.pbip` abierto en Desktop) | "Y esto es lo que vería un stakeholder: resumen ejecutivo, waterfall, cohortes, CAC por canal — Referido cuesta 36 veces menos que Outbound por cliente adquirido, ahí hay una conversación con Growth." |
| **4:00–4:40** | Vuelve a la cámara | "No fue una reconciliación perfecta a propósito: documenté exactamente por qué un 1% del MRR no cuadra — 3 filas perdieron su tipo de evento en origen, y eso se propaga a los cambios de plan posteriores. Prefiero mostrar el hueco que esconderlo." |
| **4:40–5:00** | Cierre | "Todo el código, los datos y el dashboard están en el repo de GitHub que acompaña este video. Así es como uso IA no para escribir código más rápido, sino para pensar mejor un problema de datos." |

## Notas de grabación

- **Herramienta sugerida:** Loom (graba pantalla + cámara, genera link compartible al
  instante — encaja directo con "acompañar el video con... links").
- Antes de grabar: ten `notebooks/03_carga_y_calidad.ipynb` y `04_metricas_saas.ipynb`
  ya abiertos con las salidas visibles (ya están ejecutados y guardados), y el
  `.pbip` de Power BI ya abierto en Desktop — no dependas de que algo cargue en vivo.
- Si grabas en vivo en vez de mostrar el notebook ya ejecutado: el momento más
  filmable es correr la celda de `reporte_calidad.json` y ver aparecer las 3
  colisiones — es genuinamente el hallazgo que no estaba planeado.
- Cierra mencionando el link al repo (que quede en la descripción, no solo dicho).
