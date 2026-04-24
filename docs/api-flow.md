# Luồng API — Request / Response

## 1. Tổng quan các nhóm endpoint

```mermaid
mindmap
  root((Auto-AT API\n/api/v1))
    Pipeline Templates
      GET /pipeline-templates
      POST /pipeline-templates
      GET /{id}
      PUT /{id}
      DELETE /{id}
      POST /{id}/clone
      POST /{id}/archive
      POST /{id}/validate
      GET /{id}/export
      POST /import
    Pipeline Runs
      POST /pipeline/runs
      GET /pipeline/runs
      GET /pipeline/runs/{id}
      DELETE /pipeline/runs/{id}
      GET /runs/{id}/results
      GET /runs/{id}/results/{node_id}
      POST /runs/{id}/pause
      POST /runs/{id}/resume
      POST /runs/{id}/cancel
      GET /runs/{id}/export/html
      GET /runs/{id}/export/docx
    Admin
      LLM Profiles
        GET /admin/llm-profiles
        POST /admin/llm-profiles
        PUT /{id}
        DELETE /{id}
        POST /{id}/set-default
        POST /{id}/test
      Agent Configs
        GET /admin/agent-configs
        POST /admin/agent-configs
        PUT /{agent_id}
        DELETE /{agent_id}
        POST /{agent_id}/reset
        POST /reset-all
    Chat
      GET /chat/profiles
      POST /chat/send SSE
    WebSocket
      WS /ws/pipeline/{run_id}
```

---

## 2. Luồng tạo và theo dõi Pipeline Run

```mermaid
sequenceDiagram
    participant UI as Frontend
    participant API as FastAPI
    participant DB as MongoDB
    participant BG as Background Task
    participant WS as WebSocket

    UI->>API: POST /api/v1/pipeline/runs\nFormData{file, template_id, llm_profile_id?}
    API->>DB: validate template exists
    API->>API: save uploaded file → uploads/{run_id}/
    API->>DB: create PipelineRunDocument\n{run_id, status:pending, template_id, ...}
    API-->>UI: 201 {run_id, status:"pending"}

    UI->>WS: WS connect /ws/pipeline/{run_id}
    WS-->>UI: connection accepted

    API->>BG: asyncio.create_task(_background_run)
    note over BG: runs independently

    BG->>WS: emit run.started
    WS-->>UI: {"event_type":"run.started", "data":{...}}

    loop mỗi layer
        BG->>WS: emit layer.started {layer_index, nodes[]}
        WS-->>UI: update UI

        loop mỗi node trong layer (song song)
            BG->>WS: emit node.started {node_id, label}
            WS-->>UI: node spinner
            BG->>BG: execute crew (LLM calls...)
            BG->>DB: save_node_result
            BG->>WS: emit node.completed {node_id, duration_ms}
            WS-->>UI: node ✓
        end

        BG->>WS: emit layer.completed
    end

    BG->>WS: emit run.completed
    WS-->>UI: run status = completed

    UI->>API: GET /api/v1/pipeline/runs/{run_id}
    API->>DB: fetch run + results
    API-->>UI: full run details + node outputs
```

---

## 3. Luồng quản lý LLM Profile

```mermaid
flowchart TD
    A["POST /admin/llm-profiles\n{name, provider, model, api_key, ...}"]
    B["Validate: name unique?"]
    C["409 Conflict"]
    D["Encrypt api_key nếu ENCRYPT_API_KEYS=true"]
    E["Insert LLMProfileDocument vào MongoDB"]
    F["201 {id, name, provider, model, is_default}"]

    A --> B
    B -- Đã tồn tại --> C
    B -- Unique --> D --> E --> F

    G["POST /admin/llm-profiles/{id}/set-default"]
    H["Unset is_default của profile hiện tại"]
    I["Set is_default=true cho profile {id}"]
    J["200 OK"]

    G --> H --> I --> J

    K["POST /admin/llm-profiles/{id}/test\n{test_prompt?}"]
    L["Build LLM via LLMFactory\nGọi probe prompt"]
    M["200 {latency_ms, tokens_used, model}"]
    N["422 {error: 'LLM unreachable'}"]

    K --> L
    L -- success --> M
    L -- fail --> N

    style C fill:#fee2e2,stroke:#ef4444
    style N fill:#fee2e2,stroke:#ef4444
    style F fill:#dcfce7,stroke:#22c55e
    style M fill:#dcfce7,stroke:#22c55e
```

---

## 4. Luồng Chat SSE

```mermaid
sequenceDiagram
    participant UI as Frontend
    participant API as FastAPI /chat/send
    participant LLM as LLM Provider

    UI->>API: POST /api/v1/chat/send\n{messages[], llm_profile_id?, system_prompt?}
    API->>API: resolve LLM profile\n(llm_profile_id → default profile)
    API->>LLM: streaming request

    loop stream chunks
        LLM-->>API: token chunk
        API-->>UI: SSE: data: {"type":"chunk","content":"..."}
    end

    LLM-->>API: stream done
    API-->>UI: SSE: data: {"type":"done"}
    API-->>UI: close stream

    note over UI: Content-Type: text/event-stream
```

---

## 5. Luồng Export Report

```mermaid
flowchart LR
    A["GET /pipeline/runs/{id}/export/html\nor /export/docx"]
    B["Fetch PipelineRunDocument"]
    C{"Status = completed?"}
    D["404 / 400 — run chưa hoàn thành"]
    E["Fetch tất cả PipelineResultDocument\ncủa run này"]

    F1["ExportService.export_html()\nJinja2 template render"]
    F2["ExportService.export_docx()\nDocxReportBuilder\npython-docx"]

    G1["StreamingResponse\nContent-Type: text/html"]
    G2["StreamingResponse\nContent-Type: application/vnd.openxmlformats..."]

    A --> B --> C
    C -- Không --> D
    C -- Có --> E
    E --> F1 --> G1
    E --> F2 --> G2

    style D fill:#fee2e2,stroke:#ef4444
    style G1 fill:#dcfce7,stroke:#22c55e
    style G2 fill:#dcfce7,stroke:#22c55e
```

---

## 6. WebSocket event types

```mermaid
graph LR
    subgraph RunEvents["Run Events"]
        R1["run.started\n{run_id, template_id,\ntotal_nodes, total_layers}"]
        R2["run.completed\n{run_id, duration_seconds}"]
        R3["run.failed\n{run_id, error, failed_node}"]
        R4["run.paused\n{run_id}"]
        R5["run.resumed\n{run_id}"]
        R6["run.cancelled\n{run_id}"]
    end

    subgraph LayerEvents["Layer Events"]
        L1["layer.started\n{layer_index, nodes[]}"]
        L2["layer.completed\n{layer_index}"]
    end

    subgraph NodeEvents["Node Events"]
        N1["node.started\n{node_id, node_type,\nlabel, layer_index}"]
        N2["node.completed\n{node_id, duration_ms,\noutput_preview}"]
        N3["node.failed\n{node_id, error_detail,\nretry_attempt, will_retry}"]
    end

    WS["WS /ws/pipeline/{run_id}"] --> RunEvents
    WS --> LayerEvents
    WS --> NodeEvents
```
