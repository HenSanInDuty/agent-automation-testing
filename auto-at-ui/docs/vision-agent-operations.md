# Vision agent operational runbook

## Local evaluation only

Vision exploration is disabled by default. Before a local evaluation, use an
evaluation-only Hugging Face token with the smallest practical scope and place
it only in local secret configuration as `HUGGINGFACE_API_KEY`. Never put a
token in tenant settings, reports, browser requests, logs, fixtures, or source
control. The approved local candidate is `Qwen/Qwen3.8-27B:deepinfra` at
`1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`; verify that the deployment endpoint
resolves this exact revision before enabling a tenant policy.

The temporary-image adapter supports My Drive through
`GOOGLE_DRIVE_OAUTH_CLIENT_ID`, `GOOGLE_DRIVE_OAUTH_CLIENT_SECRET`, and
`GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN`; set `GOOGLE_DRIVE_VISION_FOLDER_ID` to a
folder owned by that OAuth user. Shared Drive service-account credentials are
also supported, but require a deployment-specific secret-file mount. Each
verified screenshot is shared by an
unlisted public link only for the model request, then deleted; neither the URL
nor image is saved in application records or logs.

For My Drive OAuth, no credential-file mount is required by the supplied local
Compose configuration.

Run the fixture-only checks before any provider call:

```bash
uv run pytest tests/test_vision_benchmark.py tests/test_vision_executor.py
```

The manifest at `benchmark/vision/v1/manifest.json` contains synthetic
fixtures only. Store aggregate metrics, fixture identifiers, model revision,
dataset version, and correlation IDs; do not store raw screenshots, prompts,
or provider output in reports.

## Consent and disablement

A tenant administrator must explicitly acknowledge raw screenshot transfer to
Hugging Face before enabling vision. The policy is tenant-scoped. To stop
future exploration immediately, disable the tenant's Vision policy in
`/agent`; this preserves prior runs and does not alter any deterministic test
result. Do not delete artifacts to enact a kill switch.

## Guardrails and incident response

## Advisory session progress

The Advisory session timeline is server-owned, session-scoped operational
evidence. A project reader can retrieve its safe history or connect to its SSE
stream; the dashboard falls back to bounded polling if streaming fails. It is
not model reasoning, raw visual evidence, a prompt, typed action text, provider
output, diagnostics, or a deterministic test verdict. Progress is authorized
against the exploration session's project, never a caller-provided correlation
ID. Monitor aggregate stream connections, fallback activation, safe-stage
counts, unauthorized attempts, and activity write/query failures only.

Keep concurrency, steps, screenshot bytes, session duration, request rate, and
cost caps at their disabled-by-default local values until a benchmark gate is
approved. Investigate `unavailable` outcomes using the correlation ID and safe
activity/audit records. On suspected prompt injection, privacy exposure, cost
spike, or provider incident: disable the tenant policy, retain only the normal
artifact-retention evidence, review correlation-linked audit/activity events,
and roll back to the last approved immutable model revision. Do not retry by
raising limits or bypassing consent.

## Visual replay evidence

Verified state screenshots retained for visual replay are private RustFS evidence,
not temporary provider images or normal run artifacts. They persist without an
automatic expiry until a tenant administrator explicitly deletes a frame or the
whole replay. Readers need project `READ` authorization and receive image bytes
only through the authorized control-plane route; storage keys, URLs, prompts,
typed text, and provider output must never appear in API responses, logs,
activity events, audit detail, tickets, or dashboards.

Production retention of screenshots indefinitely remains gated on privacy/legal
approval. Do not enable it for production data, choose a data region, or alter
the existing consent/provider/cost limits without the corresponding approval.

## Production diagnostic evidence

Rejected Vision candidate batches may create a separate, privileged diagnostic record.
This is not normal Vision evidence: it contains only redacted, bounded model text and
allow-listed metadata, encrypted before persistence. It never contains screenshots,
prompts, temporary image URLs, credentials, provider request bodies, or exception text.

Inject `VISION_DEBUG_EVIDENCE_ENCRYPTION_KEY` and
`VISION_DEBUG_EVIDENCE_KEY_ID` through the approved production secret boundary. The
key must be distinct from `VISION_INTENT_ENCRYPTION_KEY`; no secret manager, cloud, or
KMS vendor is implied by these variable names. Capture is safely unavailable when the
current key or key ID is absent. Evidence expires exactly seven days after capture;
the cleanup worker deletes it without needing the key.

Only an authenticated, non-service `tenant_admin` may request diagnostic metadata or
payload through the no-store endpoint. Every allowed, denied, unavailable, capture,
and cleanup outcome is audited using IDs and safe event codes only. Never paste a
payload, ciphertext, prompt, screenshot, URL, or secret-shaped value into logs,
Grafana, tickets, or activity events.

For rotation, deploy readers with the retired values in
`VISION_DEBUG_EVIDENCE_PREVIOUS_ENCRYPTION_KEY` and
`VISION_DEBUG_EVIDENCE_PREVIOUS_KEY_ID`, verify a synthetic old record can be read in
the rotation window, then switch the injected current key and key ID. Do not remove the
retired values until all records using them have expired.
For a suspected key or data incident, disable Vision diagnostic capture/read access,
preserve records for scheduled deletion, investigate only safe audit codes, and do not
blindly rotate or delete evidence during the incident.

Before enabling a canary tenant: apply Alembic migrations, verify the two injected
variables, exercise a synthetic secret-redaction and unauthorized-read smoke test,
confirm cleanup metrics, and verify no payload appears in logs or Grafana. Monitor
capture counts by diagnostic code, encryption/redaction failures, allowed/denied
reads, and expiry deleted/failed/overdue counts. Alert when cleanup lag exceeds 24
hours, any key/decryption mismatch occurs, cleanup failures persist, or plaintext
payload-log detection is nonzero. Labels must not include tenant IDs, session IDs,
correlation IDs, payloads, ciphertext, prompts, screenshots, URLs, or exception text.
