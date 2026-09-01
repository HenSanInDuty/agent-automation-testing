# Local threat model

**Scope:** the local, first-release Web UI slice. This is a provider-neutral
baseline, not a production security approval.

## Assets and trust boundaries

The control plane owns run records, approvals, audit events, and the outbox in
PostgreSQL. The Playwright worker is trusted only to execute a versioned
`TestExecutionRequest` and return its observed `TestExecutionResult`.
RustFS stores binary evidence; it is not an authorization source. The agent may
read a bounded, redacted evidence bundle and create a proposal, but cannot
change source code, a test suite, an approval, or a runner verdict.

In local development there is one trusted developer and no enabled tenant
identity provider. Multi-tenant authorization is therefore deferred; no local
assumption may become a production authorization rule.

## Threats and required controls

| Threat | Local control | Production decision still required |
| --- | --- | --- |
| Cross-tenant access to runs, evidence, or proposals | Keep tenant identity as an application boundary; do not rely on dashboard filtering. Local mode has one trusted developer. | Identity provider, RBAC roles, tenant model, and authorization tests. |
| Secrets or PII leak through logs, artifacts, or agent input | Keep secrets in runtime configuration only; redact headers, cookies, URLs, form/JSON fields, and logs before storage or agent use. Never commit `.env`. | Secret manager, data classification, retention, access review, and redaction evaluation. |
| Artifact URI disclosure or tampering | Store artifact metadata with checksum; treat URIs as untrusted references and restrict local bucket access to the local stack. | Signed access, per-tenant authorization, encryption, lifecycle/deletion policy. |
| Agent changes a test or masks a failure | Agent output is a structured proposal only. `may_apply_proposal` requires an explicit matching approval; runner is sole verdict authority. | Named principals, immutable approval persistence, prompt/tool allowlists, and LLM governance ADR. |
| Duplicate API delivery or workflow retry creates duplicate work | Every command/event uses an idempotency key; persist the run and outbox atomically. Retry only transient/infrastructure errors, never known functional failures. | Durable workflow implementation and duplicate/timeout integration tests. |
| Lost or untraceable action | Carry `correlation_id` from API through worker, artifacts, agent proposal, and audit event; audit records are append-only. | OpenTelemetry exporter, tamper-resistant audit retention, and monitoring/SLO policy. |
| Untrusted test content attacks the worker or local machine | Execute only version-pinned test revisions with bounded timeouts; do not grant agents arbitrary shell, database, browser-profile, or repository access. | Worker isolation, network egress policy, sandbox/image-pinning design. |

## Failure behaviour

A functional test failure is stored as the runner reported it. AI triage may be
unavailable, malformed, over budget, or rejected; in every case the stored
runner result remains unchanged. An approved healing proposal must cause a new,
versioned deterministic run. Only that new runner result can validate the
healing.

## Explicit deferrals

This document does not select an LLM provider/model, identity provider,
workflow engine deployment, cloud/tenant model, or production retention and
deletion period. Those decisions require explicit user direction and an ADR
before the corresponding production-like phase.
