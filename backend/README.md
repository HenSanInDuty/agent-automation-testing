# Auto-AT Backend

> **Auto-AT** — Multi-Agent Automated Testing System
> FastAPI REST/WebSocket server + CrewAI 4-crew pipeline

---

## 🆕 V2 Changes

Auto-AT V2 introduces seven major backend enhancements on top of the existing V1 pipeline:

| # | Feature | Summary |
|---|---------|---------|
| 1 | **Report Export (HTML/DOCX)** | New endpoints to export pipeline run results as styled HTML or DOCX documents. Powered by Jinja2 templates and `python-docx`. |
| 2 | **Per-Stage Results Display** | The `stage.completed` WebSocket event now includes a `summary` payload so the frontend can display results incrementally as each stage finishes. |
| 3 | **Persistent Pipeline Session** | Frontend-only change (Zustand store). No backend modifications required. |
| 4 | **MongoDB Replacing SQLite** | SQLAlchemy + SQLite/PostgreSQL replaced by **Motor** (async driver) + **Beanie** ODM + **MongoDB**. All API handlers are fully `async`. Alembic migrations removed. |
| 5 | **Dynamic Agent Management** | Create and delete custom agents via Admin API. Built-in agents can only be disabled, never deleted. New `is_custom` field on `AgentConfig`. |
| 6 | **Dynamic Stage Configuration** | New `stage_configs` MongoDB collection allows full CRUD + reorder of pipeline stages. Supports three crew types: `pure_python`, `crewai_sequential`, `crewai_hierarchical`. Pipeline runner dynamically reads stages from DB at runtime. |
| 7 | **Pause / Resume / Cancel Pipeline** | New `paused` and `cancelled` run statuses. A `SignalManager` checks for signals between stages. Dedicated pause/resume endpoints and new WebSocket events (`run.paused`, `run.resumed`, `run.cancelled`). |

**Key dependency changes (V2):**

| Removed | Added |
|---------|-------|
| `sqlalchemy` 2.x | `motor >= 3.6.0` |
| `alembic` | `beanie >= 1.27.0` |
| | `jinja2 >= 3.1.0` |

---

## Overview

Auto-AT Backend orchestrates a **multi-agent pipeline** that takes a requirements document (PDF, DOCX, XLSX, or TXT) and automatically produces a complete test suite — from requirement parsing all the way through test execution and final reporting.

```
Upload Document
      │
      ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ Ingestion Crew   │───▶│ Test-Case Crew   │───▶│ Execution Crew   │───▶│ Reporting Crew   │
│  Pure Python     │    │  10-agent CrewAI │    │  5-agent CrewAI  │    │  3-agent CrewAI  │
│  5-step pipeline │    │  Sequential crew │    │  Sequential crew │    │  Sequential crew │
│  (parse+extract  │    │  (generate test  │    │  (run API tests  │    │  (coverage +     │
│   requirements)  │    │   cases + steps) │    │   capture logs)  │    │   final report)  │
└──────────────────┘    └──────────────────┘    └──────────────────┘    └──────────────────┘
        │                        │                        │                        │
        ▼                        ▼                        ▼                        ▼
  IngestionOutput  ──▶   TestCaseOutput   ──▶   ExecutionOutput   ──▶   PipelineReport
```

In V2 the pipeline is **dynamic** — additional custom stages can be inserted, reordered, or disabled via the Stage Configuration admin API. The built-in 4-crew flow above remains the default.

The REST API exposes pipeline management, real-time WebSocket progress streaming, admin endpoints for configuring LLM profiles, per-agent overrides, stage configuration, report export, and a streaming chat interface.

---

## Prerequisites

