# Observability — Kafka + ClickHouse

## 1. Kiến trúc observability tổng thể

```mermaid
flowchart LR
    subgraph APP["🖥️ Auto-AT Backend"]
        MW["ObservabilityMiddleware\n(HTTP layer)"]
        DAG["DAGPipelineRunner\n(pipeline events)"]
        NODE["Node Execution\n(node events + LLM calls)"]
    end

    subgraph KAFKA["📨 Apache Kafka 3.9.0 (KRaft)"]
        direction TB
        T1["auto_at.api_requests"]
        T2["auto_at.pipeline_events"]
        T3["auto_at.node_events"]
        T4["auto_at.llm_calls"]
    end

    subgraph CLICKHOUSE["🗄️ ClickHouse 24.8"]
        direction TB
        subgraph KE["Kafka Engine Tables (buffer)"]
            KT1["kafka_api_requests"]
            KT2["kafka_pipeline_events"]
            KT3["kafka_node_events"]
            KT4["kafka_llm_calls"]
        end
        subgraph MV["Materialized Views (ETL)"]
            MV1["mv_api_requests"]
            MV2["mv_pipeline_events"]
            MV3["mv_node_events"]
            MV4["mv_llm_calls"]
        end
        subgraph MT["MergeTree Tables (query)"]
            MT1["api_requests\n(sharded by request_id)"]
            MT2["pipeline_events\n(sharded by run_id)"]
            MT3["node_events\n(sharded by run_id)"]
            MT4["llm_calls\n(sharded by run_id)"]
        end
    end

    KAFKAUI["kafka-ui\nport :8080\nbrowse topics"]

    MW -->|"fire-and-forget\naiokafka"| T1
    DAG -->|"fire-and-forget\naiokafka"| T2
    NODE -->|"fire-and-forget\naiokafka"| T3
    NODE -->|"fire-and-forget\naiokafka"| T4

    T1 --> KT1 --> MV1 --> MT1
    T2 --> KT2 --> MV2 --> MT2
    T3 --> KT3 --> MV3 --> MT3
    T4 --> KT4 --> MV4 --> MT4

    KAFKAUI -->|"browse"| T1
    KAFKAUI -->|"browse"| T2
    KAFKAUI -->|"browse"| T3
    KAFKAUI -->|"browse"| T4

    style APP fill:#dbeafe,stroke:#3b82f6
    style KAFKA fill:#fef3c7,stroke:#f59e0b
    style CLICKHOUSE fill:#f0fdf4,stroke:#16a34a
```

---

## 2. EventBus — luồng emit

```mermaid
flowchart TD
    CALL["Caller code\n(DAGRunner, Middleware)"]
    SYNC["emit_sync(topic_suffix, payload)\n→ fire-and-forget từ sync context"]
    ASYNC["emit(topic_suffix, payload)\n→ await từ async context"]
    CHECK{"KAFKA_ENABLED\n&& _available?"}
    BASE["Merge payload + _base_fields()\n{timestamp, app_version, env, hostname, pid}"]
    SERIALIZE["JSON serialize payload"]
    PRODUCER["AIOKafkaProducer.send(\n  f'{PREFIX}.{topic_suffix}',\n  value=bytes\n)"]
    NOOP["No-op\n(graceful degradation)"]
    ERR["Log warning\n(exception không re-raise)"]

    CALL --> SYNC
    CALL --> ASYNC
    SYNC -->|"asyncio.ensure_future"| ASYNC
    ASYNC --> CHECK
    CHECK -- Có --> BASE --> SERIALIZE --> PRODUCER
    CHECK -- Không --> NOOP
    PRODUCER -->|"exception"| ERR

    style NOOP fill:#f3f4f6,stroke:#9ca3af
    style ERR fill:#fef3c7,stroke:#f59e0b
```

---

## 3. Schema các Kafka topics

### `auto_at.pipeline_events`

| Field | Type | Mô tả |
|-------|------|-------|
| `event_type` | String | `run.started` \| `run.completed` \| `run.failed` \| `run.paused` \| `run.cancelled` |
| `run_id` | String | UUID của pipeline run |
| `template_id` | String | UUID của template |
| `document_name` | String | Tên file upload |
| `total_nodes` | Int32 | Số node trong template |
| `total_layers` | Int32 | Số layer thực thi |
| `duration_seconds` | Float32 | Thời gian tổng (chỉ có khi completed/failed) |
| `error` | String | Error message (nếu failed) |
| `failed_node` | String | node_id fail đầu tiên |
| `data` | String | JSON blob — thông tin bổ sung |
| `app_version` | String | APP_VERSION từ config |
| `env` | String | APP_ENV (development/production) |
| `hostname` | String | Tên máy chủ |
| `pid` | Int32 | Process ID |
| `timestamp` | DateTime | ISO-8601 UTC |

