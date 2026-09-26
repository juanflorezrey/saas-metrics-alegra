# Agente conversacional — "chatea con las métricas del SaaS"

Un agente al que se le pregunta en español, por ejemplo *"¿por qué cayó el MRR en noviembre?"*
o *"¿qué canal de adquisición recortarías?"*, y que responde **consultando la capa gold**,
sin inventar cifras. Cada consulta que ejecuta queda a la vista y en una bitácora.

Tiene dos piezas:

1. **Un servidor MCP** (`agente/servidor_mcp.py`) que expone la capa gold como herramientas
   gobernadas: solo lectura, solo vistas gold, límites y auditoría. MCP (Model Context
   Protocol) es el estándar para conectar datos a asistentes de IA. Cualquier cliente MCP
   puede usarlo: Claude Code, Claude Desktop, etc.
2. **Un skill de Claude Code** (`.claude/skills/analista-saas/SKILL.md`) que le da al modelo
   el rol de analista de BI: reglas de negocio del diccionario de métricas, cuándo advertir
   sobre calidad de datos, formato de respuesta.

**Costo:** cero créditos de API adicionales. Corre dentro de Claude Code con la suscripción
que ya se usa (Pro/Max). Si Claude Code estuviera con facturación de API, cada pregunta sí
consumiría créditos.

---

## Arquitectura

```
 VS Code · Claude Code      /analista-saas <pregunta>
        │  MCP (stdio)
        ▼
 agente/servidor_mcp.py     4 herramientas (MCPServer, mcp 2.x)
        │
 agente/guardrails.py       capa publicada en memoria + authorizer + límites + bitácora
        │   (al arrancar copia SOLO gold_v_* y dim_*; bronze/silver/control no existen ahí)
        ▼
 db/saas_metrics.db
```

## Herramientas

| Herramienta | Qué hace |
|---|---|
| `describir_modelo` | Lista las vistas que el agente puede leer, con su grano, columnas, filas y descripción de negocio (`agente/catalogo.py`). |
| `consultar_sql(sql, motivo)` | Una sentencia `SELECT` de solo lectura; devuelve una tabla (máx. 200 filas). El `motivo` queda en la bitácora. |
| `leer_documentacion(documento)` | `diccionario_metricas`, `informe` o `contexto_simulacion`: definiciones, advertencias y supuestos, para que el agente no los invente. |
| `graficar(sql, tipo, x, y, titulo, linea_referencia?)` | Línea o barras con la paleta del proyecto; guarda el PNG en `salidas/` y devuelve la imagen al agente. |

## Gobernanza: las reglas las hace cumplir el motor, no el prompt

El agente escribe SQL libre, así que "por favor solo lee gold" en el prompt no es una
garantía. Lo que sí la da:

- **Capa publicada.** El agente nunca se conecta a `db/saas_metrics.db`. Al arrancar, el
  servidor adjunta la base en modo solo lectura, **materializa en memoria solo las vistas
  gold y las dimensiones**, y la desconecta. En la conexión del agente, bronze, silver y
  control simplemente no existen.
- **Solo lectura.** `PRAGMA query_only` + un authorizer de SQLite que niega todo lo que no
  sea leer las tablas publicadas (INSERT, UPDATE, DELETE, DROP, CREATE, ATTACH, PRAGMA…).
- **Una sentencia por llamada**, **máximo 200 filas** y **5 segundos** por consulta.
- **Bitácora de auditoría.** Cada llamada queda en `salidas/auditoria_consultas.jsonl`:
  hora, motivo, SQL, estado (permitida / bloqueada / error), filas y milisegundos.
- **Errores legibles.** Una consulta bloqueada vuelve como error de herramienta con la
  razón ("Bloqueado por gobernanza…"), y el servidor sigue funcionando.
- **La capa se re-publica sola** si la base cambia (por ejemplo, si se vuelve a correr el
  ETL con el servidor encendido).

**Por qué una copia publicada y no un allowlist sobre la base real:** la primera versión
usaba un authorizer sobre la base completa y permitía las lecturas que ocurrían "dentro de
una vista gold". Las pruebas mostraron que SQLite reporta como origen de una lectura tanto
una vista como un **CTE**. Por eso `WITH gold_v_arr_mrr AS (SELECT * FROM bronze_billing) …`
se colaba hasta bronze. Publicar solo lo permitido elimina esa clase entera de evasiones.
Está cubierto por `pruebas/test_guardrails.py`.

## Cómo usarlo

1. Instalar dependencias (una vez): `python -m pip install -r requirements.txt`
2. Abrir **`D:\Claudia\Alegra`** como carpeta en VS Code. El panel de Claude Code tiene
   que arrancar en esta carpeta para cargar `.mcp.json` y `.claude/`.
3. En Claude Code escribir `/mcp` y confirmar que `saas-metrics` aparece **✔ Connected**.
   `.claude/settings.json` ya pre-aprueba el servidor y sus 4 herramientas, así que la
   demo no muestra ventanas de permiso.
4. Preguntar: `/analista-saas ¿Cuál es el MRR a diciembre y cómo evolucionó en el año?`
   Las preguntas de demo con sus respuestas esperadas están en `pruebas/preguntas_demo.md`.

**Al clonar en otro equipo:** `.mcp.json` apunta a la ruta absoluta de Python de este
equipo (`C:/Users/USUARIO/AppData/Local/Programs/Python/Python312/python.exe`), porque aquí
el `python` del PATH es el acceso directo de Microsoft Store y no arranca. Ajusta
`command` a tu intérprete. El script (`agente/servidor_mcp.py`) va relativo: Claude Code
lanza los servidores de `.mcp.json` con la carpeta del proyecto como directorio de trabajo.

### Bonus: el mismo servidor en Claude Desktop

En `%APPDATA%\Claude\claude_desktop_config.json` (rutas absolutas, porque Claude Desktop
no arranca en la carpeta del proyecto):

```json
{
  "mcpServers": {
    "saas-metrics": {
      "command": "C:/Users/USUARIO/AppData/Local/Programs/Python/Python312/python.exe",
      "args": ["D:/Claudia/Alegra/agente/servidor_mcp.py"],
      "env": { "PYTHONUTF8": "1" }
    }
  }
}
```

## Pruebas (sin LLM, sin costo)

| Comando | Qué verifica | Resultado |
|---|---|---|
| `python pruebas/test_guardrails.py` | 27 casos: lecturas permitidas, bronze/silver/control bloqueados, CTE que suplanta una vista gold, subconsultas, escrituras, ATTACH, PRAGMA, dos sentencias, consulta infinita cortada a 5 s, truncado a 200 filas, bitácora e integridad de la base | 27/27 |
| `python pruebas/smoke_mcp.py` | Levanta el servidor por stdio con el cliente MCP oficial, igual que Claude Code, y llama cada herramienta: MRR de diciembre = 57.201.326, bloqueos de gobernanza, tildes por stdio, PNG generado | 10/10 |

## Limitaciones conocidas

- Las respuestas del modelo no son deterministas: ensayar con `pruebas/preguntas_demo.md`.
- Los gráficos se guardan como PNG y se abren en una pestaña de VS Code (el agente también
  recibe la imagen, así que puede comentarla).
- `dim_cliente.moneda_principal` quedó en `COP` para todos los clientes (el ETL no la
  calcula). El catálogo lo advierte y dirige al agente a `gold_v_eventos_detalle.moneda_origen`.
- El MRR en USD se registra a la tasa del mes del último evento de cada cliente (ver
  `docs/INFORME.md`, advertencia metodológica).
