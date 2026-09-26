-- =====================================================================================
-- Reto Alegra - SaaS Metrics (ficticio)
-- Modelo fisico (SQLite). Arquitectura en 4 capas:
--
--   raw/       archivos originales inmutables en disco (no es una tabla)
--   bronze_*   ingesta literal, todo TEXT, sin castear, con linaje (id_carga, hash_fila)
--   dim_/fact_ capa Silver: modelo relacional normalizado en 3FN
--   gold_v_*   vistas de consumo (sql/02_vistas_gold.sql). Power BI, los notebooks y
--              el agente conversacional leen SOLO de aqui.
--   ctl_/err_  control de cargas y cuarentena de calidad
--
-- Los alias (map_alias_*) NO se siembran a mano: los deriva el ETL
-- (notebooks/03_carga_y_calidad.ipynb) resolviendo las variantes de texto reales que
-- trae cada archivo de origen, y se guardan versionados en data/seeds/ para
-- reproducibilidad: los construye el analisis, no se escriben de antemano.
-- =====================================================================================

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------------
-- Limpieza (permite reejecutar el script completo de forma idempotente)
-- ------------------------------------------------------------------
DROP TABLE IF EXISTS err_registro_rechazado;
DROP TABLE IF EXISTS fact_gasto_adquisicion;
DROP TABLE IF EXISTS fact_contrato;
DROP TABLE IF EXISTS fact_evento_suscripcion;
DROP TABLE IF EXISTS bronze_marketing;
DROP TABLE IF EXISTS bronze_contrato;
DROP TABLE IF EXISTS bronze_billing;
DROP TABLE IF EXISTS bronze_crm;
DROP TABLE IF EXISTS ctl_carga;
DROP TABLE IF EXISTS map_alias_canal;
DROP TABLE IF EXISTS map_alias_plan;
DROP TABLE IF EXISTS map_alias_cliente;
DROP TABLE IF EXISTS dim_canal;
DROP TABLE IF EXISTS dim_plan;
DROP TABLE IF EXISTS dim_tasa_cambio;
DROP TABLE IF EXISTS dim_periodo;
DROP TABLE IF EXISTS dim_cliente;

-- =====================================================================================
-- CAPA SILVER - DIMENSIONES
-- =====================================================================================

-- Un cliente = una empresa real, resuelta entre CRM, Billing y Contratos.
-- nombre_canonico es la decision del analisis: cual de las variantes se usa para mostrar.
-- moneda_principal = moneda de su ultimo evento de facturacion (NULL si nunca facturo).
-- etapa_crm = ultima etapa en el CRM (Cliente, Lead, Trial, Perdido); NULL si no existe en CRM.
CREATE TABLE dim_cliente (
    id_cliente       INTEGER PRIMARY KEY,
    nombre_canonico  TEXT    NOT NULL,
    fecha_alta       TEXT,
    id_canal         INTEGER,
    moneda_principal TEXT    CHECK (moneda_principal IN ('COP','USD')),
    activo           INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0,1)),
    etapa_crm        TEXT
);

-- id_periodo = AAAAMM. Se siembra 2024-2025 completos aunque hoy solo haya datos 2024,
-- asi el mes siguiente se carga sin tocar el modelo.
CREATE TABLE dim_periodo (
    id_periodo   INTEGER PRIMARY KEY,
    anio         INTEGER NOT NULL,
    mes          INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
    nombre_mes   TEXT    NOT NULL,
    fecha_inicio TEXT    NOT NULL,
    fecha_fin    TEXT    NOT NULL,
    UNIQUE (anio, mes)
);

CREATE TABLE dim_plan (
    id_plan            INTEGER PRIMARY KEY,
    nombre_plan        TEXT    NOT NULL UNIQUE,
    precio_cop_mensual NUMERIC(18,2) NOT NULL,
    precio_usd_mensual NUMERIC(18,2) NOT NULL,
    orden              INTEGER NOT NULL
);

CREATE TABLE dim_canal (
    id_canal     INTEGER PRIMARY KEY,
    nombre_canal TEXT NOT NULL UNIQUE
);

-- Tasa de cambio por periodo, necesaria para convertir clientes facturados en USD.
CREATE TABLE dim_tasa_cambio (
    id_periodo   INTEGER PRIMARY KEY REFERENCES dim_periodo(id_periodo),
    tasa_usd_cop NUMERIC(18,4) NOT NULL
);

