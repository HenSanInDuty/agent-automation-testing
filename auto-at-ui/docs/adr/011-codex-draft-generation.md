# ADR-011: Explicit Codex / Hugging Face draft generation

- Status: Accepted for local implementation
- Date: 2026-10-25
- Extends ADR-010; user selected Codex and requested a Hugging Face switch.

Draft generation has its own tenant-admin provider selection under
`agent.runtime.v1.generation`. Existing tenants retain their prior text provider
until changed. Codex uses the existing account and pinned `gpt-6-luna`; Hugging
Face retains the configured model. The dashboard exposes explicit buttons,
provider-specific text-transfer consent and a save action. Each provider's model
is remembered. Exploration and triage selections remain independent.

Codex receives bounded redacted task text and immutable branch/observation IDs;
generation sends no screenshots, credentials, raw DOM, or locator bindings. Target
URL queries/fragments are omitted. Free-text redaction is not a general PII
classifier: use approved synthetic data for local evaluation. The same isolated,
qualified bridge consumes a separate `.generation` queue sequentially with DOM
jobs, using immutable centralized generation instructions and no callable tools.

Requests have tenant/project/correlation/request IDs, input and policy hashes,
a maximum 120-second deadline, at most 100 KB input and 64 KiB model output, and
short renewable authorization. Policy changes or cancellation stop the owned CLI
process group; no provider/model fallback or automatic retry occurs. Existing
account limits apply; neither CLI call count nor token hints are a hard dollar
ceiling. Existing submission rate limits and the single bridge consumer apply.

A unique `generation.codex.call.v1.<request-id>` reservation in tenant-scoped
configuration commits with an audit event before publication. It contains only
safe identifiers/hashes/model metadata. It prevents a worker rollback, restart or
spool cleanup from launching the same generation request twice. A deliberate new
request is needed after interruption. Inputs are purged after processing and
transient jobs expire; reservations and draft audit/provenance use existing
tenant data lifecycle rules, with no new production retention period.

Both text drafts and Vision selections pass the existing strict contract parser.
Vision code is still rendered deterministically from verified evidence; unbound
inputs remain blocked. Drafts are pending human review. TestExecutionRequest /
TestExecutionResult v1 and deterministic verdict ownership do not change.

Offline validation covers both provider choices, tenant/RBAC/CSRF boundaries,
policy revocation, immutable instructions, duplicate claims, input integrity,
private root/non-root handoff and pending-review drafts. Offline tests do not
establish live account quota or model access. Deployment requires compatible API,
worker and bridge images before changing the tenant generation selection.
