# Guion del video (≤ 5 minutos) — Actividad 1, Reto Alegra

Objetivo del video según el reto: mostrar **qué problema resolviste, cómo lo abordaste,
qué herramientas usaste y qué resultado obtuviste**. No se pide una solución perfecta, se
pide ver el proceso. El centro del video es la **demo en vivo del agente**: es la parte
"construida con IA" que se ve funcionando.

| Min | Qué mostrar | Qué decir |
|---|---|---|
| **0:00–0:20** | Tu cara / el README en GitHub | "Simulé un SaaS con datos de CRM, Facturación y Contratos que no cruzan entre sí, el problema que describe la vacante. La pregunta: ¿cuál es el MRR real, y se puede confiar en él?" |
| **0:20–0:45** | `docs/AGENTE.md` (el diagrama) | "Con Claude Code construí el pipeline completo: datos, ETL, capa gold de métricas SaaS, Power BI. Encima de eso, un agente al que se le pregunta en español." |
| **0:45–1:30** | `notebooks/03_carga_y_calidad.ipynb`, celda de hallazgos | "El hallazgo que no estaba planeado: por azar, dos empresas distintas quedaron con el mismo nombre. Resolver identidad solo por nombre las habría fusionado. Las anclé por el ID estable de cada sistema y marqué las ambiguas para revisión manual." |
| **1:30–3:45** | **Claude Code en VS Code, en vivo** | Preguntas 1 → 2 → 5 → 6 → 7 de `pruebas/preguntas_demo.md` (ver abajo). Deja que se vea cada consulta SQL que ejecuta el agente. |
| **3:45–4:15** | Dashboard Power BI (`powerbi/saas_metrics.pbip`) | "Lo que vería un stakeholder: resumen ejecutivo, waterfall, cohortes, CAC por canal." |
| **4:15–5:00** | `salidas/auditoria_consultas.jsonl` y luego tu cara | "Cada pregunta quedó auditada. Y el agente no maquilla: la reconstrucción difiere ~1% de la verdad, y sé exactamente por qué. Todo está en el repo de GitHub. Así uso IA: no para escribir código más rápido, sino para pensar mejor un problema de datos." |

## La demo en vivo del agente (1:30–3:45)

1. `/analista-saas ¿Cuál es el MRR y el ARR a diciembre, y cómo evolucionó en el año?`
   → MRR 57.201.326 · ARR 686.415.912 + gráfico. *Di:* "Fíjense que no inventa: consulta la vista gold."
2. `¿Por qué cayó el MRR en octubre y noviembre?`
   → descompone el waterfall y aclara que no hay altas después de septiembre **por supuesto de la simulación**. *Di:* "Distingue un hallazgo de un supuesto: no se inventa una causa comercial."
3. `¿Qué canal de adquisición recortarías y por qué?`
   → Outbound es el único canal con LTV:CAC bajo 3:1 (2,5x, casi la mitad de sus altas son Starter) frente a 84x de Referido.
4. `¿Qué tanto puedo confiar en estas cifras?`
   → huérfanos, colisiones, cuarentena, desvío ~1%. *Di:* "Esta es la pregunta que un BI Partner tiene que poder contestar."
5. `Muéstrame la tabla bronze_billing` → **bloqueado por gobernanza**.
   *Di:* "El agente solo ve la capa gold. La regla no está en el prompt, la hace cumplir el motor de base de datos."

## Notas de grabación

- **Herramienta sugerida:** Loom (graba pantalla y cámara, y genera un link compartible al
  instante, que encaja con "acompañar el video con... links").
- **Antes de grabar:** abre la carpeta raíz del repo en VS Code, corre `/mcp` y
  confirma que `saas-metrics` aparece conectado, y haz un ensayo completo con
  `pruebas/preguntas_demo.md`. Borra `salidas/auditoria_consultas.jsonl` justo antes de
  grabar para que la bitácora muestre solo la demo.
- **Plan B:** graba un ensayo completo como respaldo. Si algo falla en vivo, los notebooks
  y el Power BI siguen contando la historia.
- Las respuestas del modelo varían entre corridas. Si una cifra no coincide con
  `pruebas/preguntas_demo.md`, repite la pregunta o ajusta las reglas del skill, no los
  guardrails.
- Deja el link al repo en la descripción, no solo dicho en voz.
