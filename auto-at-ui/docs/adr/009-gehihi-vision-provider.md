# ADR-009: Gehihi as an opt-in Gemini Vision provider

- Status: Accepted for local synthetic evaluation; live canary not run
- Date: 2026-10-17
- Supplements: ADR-007 (HF model) and ADR-008 (HF image delivery)

The user selected Google Gemini, displayed as **Gehihi (Google Gemini)**, with
model `gemini-3.8-flash`. Keep technical provider ID `gemini`; retain Hugging Face
and disabled defaults. This decision applies only to Vision, including legacy
and v4 orchestration. General text generation, draft approval and deterministic
execution remain separate.

Use the existing `httpx` dependency against Google's fixed OpenAI-compatible
chat-completions endpoint. Send bounded PNG screenshots inline, JSON-object output
and low reasoning effort. Gemini does not construct a Drive store or use HF
credentials. HF retains its existing Drive/OAuth transport and retention rules.
As amended on 2026-10-23 following user authorization, Gemini retries only HTTP
500/502/503/504, with at most three attempts per candidate request. Backoff is
1 then 2 seconds plus up to 0.5 seconds jitter, respecting Retry-After when present.
All attempts and waits share the existing request/session deadline (at most 120
seconds). A retry that cannot fit its wait is skipped. Authentication, quota,
invalid output, transport errors and timeouts are not retried. There is no provider
fallback or redirect, and browser operations are never replayed by this retry.
Each attempt sends the same bounded payload to the consented provider; per-attempt
token limits remain unchanged, so worst-case provider request/token exposure can
be up to three times one attempt. No monetary reservation is implied. Logs record
only retry status, attempt number and delay, never provider bodies or screenshots.

Official documentation rechecked on 2026-10-17 confirms the model ID, image input
and structured output, and documents low reasoning. The stable name is not an
immutable weights snapshot. See [model capabilities](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)
and [inline images and compatibility](https://ai.google.dev/gemini-api/docs/openai).
This check does not establish account availability or real-model accuracy.

`GEMINI_API_KEY` remains server-only in centralized Settings. Catalogue
`configured` means a nonblank key exists, not that it works or quota remains.
The API and worker share the existing deployment secret boundary. No secret
enters tenant JSON, dashboard inputs, audit snapshots or ordinary diagnostics.

Consent is bound to the recipient through `raw_screenshot_transfer_provider`.
Old boolean consent applies only to HF. Switching providers resets consent and
enablement. Dashboard confirmation freezes saved provider/model and submits an
expected pair; a stale pair receives 409 before session creation. Session
snapshots and fresh policy checks prevent switching an active session's recipient.
Already sent requests cannot be recalled.

Raw image pixels can contain personal data and secrets; text redaction is not
pixel anonymization. Use approved synthetic fixtures only. Google's free-tier
data-use terms include product improvement; quota depends on the account/project.
Review [pricing and data use](https://ai.google.dev/gemini-api/docs/pricing) and
[project rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) before a
canary. Do not enable billing or claim zero cost from application metadata.

Tenant RBAC, correlation, before/after policy audit snapshots, encrypted debug
evidence and existing artifact retention continue unchanged. Step/token/byte/rate
and deadline guards remain enforced. `max_cost_usd` is compatibility metadata;
there is no monetary reservation or project-wide quota accounting. Provider errors
use safe codes and preserve partial traces; they never pass a deterministic test.

No DB migration, new SDK, new runner contract or prompt change is required. New
policy JSON is incompatible with the old `extra=forbid` runtime. Before downgrading,
disable/drain, back up scoped non-secret overrides and convert each affected policy
to disabled HF with its former model, removing the new binding field and clearing
Google consent. Preserve unrelated runtime sections and historical evidence.
The [runbook](../vision-agent-operations.md#gehihi-google-gemini-local-setup)
defines deployment order and rollback verification.

Acceptance uses [mocked HTTP and local browser/SQL fixtures](../../benchmark/vision/gehihi/README.md).
Live quota, quality and token sufficiency remain canary questions. Production
deployment, cloud/auth selection and new retention/SLO decisions are out of scope.