| Tool | Minimum Version | Notes |
|------|----------------|-------|
| Python | 3.11+ | 3.12 recommended |
| [uv](https://github.com/astral-sh/uv) | 0.4+ | Fast Python package manager |
| MongoDB | **7.0+** 🆕 | Required — replaces SQLite from V1 |

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

# 4. (V2) Start MongoDB
#    Option A — Docker (recommended):
docker compose up -d mongodb
#    Option B — local install:
#    Ensure mongod is running on localhost:27017

# 5. Start the development server (auto-reload)
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

### 🆕 Database (V2 — MongoDB)

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

### Pipeline / Crews

| Variable | Default | Description |
|----------|---------|-------------|
| `MOCK_CREWS` | `false` | When `true`, all crews return deterministic mock output without calling any LLM — useful for CI or offline development |
| `MAX_CONCURRENT_RUNS` | `3` | Maximum number of pipeline runs that may execute simultaneously |
| `INGESTION_TIMEOUT_SECONDS` | `120` | Per-stage timeout for the Ingestion crew |
| `TESTCASE_TIMEOUT_SECONDS` | `600` | Per-stage timeout for the Test-Case crew |
| `EXECUTION_TIMEOUT_SECONDS` | `300` | Per-stage timeout for the Execution crew |
| `REPORTING_TIMEOUT_SECONDS` | `180` | Per-stage timeout for the Reporting crew |
| `INGESTION_CHUNK_SIZE` | `2000` | Character chunk size when splitting large requirement documents |
| `INGESTION_CHUNK_OVERLAP` | `200` | Overlap between consecutive chunks |
| 🆕 `PAUSE_TIMEOUT_SECONDS` | `3600` | Maximum time (seconds) a run may stay paused before auto-cancellation |
| 🆕 `REPORT_TEMPLATE_DIR` | `app/templates` | Directory containing Jinja2 report templates |

### Seeding

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_SEED` | `true` | Automatically seed default LLM profiles, agent configs, and stage configs on first startup |

---

## API Endpoints

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Returns service status, version, env, and **MongoDB connectivity** (V2) |
| `GET` | `/` | Root — redirects to Swagger UI docs |

### Pipeline

All pipeline routes are mounted under `/api/v1`.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/pipeline/runs` | Start a new pipeline run; accepts a multipart file upload + config options |
| `GET` | `/api/v1/pipeline/runs` | List all pipeline runs (paginated, optional `status` filter) |
| `GET` | `/api/v1/pipeline/runs/{run_id}` | Get full details of a single run including per-agent statuses |
| `DELETE` | `/api/v1/pipeline/runs/{run_id}` | Delete a run and cascade-delete all associated results |
| `POST` | `/api/v1/pipeline/runs/{run_id}/cancel` | Request cancellation of an in-progress run |
| `GET` | `/api/v1/pipeline/runs/{run_id}/results` | Retrieve structured results; filterable by `stage` and `agent` |
| 🆕 `POST` | `/api/v1/pipeline/runs/{run_id}/pause` | Pause a running pipeline (takes effect between stages) |
| 🆕 `POST` | `/api/v1/pipeline/runs/{run_id}/resume` | Resume a paused pipeline run |
| 🆕 `GET` | `/api/v1/pipeline/runs/{run_id}/export/html` | Export the run's report as a styled HTML document |
| 🆕 `GET` | `/api/v1/pipeline/runs/{run_id}/export/docx` | Export the run's report as a DOCX document |

### WebSocket

| Path | Description |
|------|-------------|
| `WS /ws/pipeline/{run_id}` | Real-time progress stream for a running pipeline — emits JSON events as each crew stage and agent progresses; 30 s keepalive ping/pong |

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

### Admin — Agent Configs

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/agent-configs` | List all agent configs; supports `grouped=true`, `stage=`, `enabled_only=` query params |
| `GET` | `/api/v1/admin/agent-configs/{agent_id}` | Get a single agent config with its joined LLM profile |
| `PUT` | `/api/v1/admin/agent-configs/{agent_id}` | Partial update — role, goal, backstory, llm_profile_id, flags |
| `POST` | `/api/v1/admin/agent-configs/{agent_id}/reset` | Reset one agent to factory defaults |
| `POST` | `/api/v1/admin/agent-configs/reset-all` | Reset **all** agents to factory defaults |
| 🆕 `POST` | `/api/v1/admin/agent-configs` | Create a new **custom** agent (`is_custom=true`) |
| 🆕 `DELETE` | `/api/v1/admin/agent-configs/{agent_id}` | Delete a custom agent (built-in agents cannot be deleted, only disabled) |

### 🆕 Admin — Stage Configs (V2)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/stage-configs` | List all stage configurations in pipeline order |
| `POST` | `/api/v1/admin/stage-configs` | Create a new custom stage |
| `GET` | `/api/v1/admin/stage-configs/{stage_id}` | Get a single stage config |
| `PUT` | `/api/v1/admin/stage-configs/{stage_id}` | Update a stage config (display name, description, order, crew type, timeout, enabled) |
| `DELETE` | `/api/v1/admin/stage-configs/{stage_id}` | Delete a custom stage (built-in stages cannot be deleted) |
| `POST` | `/api/v1/admin/stage-configs/reorder` | Bulk-reorder stages by passing an ordered list of `stage_id` values |

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

> **V2 note:** Alembic migration commands (`alembic revision`, `alembic upgrade`, `alembic downgrade`) have been removed. Beanie ODM handles MongoDB document schema evolution without explicit migrations.

---

## Architecture Overview

### 4 Built-in Crews — 1 Pure-Python + 3 CrewAI Sequential

Auto-AT is structured as four sequential processing stages. Each stage produces a strongly-typed output object that is passed as input to the next stage.

```
IngestionOutput  ──▶  TestCaseOutput  ──▶  ExecutionOutput  ──▶  PipelineReport
```

#### Crew 1 — Ingestion (`ingestion_crew.py`)

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

#### Crew 2 — Test-Case Generation (`testcase_crew.py`)

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

#### Crew 3 — Execution (`execution_crew.py`)

5-agent CrewAI Sequential crew. Executes the generated test cases against a live or configured API environment.

| # | Agent | Responsibility |
|---|-------|---------------|
| 1 | `execution_orchestrator` | Plan execution order and per-case timeouts |
| 2 | `env_adapter` | Resolve environment configuration via `ConfigLoaderTool` |
| 3 | `test_runner` | Execute API test cases via `APIRunnerTool` (httpx) |
| 4 | `execution_logger` | Aggregate per-case logs and timing statistics |
| 5 | `result_store` | Consolidate all outcomes into the final `ExecutionOutput` |

#### Crew 4 — Reporting (`reporting_crew.py`)

3-agent CrewAI Sequential crew. Aggregates execution results into a comprehensive report.

| # | Agent | Responsibility |
|---|-------|---------------|
| 1 | `coverage_analyzer` | Post-execution requirement and scenario coverage analysis |
| 2 | `root_cause_analyzer` | Failure pattern grouping and root-cause mapping |
| 3 | `report_generator` | Produce the comprehensive executive + technical `PipelineReport` |

#### 🆕 Custom Stages — `DynamicCrewAICrew` (V2)

Custom stages created via the Stage Config admin API are executed by the generic `DynamicCrewAICrew` (`crews/dynamic_crew.py`). This crew dynamically builds a CrewAI crew from the agents assigned to the stage and supports all three crew types:

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
| `pipeline_runner.py` | `run_pipeline_async()` | Dynamic N-stage orchestrator (V2) — reads enabled stages from DB, runs them in order, checks pause/cancel signals between stages, broadcasts WebSocket events with per-stage summaries |
| 🆕 `signal_manager.py` | `SignalManager` | Coordinates pause, resume, and cancel signals between stages. Checked by the pipeline runner between each stage transition. Supports timeout-based auto-cancellation of paused runs. |

---

### 🆕 Services (`app/services/`) (V2)

| File | Key Exports | Description |
|------|-------------|-------------|
| `export_service.py` | `export_html()`, `export_docx()` | Orchestrates report export — loads run data, renders template, returns file response |
| `docx_builder.py` | `build_docx()` | Builds a styled DOCX document from pipeline report data using `python-docx` |

---

### 🆕 Database Schema — MongoDB Collections (V2)

All persistence uses MongoDB via Motor (async driver) and Beanie ODM. Each collection maps to a Beanie `Document` class.

| Collection | Document Class | Key Fields | Notes |
|------------|---------------|------------|-------|
| `llm_profiles` | `LLMProfileDocument` | `name` (unique), `provider`, `model`, `api_key`, `base_url`, `temperature`, `max_tokens`, `is_default`, timestamps | API keys optionally encrypted at rest |
| `agent_configs` | `AgentConfigDocument` | `agent_id` (unique), `display_name`, `stage`, `role`, `goal`, `backstory`, `llm_profile_id` (ref), `enabled`, `verbose`, `max_iter`, 🆕 `is_custom`, timestamps | `is_custom=false` for built-in agents (cannot be deleted) |
| `pipeline_runs` | `PipelineRunDocument` | `id` (UUID), `document_name`, `document_path`, `llm_profile_id` (ref), `status`, `agent_statuses` (dict), `error`, 🆕 `current_stage`, 🆕 `completed_stages`, 🆕 `stage_results_summary`, 🆕 `paused_at`, 🆕 `resumed_at`, timestamps | `status` ∈ `pending \| running \| paused \| completed \| failed \| cancelled` |
| `pipeline_results` | `PipelineResultDocument` | `run_id` (ref), `stage`, `agent_id`, `output` (dict), `created_at` | Linked to parent run via `run_id` |
| 🆕 `stage_configs` | `StageConfigDocument` | `stage_id` (unique), `display_name`, `description`, `order`, `enabled`, `crew_type`, `timeout_seconds`, `is_builtin`, timestamps | `crew_type` ∈ `pure_python \| crewai_sequential \| crewai_hierarchical` |

> **Migrated from V1:** The SQLite tables (`llm_profiles`, `agent_configs`, `pipeline_runs`, `pipeline_results`) have been replaced by equivalent MongoDB collections. Alembic migrations are no longer used.

---

### Schemas & Enums

| Enum | Values |
|------|--------|
| `LLMProvider` | `openai`, `anthropic`, `ollama`, `huggingface`, `azure_openai`, `groq` |
| `PipelineStatus` | `pending`, `running`, 🆕 `paused`, `completed`, `failed`, 🆕 `cancelled` |
| `AgentRunStatus` | `waiting`, `running`, `done`, `skipped`, `error` |
| `WSEventType` | `run.started`, `stage.started`, `stage.completed`, `agent.started`, `agent.completed`, `agent.failed`, `run.completed`, `run.failed`, `log`, 🆕 `run.paused`, 🆕 `run.resumed`, 🆕 `run.cancelled` |
| 🆕 `CrewType` | `pure_python`, `crewai_sequential`, `crewai_hierarchical` |

---

### Real-Time Progress via WebSocket

Connect to `WS /ws/pipeline/{run_id}` while a run is in progress. The server broadcasts JSON events and sends a keepalive every 30 seconds. The client may send `{"action": "ping"}` and will receive `{"event": "pong"}` in response.

**Event envelope:**

```json
{
  "event": "agent.completed",
  "run_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "timestamp": "2025-01-15T10:30:00Z",
  "data": { "agent_id": "test_case_generator", "stage": "testcase", "status": "done" }
}
```

**Event types (`WSEventType`):**

| Event | Meaning |
|-------|---------|
| `run.started` | Pipeline run has begun |
| `stage.started` | A crew stage has started |
| `stage.completed` | A crew stage finished successfully (V2: includes `summary` in `data`) |
| `agent.started` | An individual agent has started its task |
| `agent.completed` | An individual agent finished successfully |
| `agent.failed` | An individual agent encountered an error |
| `run.completed` | The full pipeline run completed successfully |
| `run.failed` | The pipeline run terminated with an error |
| `log` | Informational log message from any stage or agent |
| 🆕 `run.paused` | The pipeline run has been paused (between stages) |
| 🆕 `run.resumed` | A paused pipeline run has been resumed |
| 🆕 `run.cancelled` | The pipeline run has been cancelled |

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
| 🆕 `motor >= 3.6.0` | Async MongoDB driver |
| 🆕 `beanie >= 1.27.0` | Async MongoDB ODM (document models, queries) |
| `pydantic` v2, `pydantic-settings` | Schemas and config |
| `crewai >= 1.0`, `lancedb==0.30.0` | Multi-agent crew orchestration |
| `litellm >= 1.50` | Unified LLM provider interface |
| `pdfplumber`, `python-docx`, `openpyxl` | Document parsing |
| 🆕 `jinja2 >= 3.1.0` | HTML report template rendering |
| `httpx` | HTTP client for test execution |
| `cryptography` | Optional API key encryption |
| `python-dotenv`, `aiofiles` | Env loading and async file I/O |
| `pytest`, `pytest-asyncio` | _(dev)_ Test framework |

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

The `docker-compose.yml` at the project root now includes a **MongoDB** service (V2). The backend service depends on MongoDB being healthy before starting. See [`docker-compose.yml`](../docker-compose.yml) for the full configuration.

---

## Project Structure

```
backend/
├── app/
│   ├── agents/               Reserved for future per-crew agent sub-classes
│   │   ├── ingestion/        (future)
│   │   ├── testcase/         (future)
│   │   ├── execution/        (future)
│   │   └── reporting/        (future)
│   │
│   ├── api/v1/               FastAPI route handlers
│   │   ├── deps.py           Shared dependencies (DB session, etc.)
│   │   ├── pipeline.py       Pipeline run CRUD + cancel + pause/resume + export (V2)
│   │   ├── llm_profiles.py
│   │   ├── agent_configs.py  + create/delete custom agents (V2)
│   │   ├── stage_configs.py  🆕 Stage management CRUD + reorder (V2)
│   │   ├── chat.py           Streaming chat endpoint
│   │   └── websocket.py      WS progress stream
│   │
│   ├── core/
│   │   ├── agent_factory.py      Builds crewai.Agent from AgentConfig documents
│   │   ├── llm_factory.py        LiteLLM provider map + probe
│   │   ├── pipeline_runner.py    Dynamic N-stage orchestrator (V2)
│   │   └── signal_manager.py     🆕 Pause/Resume/Cancel signal coordination (V2)
│   │
│   ├── crews/
│   │   ├── base_crew.py
│   │   ├── ingestion_crew.py     Crew 1 — pure Python, 5-step pipeline
│   │   ├── testcase_crew.py      Crew 2 — 10-agent CrewAI Sequential
│   │   ├── execution_crew.py     Crew 3 — 5-agent CrewAI Sequential
│   │   ├── reporting_crew.py     Crew 4 — 3-agent CrewAI Sequential
│   │   └── dynamic_crew.py       🆕 Generic crew for custom stages (V2)
│   │
│   ├── db/
│   │   ├── database.py      Motor client + Beanie ODM initialization (V2)
│   │   ├── models.py        Beanie Document models (V2)
│   │   ├── crud.py          CRUD helpers (async, V2)
│   │   └── seed.py          seed_all() — default profiles + agent configs + stage configs
│   │
│   ├── schemas/
│   │   ├── llm_profile.py
│   │   ├── agent_config.py
│   │   ├── pipeline.py
│   │   ├── pipeline_io.py   IngestionOutput / TestCaseOutput / ExecutionOutput / PipelineReport
│   │   └── stage_config.py  🆕 Stage config request/response schemas (V2)
│   │
│   ├── services/             🆕 (V2)
│   │   ├── export_service.py     HTML + DOCX export orchestration
│   │   └── docx_builder.py       DOCX builder using python-docx
│   │
│   ├── tasks/
│   │   ├── testcase_tasks.py     10 task factories for Crew 2
│   │   ├── execution_tasks.py    5 task factories for Crew 3
│   │   └── reporting_tasks.py    3 task factories for Crew 4
│   │
│   ├── templates/            🆕 (V2)
│   │   └── report.html.j2       Jinja2 HTML report template
│   │
│   ├── tools/
│   │   ├── document_parser.py    Multi-format document reader
│   │   ├── text_chunker.py       Overlapping text chunker
│   │   ├── api_runner.py         httpx-based APIRunnerTool
│   │   └── config_loader.py      Env resolution ConfigLoaderTool
│   │
│   ├── config.py             Pydantic-settings application config
│   └── main.py               FastAPI app factory + lifespan hooks (mounts 6 routers in V2)
│
├── tests/                    pytest test suite
├── uploads/                  Uploaded requirement documents (gitignored)
├── pyproject.toml            Project metadata + dependencies (uv)
├── uv.lock                   Locked dependency tree
├── Dockerfile                Production container image
└── README.md                 This file
```

---

## License

MIT © Auto-AT Project