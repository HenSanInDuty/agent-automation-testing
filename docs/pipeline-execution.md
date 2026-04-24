# Luồng thực thi Pipeline (DAG)

## 1. Luồng tổng quan — từ API call đến kết quả

```mermaid
flowchart TD
    A["POST /api/v1/pipeline/runs\n{template_id, file, llm_profile_id?}"]
    B["Tạo PipelineRunDocument\nstatus = pending"]
    C["Lưu file upload → uploads/{run_id}/"]
    D["asyncio.create_task\n_run_dag_pipeline_background()"]
    E["DAGPipelineRunner(run_id, template, llm_profile_id)"]
    F["DAGResolver.validate(template)"]
    G{DAG hợp lệ?}
    H["Lỗi: status = failed\nDAGValidationError"]
    I["DAGResolver.get_execution_layers()\ntopological sort → [[layer0], [layer1], ...]"]
    J["Update run: status = running\nEmit run.started → WS + Kafka"]
    K["Vòng lặp qua từng layer"]
    L{"Có signal\npause/cancel?"}
    M["Pause: chờ RESUME signal\nhết PAUSE_TIMEOUT → cancel"]
    N["Cancel: status = cancelled\nEmit run.cancelled"]
    O["asyncio.gather(*node_tasks)\nthực thi tất cả nodes trong layer song song"]
    P["Node thực thi thành công"]
    Q["Node thất bại\nretry_count > 0?"]
    R["Exponential backoff\n5s → 10s → 20s..."]
    S["Hết retry: status = failed\nEmit run.failed → WS + Kafka"]
    T{"Còn layer\ntiếp theo?"}
    U["Collect OUTPUT node result\nUpdate run: status = completed\nEmit run.completed → WS + Kafka"]

    A --> B --> C --> D --> E --> F --> G
    G -- Không --> H
    G -- Có --> I --> J --> K --> L
    L -- pause --> M --> L
    L -- cancel --> N
    L -- không --> O --> P --> T
    O --> Q -- Có retry --> R --> O
    Q -- Không --> S
    T -- Có --> K
    T -- Không --> U

    style H fill:#fee2e2,stroke:#ef4444
    style N fill:#fee2e2,stroke:#ef4444
    style S fill:#fee2e2,stroke:#ef4444
    style U fill:#dcfce7,stroke:#22c55e
```

---

## 2. Thực thi từng node (AgentNode)

```mermaid
flowchart TD
    START["_run_agent_node(node_config, parent_outputs)"]
    MERGE["Merge parent_outputs + document_content\nvào input context"]
    EMIT_START["Emit node.started\n→ WS + Kafka node_events"]
    BUILD_AGENT["AgentFactory.build(agent_id, override_profile_id)"]
    BUILD_CREW["Build CrewAI Crew\n(agent + task)"]
    TIMEOUT["asyncio.wait_for(\n  asyncio.to_thread(crew.kickoff),\n  timeout_seconds\n)"]
    LLM_CALL["LLM API call\n(LiteLLM → Provider)"]
    TRACK["Ghi lại:\n- latency_ms\n- prompt/completion/total tokens\n- model, provider"]
    SUCCESS["Lưu output vào _node_outputs[node_id]\nEmit node.completed → WS + Kafka"]
    LLM_EMIT["Emit llm_call → Kafka\n(latency, tokens, model, success)"]
    FAIL["Emit node.failed → WS + Kafka\n_llm_success = False\nerror_type, error_message"]
    RETRY_CHECK{"will_retry?"}
    RAISE["Re-raise exception\n→ runner xử lý retry"]

    START --> MERGE --> EMIT_START --> BUILD_AGENT --> BUILD_CREW --> TIMEOUT
    TIMEOUT -->|success| LLM_CALL --> TRACK --> SUCCESS --> LLM_EMIT
    TIMEOUT -->|timeout/exception| FAIL --> RETRY_CHECK
    RETRY_CHECK -- có --> RAISE
    RETRY_CHECK -- không --> LLM_EMIT

    style SUCCESS fill:#dcfce7,stroke:#22c55e
    style FAIL fill:#fee2e2,stroke:#ef4444
```

---

## 3. DAG Resolver — Validation & Layer computation

