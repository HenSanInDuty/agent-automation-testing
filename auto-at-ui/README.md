# Auto-AT Platform

Production-oriented multi-agent testing platform. The platform keeps execution deterministic while agents assist with planning, generation, failure triage, and reviewable healing proposals.

## Architecture decision

- **Python + uv**: control plane, API, workflow activities, agents, evaluation, API and game adapters.
- **TypeScript**: dashboard and the Playwright browser worker.
- **Adapter model**: Web UI, API, and Game targets implement the same runner contract; Playwright is not the platform core.
- **Deterministic execution**: agents never mark a failed test as passed or mutate test suites without an approved change.

See [architecture.md](docs/architecture.md) and [ADR-001](docs/adr/001-platform-architecture.md).

## Local development

Install [uv](https://docs.astral.sh/uv/) and Node.js 22+, then:

```bash
uv sync --all-groups
uv run uvicorn main:app --reload --app-dir apps/control-plane
```

Open `http://127.0.0.1:8000/docs`. Run checks with:

```bash
uv run ruff check .
uv run pytest
```

Start local backing services when they are needed:

```bash
docker compose up -d postgres redis minio
```

Temporal is deliberately an external dependency in this first scaffold. Use Temporal Cloud for production or its official self-hosted deployment chart; the control plane will integrate through a dedicated workflow module rather than exposing workflow state as application state.

## Repository layout

```text
apps/control-plane/       FastAPI API and orchestration boundary
apps/dashboard/           Next.js dashboard (placeholder)
workers/playwright/       TypeScript Playwright execution adapter
packages/contracts/       Target-neutral Python runner contracts
docs/                     Architecture and ADRs
```
