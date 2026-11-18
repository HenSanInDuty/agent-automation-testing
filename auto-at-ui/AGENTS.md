# Auto-AT Platform: assistant context and pre-flight checklist

Read this file before assisting with this repository.

## Product direction

This is a production-oriented multi-agent automation-testing platform, initially for Web UI and designed to expand to API and Game testing.

- Python is the control-plane language and **must use `uv`** for dependency management, virtual environments, locking, and commands.
- TypeScript is reserved for the dashboard and Playwright worker.
- The platform is runner-neutral: `web_ui`, `api`, and `game` are adapters behind shared contracts.
- Test execution is deterministic. LLM agents may plan, generate, triage, evaluate, and propose healing changes; they must not silently pass failures or change test suites without an approval mechanism.

Primary architecture records:

- `docs/architecture.md`
- `docs/adr/001-platform-architecture.md`
- `packages/contracts/src/auto_at/contracts/execution.py`

## Code organization rules

Keep the control plane under `apps/control-plane/` with one-way dependencies:

- `main.py` only creates the FastAPI application and registers routers; keep business logic out of it.
- `config.py` is the only module that reads environment variables or `.env`; pass `Settings` into dependent code.
- `api/` owns HTTP concerns only: request/response schemas, routing, and dependencies. Routes validate input, call an application use case, and return a response; they do not call databases, LangChain, or runners directly.
- `application/` owns use-case orchestration and may depend on domain ports and contracts.
- `domain/` contains pure business rules and models. It must not import FastAPI, persistence clients, LangChain, or cloud SDKs.
- `infrastructure/` implements database, queue, artifact, workflow, and external-service adapters behind interfaces used by the application layer.
- `agents/` contains LLM-assisted capabilities. Agents return structured, auditable proposals and must never change test suites or execution verdicts without an explicit approval flow.
- **Prompt management:** Every new or changed prompt sent to an LLM must be added or updated in `apps/control-plane/agents/prompts/`. Do not hard-code prompt text in callers, routes, application services, workers, or adapters; those components import the centralized prompt instead. Update the prompt directory README and its prompt version when the prompt's behavior changes.
- `runners/` dispatches target adapters and preserves the versioned `TestExecutionRequest` / `TestExecutionResult` contract.
- Shared runner and agent contracts belong in `packages/contracts/`; do not duplicate them in the control plane or workers.
- Add focused tests with each behavior change: pure unit tests for domain/application rules and HTTP tests for routes.

## Required checks before helping

1. Read `README.md`, this file, relevant ADRs, and the files directly related to the request.
2. Check the working tree with `git status --short`; preserve existing user changes.
3. For Python work, inspect `pyproject.toml` and `uv.lock`; use `uv run ...` and never introduce `pip`, `requirements.txt`, Poetry, or Conda without explicit approval.
4. For any change affecting execution, verify it preserves the target-neutral `TestExecutionRequest` / `TestExecutionResult` contract or version the contract deliberately.
5. For agent/LLM work, establish: model/provider, data classification, secret/PII redaction, cost and rate limits, evaluation data, approval boundary, audit trail, and fallback behavior before implementation.
6. For production/infrastructure work, establish: tenant isolation, RBAC, secrets source, artifact retention, observability/correlation IDs, SLOs, retry/idempotency semantics, and deployment environment.
7. For a new runner, establish: supported target, pinned runner/browser/game build version, isolated test data, artifact policy, timeout/retry semantics, and adapter contract compatibility.
8. Run the smallest relevant validation after changes. The baseline Python checks are:

   ```bash
   uv run ruff check .
   uv run pytest
   ```

## Assistant token budget and round handoff

- Run polling in one script/process; default to final-result output and emit only
  meaningful state changes when requested. For Vision use
  `uv run python scripts/watch_vision_session.py --help`. Do not alternate model
  turns between `sleep` and unchanged status queries. Keep individual tool waits
  at most 60 seconds; empty output needs no new investigation or repeated status prose.
- Keep complete logs and evidence on disk. Default tool output to 2,000 tokens;
  read targeted ranges or error summaries instead of entire logs, histories or
  tool inventories. Read unchanged documentation once per session.
- Review at most two relevant images per tool call, with a specific question for
  each comparison. Record image paths/checksums and findings in the review artifact;
  do not reload reviewed images without a new reason. Preserve all evidence and
  required independent reviews; output limits must not weaken scoring or validation.
- Finish one benchmark round, collect its evidence and record its result, then
  write a concise handoff in the canonical plan README: iteration/session IDs,
  source/config/oracle identity, changed files, checks, result, artifact paths,
  active processes and the exact next command. End the conversation turn at that
  boundary and continue the next round in a fresh session. This user preference
  overrides plan guidance to continue across rounds. Do not claim to have created
  a fresh session automatically or mark an incomplete plan complete.

## Boundaries requiring user direction

Ask before selecting a cloud provider, LLM provider/model, authentication provider, managed-vs-self-hosted Temporal deployment, production data retention period, or any action that can incur material cost or touch external production systems.

## Current scaffold status

- FastAPI control-plane exposes `/healthz` and `/api/v1/platform`.
- Local backing services are PostgreSQL, Redis, and RustFS via `docker-compose.yml`.
- Temporal, database migrations, authentication, agent services, runner transport, and actual dashboard pages are not yet implemented.
