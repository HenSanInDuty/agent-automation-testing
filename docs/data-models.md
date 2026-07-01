# Mô hình dữ liệu MongoDB

## 1. ER Diagram — Tất cả collections

```mermaid
erDiagram
    UserDocument {
        ObjectId id PK
        string username UK
        string hashed_password
        string full_name
        string role "admin|qa|viewer"
        bool is_active
        datetime created_at
        datetime updated_at
    }

    LLMProfileDocument {
        ObjectId id PK
        string name UK
        string provider "openai|anthropic|ollama|azure_openai|groq|huggingface|lm_studio"
        string model "e.g. gpt-4o"
        string api_key "encrypted nếu ENCRYPT_API_KEYS=true"
        string base_url "optional — Ollama, LM Studio, Azure"
        float temperature "default 0.1"
        int max_tokens "default 2048"
        bool is_default "exactly 1 profile is_default=true"
        datetime created_at
        datetime updated_at
    }

    AgentConfigDocument {
        ObjectId id PK
        string agent_id UK "slugified name"
        string display_name
        string role
        string goal
        string backstory
        string stage "ingestion|testcase|execution|reporting|custom"
        string llm_profile_id FK "→ LLMProfileDocument (ObjectId string)"
        string[] tool_names "tool slugs: api_runner, document_parser, ..."
        bool enabled
        bool verbose
        int max_iter "default 5"
        bool is_custom "true = user-created, can delete"
        datetime created_at
        datetime updated_at
    }

    StageConfigDocument {
        ObjectId id PK
        string stage_id "compound UK with template_id"
        string display_name
        string description
        int order "sort order in UI"
        string color "hex color"
        string icon "Lucide icon name"
        bool enabled
        bool is_builtin
        string template_id FK "optional — linked template"
        datetime created_at
        datetime updated_at
    }

    PipelineTemplateDocument {
        ObjectId id PK
        string template_id UK "URL-safe slug"
        string name
        string description
        int version "auto-incremented on each save"
        PipelineNodeConfig[] nodes "embedded array"
        PipelineEdgeConfig[] edges "embedded array"
        bool is_builtin "built-in cannot be deleted"
        bool is_archived
        string[] tags
        string thumbnail "Base64 or URL"
        datetime created_at
        datetime updated_at
    }

    PipelineNodeConfig {
        string node_id UK "within template, a-z0-9_-"
        string node_type "input|output|agent|pure_python"
        string agent_id FK "→ AgentConfigDocument.agent_id"
        string label
        string description
        float position_x
        float position_y
        int timeout_seconds "10–7200, default 300"
        int retry_count "0–5"
        bool enabled
        object config_overrides "llm_profile_id override, max_iter, etc."
        string stage_id FK "→ StageConfigDocument.stage_id (within pipeline)"
    }

    PipelineEdgeConfig {
        string edge_id UK
        string source_node_id FK "→ PipelineNodeConfig.node_id"
        string target_node_id FK "→ PipelineNodeConfig.node_id"
        string source_handle "named output port"
        string target_handle "named input port"
        string label
        bool animated
    }

    PipelineRunDocument {
        ObjectId id PK
        string run_id UK "UUID"
        string template_id FK "→ PipelineTemplateDocument.template_id"
        string status "pending|running|paused|completed|failed|cancelled"
        string document_name
        string file_path "MinIO object key (V3)"
        string llm_profile_id FK "→ LLMProfileDocument"
        object template_snapshot "frozen copy of template at run time"
        string[] completed_nodes
        string[] failed_nodes
        object node_statuses "node_id → waiting|running|completed|failed|skipped"
        list execution_layers "[[node_id, ...], ...]"
        float duration_seconds
        string error_message
        datetime started_at
        datetime completed_at
        datetime created_at
        datetime updated_at
    }

    PipelineResultDocument {
        ObjectId id PK
        string run_id FK "→ PipelineRunDocument.run_id"
        string node_id FK "→ PipelineNodeConfig.node_id"
        string agent_id FK "→ AgentConfigDocument.agent_id (if AGENT type)"
        string result_type "node_output|error|metadata"
        any output "JSON — varies by node type (native BSON)"
        object input_data "what input the node received"
        string status "completed|failed|skipped"
        string error_message
        float duration_seconds
        datetime started_at
        datetime completed_at
        datetime created_at
    }

    LLMProfileDocument ||--o{ AgentConfigDocument : "referenced by agent_id.llm_profile_id"
    PipelineTemplateDocument ||--|{ PipelineNodeConfig : "contains nodes[]"
    PipelineTemplateDocument ||--o{ PipelineEdgeConfig : "contains edges[]"
    PipelineNodeConfig }|--o| AgentConfigDocument : "agent_id FK"
    PipelineNodeConfig }o--o| StageConfigDocument : "stage_id FK (optional)"
    PipelineEdgeConfig }|--|| PipelineNodeConfig : "source_node_id"
    PipelineEdgeConfig }|--|| PipelineNodeConfig : "target_node_id"
    PipelineTemplateDocument ||--o{ PipelineRunDocument : "template_id FK"
    PipelineRunDocument ||--|{ PipelineResultDocument : "run_id FK"
    LLMProfileDocument ||--o{ PipelineRunDocument : "llm_profile_id FK"
    StageConfigDocument }o--o| PipelineTemplateDocument : "template_id optional"
```

