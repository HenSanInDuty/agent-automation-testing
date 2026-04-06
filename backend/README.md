# Auto-AT Backend

> **Auto-AT** — Multi-Agent Automated Testing System
> FastAPI REST/WebSocket server · DAG Pipeline Engine · CrewAI agents

---

## 🆕 V3 Changes

Auto-AT V3 replaces the linear stage-based pipeline with a fully visual, **DAG-driven** pipeline system:

| # | Feature | Summary |
|---|---------|---------|
| 1 | **DAG Pipeline Templates** | The stage-based system is superseded by reusable, versioned Pipeline Templates — directed acyclic graphs (DAGs) of typed agent nodes. Templates are stored in MongoDB, versioned, and support clone, archive, export, and import operations. |
| 2 | **Visual Pipeline Builder** | New React Flow–based frontend lets users drag-and-drop agents from the catalog onto a canvas, connect them with directed edges, and configure node properties — all without writing code. |
| 3 | **DAG Pipeline Runner** | `dag_pipeline_runner.py` replaces `pipeline_runner.py`. The `DAGResolver` computes independent execution layers via topological sort; the runner then executes each layer's nodes concurrently via `asyncio.gather`. |
| 4 | **Pipeline Template CRUD API** | Ten new REST endpoints under `/api/v1/pipeline-templates` for the full template lifecycle: create, read, update, delete, clone, archive, validate DAG integrity, and export/import JSON. |
| 5 | **`/admin/stage-configs` Deprecated** | All stage-config endpoints return `410 Gone` with a migration message. Pipeline stages are replaced by DAG template nodes. |
| 6 | **Migration Script** | `scripts/migrate_v2_to_v3.py` converts existing V2 stage configurations into a default Pipeline Template so that no data is lost on upgrade. |

**Key structural changes (V3):**

| Removed / Superseded | Added / Replaces |
|----------------------|-----------------|
| `/api/v1/admin/stage-configs` endpoints | `/api/v1/pipeline-templates` endpoints |
| `stage_configs` MongoDB collection | `pipeline_templates` MongoDB collection |
| `core/pipeline_runner.py` (sequential N-stage) | `core/dag_pipeline_runner.py` (parallel layers) |
| — | `core/dag_resolver.py` (topological sort + cycle detection) |
| `stage` as a required field on `AgentConfig` | Agents become a free catalog; placed in pipelines via nodes |

---

## 🆕 V2 Changes

Auto-AT V2 introduced seven major backend enhancements on top of the V1 pipeline:

| # | Feature | Summary |
|---|---------|---------|
| 1 | **Report Export (HTML/DOCX)** | New endpoints to export pipeline run results as styled HTML or DOCX documents. Powered by Jinja2 templates and `python-docx`. |
| 2 | **Per-Stage Results Display** | The `stage.completed` WebSocket event now includes a `summary` payload so the frontend can display results incrementally as each stage finishes. |
| 3 | **Persistent Pipeline Session** | Frontend-only change (Zustand store). No backend modifications required. |
| 4 | **MongoDB Replacing SQLite** | SQLAlchemy + SQLite/PostgreSQL replaced by **Motor** (async driver) + **Beanie** ODM + **MongoDB**. All API handlers are fully `async`. Alembic migrations removed. |
| 5 | **Dynamic Agent Management** | Create and delete custom agents via Admin API. Built-in agents can only be disabled, never deleted. New `is_custom` field on `AgentConfig`. |
| 6 | **Dynamic Stage Configuration** | New `stage_configs` MongoDB collection allowed full CRUD + reorder of pipeline stages. Supported three crew types: `pure_python`, `crewai_sequential`, `crewai_hierarchical`. *(Superseded by Pipeline Templates in V3.)* |
| 7 | **Pause / Resume / Cancel Pipeline** | New `paused` and `cancelled` run statuses. A `SignalManager` checks for signals between stages/layers. Dedicated pause/resume endpoints and new WebSocket events (`run.paused`, `run.resumed`, `run.cancelled`). |

**Key dependency changes (V2):**

| Removed | Added |
|---------|-------|
| `sqlalchemy` 2.x | `motor >= 3.6.0` |
| `alembic` | `beanie >= 1.27.0` |
| | `jinja2 >= 3.1.0` |

---

## Overview

Auto-AT Backend orchestrates a **multi-agent pipeline** that takes a requirements document (PDF, DOCX, XLSX, or TXT) and automatically produces a complete test suite — from requirement parsing all the way through test execution and final reporting.

In **V3** the pipeline is modelled as a **DAG (directed acyclic graph)** of agent nodes. You define the graph visually in the Pipeline Builder, save it as a **Pipeline Template**, and then run it against a document. The DAG runner resolves independent execution layers and processes them concurrently:

