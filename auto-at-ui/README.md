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

Start the complete local stack (control plane, dashboard, PostgreSQL, Redis, and MinIO):

```bash
docker compose up --build
```

The control-plane API is available at `http://localhost:7000/docs`, the dashboard at
`http://localhost:3000`, PostgreSQL at `localhost:5432`, Redis at `localhost:6379`,
and the MinIO console at `http://localhost:9001`. Docker Compose creates the
`auto-at-artifacts` bucket before starting the control plane. Copy `.env.example` to
`.env` to override local credentials, ports, or the Ollama endpoint.

Docker Compose also starts a local Temporal Server and UI at `http://localhost:8080`.
Temporal is behind a dedicated workflow adapter; production may use Temporal Cloud,
self-hosted Temporal, or another implementation without changing the HTTP or runner
contracts.

## Move local run data to another machine

To retain dashboard history and the evidence linked from it, export both the
PostgreSQL database and the execution-artifacts volume. The backup directory is
ignored by Git and may be copied to the destination machine by any secure transfer
method.

On the source machine:

```bash
mkdir -p auto-at-backup

docker run --rm \
  -v auto-at-ui_postgres-data:/source:ro \
  -v "$PWD/auto-at-backup":/backup \
  alpine tar czf /backup/postgres-data.tar.gz -C /source .

docker run --rm \
  -v auto-at-ui_execution-artifacts:/source:ro \
  -v "$PWD/auto-at-backup":/backup \
  alpine tar czf /backup/execution-artifacts.tar.gz -C /source .
```

On the destination machine, first clone the same repository revision and run
`docker compose up -d` once to create its volumes. Copy `auto-at-backup/` beside
the Compose file, then restore it while the application services are stopped:

```bash
docker compose stop control-plane dashboard temporal-worker

docker run --rm \
  -v auto-at-ui_postgres-data:/target \
  -v "$PWD/auto-at-backup":/backup:ro \
  alpine sh -c 'cd /target && tar xzf /backup/postgres-data.tar.gz'

docker run --rm \
  -v auto-at-ui_execution-artifacts:/target \
  -v "$PWD/auto-at-backup":/backup:ro \
  alpine sh -c 'cd /target && tar xzf /backup/execution-artifacts.tar.gz'

docker compose up -d
docker compose exec -T control-plane uv run --no-sync alembic upgrade head
```

Only these two volumes are needed for the dashboard's run history and linked
artifacts. Export the Temporal, Redis, or MinIO volumes separately only when their
own operational history or objects must also be retained.

## Bootstrap dashboard access

Apply migrations, then create the first tenant administrator. The password is
temporary and must satisfy the displayed policy; the first sign-in requires a
replacement password.

```bash
uv run python apps/control-plane/cli.py bootstrap-admin \
  --tenant demo-tenant --email admin@example.test
```

Open `http://localhost:3000/login`, sign in with the tenant, email, and
temporary password, then use **Admin → Users** to provision collaborators.
The temporary password is displayed once and is never persisted in the
dashboard. Dashboard requests use an HttpOnly session cookie and CSRF token;
the legacy development identity headers remain only for local API compatibility.
See [session API examples](docs/api-examples.md) for cookie-based calls without
identity headers.

## Dashboard troubleshooting and security boundaries

- If the dashboard returns to sign-in, check that the control-plane and
  dashboard origins match the local Compose defaults, then sign in again; do
  not work around it by entering development identity headers in the browser.
- The pipeline timeline reconnects through polling when SSE is unavailable.
  It shows only server-redacted activity summaries and cannot affect a run
  verdict.
- Evidence links are authorized, run-scoped downloads. Generated drafts and
  healing proposals remain advisory until the relevant human decision is
  accepted by the control plane; neither agents nor the dashboard can change a
  deterministic result.

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
   - `Get correlated run`, then `List run artifacts`.
   - `Operations summary` confirms the audited tenant-visible totals.

Use `Proposal review` only with an existing proposal ID. Its reviewer header is
intentional: a service identity cannot approve or reject a proposal.

## Generate, review, and run a Playwright test

The generated-test flow is advisory until a human approves the draft. It never
changes a source repository and the Playwright worker remains the sole authority
for the test verdict.

1. Configure a non-secret local credential for the already-selected generation
   model gateway, start Compose, and apply migrations as described above. Use
   only a public target that is permitted by the project origin policy.

2. In the imported Postman/Hoppscotch collection, open `Governed test
   generation` and send `Set generation origin policy (administrator only)`.
   This normalizes and stores the target origin allowlist for the project.

3. Send `Submit generation request`. The response is accepted with a
   `generation_request_id`; it does not yet run a test. Send `Poll generation
   request` until its `state` is terminal:

   - `queued`: waiting for the generation worker.
   - `generating`: planner is producing a bounded draft.
   - `completed`: a `generated_draft_id` is available.
   - `failed`: inspect the safe `failure_reason`; it intentionally excludes
     provider diagnostics and secrets.

4. Send `Inspect generated draft`. Review `playwright_test_source`,
   `source_hash`, `assumptions`, `stop_conditions`, and `provenance`. Do not
   approve a draft whose assumptions or source do not meet the intended test.

5. For an acceptable draft, send `Approve draft and dispatch one v1 run`.
   The response is immutable and the collection stores `generated_test_case_id`
   and `generated_run_id`. To decline a different pending draft, use `Reject
   draft (immutable final decision)` instead. Contributors, project
   administrators, and tenant administrators can decide drafts; reviewer-only
   and service identities cannot.

6. Send `Get approved generated run` until the deterministic status is
   terminal, then send `List approved generated run evidence`. The artifacts
   contain the runner evidence (for example trace, screenshot, video, console,
   and network output) needed to inspect a failure. The same flow is available
   in the dashboard, which polls only `queued` and `generating` requests.

For live local diagnostics, follow the generation worker log:

```bash
docker compose logs -f temporal-worker
```

## Repository layout

```text
apps/control-plane/       FastAPI API and orchestration boundary
apps/dashboard/           Next.js dashboard for governed test review
workers/playwright/       TypeScript Playwright execution adapter
packages/contracts/       Target-neutral Python runner contracts
docs/                     Architecture and ADRs
```
