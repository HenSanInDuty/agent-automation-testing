-- ═══════════════════════════════════════════════════════════════════════════
--  Auto-AT – ClickHouse schema
--  Runs automatically on first container start via docker-entrypoint-initdb.d
--
--  Pattern (per topic):
--    1. kafka_* table   – Kafka Engine reader (stateless, no storage)
--    2. *_events table  – MergeTree storage (actual data)
--    3. *_mv view       – Materialized View bridges 1 → 2 automatically
--
--  Topics consumed:
--    auto_at.pipeline_events   – run-level lifecycle (run.started/completed/…)
--    auto_at.node_events       – per-node progress  (node.started/completed/…)
--    auto_at.llm_calls         – every LLM/CrewAI invocation
--    auto_at.api_requests      – HTTP request telemetry
-- ═══════════════════════════════════════════════════════════════════════════

CREATE DATABASE IF NOT EXISTS auto_at;

-- ─────────────────────────────────────────────────────────────────────────────
-- pipeline_events
-- Fields: run lifecycle events with run-level metadata + common debug fields
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS auto_at.kafka_pipeline_events
(
    -- event identity
    event_type              String,
    run_id                  String,
    timestamp               DateTime64(3, 'UTC'),

    -- pipeline metadata
    template_id             String,
    document_name           String,
    total_nodes             UInt16,
    total_layers            UInt16,

    -- outcome fields (populated for terminal events)
    duration_seconds        Float32,
    error                   String,
    failed_node             String,

    -- debug / misc (JSON blob of remaining event data)
    data                    String,

    -- common debug fields
    app_version             String,
    env                     String,
    hostname                String,
    pid                     Int32
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list          = 'kafka:9092',
    kafka_topic_list           = 'auto_at.pipeline_events',
    kafka_group_name           = 'ch_pipeline_events',
    kafka_format               = 'JSONEachRow',
    kafka_skip_broken_messages = 10;

CREATE TABLE IF NOT EXISTS auto_at.pipeline_events
(
    event_type              LowCardinality(String),
    run_id                  String,
    timestamp               DateTime64(3, 'UTC'),
    template_id             String,
    document_name           String,
    total_nodes             UInt16,
    total_layers            UInt16,
    duration_seconds        Float32,
    error                   String,
    failed_node             String,
    data                    String,
    app_version             LowCardinality(String),
    env                     LowCardinality(String),
    hostname                String,
    pid                     Int32,
    _ingested_at            DateTime DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (run_id, timestamp)
SETTINGS index_granularity = 8192;

CREATE MATERIALIZED VIEW IF NOT EXISTS auto_at.pipeline_events_mv
TO auto_at.pipeline_events AS
SELECT * FROM auto_at.kafka_pipeline_events;

-- ─────────────────────────────────────────────────────────────────────────────
-- node_events
-- Fields: rich per-node debug info including retry, errors, output preview
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS auto_at.kafka_node_events
(
    -- event identity
    event_type              String,
    run_id                  String,
    timestamp               DateTime64(3, 'UTC'),

    -- node metadata
    node_id                 String,
    node_type               String,
    agent_id                String,
    label                   String,

    -- execution state
    status                  String,   -- running | completed | failed | skipped
    duration_ms             UInt32,

    -- retry debug
    retry_attempt           UInt8,    -- 0 = first attempt
    will_retry              UInt8,    -- 0=false, 1=true (Bool not supported in JSONEachRow)

    -- error debug
    error_detail            String,

    -- output debug
    output_preview          String,   -- first 300 chars of node output
    parent_node_ids         String,   -- JSON array of upstream node_ids

    -- common debug fields
    app_version             String,
    env                     String,
    hostname                String,
    pid                     Int32
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list          = 'kafka:9092',
    kafka_topic_list           = 'auto_at.node_events',
    kafka_group_name           = 'ch_node_events',
    kafka_format               = 'JSONEachRow',
    kafka_skip_broken_messages = 10;

CREATE TABLE IF NOT EXISTS auto_at.node_events
(
    event_type              LowCardinality(String),
    run_id                  String,
    timestamp               DateTime64(3, 'UTC'),
    node_id                 String,
    node_type               LowCardinality(String),
    agent_id                String,
    label                   String,
    status                  LowCardinality(String),
    duration_ms             UInt32,
    retry_attempt           UInt8,
    will_retry              UInt8,
    error_detail            String,
    output_preview          String,
    parent_node_ids         String,
    app_version             LowCardinality(String),
    env                     LowCardinality(String),
    hostname                String,
    pid                     Int32,
    _ingested_at            DateTime DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (run_id, node_id, timestamp)
SETTINGS index_granularity = 8192;

CREATE MATERIALIZED VIEW IF NOT EXISTS auto_at.node_events_mv
TO auto_at.node_events AS
SELECT * FROM auto_at.kafka_node_events;

-- ─────────────────────────────────────────────────────────────────────────────
-- llm_calls
-- Fields: full LLM debug data – latency, token usage, model, task context
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS auto_at.kafka_llm_calls
(
    -- call identity
    run_id                      String,
    node_id                     String,
    agent_id                    String,
    timestamp                   DateTime64(3, 'UTC'),

    -- model info
    model                       String,   -- e.g. "openai/gpt-4o"
    provider                    String,   -- e.g. "openai"

    -- performance
    latency_ms                  UInt32,

    -- token usage (0 when provider doesn't expose)
    prompt_tokens               UInt32,
    completion_tokens           UInt32,
    total_tokens                UInt32,

    -- outcome
    success                     UInt8,    -- 1=ok, 0=error
    error_type                  String,   -- exception class name
    error_message               String,

    -- task debug
    task_description_len        UInt32,   -- total length in chars
    task_description_preview    String,   -- first 200 chars

    -- common debug fields
    app_version                 String,
    env                         String,
    hostname                    String,
    pid                         Int32
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list          = 'kafka:9092',
    kafka_topic_list           = 'auto_at.llm_calls',
    kafka_group_name           = 'ch_llm_calls',
    kafka_format               = 'JSONEachRow',
    kafka_skip_broken_messages = 10;

CREATE TABLE IF NOT EXISTS auto_at.llm_calls
(
    run_id                      String,
    node_id                     String,
    agent_id                    String,
    timestamp                   DateTime64(3, 'UTC'),
    model                       LowCardinality(String),
    provider                    LowCardinality(String),
    latency_ms                  UInt32,
    prompt_tokens               UInt32,
    completion_tokens           UInt32,
    total_tokens                UInt32,
    success                     UInt8,
    error_type                  LowCardinality(String),
    error_message               String,
    task_description_len        UInt32,
    task_description_preview    String,
    app_version                 LowCardinality(String),
    env                         LowCardinality(String),
    hostname                    String,
    pid                         Int32,
    _ingested_at                DateTime DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (run_id, node_id, timestamp)
SETTINGS index_granularity = 8192;

CREATE MATERIALIZED VIEW IF NOT EXISTS auto_at.llm_calls_mv
TO auto_at.llm_calls AS
SELECT * FROM auto_at.kafka_llm_calls;

-- ─────────────────────────────────────────────────────────────────────────────
-- api_requests
-- Fields: HTTP telemetry for every non-health-check request
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS auto_at.kafka_api_requests
(
    -- request identity
    method              String,
    path                String,
    status_code         UInt16,
    timestamp           DateTime64(3, 'UTC'),

    -- performance
    duration_ms         UInt32,

    -- caller info
    client_ip           String,
    user_agent          String,
    request_id          String,   -- X-Request-ID header or auto UUID4

    -- response info
    content_length      Int64,    -- -1 when unknown

    -- common debug fields
    app_version         String,
    env                 String,
    hostname            String,
    pid                 Int32
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list          = 'kafka:9092',
    kafka_topic_list           = 'auto_at.api_requests',
    kafka_group_name           = 'ch_api_requests',
    kafka_format               = 'JSONEachRow',
    kafka_skip_broken_messages = 10;

CREATE TABLE IF NOT EXISTS auto_at.api_requests
(
    method              LowCardinality(String),
    path                String,
    status_code         UInt16,
    timestamp           DateTime64(3, 'UTC'),
    duration_ms         UInt32,
    client_ip           String,
    user_agent          String,
    request_id          String,
    content_length      Int64,
    app_version         LowCardinality(String),
    env                 LowCardinality(String),
    hostname            String,
    pid                 Int32,
    _ingested_at        DateTime DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (path, status_code, timestamp)
SETTINGS index_granularity = 8192;

CREATE MATERIALIZED VIEW IF NOT EXISTS auto_at.api_requests_mv
TO auto_at.api_requests AS
SELECT * FROM auto_at.kafka_api_requests;