---

## 2. Sơ đồ luồng dữ liệu qua các collections

```mermaid
flowchart LR
    subgraph Auth["🔐 Auth"]
        USR["users\n{username, role,\nhashed_password}"]
    end

    subgraph Config["📋 Config (seeded on startup)"]
        LLP["llm_profiles\n{is_default: true}"]
        ACP["agent_configs\n{is_custom: false,\ntool_names[]}"]
        SCP["stage_configs\n(agent grouping)"]
    end

    subgraph Templates["📐 Templates"]
        PT["pipeline_templates\n{nodes[], edges[],\nversion: int}"]
    end

    subgraph Runtime["🚀 Runtime (per run)"]
        PR["pipeline_runs\n{run_id, status,\nnode_statuses{},\nexecution_layers,\ntemplate_snapshot}"]
        RES["pipeline_results\n{run_id + node_id\noutput JSON,\ninput_data, duration_seconds}"]
    end

    subgraph MinIO["🗄️ MinIO (S3)"]
        UP["uploads/{run_id}/{filename}\n(original document)"]
        PW["runs/{run_id}/playwright/{filename}\n(generated test files)"]
    end

    LLP -->|"resolved by LLMFactory"| PT
    ACP -->|"nodes reference agent_id"| PT
    PT -->|"template_id + snapshot"| PR
    PR -->|"run_id"| RES
    PR -->|"file_path"| UP
    RES -->|"playwright artifacts"| PW

    style Auth fill:#fce7f3,stroke:#ec4899
    style Config fill:#dbeafe,stroke:#3b82f6
    style Templates fill:#fef3c7,stroke:#f59e0b
    style Runtime fill:#dcfce7,stroke:#22c55e
    style MinIO fill:#f3e8ff,stroke:#a855f7
```

---

## 3. Output schema của từng node type

```mermaid
graph TB
    subgraph IngestionOutput["IngestionCrew output"]
        I1["RequirementItem[]\n- id\n- title\n- description\n- priority\n- category\n- source_chunk"]
    end

    subgraph TestcaseOutput["TestCaseOutput (includes adaptive planning audit)"]
        T0["ComplexityDecision\n- score, signals{}, agent_count (1-5)\n- selected_roles[], rationale"]
        T0A["SourceObligation[]\n- id, kind, description, required\n(normalized from doc)"]
        T0B["ReviewGateSummary\n- coverage_threshold_percent\n- iterations[ReviewIteration]\n- selected_iteration, coverage_gate_exhausted\n- final_verdict (approve|revise|reject)\n- warnings[]"]
        T1["TestCase[]\n- id, title, description, steps[]\n- expected_result, priority, category\n- obligation_ids[] (traceability)\n- source_role, is_assumption\n- test_level (unit|integration|contract|e2e)"]
        T2["CoverageSummary + extensions\n- total_requirements, covered_requirements\n- coverage_percent, uncovered_ids[]\n- assumptions[], duplicates_removed count\n- planner_warnings[]"]
        T0 --> T1
        T0A --> T1
        T0B --> T2
    end

    subgraph ExecutionOutput["ExecutionCrew output"]
        E1["TestExecutionResult[]\n- test_case_id\n- status: pass|fail|skip|error\n- actual_result\n- error_message\n- execution_time_ms\n- api_response{}"]
        E2["ExecutionSummary\n- total_tests\n- pass/fail/skip/error counts\n- pass_rate\n- environment"]
    end

    subgraph ReportOutput["ReportingCrew output"]
        R1["PipelineReport\n- coverage_analysis\n- risk_assessment\n- root_cause_analysis\n- executive_summary\n- recommendations[]"]
    end

    IngestionOutput -->|"requirements[]"| TestcaseOutput
    TestcaseOutput -->|"test_cases[]"| ExecutionOutput
    ExecutionOutput -->|"results[]"| ReportOutput
```

## 4. Adaptive Planning & Review Gate Schemas (Phase 3–5)

The `automation-testing-api` pipeline (Phases 3–5) adds traceability and bounded review:

### ParsedSpec (`md_spec_parsed` — multi-endpoint)
`md_api_spec_verifier` emits this contract; it is carried forward to every
downstream node (test-case generator, complexity, planner prompts, runner).

