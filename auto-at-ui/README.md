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
| Workflow engine | Temporal | Local self-hosted development backend for durable run dispatch; production deployment remains undecided. |

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

Docker Compose also starts a local Temporal Server and UI at `http://localhost:8080`.
Temporal is behind a dedicated workflow adapter; production may use Temporal Cloud,
self-hosted Temporal, or another implementation without changing the HTTP or runner
contracts.

## Run a basic pipeline

This local path creates one deterministic run, records a passed result, and
inspects its correlated evidence. It uses the self-hosted stack and local RBAC
adapter only; do not use the development actor headers outside local mode.

1. Start services and apply migrations:

   ```bash
   docker compose up -d --build
   docker compose exec -T control-plane uv run --no-sync alembic upgrade head
   ```

2. Seed the project and test case expected by the collection. The commands are
   idempotent and use the default local credentials from `docker-compose.yml`:

   ```bash
   docker compose exec -T postgres psql -U auto_at -d auto_at -c "INSERT INTO projects (id, tenant_id, name, default_target) VALUES ('11111111-1111-4111-8111-111111111111', 'demo-tenant', 'Postman demo', 'web_ui') ON CONFLICT (id) DO UPDATE SET tenant_id = EXCLUDED.tenant_id, name = EXCLUDED.name, default_target = EXCLUDED.default_target;"
   docker compose exec -T postgres psql -U auto_at -d auto_at -c "INSERT INTO test_cases (id, tenant_id, project_id, target_type, revision, specification) VALUES ('demo-healthz', 'demo-tenant', '11111111-1111-4111-8111-111111111111', 'web_ui', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', '{}'::jsonb) ON CONFLICT (id) DO UPDATE SET tenant_id = EXCLUDED.tenant_id, project_id = EXCLUDED.project_id, target_type = EXCLUDED.target_type, revision = EXCLUDED.revision, specification = EXCLUDED.specification;"
   ```

3. Import [the Phase 6 Postman collection](docs/hoppscotch/auto-at-phase-1.postman_collection.json).
   Keep its default local variables, then send these requests in order:

   - `Health and operations / Health check`
   - `Basic deterministic pipeline / Create run` — this saves `run_id` and
     `correlation_id` as collection variables.
   - `Get correlated run`, `Record passed deterministic result`, then `List run artifacts`.
   - `Operations summary` confirms the audited tenant-visible totals.

Use `Proposal review` only with an existing proposal ID. Its reviewer header is
intentional: a service identity cannot approve or reject a proposal.

## Repository layout

```text
apps/control-plane/       FastAPI API and orchestration boundary
apps/dashboard/           Next.js dashboard (placeholder)
workers/playwright/       TypeScript Playwright execution adapter
packages/contracts/       Target-neutral Python runner contracts
docs/                     Architecture and ADRs
```
