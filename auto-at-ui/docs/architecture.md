# Architecture

## Objective

Provide a production platform that plans, dispatches, executes, and audits automated tests across Web UI, API, and Game targets.

## Boundaries

| Layer | Responsibility | Technology |
|---|---|---|
| Control plane | API, tenancy, RBAC, test catalog, scheduling, audit | Python, FastAPI, PostgreSQL |
| Workflow plane | Durable dispatch, retries, timeouts, approvals | Temporal |
| Intelligence plane | Plan, generate, triage, evaluate, propose changes | Python agent services |
| Execution plane | Isolated, version-pinned test runs | Kubernetes workers and runner adapters |
| Evidence plane | Traces, video, screenshots, reports, telemetry | S3-compatible storage, OpenTelemetry |

## Runner contract

Every runner consumes a `TestExecutionRequest` and emits a `TestExecutionResult`. Target-specific configuration lives in a typed adapter payload, while project, environment, correlation ID, artifact policy, and result semantics remain common.

Initial adapters:

- `web_ui`: Playwright TypeScript worker.
- `api`: Python HTTP/OpenAPI adapter.
- `game`: Unity/Unreal integration plus optional black-box input/CV adapter.

## Production safeguards

- Version-pin test revision, runner image, browser/build, environment and dataset per run.
- Treat PostgreSQL as application source of truth; Temporal owns workflow execution history.
- Redact secrets and PII from logs, requests, responses and LLM prompts.
- Store failure artifacts by default and apply lifecycle policies.
- Require human approval for generated or healed test changes.
- Propagate `correlation_id` through API, workflow, agent, runner, and artifact events.