### `auto_at.node_events`

| Field | Type | Mô tả |
|-------|------|-------|
| `event_type` | String | `node.started` \| `node.completed` \| `node.failed` |
| `run_id` | String | UUID của run |
| `node_id` | String | node_id trong template |
| `node_type` | String | `agent` \| `input` \| `output` \| `pure_python` |
| `agent_id` | String | agent_id (nếu là agent node) |
| `label` | String | Display label của node |
| `status` | String | `running` \| `done` \| `error` |
| `duration_ms` | Int64 | Thời gian thực thi node (ms) |
| `retry_attempt` | UInt8 | Lần retry (0 = lần đầu) |
| `will_retry` | UInt8 | 1 nếu sẽ retry |
| `error_detail` | String | Chi tiết lỗi |
| `output_preview` | String | 300 ký tự đầu của output |
| `parent_node_ids` | String | JSON array node cha |
| `app_version`, `env`, `hostname`, `pid`, `timestamp` | — | Base fields |

### `auto_at.llm_calls`

| Field | Type | Mô tả |
|-------|------|-------|
| `run_id` | String | UUID của run |
| `node_id` | String | node đang gọi LLM |
| `agent_id` | String | agent đang gọi |
| `model` | String | Full model string, e.g. `openai/gpt-4o` |
| `provider` | String | Phần prefix trước `/`, e.g. `openai` |
| `latency_ms` | Int64 | Thời gian chờ LLM response (ms) |
| `prompt_tokens` | Int32 | Tokens input |
| `completion_tokens` | Int32 | Tokens output |
| `total_tokens` | Int32 | Tổng tokens |
| `success` | UInt8 | 1 = OK, 0 = error |
| `error_type` | String | Exception class name |
| `error_message` | String | Exception message |
| `task_description_len` | Int32 | Độ dài task description (chars) |
| `task_description_preview` | String | 200 ký tự đầu của task |
| `app_version`, `env`, `hostname`, `pid`, `timestamp` | — | Base fields |

### `auto_at.api_requests`

| Field | Type | Mô tả |
|-------|------|-------|
| `method` | String | HTTP method (GET/POST/...) |
| `path` | String | Request path |
| `status_code` | Int32 | HTTP status code |
| `duration_ms` | Int64 | Thời gian xử lý (ms) |
| `client_ip` | String | IP client (X-Forwarded-For first) |
| `user_agent` | String | User-Agent header |
| `request_id` | String | X-Request-ID hoặc UUID4 generated |
| `content_length` | Int64 | Request body size |
| `app_version`, `env`, `hostname`, `pid`, `timestamp` | — | Base fields |

---

## 4. ClickHouse — schema pattern

```mermaid
flowchart LR
    KAFKA_TOPIC["Kafka topic\nauto_at.llm_calls"]

    KAFKA_ENGINE["kafka_llm_calls\nKafka Engine\n(broker='kafka:9092'\nformat=JSONEachRow)"]

    MAT_VIEW["mv_llm_calls\nMATERIALIZED VIEW\nINSERT INTO llm_calls\nSELECT FROM kafka_llm_calls"]

    MERGE_TREE["llm_calls\nReplacingMergeTree\nPARTITION BY toYYYYMM(timestamp)\nORDER BY (run_id, node_id, timestamp)"]

    QUERY["ClickHouse Query\nSELECT avg(latency_ms), sum(total_tokens)\nFROM llm_calls\nWHERE toDate(timestamp) = today()"]

    KAFKA_TOPIC -->|"poll"| KAFKA_ENGINE
    KAFKA_ENGINE --> MAT_VIEW --> MERGE_TREE
    MERGE_TREE --> QUERY

    note1["Pattern này áp dụng\ncho tất cả 4 topics"]

    style QUERY fill:#dcfce7,stroke:#22c55e
```

---

## 5. Graceful degradation

```mermaid
stateDiagram-v2
    [*] --> starting: app startup

    starting --> connected: Kafka reachable\n_available = True
    starting --> degraded: Kafka unreachable\n_available = False\n(log warning)

    connected --> emitting: emit(topic, payload)
    emitting --> connected: success

    emitting --> degraded: producer exception\n_available = False

    degraded --> noop: emit() called\n→ silent no-op

    connected --> shutdown: app shutdown\nflush + close producer
    degraded --> shutdown: app shutdown\n(nothing to close)

    note: Pipeline execution KHÔNG bị block\nkhi Kafka unavailable
```