```python
base_url: str                       # spec-level, shared by all endpoints
endpoints: list[ParsedEndpointSpec] # one entry per declared endpoint
headers: list[ParsedHeader]         # spec-level (shared)

# ParsedEndpointSpec
endpoint: ParsedEndpoint            # method, path, auth
request: ParsedRequest              # content_type, body_fields, raw_body_schema
responses: list[ParsedResponse]     # status_code, description, payload_preview
response_body: str
```

- Every declared endpoint is parsed (a document with 8 endpoints yields
  `len(endpoints) == 8`). The parser previously kept only the first endpoint,
  which produced a tiny suite and a falsely-100% coverage.
- Backward-compat: read-only `.endpoint`/`.request`/`.responses`/`.response_body`
  properties resolve to `endpoints[0]`, and the model folds legacy single-endpoint
  constructor kwargs into a one-element `endpoints` list.
- Obligation traversal order (determinism contract): spec-level headers ONCE,
  then per endpoint in document order (responses → auth → fields/rules).

### SourceObligation (per-document normalized)
```python
id: str              # OBL-001, OBL-002, … (document-scoped)
kind: str            # response | header | auth | field | rule | parameter
description: str     # Full obligation text
evidence: str        # Source quote or reference
required: bool       # True = mandatory for coverage; False = optional
```

### ComplexityDecision (per-run deterministic)
```python
score: int                          # Raw signal count (endpoints + params + responses)
signals: dict[str, int]             # Breakdown: {"endpoints": 5, "parameters": 8, …}
agent_count: int                    # Selected planner count: 1–5 (deterministic)
selected_roles: list[PlannerRole]   # [PlannerRole.POSITIVE, .AUTH_SECURITY, …]
rationale: str                      # Why this count was selected
# PlannerRole enum: POSITIVE | NEGATIVE_SCHEMA | AUTH_SECURITY | BOUNDARY_DATA | RESILIENCE_IDEMPOTENCY
```

### ReviewIteration (per planning attempt)
```python
iteration: int                           # 0 = baseline, 1+ = retry after feedback
case_count: int                          # Selected test cases in this iteration
coverage: CoverageReport                 # Numeric obligation-to-case mapping
review: SeniorReviewResult               # Qualitative verdict + feedback
accepted: bool                           # True when gate approved this iteration
feedback_applied: str                    # Feedback fed INTO this iteration (empty for baseline)
```

### CoverageReport (deterministic, never LLM-scored)
```python
total_required: int                      # Count of SourceObligation(required=true)
covered_required: int                    # Count of covered required obligations
coverage_percent: float                  # Computed: covered / total * 100
gaps: list[CoverageGap]                  # Uncovered required obligations
unknown_obligation_ids: list[str]        # Obligation IDs cited by cases but not in inventory
# Formula: vacuously 100% if total_required=0; otherwise [0, 100]
```

### ReviewGateSummary (final outcome + audit)
```python
coverage_threshold_percent: float        # Config: pass on >= (default 90)
max_review_iterations: int               # Config: max retries (default 3, range 0–5)
continue_on_review_exhaustion: bool      # Config: execute plan even if exhausted (default true)
iterations: list[ReviewIteration]        # Full audit trail (persisted in MongoDB)
selected_iteration: int                  # Which iteration was selected (0 = baseline)
final_coverage_percent: float            # Coverage of selected iteration
final_verdict: ReviewVerdict             # APPROVE | REVISE | REJECT
accepted: bool                           # True if gate passed before exhaustion
coverage_gate_exhausted: bool            # True if retries exhausted (best plan selected + warning)
warnings: list[str]                      # Visible warnings (e.g. "exhausted retries", "reviewer mocked")
# ReviewVerdict enum: APPROVE | REVISE | REJECT (senior reviewer's verdict; never blocks numeric coverage)
```

### TestCase additions (traceability)
```python
obligation_ids: list[str]                # OBL-IDs this case satisfies
source_role: str                         # "baseline" | "positive" | "negative_schema" | …
is_assumption: bool                      # True = invented edge case (not in source doc)
test_level: TestLevel                    # unit | integration | contract | e2e (enum)
executable: bool                         # True = can run in ExecutionCrew; False = skipped
depends_on: list[str]                    # TC ids that must run first (chaining order)
extract: dict[str, str]                  # variable_name → response body field to capture
```

**Request chaining.** Path-param item endpoints (`/api/tasks/:id`) do not hardcode an
id. The collection's POST create case declares `extract={"tasks_id": "id"}`; the item
case references `{tasks_id}` inside `api_endpoint` and lists the create in `depends_on`.
The runner orders producers first, captures `id` from the create's response into a
run-scoped context, and substitutes `{tasks_id}` at execution time. If the create fails
(no id captured), dependents are skipped with reason `Unresolved chained value(s): …`.
The not-found (404) case stays independent and uses a deliberately missing id.

### TestExecutionResult additions (traceability)
```python
obligation_ids: list[str]                # Obligations this result covers (from source case)
# Allows MongoDB to reconstruct: which test case (and its obligations) produced each result
```
