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

## Governed generation experience

The dashboard is a thin API client for the generated-test lifecycle. It submits
a project, allowed target URL, and natural-language request; polls only the
control-plane-owned request states; and renders the returned redacted request,
draft source/hash, provenance, assumptions, stop conditions, safe failure, and
linked deterministic evidence. It never applies redaction or authorization
rules in the browser. A decision request reaches the same immutable API flow
as all other clients; only the control plane can create the versioned test case
and its single v1 run.


## Vision locator traces

A visual proposal is advisory until the v4 worker verifies a unique live locator.
The application orchestrates fenced, short database transactions through the trace
unit-of-work port. Intent and before-frame commits precede dispatch; outcome and
after-frame commits precede staging acknowledgment. Remote browser/model/storage
I/O occurs outside the outbox publisher transaction. Recovery reconciles the same
operation and stops on unknown execution instead of repeating physical actions.

Checkpoints and immutable operation ancestry separate observed business branches
from back/restore/replay operations. The handoff and generation request commit
together. A centralized structured prompt can select only recorded branches and
assertion references; deterministic rendering supplies the verified locators.
Unbound typed inputs block affected branches. Existing explicit draft approval
creates the same target-neutral v1 execution request; the model cannot modify its
verdict. Results join session, handoff, generation, draft, run and report through
scoped identifiers. Trace images are authorized private evidence; metadata exports
and deletion tombstones preserve history without exposing storage keys.

`VISION_TRACE_V4_ENABLED` selects only new-session writers. Additive migration and
legacy/v4 readers allow rollback without rewriting sessions or deleting evidence.
See the [Vision runbook](vision-agent-operations.md) for ordering, limits and the
synthetic validation boundary.