-- ------------------------------------------------------------------------------------
-- Tablas puente: resuelven variantes de texto contra la dimension canonica.
-- Se llenan desde el ETL (notebooks/03_carga_y_calidad.ipynb), no a mano.
-- ------------------------------------------------------------------------------------
CREATE TABLE map_alias_cliente (
    texto_origen   TEXT    NOT NULL,   -- nombre normalizado (o clave) tal como aparece en origen
    origen_sistema TEXT    NOT NULL CHECK (origen_sistema IN ('CRM','BILLING','CONTRATO')),
    id_cliente     INTEGER NOT NULL REFERENCES dim_cliente(id_cliente),
    metodo         TEXT    NOT NULL CHECK (metodo IN ('NORMALIZACION','ALIAS_MANUAL')),
    nota           TEXT,
    PRIMARY KEY (texto_origen, origen_sistema)
);

CREATE TABLE map_alias_plan (
    texto_origen   TEXT    NOT NULL,
    origen_sistema TEXT    NOT NULL CHECK (origen_sistema IN ('CRM','BILLING','CONTRATO')),
    id_plan        INTEGER NOT NULL REFERENCES dim_plan(id_plan),
    PRIMARY KEY (texto_origen, origen_sistema)
);

CREATE TABLE map_alias_canal (
    texto_origen   TEXT    NOT NULL,
    origen_sistema TEXT    NOT NULL CHECK (origen_sistema IN ('CRM','MARKETING')),
    id_canal       INTEGER NOT NULL REFERENCES dim_canal(id_canal),
    PRIMARY KEY (texto_origen, origen_sistema)
);

-- =====================================================================================
-- CONTROL DE CARGAS
-- =====================================================================================
CREATE TABLE ctl_carga (
    id_carga         INTEGER PRIMARY KEY,
    archivo_origen   TEXT    NOT NULL UNIQUE,
    hash_archivo     TEXT    NOT NULL,
    formato          TEXT    NOT NULL CHECK (formato IN ('CSV','XLSX')),
    contenido        TEXT    NOT NULL CHECK (contenido IN ('CRM','BILLING','CONTRATO','MARKETING')),
    filas_leidas     INTEGER NOT NULL DEFAULT 0,
    filas_aceptadas  INTEGER NOT NULL DEFAULT 0,
    filas_rechazadas INTEGER NOT NULL DEFAULT 0,
    fecha_carga      TEXT    NOT NULL
);

-- =====================================================================================
-- CAPA BRONZE - ingesta literal. Nada se rechaza aqui, nada se castea.
-- =====================================================================================
CREATE TABLE bronze_crm (
    id_bronze          INTEGER PRIMARY KEY,
    id_carga           INTEGER NOT NULL REFERENCES ctl_carga(id_carga) ON DELETE CASCADE,
    numero_linea       INTEGER NOT NULL,
    id_contacto_crm    TEXT,
    nombre_empresa     TEXT,
    nombre_contacto    TEXT,
    email              TEXT,
    telefono           TEXT,
    canal_adquisicion  TEXT,
    fecha_alta_lead    TEXT,
    etapa              TEXT,
    hash_fila          TEXT NOT NULL
);

CREATE TABLE bronze_billing (
    id_bronze                   INTEGER PRIMARY KEY,
    id_carga                    INTEGER NOT NULL REFERENCES ctl_carga(id_carga) ON DELETE CASCADE,
    numero_linea                INTEGER NOT NULL,
    id_customer_stripe          TEXT,
    nombre_cliente_facturacion  TEXT,
    email_facturacion           TEXT,
    plan_contratado             TEXT,
    moneda                      TEXT,
    monto                       TEXT,
    fecha_evento                TEXT,
    tipo_evento                 TEXT,
    id_periodo                  TEXT,
    hash_fila                   TEXT NOT NULL
);

CREATE TABLE bronze_contrato (
    id_bronze               INTEGER PRIMARY KEY,
    id_carga                INTEGER NOT NULL REFERENCES ctl_carga(id_carga) ON DELETE CASCADE,
    numero_linea             INTEGER NOT NULL,
    razon_social             TEXT,
    nit                      TEXT,
    plan_contratado          TEXT,
    valor_mensual_contrato   TEXT,
    moneda                   TEXT,
    fecha_firma              TEXT,     -- guarda el valor crudo (a veces Timestamp, a veces texto)
    vigencia_meses           TEXT,
    hash_fila                TEXT NOT NULL
);