```mermaid
flowchart LR
    subgraph INPUT["Input: PipelineTemplate"]
        N["nodes[]"]
        E["edges[]"]
    end

    subgraph VALIDATION["Validation (tuần tự)"]
        V1["✓ Đúng 1 node INPUT"]
        V2["✓ Đúng 1 node OUTPUT"]
        V3["✓ Tất cả edge refs hợp lệ"]
        V4["✓ Không có cycle\n(Kahn's algorithm)"]
        V5["✓ Tất cả nodes reachable\ntừ INPUT (DFS)"]
        V1 --> V2 --> V3 --> V4 --> V5
    end

    subgraph LAYERS["Layer Computation (Longest Path)"]
        L0["Layer 0: [INPUT]"]
        L1["Layer 1: [A, B] ← no unresolved deps"]
        L2["Layer 2: [C] ← depends on A+B"]
        LN["Layer N: [OUTPUT]"]
        L0 --> L1 --> L2 --> LN
    end

    INPUT --> VALIDATION --> LAYERS
    VALIDATION -->|"DAGValidationError"| ERR["Run fails immediately"]

    style ERR fill:#fee2e2,stroke:#ef4444
```

---

## 4. Cơ chế Retry và Backoff

```mermaid
sequenceDiagram
    participant R as DAGRunner
    participant N as Node Execution
    participant LLM as LLM Provider

    R->>N: execute attempt #1
    N->>LLM: kickoff()
    LLM-->>N: ❌ timeout / error
    N-->>R: exception (retry_attempt=1, will_retry=true)
    R->>R: emit node.failed + will_retry=true
    R->>R: wait 5s (backoff)

    R->>N: execute attempt #2
    N->>LLM: kickoff()
    LLM-->>N: ❌ error again
    N-->>R: exception (retry_attempt=2, will_retry=true)
    R->>R: wait 10s (backoff × 2)

    R->>N: execute attempt #3
    N->>LLM: kickoff()
    LLM-->>N: ✅ result
    N-->>R: output_data
    R->>R: emit node.completed
    note over R: run tiếp tục
```

---

## 5. Luồng Pause / Resume / Cancel

```mermaid
stateDiagram-v2
    [*] --> pending: POST /pipeline/runs
    pending --> running: DAGRunner starts
    running --> paused: POST /runs/{id}/pause\n(checked between layers)
    paused --> running: POST /runs/{id}/resume
    paused --> cancelled: PAUSE_TIMEOUT exceeded\nor POST /runs/{id}/cancel
    running --> cancelled: POST /runs/{id}/cancel
    running --> completed: All layers done ✓
    running --> failed: Node fails (no retry left)
    completed --> [*]
    failed --> [*]
    cancelled --> [*]
```

---

## 6. Luồng dữ liệu giữa các node

```mermaid
graph LR
    subgraph Template["Pipeline Template mặc định"]
        INPUT["INPUT node\n(seed document)"]
        INGEST["IngestionCrew\nRequirementItem[]"]
        TESTCASE["TestcaseCrew\nTestCase[]"]
        EXECUTE["ExecutionCrew\nTestExecutionResult[]"]
        REPORT["ReportingCrew\nPipelineReport"]
        OUTPUT["OUTPUT node\n(collect result)"]

        INPUT -->|"document_content\ndocument_name"| INGEST
        INGEST -->|"requirements: RequirementItem[]"| TESTCASE
        TESTCASE -->|"test_cases: TestCase[]\ncoverage_summary"| EXECUTE
        EXECUTE -->|"execution_results: TestExecutionResult[]\nexecution_summary"| REPORT
        REPORT -->|"pipeline_report: PipelineReport"| OUTPUT
    end

    subgraph Storage["MongoDB"]
        RUN[("PipelineRunDocument\nrun_id, status,\nnode_statuses{}")]
        RESULT[("PipelineResultDocument\nrun_id + node_id\noutput_data JSON")]
    end

    INGEST -->|"save_node_result"| RESULT
    TESTCASE -->|"save_node_result"| RESULT
    EXECUTE -->|"save_node_result"| RESULT
    REPORT -->|"save_node_result"| RESULT
    OUTPUT -->|"update status"| RUN
```