```
Upload Document
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       DAG Pipeline Runner (V3)                          │
│                                                                         │
│  Layer 1           Layer 2                   Layer 3       Layer 4      │
│  ┌───────────┐     ┌─────────────────┐       ┌─────────┐  ┌────────┐   │
│  │ Ingestion │────▶│  TestCaseGen    │──┬───▶│Execution│─▶│Report  │   │
│  │  (node)   │     │    (node)       │  │    │  (node) │  │ (node) │   │
│  └───────────┘     └─────────────────┘  │    └─────────┘  └────────┘   │
│                    ┌─────────────────┐  │                               │
│                    │  Custom Agent   │──┘  ← parallel peers in same     │
│                    │    (node)       │       layer run concurrently      │
│                    └─────────────────┘                                   │
└─────────────────────────────────────────────────────────────────────────┘
      │
      ▼
  Results keyed by node_id → PipelineReport
```

Built-in agent implementations (ingestion, testcase, execution, reporting crews) are preserved and used as the **default built-in Pipeline Template**. The REST API exposes pipeline management, real-time WebSocket progress streaming, admin endpoints for configuring LLM profiles and agent catalog, Pipeline Template CRUD, report export, and a streaming chat interface.

---

## Prerequisites

| Tool | Minimum Version | Notes |
|------|----------------|-------|
| Python | 3.11+ | 3.12 recommended |
| [uv](https://github.com/astral-sh/uv) | 0.4+ | Fast Python package manager |
| MongoDB | **7.0+** | Required — introduced in V2, unchanged in V3 |

> **Windows note:** `crewai` depends on `lancedb`. From version `0.30.1` onward, `lancedb`
> dropped Windows (`win_amd64`) wheels — only Linux/macOS builds are published.
> The project therefore pins `lancedb==0.30.0`, which **does** ship a Windows wheel and
> installs cleanly with `uv add "crewai>=1.0.0" "lancedb==0.30.0"`.
> If you upgrade `lancedb` in the future, check the
> [lancedb releases](https://github.com/lancedb/lancedb/releases) page first to confirm
> a Windows wheel is available.
> The `MOCK_CREWS=true` env var is still useful for offline / CI development without a live LLM.

---

## Quick Start

```bash
# 1. Clone and enter the backend directory
cd auto-at/backend

# 2. Install all dependencies (including dev tools)
#    crewai + lancedb==0.30.0 are bundled in the core deps — no extra step needed.
uv sync --group dev

# 3. Copy and configure environment variables
cp .env.example .env
# Edit .env — at minimum set DEFAULT_LLM_API_KEY and MONGODB_URI

# 4. Start MongoDB
#    Option A — Docker (recommended):
docker compose up -d mongodb
#    Option B — local install:
#    Ensure mongod is running on localhost:27017

# 5. (V3 upgrade only) Run the migration script
#    Converts existing V2 stage configs into a default Pipeline Template.
#    Safe to skip on a fresh install — AUTO_SEED handles it automatically.
uv run python scripts/migrate_v2_to_v3.py

# 6. Start the development server (auto-reload)
uv run uvicorn app.main:app --reload --port 8000
```

The API will be available at:
- **REST API:** http://localhost:8000
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **Health check:** http://localhost:8000/health

---

## Environment Variables

Create a `.env` file in the `backend/` directory. All variables are optional and fall back to sensible development defaults.

### Application

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `development` | Runtime environment: `development` \| `production` |
| `APP_PORT` | `8000` | Port the uvicorn server listens on |
| `APP_HOST` | `0.0.0.0` | Bind address |
| `ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:3001` | Comma-separated CORS allowed origins |

### Database (MongoDB)

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGODB_DB_NAME` | `auto_at` | Database name inside MongoDB |

> **Migrated from V1:** The `DATABASE_URL` variable (SQLAlchemy DSN for SQLite/PostgreSQL) has been removed. All persistence now goes through MongoDB via Motor + Beanie.

### Default LLM Fallback

Used when no LLM profile is marked `is_default=true` in the database.

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_LLM_PROVIDER` | `openai` | LLM provider (e.g. `openai`, `anthropic`, `ollama`) |
| `DEFAULT_LLM_MODEL` | `gpt-4o` | Model identifier |
| `DEFAULT_LLM_API_KEY` | _(empty)_ | API key for the default provider |
| `DEFAULT_LLM_BASE_URL` | _(empty)_ | Custom base URL (for Ollama, LiteLLM proxies, Azure, etc.) |
| `DEFAULT_LLM_TEMPERATURE` | `0.1` | Sampling temperature |
| `DEFAULT_LLM_MAX_TOKENS` | `2048` | Maximum tokens per LLM call |

### File Upload

| Variable | Default | Description |
|----------|---------|-------------|
| `UPLOAD_DIR` | `./uploads` | Directory where uploaded requirement files are stored |
| `MAX_FILE_SIZE_MB` | `50` | Maximum accepted file size in megabytes |

### Security

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `change-me-…` | Secret key used for cryptographic operations — **must be changed in production** |
| `ENCRYPT_API_KEYS` | `false` | When `true`, LLM profile API keys are encrypted at rest using `cryptography` |

### Pipeline / DAG Runner

| Variable | Default | Description |
|----------|---------|-------------|
| `MOCK_CREWS` | `false` | When `true`, all crews return deterministic mock output without calling any LLM — useful for CI or offline development |
| `MAX_CONCURRENT_RUNS` | `3` | Maximum number of pipeline runs that may execute simultaneously across all templates |
| 🆕 `MAX_PARALLEL_NODES` | `4` | Maximum number of DAG nodes that may execute in parallel within a single execution layer *(planned — not yet in `config.py`)* |
| 🆕 `NODE_DEFAULT_TIMEOUT` | `300` | Default per-node execution timeout in seconds; `0` disables the timeout. Overridable per node in the template definition *(planned — not yet in `config.py`)* |
| `INGESTION_TIMEOUT_SECONDS` | `120` | Per-node timeout for built-in Ingestion nodes *(V2 legacy — superseded by `NODE_DEFAULT_TIMEOUT` in V3)* |
| `TESTCASE_TIMEOUT_SECONDS` | `600` | Per-node timeout for built-in Test-Case nodes *(V2 legacy)* |
| `EXECUTION_TIMEOUT_SECONDS` | `300` | Per-node timeout for built-in Execution nodes *(V2 legacy)* |
| `REPORTING_TIMEOUT_SECONDS` | `180` | Per-node timeout for built-in Reporting nodes *(V2 legacy)* |
| `PAUSE_TIMEOUT_SECONDS` | `3600` | Maximum time (seconds) a run may stay paused before auto-cancellation |
| `INGESTION_CHUNK_SIZE` | `2000` | Character chunk size when splitting large requirement documents |
| `INGESTION_CHUNK_OVERLAP` | `200` | Overlap between consecutive chunks |

### Seeding

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_SEED` | `true` | Automatically seed default LLM profiles, agent configs, and the default Pipeline Template on first startup |

---

## API Endpoints

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Returns service status, version `"3.0"`, env, and MongoDB connectivity |
| `GET` | `/` | Root — redirects to Swagger UI docs |

### 🆕 Pipeline Templates (V3)

All template routes are mounted under `/api/v1`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/pipeline-templates` | List all pipeline templates (paginated, filterable by `status`) |
| `POST` | `/api/v1/pipeline-templates` | Create a new pipeline template with nodes and edges |
| `GET` | `/api/v1/pipeline-templates/{template_id}` | Get a full template including all nodes, edges, and metadata |
| `PUT` | `/api/v1/pipeline-templates/{template_id}` | Update template metadata, nodes, and/or edges |
| `DELETE` | `/api/v1/pipeline-templates/{template_id}` | Delete a template (associated runs are preserved with a snapshot) |
| `POST` | `/api/v1/pipeline-templates/{template_id}/clone` | Clone a template into a new editable copy |
| `POST` | `/api/v1/pipeline-templates/{template_id}/archive` | Archive a template (hidden from active listing but preserved) |
| `POST` | `/api/v1/pipeline-templates/{template_id}/validate` | Validate DAG integrity: cycle detection, orphan nodes, missing input/output nodes |
| `GET` | `/api/v1/pipeline-templates/{template_id}/export` | Export the full template as a portable JSON file |
| `POST` | `/api/v1/pipeline-templates/import` | Import a template from a previously exported JSON file |

### Pipeline Runs (Updated — V3 DAG Runner)

All pipeline run routes are mounted under `/api/v1`.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/pipeline/runs` | Start a new pipeline run; now requires `template_id` in the body alongside the file upload |
| `GET` | `/api/v1/pipeline/runs` | List all pipeline runs (paginated; filterable by `status`, `template_id`) |
| `GET` | `/api/v1/pipeline/runs/{run_id}` | Get full run details including `node_statuses`, `execution_layers`, and `template_snapshot` |
| `DELETE` | `/api/v1/pipeline/runs/{run_id}` | Delete a run and cascade-delete all associated node results |
| `GET` | `/api/v1/pipeline/runs/{run_id}/results` | Retrieve all results for a run, keyed by `node_id` (V3) |
| 🆕 `GET` | `/api/v1/pipeline/runs/{run_id}/results/{node_id}` | Get the result for a specific node within a run |
| `POST` | `/api/v1/pipeline/runs/{run_id}/cancel` | Request cancellation of an in-progress run |
| `POST` | `/api/v1/pipeline/runs/{run_id}/pause` | Pause a running pipeline (takes effect between DAG layers) |
| `POST` | `/api/v1/pipeline/runs/{run_id}/resume` | Resume a paused pipeline run |
| `GET` | `/api/v1/pipeline/runs/{run_id}/export/html` | Export the run's report as a styled HTML document |
| `GET` | `/api/v1/pipeline/runs/{run_id}/export/docx` | Export the run's report as a DOCX document |

### WebSocket (Updated — V3 Node Events)

| Path | Description |
|------|-------------|
| `WS /ws/pipeline/{run_id}` | Real-time progress stream for a running pipeline. Emits both V3 layer/node events and legacy stage-level events for backward compatibility. 30 s keepalive ping/pong. |

### Admin — LLM Profiles

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/llm-profiles` | List all LLM profiles (API keys masked, paginated) |
| `POST` | `/api/v1/admin/llm-profiles` | Create a new LLM profile (409 if name already exists) |
| `GET` | `/api/v1/admin/llm-profiles/{id}` | Get a single profile |
| `PUT` | `/api/v1/admin/llm-profiles/{id}` | Partial update of a profile |
| `DELETE` | `/api/v1/admin/llm-profiles/{id}` | Delete a profile; agents referencing it fall back to the global default |
| `POST` | `/api/v1/admin/llm-profiles/{id}/set-default` | Mark a profile as the global default |
| `POST` | `/api/v1/admin/llm-profiles/{id}/test` | Send a probe prompt and measure response latency |

### Admin — Agent Configs (Agent Catalog)

In V3, agents are no longer tied to pipeline stages. The **Agent Catalog** is the source of all agents that can be placed onto the Pipeline Builder canvas as nodes.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/agent-configs` | List all agents in the catalog; supports `grouped=true`, `enabled_only=`, and `category=` query params. The `stage=` filter is now optional. |
| `POST` | `/api/v1/admin/agent-configs` | Create a new custom agent in the catalog (`is_custom=true`). The `stage` field is optional in V3. |
| `GET` | `/api/v1/admin/agent-configs/{agent_id}` | Get a single agent config with its joined LLM profile |
| `PUT` | `/api/v1/admin/agent-configs/{agent_id}` | Partial update — role, goal, backstory, llm_profile_id, flags |
| `DELETE` | `/api/v1/admin/agent-configs/{agent_id}` | Delete a custom agent (built-in agents cannot be deleted, only disabled) |
| `POST` | `/api/v1/admin/agent-configs/{agent_id}/reset` | Reset one agent to factory defaults |
| `POST` | `/api/v1/admin/agent-configs/reset-all` | Reset **all** agents to factory defaults |

### ~~Admin — Stage Configs~~ (DEPRECATED — V3)

> ⚠️ **All `/api/v1/admin/stage-configs` endpoints return `410 Gone`** in V3 with a JSON
> body directing users to the Pipeline Templates API and the migration script.

| Method | Path | V3 Status |
|--------|------|-----------|
| `GET` | `/api/v1/admin/stage-configs` | **DEPRECATED** — returns `410 Gone` with migration message |
| `POST` | `/api/v1/admin/stage-configs` | **DEPRECATED** — returns `410 Gone` |
| `GET` | `/api/v1/admin/stage-configs/{stage_id}` | **DEPRECATED** — returns `410 Gone` |
| `PUT` | `/api/v1/admin/stage-configs/{stage_id}` | **DEPRECATED** — returns `410 Gone` |
| `DELETE` | `/api/v1/admin/stage-configs/{stage_id}` | **DEPRECATED** — returns `410 Gone` |
| `POST` | `/api/v1/admin/stage-configs/reorder` | **DEPRECATED** — returns `410 Gone` |

Run `scripts/migrate_v2_to_v3.py` to convert existing V2 stage configs into a Pipeline Template.

### Chat

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/chat/profiles` | Lightweight profile list for the chat profile picker UI |
| `POST` | `/api/v1/chat/send` | Accept `{messages, llm_profile_id?, system_prompt?}` and stream the LLM response as SSE (`text/event-stream`) |

SSE chunk format:
```
data: {"type": "chunk", "content": "…"}
data: {"type": "done"}
```

---

## Development Commands

```bash
# Install all deps including dev group
# (crewai + lancedb==0.30.0 are included — works on Windows, Linux, and macOS)
uv sync --group dev

# Run dev server with hot-reload
uv run uvicorn app.main:app --reload

# (V3) Run the V2 → V3 migration script
uv run python scripts/migrate_v2_to_v3.py

# Run all tests
uv run pytest

# Run tests with verbose output
uv run pytest -v

# Run tests with coverage
uv run pytest --cov=app --cov-report=term-missing

# Run a specific test file
uv run pytest tests/test_pipeline.py -v

# Type-check with mypy (if installed)
uv run mypy app/

# Format code with ruff
uv run ruff format app/ tests/

# Lint with ruff
uv run ruff check app/ tests/
```

> **V3 note:** Alembic migration commands are not used (removed in V2). The
> `scripts/migrate_v2_to_v3.py` script handles one-time data migration from the V2
> stage-based schema to V3 pipeline templates.

---

## Architecture Overview

### DAG Pipeline Runner (V3)

Auto-AT V3 replaces the sequential stage runner with a topology-aware DAG execution engine. Pipelines are defined as **templates** — a set of typed nodes connected by directed edges — stored in MongoDB and editable through the visual Pipeline Builder.

```
PipelineTemplate (stored in MongoDB)
  nodes: [InputNode, AgentNode, AgentNode, …, OutputNode]
  edges: [{source_node_id, target_node_id}, …]
         │
         ▼
DAGResolver.resolve(template)
  → validates for cycles (DFS)
  → validates for orphan nodes, missing input/output nodes
  → computes execution layers via Kahn's topological sort
  → layers: [[node_A], [node_B, node_C], [node_D]]
         │
         ▼
DAGPipelineRunner.execute(run_id, layers, context)
  Layer 0: run node_A            (single node — sequential)
  Layer 1: run node_B ‖ node_C   (asyncio.gather — up to MAX_PARALLEL_NODES)
  Layer 2: run node_D            (single node — sequential)
         │
         ▼
  Results keyed by node_id, persisted to pipeline_results, broadcast via WebSocket
```

#### `dag_resolver.py`

| Export | Description |
|--------|-------------|
| `DAGResolver` | Validates DAG structure (cycle detection via DFS, orphan-node check, input/output node presence) and computes topological execution layers. Each layer is a list of nodes that have no unresolved upstream dependencies and can therefore execute in parallel. Raises `DAGValidationError` with a human-readable message on any structural problem. |

#### `dag_pipeline_runner.py`

| Export | Description |
|--------|-------------|
| `DAGPipelineRunner` | Executes a resolved DAG layer-by-layer. Within each layer, nodes run concurrently via `asyncio.gather()` bounded by `MAX_PARALLEL_NODES`. Checks pause/cancel signals between layers via `SignalManager`. Broadcasts `layer.started`, `layer.completed`, `node.started`, `node.completed`, `node.failed`, and `node.skipped` WebSocket events. Stores a `template_snapshot` on the run document so historical runs are always reproducible. |
| `run_dag_pipeline_async()` | Top-level async entry point — resolves the template, creates the run document, and delegates to `DAGPipelineRunner`. |

---

### Built-in Node Implementations (Legacy Crews)

The four original crew implementations are preserved and used as the **default built-in Pipeline Template**. Each maps to a specific node type in the DAG:

#### Ingestion Node (`ingestion_crew.py`)

> **Pure Python — no CrewAI agents.** Implemented as a direct 5-step function pipeline
> using `litellm.completion()` calls for LLM extraction.

| Step | Function | Responsibility |
|------|----------|---------------|
| 1 | `parse_document()` | File → raw text via pdfplumber (PDF), python-docx (DOCX), openpyxl (XLSX), or plain read (TXT/MD) |
| 2 | `chunk_text()` | Split text into overlapping chunks using the `TextChunker` tool |
| 3 | `_llm_extract(chunk)` | Call `litellm.completion()` on each chunk to extract structured requirements JSON |
| 4 | `_deduplicate()` | Fuzzy de-duplication by normalized title |
| 5 | ID assignment | Assign sequential `REQ-001 … REQ-NNN` identifiers |

One virtual agent (`ingestion_pipeline`) is seeded in the `agent_configs` collection so its LLM settings can be managed through the Admin API like any other agent.

#### Test-Case Generation Node (`testcase_crew.py`)

10-agent CrewAI Sequential crew. Transforms structured requirements into detailed, executable test cases.

| # | Agent | Responsibility |
|---|-------|---------------|
| 1 | `requirement_analyzer` | Enrich and normalize incoming requirements |
| 2 | `scope_classifier` | Classify test scope and risk level per requirement |
| 3 | `data_model_agent` | Build the test data model |
| 4 | `rule_parser` | Extract and formalize validation rules |
| 5 | `test_condition_agent` | Apply Equivalence Partitioning and Boundary Value Analysis |
| 6 | `dependency_agent` | Map inter-requirement dependencies |
| 7 | `test_case_generator` | Generate complete `TestCase` objects (core output of the crew) |
| 8 | `automation_agent` | Write automation scripts for generated test cases |
| 9 | `coverage_agent_pre` | Compute pre-execution (design-phase) coverage metrics |
| 10 | `report_agent_pre` | Produce a design-phase summary report |

#### Execution Node (`execution_crew.py`)

5-agent CrewAI Sequential crew. Executes the generated test cases against a live or configured API environment.

| # | Agent | Responsibility |
|---|-------|---------------|
| 1 | `execution_orchestrator` | Plan execution order and per-case timeouts |
| 2 | `env_adapter` | Resolve environment configuration via `ConfigLoaderTool` |
| 3 | `test_runner` | Execute API test cases via `APIRunnerTool` (httpx) |
| 4 | `execution_logger` | Aggregate per-case logs and timing statistics |
| 5 | `result_store` | Consolidate all outcomes into the final `ExecutionOutput` |

#### Reporting Node (`reporting_crew.py`)

3-agent CrewAI Sequential crew. Aggregates execution results into a comprehensive report.

| # | Agent | Responsibility |
|---|-------|---------------|
| 1 | `coverage_analyzer` | Post-execution requirement and scenario coverage analysis |
| 2 | `root_cause_analyzer` | Failure pattern grouping and root-cause mapping |
| 3 | `report_generator` | Produce the comprehensive executive + technical `PipelineReport` |

#### Custom Agent Nodes — `DynamicCrewAICrew`

Custom agents from the Agent Catalog are placed onto the pipeline canvas as `agent` nodes and executed by the generic `DynamicCrewAICrew` (`crews/dynamic_crew.py`). This crew dynamically builds a CrewAI crew from the agents assigned to the node and supports all three crew types:

| Crew Type | Description |
|-----------|-------------|
| `pure_python` | Direct function pipeline — no CrewAI orchestration |
| `crewai_sequential` | Agents execute tasks in strict sequential order |
| `crewai_hierarchical` | Manager agent delegates tasks dynamically |

---

### Tools (`app/tools/`)

| File | Class / API | Description |
|------|-------------|-------------|
| `document_parser.py` | `DocumentParser` | Auto-dispatches by file extension: PDF (pdfplumber), DOCX (python-docx), XLSX (openpyxl), TXT/MD, CSV |
| `text_chunker.py` | `TextChunker`, `TextChunk` | Pure-Python chunker; paragraph → sentence → line → word → hard-cut priority; includes token estimate |
| `api_runner.py` | `APIRunnerTool` (CrewAI `BaseTool`) | httpx-based HTTP executor for the `test_runner` agent; supports batch execution |
| `config_loader.py` | `ConfigLoaderTool` (CrewAI `BaseTool`) | Environment config resolution chain: explicit file → auto-discover → `TEST_ENV_*` vars → well-known vars → defaults |

---

### Core (`app/core/`)

| File | Key Exports | Description |
|------|-------------|-------------|
| `agent_factory.py` | `build()`, `build_many()`, `build_for_stage()` | Builds `crewai.Agent` instances from `AgentConfig` DB documents using a 5-level LLM override chain |
| `llm_factory.py` | `build_llm()`, `build_fallback_llm()`, `probe_llm_connection()` | LiteLLM provider prefix map: `openai`, `anthropic`, `ollama`, `huggingface`, `azure` → `azure_openai`, `groq`, `lm_studio` → `openai` |
| 🆕 `dag_resolver.py` | `DAGResolver`, `DAGValidationError` | DAG validation (cycle detection via DFS, orphan nodes, required node types) + topological sort + execution layer computation |
| 🆕 `dag_pipeline_runner.py` | `DAGPipelineRunner`, `run_dag_pipeline_async()` | DAG-based parallel execution engine. Runs each topological layer concurrently. Replaces `pipeline_runner.py` for all template-backed runs. |
| `pipeline_runner.py` | `run_pipeline_async()` | *(Deprecated — kept for reference.)* Sequential N-stage orchestrator from V2. Not used for new runs in V3. |
| `signal_manager.py` | `SignalManager` | Coordinates pause, resume, and cancel signals between the API layer and the runner. Checked between DAG layers (was: between stages). Supports timeout-based auto-cancellation of paused runs. |

---

### Services (`app/services/`)

| File | Key Exports | Description |
|------|-------------|-------------|
| `export_service.py` | `export_html()`, `export_docx()` | Orchestrates report export — loads run data (now keyed by `node_id`), renders the Jinja2 template, and returns a file response |
| `docx_builder.py` | `build_docx()` | Builds a styled DOCX document from pipeline report data using `python-docx` (updated for V3 node-based result structure) |

---

### Database Schema — MongoDB Collections (V3)

All persistence uses MongoDB via Motor (async driver) and Beanie ODM. Each collection maps to a Beanie `Document` class.

| Collection | Document Class | Key Fields | Notes |
|------------|---------------|------------|-------|
| `llm_profiles` | `LLMProfileDocument` | `name` (unique), `provider`, `model`, `api_key`, `base_url`, `temperature`, `max_tokens`, `is_default`, timestamps | API keys optionally encrypted at rest. No change from V2. |
| `agent_configs` | `AgentConfigDocument` | `agent_id` (unique), `display_name`, `category`, `role`, `goal`, `backstory`, `llm_profile_id` (ref), `enabled`, `verbose`, `max_iter`, `is_custom`, timestamps | `stage` field is now **optional** in V3. Agents serve as a free catalog picked by template nodes. |
| 🆕 `pipeline_templates` | `PipelineTemplateDocument` | `template_id` (UUID), `name`, `description`, `status` (`active`/`archived`), `nodes` (list), `edges` (list), `version`, `is_builtin`, timestamps | Replaces `stage_configs`. Each node carries `node_id`, `node_type`, `agent_id`, `config`, `position`. Each edge carries `source_node_id`, `target_node_id`. |
| `pipeline_runs` | `PipelineRunDocument` | `id` (UUID), `template_id` (ref), `template_snapshot` (embedded copy of template at run time), `document_name`, `document_path`, `llm_profile_id` (ref), `status`, `node_statuses` (dict keyed by `node_id`), `execution_layers`, `error`, `current_node`, `paused_at`, `resumed_at`, timestamps | `status` ∈ `pending \| running \| paused \| completed \| failed \| cancelled` |
| `pipeline_results` | `PipelineResultDocument` | `run_id` (ref), `node_id`, `node_type`, `output` (dict), `created_at` | Results are now keyed by `node_id`. The V2 `stage` + `agent_id` composite key is replaced. |
| ~~`stage_configs`~~ | ~~`StageConfigDocument`~~ | — | **Deprecated** — replaced by `pipeline_templates`. Existing data migrated by `scripts/migrate_v2_to_v3.py`. |

> **Migrated from V1:** The SQLite tables (`llm_profiles`, `agent_configs`, `pipeline_runs`,
> `pipeline_results`) were replaced by MongoDB collections in V2. Alembic migrations are not used.

---

### Schemas & Enums

| Enum | Values |
|------|--------|
| `LLMProvider` | `openai`, `anthropic`, `ollama`, `huggingface`, `azure_openai`, `groq` |
| `PipelineStatus` | `pending`, `running`, `paused`, `completed`, `failed`, `cancelled` |
| `AgentRunStatus` | `waiting`, `running`, `done`, `skipped`, `error` |
| `WSEventType` | `run.started`, `run.completed`, `run.failed`, `run.paused`, `run.resumed`, `run.cancelled`, `stage.started` *(legacy)*, `stage.completed` *(legacy)*, `agent.started`, `agent.completed`, `agent.failed`, 🆕 `layer.started`, 🆕 `layer.completed`, 🆕 `node.started`, 🆕 `node.completed`, 🆕 `node.failed`, 🆕 `node.skipped`, 🆕 `node.progress`, `log` |
| `CrewType` | `pure_python`, `crewai_sequential`, `crewai_hierarchical` |
| 🆕 `NodeType` | `input`, `output`, `agent`, `pure_python` |
| 🆕 `TemplateStatus` | `active`, `archived` |

---

### Real-Time Progress via WebSocket

Connect to `WS /ws/pipeline/{run_id}` while a run is in progress. The server broadcasts JSON events and sends a keepalive every 30 seconds. The client may send `{"action": "ping"}` and will receive `{"event": "pong"}` in response.

**Event envelope (V3 — node event example):**

```json
{
  "event": "node.completed",
  "run_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "timestamp": "2025-01-15T10:30:00Z",
  "data": {
    "node_id": "node_testcase_01",
    "node_type": "agent",
    "layer_index": 1,
    "status": "done",
    "duration_ms": 4820
  }
}
```

**Event types (`WSEventType`):**

| Event | Meaning |
|-------|---------|
| `run.started` | Pipeline run has begun |
| `run.completed` | The full pipeline run completed successfully |
| `run.failed` | The pipeline run terminated with an error |
| `run.paused` | The pipeline run has been paused (between layers) |
| `run.resumed` | A paused pipeline run has been resumed |
| `run.cancelled` | The pipeline run has been cancelled |
| 🆕 `layer.started` | A DAG execution layer has started (includes `layer_index` and `node_ids`) |
| 🆕 `layer.completed` | All nodes in a DAG execution layer have finished |
| 🆕 `node.started` | An individual DAG node has started execution |
| 🆕 `node.completed` | An individual DAG node finished successfully |
| 🆕 `node.failed` | An individual DAG node encountered an unrecoverable error |
| 🆕 `node.skipped` | A DAG node was skipped (disabled, or an upstream node failed) |
| 🆕 `node.progress` | Incremental progress update from within a long-running node |
| `agent.started` | An individual CrewAI agent within a node has started its task |
| `agent.completed` | An individual CrewAI agent finished successfully |
| `agent.failed` | An individual CrewAI agent encountered an error |
| `stage.started` | *(Legacy — emitted for backward compatibility with V2 clients)* |
| `stage.completed` | *(Legacy — emitted for backward compatibility; includes `summary` in `data`)* |
| `log` | Informational log message from any layer, node, or agent |

---

## Dependency Notes

### crewAI on Windows

`crewai` pulls in `lancedb` as a transitive dependency.
`lancedb >= 0.30.1` **only** publishes Linux/macOS wheels, so naively running
`uv add crewai` on Windows fails with a platform-compatibility error.

**Fix already applied in `pyproject.toml`:**

```toml
"crewai>=1.0.0",
"lancedb==0.30.0",   # 0.30.0 is the last release with a win_amd64 wheel
```

To re-install from scratch on Windows:

```bash
uv add "crewai>=1.0.0" "lancedb==0.30.0"
# or with plain pip inside the venv:
pip install "crewai>=1.0.0" "lancedb==0.30.0"
```

When `lancedb` publishes a new Windows-compatible release, update the pin and run
`uv sync` again.

### Key Runtime Dependencies

| Package | Role |
|---------|------|
| `fastapi`, `uvicorn` | HTTP/WebSocket server |
| `motor >= 3.6.0` | Async MongoDB driver |
| `beanie >= 1.27.0` | Async MongoDB ODM (document models, queries) |
| `pydantic` v2, `pydantic-settings` | Schemas and config |
| `crewai >= 1.0`, `lancedb==0.30.0` | Multi-agent crew orchestration |
| `litellm >= 1.50` | Unified LLM provider interface |
| `pdfplumber`, `python-docx`, `openpyxl` | Document parsing |
| `jinja2 >= 3.1.0` | HTML report template rendering |
| `httpx` | HTTP client for test execution |
| `cryptography` | Optional API key encryption |
| `python-dotenv`, `aiofiles` | Env loading and async file I/O |
| `pytest`, `pytest-asyncio` | *(dev)* Test framework |

> **Removed in V2:** `sqlalchemy` 2.x and `alembic` are no longer dependencies.

---

## Docker

```bash
# Build and run all services (backend + MongoDB)
docker compose up --build

# Backend only (requires external MongoDB)
docker compose up backend

# MongoDB only (for local development)
docker compose up -d mongodb

# View backend logs
docker compose logs -f backend
```

The `docker-compose.yml` at the project root includes a **MongoDB** service. The backend service depends on MongoDB being healthy before starting. See [`docker-compose.yml`](../docker-compose.yml) for the full configuration.

---

## Project Structure

```
backend/
├── app/
│   ├── main.py                        # FastAPI app entry + lifespan hooks (mounts V3 routers)
│   ├── config.py                      # Pydantic-settings config
│   │                                  # +MAX_CONCURRENT_RUNS, +NODE_DEFAULT_TIMEOUT (planned),
│   │                                  # +MAX_PARALLEL_NODES (planned)
│   │
│   ├── api/v1/
│   │   ├── __init__.py
│   │   ├── deps.py                    # Shared FastAPI dependencies (DB session, etc.)
│   │   ├── pipeline.py                # UPDATED: requires template_id, returns node-based results
│   │   ├── pipeline_templates.py      # NEW: template CRUD, clone, archive, validate, export/import
│   │   ├── llm_profiles.py            # No change
│   │   ├── agent_configs.py           # Updated: stage field optional (Agent Catalog)
│   │   ├── stage_configs.py           # DEPRECATED: all routes return 410 Gone
│   │   ├── chat.py                    # No change
│   │   └── websocket.py               # Updated: +layer.*, +node.* events
│   │
│   ├── core/
│   │   ├── llm_factory.py             # No change
│   │   ├── agent_factory.py           # No change
│   │   ├── dag_resolver.py            # NEW: DAG validation + topological sort + layer computation
│   │   ├── dag_pipeline_runner.py     # NEW: DAG-based parallel execution engine
│   │   ├── pipeline_runner.py         # DEPRECATED: kept for reference, superseded by dag_pipeline_runner
│   │   └── signal_manager.py          # No change (now checks signals between layers)
│   │
│   ├── crews/
│   │   ├── __init__.py
│   │   ├── base_crew.py               # No change
│   │   ├── dynamic_crew.py            # No change (used by agent nodes)
│   │   ├── ingestion_crew.py          # No change (used by input/ingestion nodes)
│   │   ├── testcase_crew.py           # Kept for reference / built-in template
│   │   ├── execution_crew.py          # Kept for reference / built-in template
│   │   └── reporting_crew.py          # Kept for reference / built-in template
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── export_service.py          # Updated: per-node results instead of per-stage
│   │   └── docx_builder.py            # Updated: node-based result structure
│   │
│   ├── templates/
│   │   └── report.html.j2             # Updated: node-based results rendering
│   │
│   ├── agents/
│   │   ├── ingestion/
│   │   ├── testcase/
│   │   ├── execution/
│   │   └── reporting/
│   │
│   ├── tasks/
│   │   ├── testcase_tasks.py          # 10 task factories for Test-Case crew
│   │   ├── execution_tasks.py         # 5 task factories for Execution crew
│   │   └── reporting_tasks.py         # 3 task factories for Reporting crew
│   │
│   ├── tools/
│   │   ├── document_parser.py         # Multi-format document reader
│   │   ├── text_chunker.py            # Overlapping text chunker
│   │   ├── api_runner.py              # httpx-based APIRunnerTool
│   │   └── config_loader.py           # Env resolution ConfigLoaderTool
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py                # Motor client + Beanie ODM initialization
│   │   ├── models.py                  # +PipelineTemplateDocument, +PipelineNodeConfig,
│   │   │                              #  +PipelineEdgeConfig; updated PipelineRunDocument,
│   │   │                              #  updated PipelineResultDocument
│   │   ├── crud.py                    # +template CRUD helpers; updated run/result functions
│   │   └── seed.py                    # +seed default Pipeline Template (migrated from built-in stages)
│   │
│   └── schemas/
│       ├── __init__.py
│       ├── llm_profile.py             # No change
│       ├── agent_config.py            # stage field optional in V3
│       ├── stage_config.py            # DEPRECATED
│       ├── pipeline.py                # +new WSEventType values; updated PipelineRunResponse
│       ├── pipeline_template.py       # NEW: PipelineTemplate request/response schemas
│       └── pipeline_io.py             # No change
│
├── scripts/
│   └── migrate_v2_to_v3.py            # NEW: converts V2 stage configs → default Pipeline Template
│
├── tests/                             # pytest test suite
├── uploads/                           # Uploaded requirement documents (gitignored)
├── pyproject.toml                     # Project metadata + dependencies (uv)
├── uv.lock                            # Locked dependency tree
├── Dockerfile                         # Production container image
└── README.md                          # This file
```

---

## License

MIT © Auto-AT Project