CREATE TABLE bronze_marketing (
    id_bronze     INTEGER PRIMARY KEY,
    id_carga      INTEGER NOT NULL REFERENCES ctl_carga(id_carga) ON DELETE CASCADE,
    numero_linea  INTEGER NOT NULL,
    canal         TEXT,
    mes           TEXT,
    gasto_cop     TEXT,
    hash_fila     TEXT NOT NULL
);

-- =====================================================================================
-- CAPA SILVER - HECHOS
-- =====================================================================================

-- Grano: un evento del ciclo de vida de una suscripcion (alta/upgrade/downgrade/baja/
-- reactivacion). monto_mensual_cop es SIEMPRE el valor resultante tras el evento, ya
-- convertido a COP; monto_anterior_cop solo aplica a upgrade/downgrade y es lo que se
-- pagaba antes (permite calcular expansion/contraccion sin reconsultar el evento previo).
CREATE TABLE fact_evento_suscripcion (
    id_evento         INTEGER PRIMARY KEY,
    id_carga          INTEGER NOT NULL REFERENCES ctl_carga(id_carga) ON DELETE CASCADE,
    id_cliente        INTEGER NOT NULL REFERENCES dim_cliente(id_cliente),
    id_periodo        INTEGER NOT NULL REFERENCES dim_periodo(id_periodo),
    id_plan           INTEGER NOT NULL REFERENCES dim_plan(id_plan),
    id_plan_anterior  INTEGER REFERENCES dim_plan(id_plan),
    tipo_evento       TEXT    NOT NULL CHECK (tipo_evento IN
                        ('nueva_suscripcion','upgrade','downgrade','cancelacion','reactivacion')),
    moneda_origen     TEXT    NOT NULL CHECK (moneda_origen IN ('COP','USD')),
    monto_mensual_cop NUMERIC(18,2) NOT NULL,
    monto_anterior_cop NUMERIC(18,2),
    fecha_evento      TEXT    NOT NULL,
    numero_linea      INTEGER,
    hash_fila         TEXT
);

-- Grano: un contrato firmado.
CREATE TABLE fact_contrato (
    id_contrato            INTEGER PRIMARY KEY,
    id_carga               INTEGER NOT NULL REFERENCES ctl_carga(id_carga) ON DELETE CASCADE,
    id_cliente             INTEGER NOT NULL REFERENCES dim_cliente(id_cliente),
    id_plan                INTEGER NOT NULL REFERENCES dim_plan(id_plan),
    valor_mensual_cop      NUMERIC(18,2) NOT NULL,
    fecha_firma            TEXT NOT NULL,
    vigencia_meses         INTEGER NOT NULL
);

-- Grano: gasto de adquisicion por canal y mes.
CREATE TABLE fact_gasto_adquisicion (
    id_carga   INTEGER NOT NULL REFERENCES ctl_carga(id_carga) ON DELETE CASCADE,
    id_canal   INTEGER NOT NULL REFERENCES dim_canal(id_canal),
    id_periodo INTEGER NOT NULL REFERENCES dim_periodo(id_periodo),
    gasto_cop  NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (id_canal, id_periodo)
);

-- Cuarentena: una fila que no se puede tipificar NO rompe la carga, se aisla aqui.
CREATE TABLE err_registro_rechazado (
    id_error       INTEGER PRIMARY KEY,
    id_carga       INTEGER REFERENCES ctl_carga(id_carga) ON DELETE CASCADE,
    numero_linea   INTEGER,
    fila_cruda     TEXT,
    motivo         TEXT NOT NULL,
    fecha_registro TEXT NOT NULL
);

-- =====================================================================================
-- INDICES
-- =====================================================================================
CREATE INDEX ix_evento_cliente     ON fact_evento_suscripcion (id_cliente);
CREATE INDEX ix_evento_periodo     ON fact_evento_suscripcion (id_periodo);
CREATE INDEX ix_evento_tipo        ON fact_evento_suscripcion (tipo_evento);
CREATE INDEX ix_evento_analitico   ON fact_evento_suscripcion (id_periodo, tipo_evento, id_cliente);
CREATE INDEX ix_contrato_cliente   ON fact_contrato (id_cliente);
CREATE INDEX ix_bronze_crm_carga   ON bronze_crm (id_carga);
CREATE INDEX ix_bronze_bill_carga  ON bronze_billing (id_carga);
CREATE INDEX ix_bronze_contr_carga ON bronze_contrato (id_carga);
CREATE INDEX ix_bronze_mkt_carga   ON bronze_marketing (id_carga);
