# Auto-AT Platform

Production-oriented multi-agent testing platform. The platform keeps execution deterministic while agents assist with planning, generation, failure triage, and reviewable healing proposals.

## Architecture decision

- **Python + uv**: control plane, API, workflow activities, agents, evaluation, API and game adapters.
- **TypeScript**: dashboard and the Playwright browser worker.
- **Adapter model**: Web UI, API, and Game targets implement the same runner contract; Playwright is not the platform core.
- **Deterministic execution**: agents never mark a failed test as passed or mutate test suites without an approved change.

See [architecture.md](docs/architecture.md) and [ADR-001](docs/adr/001-platform-architecture.md).

## Tech stack

| Layer | Technology | Purpose |
| --- | --- | --- |
| Control plane | Python 3.12, FastAPI, Uvicorn | REST API, orchestration boundary, and platform health endpoints. |
| Python tooling | uv, Ruff, Pytest | Dependency locking, virtual environments, linting, and tests. |
| AI assistance | LangChain, LangChain Ollama | Agent-assisted planning and triage; deterministic execution remains outside the LLM. |
| Dashboard | Next.js 15, React 19, TypeScript | Web dashboard (currently a scaffold). |
| Web UI runner | Playwright, TypeScript | Browser automation adapter (currently a scaffold). |
| Primary database | PostgreSQL 17 | Source of truth for future application, tenancy, audit, and test data. |
| Cache / queue support | Redis 7 | Cache, coordination, and future background-job support. |
| Artifact storage | MinIO (S3-compatible) | Stores screenshots, videos, reports, and other execution artifacts in the `auto-at-artifacts` bucket. |
| Containers | Docker Compose | Runs the control plane and local backing services together. |
| Future workflow engine | Temporal | Planned durable workflow, retry, and approval orchestration; not included in the local stack yet. |

## Local development

Install [uv](https://docs.astral.sh/uv/) and Node.js 22+, then:

```bash
uv sync --all-groups
uv run uvicorn main:app --reload --app-dir apps/control-plane
```

Open `http://127.0.0.1:7000/docs`. Run checks with:

```bash
uv run ruff check .
uv run pytest
```

Start the complete local stack (control plane, PostgreSQL, Redis, and MinIO):

```bash
docker compose up --build
```

The control-plane API is available at `http://localhost:7000/docs`, PostgreSQL at
`localhost:5432`, Redis at `localhost:6379`, and the MinIO console at
`http://localhost:9001`. Docker Compose creates the `auto-at-artifacts` bucket before
starting the control plane. Copy `.env.example` to `.env` to override local credentials,
ports, or the Ollama endpoint.

Temporal is deliberately an external dependency in this first scaffold. Use Temporal Cloud for production or its official self-hosted deployment chart; the control plane will integrate through a dedicated workflow module rather than exposing workflow state as application state.

## Repository layout

```text
apps/control-plane/       FastAPI API and orchestration boundary
apps/dashboard/           Next.js dashboard (placeholder)
workers/playwright/       TypeScript Playwright execution adapter
packages/contracts/       Target-neutral Python runner contracts
docs/                     Architecture and ADRs
```
