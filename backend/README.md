# Auto-AT Backend

> **Auto-AT** — Multi-Agent Automated Testing System  
> FastAPI REST/WebSocket server + CrewAI 4-crew pipeline

---

## Overview

Auto-AT Backend orchestrates a **CrewAI multi-agent pipeline** that takes a requirements document (PDF, DOCX, XLSX, or TXT) and automatically produces a complete test suite — from requirement parsing all the way through test execution and final reporting.

```
Upload Document
      │
      ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐    ┌──────────────────┐
│ Ingestion Crew  │───▶│ Test-Case Crew   │───▶│ Execution Crew  │───▶│ Reporting Crew   │
│  (parse + chunk │    │  (generate test  │    │  (run tests +   │    │  (aggregate +    │
│   requirements) │    │   cases + steps) │    │   capture logs) │    │   export report) │
└─────────────────┘    └──────────────────┘    └─────────────────┘    └──────────────────┘
```

The REST API exposes pipeline management, real-time WebSocket progress streaming, and admin endpoints for configuring LLM profiles and per-agent overrides.

---

## Prerequisites

| Tool | Minimum Version | Notes |
|------|----------------|-------|
| Python | 3.11+ | 3.12 recommended |
| [uv](https://github.com/astral-sh/uv) | 0.4+ | Fast Python package manager |
| SQLite | bundled with Python | Default database; swap for Postgres in prod |

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
# Edit .env — at minimum set DEFAULT_LLM_API_KEY

# 4. Start the development server (auto-reload)
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

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./auto_at.db` | SQLAlchemy database URL; supports SQLite and PostgreSQL |

### Default LLM Fallback

Used when no LLM profile is marked `is_default=true` in the database.

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_LLM_PROVIDER` | `openai` | LLM provider (e.g. `openai`, `anthropic`, `ollama`) |
| `DEFAULT_LLM_MODEL` | `gpt-4o` | Model identifier |
| `DEFAULT_LLM_API_KEY` | _(empty)_ | API key for the default provider |
| `DEFAULT_LLM_BASE_URL` | _(empty)_ | Custom base URL (for Ollama, LiteLLM proxies, etc.) |
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

### Seeding

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_SEED` | `true` | Automatically seed default LLM profiles and agent configs on first startup |

---

## API Endpoints

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Returns service status, version, env, and DB connectivity |
| `GET` | `/` | Root — redirects to API info |

### Pipeline

All pipeline routes are mounted under `/api/v1`.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/pipeline/runs` | Start a new pipeline run; accepts a multipart file upload + config options |
| `GET` | `/api/v1/pipeline/runs` | List all pipeline runs (paginated, filterable by status) |
| `GET` | `/api/v1/pipeline/runs/{run_id}` | Get full details of a single run |
| `DELETE` | `/api/v1/pipeline/runs/{run_id}` | Delete a run and its associated files |
| `POST` | `/api/v1/pipeline/runs/{run_id}/cancel` | Request cancellation of an in-progress run |
| `GET` | `/api/v1/pipeline/runs/{run_id}/results` | Retrieve structured results (test cases, execution logs, report) |

### WebSocket

| Path | Description |
|------|-------------|
| `WS /ws/pipeline/{run_id}` | Real-time progress stream for a running pipeline — emits JSON events as each crew stage progresses |

### Admin — LLM Profiles

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/llm-profiles` | List all LLM profiles (API keys masked) |
| `POST` | `/api/v1/admin/llm-profiles` | Create a new LLM profile |
| `GET` | `/api/v1/admin/llm-profiles/{id}` | Get a single profile |
| `PUT` | `/api/v1/admin/llm-profiles/{id}` | Update a profile (partial update supported) |
| `DELETE` | `/api/v1/admin/llm-profiles/{id}` | Delete a profile |
| `POST` | `/api/v1/admin/llm-profiles/{id}/set-default` | Mark a profile as the global default |
| `POST` | `/api/v1/admin/llm-profiles/{id}/test` | Send a test prompt and measure latency |

### Admin — Agent Configs

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/agent-configs` | List all agent configurations |
| `GET` | `/api/v1/admin/agent-configs/{id}` | Get a single agent config |
| `PUT` | `/api/v1/admin/agent-configs/{id}` | Update an agent's role, goal, backstory, or LLM override |
| `POST` | `/api/v1/admin/agent-configs/reset` | Reset all agent configs to factory defaults |

### Chat

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/chat/profiles` | List available LLM profiles for the chat UI |
| `POST` | `/api/v1/chat/send` | Send a message list and stream the response as SSE (`text/event-stream`) |

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

# Generate a new Alembic migration
uv run alembic revision --autogenerate -m "describe your change"

# Apply all pending migrations
uv run alembic upgrade head

# Downgrade one migration
uv run alembic downgrade -1

# Type-check with mypy (if installed)
uv run mypy app/

# Format code with ruff
uv run ruff format app/ tests/

# Lint with ruff
uv run ruff check app/ tests/
```

---

## Architecture Overview

### 4 Crews × ~18 Agents

Auto-AT is structured as four sequential CrewAI crews. Each crew contains a set of specialized agents that collaborate via tasks to produce a structured output which is passed as input to the next crew.

```
backend/app/
├── crews/
│   ├── ingestion_crew.py     ← Crew 1
│   ├── testcase_crew.py      ← Crew 2
│   ├── execution_crew.py     ← Crew 3
│   ├── reporting_crew.py     ← Crew 4
│   └── base_crew.py          ← Shared base class
│
├── agents/
│   ├── ingestion/            ← Ingestion agents
│   ├── testcase/             ← Test-case generation agents
│   ├── execution/            ← Test execution agents
│   └── reporting/            ← Reporting agents
│
├── tasks/                    ← CrewAI task definitions
├── tools/                    ← Custom CrewAI tools (file parsers, etc.)
├── api/v1/                   ← FastAPI route handlers
├── core/                     ← LLM factory, pipeline orchestrator
├── db/                       ← SQLAlchemy models, CRUD, seed data
├── schemas/                  ← Pydantic request/response models
└── config.py                 ← Pydantic-settings configuration
```

#### Crew 1 — Ingestion

Parses the uploaded requirements document and produces structured, chunked requirement objects.

| Agent | Responsibility |
|-------|---------------|
| Document Parser | Extracts raw text from PDF / DOCX / XLSX / TXT |
| Requirement Analyzer | Identifies and classifies individual requirements |
| Chunk Organizer | Splits large documents into manageable chunks with context preservation |

#### Crew 2 — Test-Case Generation

Transforms structured requirements into detailed, executable test cases.

| Agent | Responsibility |
|-------|---------------|
| Test Strategist | Selects appropriate testing strategies per requirement type |
| Test Case Writer | Generates test case title, objective, preconditions, and steps |
| Edge Case Finder | Identifies boundary conditions and negative test scenarios |
| Coverage Validator | Ensures all requirements are covered by at least one test case |
| Test Prioritizer | Assigns priority and estimated effort to each test case |

#### Crew 3 — Execution

Simulates or runs the generated test cases and captures outcomes.

| Agent | Responsibility |
|-------|---------------|
| Test Runner | Executes test steps sequentially and records pass/fail |
| Log Collector | Captures execution logs, timestamps, and error messages |
| Defect Detector | Identifies failed assertions and classifies defect severity |
| Retry Handler | Re-runs flaky or inconclusive tests with adjusted parameters |

#### Crew 4 — Reporting

Aggregates execution results into a human-readable test report.

| Agent | Responsibility |
|-------|---------------|
| Metrics Aggregator | Computes pass rate, coverage %, and execution time statistics |
| Report Writer | Produces a structured Markdown / HTML test report |
| Summary Generator | Creates an executive summary with key findings and recommendations |
| Export Formatter | Formats the report for download (Markdown, JSON) |

### Database Schema (SQLite / PostgreSQL)

```
llm_profiles          — Named LLM configurations with encrypted API keys
agent_configs         — Per-agent role / goal / backstory / LLM overrides
pipeline_runs         — Run metadata, status, timestamps, uploaded filename
pipeline_results      — Structured JSON output from each crew stage
```

### Real-Time Progress via WebSocket

When a pipeline run is in progress, the frontend connects to `WS /ws/pipeline/{run_id}`. The backend broadcasts JSON events of the following shape:

```json
{
  "event": "stage_update",
  "stage": "testcase",
  "status": "running",
  "progress": 42,
  "message": "Test Case Writer is generating scenarios…",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

---

## Dependency Notes

### crewAI on Windows

`crewai` pulls in `lancedb` as a transitive dependency (via `chromadb`).
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

---

## Docker

```bash
# Build and run both services
docker compose up --build

# Backend only
docker compose up backend

# View backend logs
docker compose logs -f backend
```

See [`docker-compose.yml`](../docker-compose.yml) at the project root for the full configuration.

---

## Project Structure

```
backend/
├── app/
│   ├── agents/           CrewAI agent definitions (4 sub-packages)
│   ├── api/v1/           FastAPI route handlers
│   ├── core/             LLM factory, pipeline orchestrator, utilities
│   ├── crews/            CrewAI crew classes (4 crews)
│   ├── db/               SQLAlchemy models, CRUD helpers, seed data
│   ├── schemas/          Pydantic I/O schemas
│   ├── tasks/            CrewAI task definitions
│   ├── tools/            Custom CrewAI tools
│   ├── config.py         Application settings (pydantic-settings)
│   └── main.py           FastAPI app factory + lifespan
├── tests/                pytest test suite
├── uploads/              Uploaded requirement documents (gitignored)
├── pyproject.toml        Project metadata + dependencies (uv)
├── uv.lock               Locked dependency tree
├── Dockerfile            Production container image
└── README.md             This file
```

---

## License

MIT © Auto-AT Project