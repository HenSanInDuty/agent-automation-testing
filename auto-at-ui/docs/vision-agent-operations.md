# Vision agent operational runbook

## Codex DOM-first sessions

Use the [local bridge runbook](codex-local-bridge.md) for container qualification,
opt-in Compose startup, migration order, failure diagnosis and scoped rollback.
See [Codex evaluation](../benchmark/vision/codex/README.md) for synthetic versus live evidence.

Codex is an optional v4 exploration provider using the existing account and pinned
Luna model. **Vision settings** shows bridge connectivity, login, compatibility,
model-access qualification and queue activity. A ready bridge with unverified
model access is not proof that the account can run the selected model.

Accept page-element/text transfer to OpenAI to enable DOM-first exploration.
Screenshot permission is separate and optional. Local transport does not mean
offline inference. If a page needs an image without permission or remaining calls,
the session stops and explains the limitation. Each image escalation consumes an
additional call within the same session deadline. Existing quota limits apply.

Dashboard live preview is independent of model image transfer. For an active v4
session, **Follow live** fetches a browser image immediately and then one second
after each completed request. Capture/network latency adds to that interval.
Keep optional OpenAI image transfer unchecked to test DOM proposals while viewing
images; preview makes no model calls. Terminal status or revoked access stops
polling. See the bridge runbook for startup commands and the preview test procedure.

The Website banner distinguishes waiting for the bridge, reading page elements,
requesting an image and checking proposals. Displayed call/elapsed values come
from recorded stage metadata. Browser steps and click highlights still require
verified worker evidence. Selecting an older step keeps its saved frame visible.
Delayed progress cannot reopen a terminal session. Reload confirms the current
saved provider, model and input-policy fingerprint and creates a new session.
An old Gemini/HF session retains its original provider. A cleanup-pending message
means cancellation is durable but temporary-file removal is not yet acknowledged.

## Exploration reports and partial coverage

Open **View exploration report** on a saved Vision session to see recorded
click/type actions, rejected actions, completed scrolls, unattempted candidates,
per-operation observations, the stopping reason and the session's saved limits.
**Download report JSON** uses the existing authorized result export. This report
is computed from retained trace metadata and is available for historical,
interrupted and cancelled sessions without invoking a model or creating a run.
It never labels observations as passing tests or asserts full page coverage.
The separate Playwright execution report still requires draft approval and a run.

An invalid model reply (`model_output_invalid`) creates no new actions. The v4
processor records `candidate.unavailable`, stops further model calls and drains
already validated queued candidates using normal restoration/locator checks and
existing time/state limits. The final session remains unavailable/partial. Provider
authentication, quota, policy, consent, unknown-action and restoration failures
retain their stop behavior. Invalid output is not retried. Gemini's bounded
transient HTTP retries are described below; session budgets are not increased.
Prompt v6 adds explicit normalized-coordinate arithmetic and short outcome text;
response validation and the 1000-token cap remain unchanged.

## External origins in v4 exploration

Vision follows external HTTP(S) navigation, redirects, popups, subresources and
WebSockets without using the deterministic runner origin allowlist as a gate.
The target origin is the reference site; other origins are recorded as
`origin.observed` events in the private, tenant-scoped activity log. Each entry
contains only the origin and request kind (navigation, popup, resource or
websocket), with no credentials, path, query or fragment. Duplicate origin/kind
pairs are collapsed; the session retains at most 100 pairs and emits an explicit
limit event if more are seen. Observations are collected after browser/model
steps and at completion, including failed explorations. The worker endpoint
requires the shared secret and matching tenant, project, session and fencing token.
The normal time, state/hop, action, screenshot, consent and approval limits still
apply. Legacy exploration and deterministic test-run policies are unchanged.
Deploy the API and both workers together for the additive private observation
contract; no execution request/result schema or database migration is changed.

## Live browser view

The Agent page opens Vision by default; a draft deep link opens its review instead.
The v4 workspace puts the website beside **Browser steps**. **New exploration**
opens the request form; **History** opens saved sessions. Settings, exploration
reports and technical details are collapsed. Progress still updates while details
are closed. Select a step to view its **Before** or **After** image in the same
viewer, then use **Return to live** to resume following.

The Website activity banner shows when the agent is waiting for a model response;
the page can remain still during this stage. If a worker or stack restart interrupts
a running session, its in-memory browser state cannot be resumed. The session ends
with `worker_state_unavailable` and the Website banner explains that the image is
the last saved screen. Use **Reload** to confirm a new session; retained evidence
from the interrupted session stays available. Avoid restarting workers during an
active exploration.

Each Vision model request may wait up to 120 seconds, bounded by the session's
remaining time. This does not extend the overall session: with a 120-second session
and 10 seconds already spent opening the page, the model can wait at most about
110 seconds. The limit applies to Gemini and Hugging Face Vision transports; text
generation keeps its existing timeout. Gemini retries HTTP 500/502/503/504 up to
two times (three attempts total), waiting 1 then 2 seconds plus up to 0.5 seconds
jitter, or longer when Retry-After requires it. Attempts and backoff share the same
deadline; retry is skipped if its wait cannot fit. Logs expose only HTTP status,
attempt and wait duration. The Website remains in its model-wait state during
backoff. Authentication, quota (429), invalid output, transport errors and timeouts
are not retried. Hugging Face still makes one attempt. No provider fallback or
browser-action replay occurs. Each retry resends the same image/prompt and retains
the per-attempt token cap; up to three provider calls may be charged per batch.

The dashboard polls the private `/api/v1/vision/explorations/{id}/screen` endpoint
once per second after each response. This is a live screenshot preview, not a
video recording. Safe progress events arrive through the existing SSE endpoint,
with five-second polling if the stream disconnects. Completed sessions show the
last retained page screenshot, or an explicit capture failure, without polling
the worker.

Confirmed clicks carry optional `executed_click` evidence: normalized viewport
coordinates, viewport dimensions, the operation's before-frame ID and confirmation
time. A yellow ring appears only over that retained before image after it loads.
The worker records this only after Playwright confirms the click; a later settling
failure can retain the point while the operation remains failed. Rejected, unknown
or historical operations without this evidence have no inferred click marker.
Transformed/zoomed, clipped, iframe or inconsistent viewport geometry may omit the
point. No coordinates are backfilled from proposals or bounding-box centers.

While following an active session, a newly observed confirmed click briefly shows
its recorded before image for 3 seconds after image load, then returns to live.
Trace refresh is normally five seconds, so this is not synchronized cursor video.
An initial history load or resuming Follow does not replay old clicks; a batch
previews only its newest click. Repeated polls do not repeat the animation. All
steps remain selectable for static replay. After images and arbitrary live images
never receive the earlier click's marker. Reduced motion disables the pulse.

The ring follows the displayed bitmap through resizing and letterboxing. A missing,
deleted, denied, undecodable or incompatible image receives no marker. Switching
steps or sessions cancels pending image work and discards the prior overlay.
The overlay is dashboard-only: target DOM, stored PNG bytes and execution verdicts
are unchanged. Frame authorization, private no-store fetches, consent and explicit
deletion remain as before.

For the additive click-evidence rollout, drain active local sessions and deploy
the updated control-plane/Temporal readers before the updated Playwright writer;
deploy the dashboard alongside them. No SQL migration is needed. New readers
accept historical payloads without the field. After new metadata has been stored,
keep compatible readers: older strict readers reject the added field. Rolling back
the UI is independent; never remove evidence to make a backend downgrade work.

Preview uses the same human project READ authorization as private evidence;
service principals cannot access it. Worker requests carry the server-side
secret, tenant/project/session scope and current fencing token. Captures are
read-only, capped at 2 MB (and the session screenshot limit), bounded by the
session deadline and a three-second capture timeout, and shared across viewers
for one second. Responses are `no-store`; preview bytes are held only in memory
and are not retained or sent to the model. The existing persisted evidence and
operation audit remain independent. Screenshots can contain target-page data.

Chromium viewport captures use CDP without waiting for web fonts. A missing
initial page capture stops with `initial_capture_failed` before any model call;
it cannot be treated as completed coverage. Reload creates a separate session
from the saved request and preserves the old operation history.

## Local evaluation only

Vision exploration is disabled by default. For the Hugging Face path, use an
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
unlisted public link for delivery. Per ADR-008,
`GOOGLE_DRIVE_VISION_DELETE_AFTER_DELIVERY=false` is the current default: files
remain until explicitly removed or their permission is revoked. Drive links
have no enforced TTL. The link is held only in memory, never saved in application
records or logs. Private replay/operation evidence is stored separately in RustFS.

For My Drive OAuth, no credential-file mount is required by the supplied local
Compose configuration.

If navigation succeeds but exploration stops before candidates arrive, inspect
the session completion reason. `image_delivery_auth_required` means Google
rejected the refresh grant with `invalid_grant`; no candidate model call or
button coverage was completed. Reauthorize the same OAuth client and account,
replace `GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN` in the local secret configuration,
recreate the consuming containers, and start a new session. A plain container
restart does not reload Compose environment values. Keep the previous trace.
For [OAuth Playground](https://developers.google.com/oauthplayground/), use your
own client credentials, register its URL as an authorized redirect URI, request
offline access with the existing Drive scope, and exchange the authorization
code for a refresh token. Never paste tokens into logs or tickets. External apps
in Testing receive Drive refresh tokens that expire after seven days; see
[Google's refresh-token expiration rules](https://developers.google.com/identity/protocols/oauth2#expiration).

Button exploration includes custom controls implemented with `div`/`span` when
the worker can identify an interactive ancestor and verify a unique supported
locator. Click handlers and pointer cursors supplement semantic roles; arbitrary
containers do not become verified controls. Prompts request distinct sibling
controls and scrolling for broad button checks. State, depth, time and model-call
limits still bound coverage; a completed navigation or exploration does not prove
every button works.

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
the selected provider before enabling vision. Consent is bound to that provider;
old HF consent does not authorize Google. The policy is tenant-scoped. To stop
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

Keep concurrency, steps, screenshot bytes, session duration and request rate
within the configured limits. Vision monetary cost fields remain compatibility
metadata; cost reservation, accounting and missing-price gating are not implemented
by the locator trace flow, as requested. Investigate `unavailable` outcomes using the correlation ID and safe
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
the existing consent/provider/resource limits without the corresponding approval.

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

## Locator trace sessions (v4)

Open `/agent?vision=<session_id>` to read the saved result, chronological operations,
selected before/after images, branch paths and verified/unresolved locator catalog.
Use **Reload** on a finished session to start a new session with its saved target
and intent, after confirming the currently saved provider/model. The original
session stays in history. Reload requires submission permission, current Vision
consent and a valid HTTP(S) target (legacy sessions also check the origin policy); an expired saved intent requires entering
a new request. The Vision Agent tab always submits Vision requests and has no
separate "Use Vision Agent" toggle.
Selecting a historical frame does not move the browser. Enable Follow latest to
follow new operations; scrubbing keeps your selection through polling. Legacy
sessions retain their original frame/trajectory view and are labeled evidence-only.

Exploration completion, draft creation, approval, deterministic execution and report
availability are independent states. Follow the explicit draft link to review the
source and its Vision provenance. Approving a draft creates one v1 Playwright run;
repeating the same decision returns that run. The run link shows its unchanged
runner verdict and advisory report. A generation/report failure leaves the trace
and result export available. Export contains metadata only, without image bytes,
private storage keys or provider URLs.

The worker grounds a model coordinate against the live page and verifies the
unique locator and actionability before acting. The control plane commits an
operation intent and its actual before image before dispatch; it commits after
image/outcome immediately afterward, then acknowledges staged-file cleanup.
Lost responses reconcile the same operation ID. Unknown actions are not repeated.
Sibling branches require checkpoint verification; back, popup closure and replay
remain separate trace operations. URL equality alone does not prove restoration.
Checkpoint semantics cover the rendered viewport (attributes, text, accessible
labels and clipped geometry), so offscreen carousel rotations do not invalidate
an unchanged screenshot. URL, scroll position, and page-wide form presence and
private values still participate in verification. Visible changes, moved controls,
overlays and changed form values invalidate the checkpoint; locator identity is
checked again immediately before a click. This applies only to new Vision browser
sessions and does not change deterministic test execution contracts or verdicts.
An after image is sampled between matching state observations with a bounded,
read-only capture retry (at most 10 seconds within the session deadline). Its
checkpoint uses that captured state, including any
hydration completed since settling. Restore validation uses the
captured state; capture failure never creates a checkpoint for model proposals.
Clicks that change URL or open a popup, history navigation and explicit navigation
get up to 10 seconds to settle the destination; local actions retain the shorter
1.5-second settle bound. Both remain capped by the session deadline.

Typed inputs remain unbound in generated drafts and block their affected branches.
Ambiguous, sensitive or unsupported targets remain unresolved; canvas, closed
shadow roots and unsupported frames have no pixel fallback. Restoring arbitrary
application/server state is not guaranteed. Observed visibility/actionability does
not establish business success. Resource limits and live consent/policy checks
still apply, including between image upload and a provider request.

Operation frames are private evidence subject to the existing explicit-deletion
policy. Deleting frames removes bytes first and retains metadata tombstones.
Failed deletion remains auditable and retryable; neither deletion nor export
modifies a run verdict. Result and trace endpoints require the session's project
permission and use private, no-store responses.

## Local rollout and rollback

The local Compose store is pinned to RustFS `1.0.0-alpha.73`. The previous
`1.0.0-alpha.69` image rejects a first `PutObject` with `If-None-Match: *` as
`NoSuchKey`; a v4 session then stops with `operation_unavailable` before browser
execution because its before image cannot be persisted. The upstream
[conditional-create fix](https://github.com/rustfs/rustfs/pull/1034) is included in
[alpha.73](https://github.com/rustfs/rustfs/releases/tag/1.0.0-alpha.73).
Keep the conditional write and checksum read-back: an unconditional retry would
allow a competing writer to replace evidence.

Before replacing an existing local storage container, stop storage writes, back
up its stopped data volume, and retain that backup. After the upgrade, verify
existing object bytes and metadata and run:

```text
docker pull rustfs/rustfs:1.0.0-alpha.73
uv run pytest tests/test_rustfs_operation_storage.py -q
```

These tests derive the image from Compose, create disposable containers with
loopback-only ports and synthetic credentials, and exercise first writes,
idempotent retries, conflicting bytes and competing writers. They do not access
the application bucket or invoke an LLM. Docker and the pinned image are required;
an unavailable prerequisite is reported as skipped, not passed. This validates
the local single-node topology, not distributed-storage concurrency.

The deployment setting `VISION_TRACE_V4_ENABLED` defaults to false and selects the
writer only for newly accepted sessions. It does not enable tenant Vision consent,
change providers, or rewrite existing session versions. Idempotent resubmission
keeps the originally recorded version across a flag change.

1. Back up the intended local application database before a real upgrade. Verify
   the additive head `f9a0b1c2d3e4` against a disposable database with legacy rows.
   Do not overwrite volumes or downgrade evidence tables.
2. Drain active sessions before restarting a worker. Deploy the worker supporting
   legacy plus v4 and its authenticated capability response, then the control-plane
   reader/orchestrator and dashboard. Apply the additive schema before enabling a
   new writer. v4 requires the separate `VISION_WORKER_SECRET` boundary.
3. Run the synthetic v2 manifest cases with an owned loopback target and fixture
   models. Set `VISION_TRACE_V4_ENABLED=true` only after the schema and worker are
   ready. Existing tenant policy and raw-image consent are still required.
4. Roll back new submissions by setting the flag false. Keep the v4 worker and
   evidence readers while existing v4 sessions finish or become interrupted; do
   not switch a running session's protocol or remove its history.

Monitor counts for unknown operations, restoration failures, staged-frame cleanup
failures, handoff failures, commit/read latency and deadline stops. Use safe codes
and aggregates, never locator values, page text, typed values, URLs or exception
payloads as labels. A real-provider/target canary requires an authorized target
and tenant scope; the synthetic suite is not a production-readiness certificate.

For test isolation, the trace fixtures use an owned PostgreSQL service on
`127.0.0.1:55437` with disposable UUID databases. Install the worker's pinned
Playwright browser before running them. Run the Python baseline in a fresh
process with dotenv disabled, no provider credentials, and only loopback network
access. The configured-stack Compose dashboard workflow is separate: it creates
users/runs and can invoke configured providers, so do not run it as a fixture-only
check. Record skipped Compose checks explicitly. Browser dashboard tests require
`VISION_DASHBOARD_URL` pointing to a local dashboard with intercepted API fixtures.

## Gehihi (Google Gemini) local setup

This is an opt-in synthetic evaluation path, approved in [ADR-009](adr/009-gehihi-vision-provider.md).
No implementation or fixture test enables a tenant. Google model quality and
account quota remain unvalidated until an explicitly requested canary.

1. Obtain an evaluation key through the operator's secret workflow and set
   `GEMINI_API_KEY` server-side. Never paste it into chat, dashboard, logs or reports.
   `.env.example` contains only an empty placeholder. Both `control-plane` and
   `temporal-worker` receive the existing Compose `env_file`. Drain active work
   and deploy both updated services before enabling Gemini. If Compose environment
   values change, recreate those consuming services; a plain container restart
   does not reload them. No application migration is added by this provider.
2. Inspect **Vision settings** as the tenant administrator. Select **Gehihi
   (Google Gemini)** and `gemini-3.8-flash`, read the raw-screenshot disclosure,
   accept transfer to Google, enable and save. Switching providers clears consent
   and enablement; confirm again. No key entry is available in this UI.
   Existing step/byte/time/rate guards can be managed through the policy API.
3. Confirm the intended tenant and project origin policy. Tenant overrides take
   precedence over environment defaults: changing `VISION_PROVIDER` alone does
   not switch an existing tenant. Environment-based Gemini enablement also needs
   `VISION_RAW_SCREENSHOT_TRANSFER_ACCEPTED=true` and
   `VISION_RAW_SCREENSHOT_TRANSFER_PROVIDER=gemini`; prefer scoped tenant settings.
4. Start only an approved synthetic target. The run dialog uses saved settings;
   save or discard draft changes first. A stale confirmation refreshes settings
   and requires a new confirmation. Existing sessions retain their recipient/model.
   `VISION_TRACE_V4_ENABLED` is unchanged and only chooses new-session writers.

Gemini uses inline PNG delivery and does not require Drive OAuth. HF retains its
own Drive image path and consent. Screenshots are raw pixels, potentially including
PII or secrets; there is no screenshot anonymizer. Google's free tier has data-use
conditions, including product improvement. Before each canary, verify current
[model availability](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash),
[data-use/pricing terms](https://ai.google.dev/gemini-api/docs/pricing) and account
quota in [Google AI Studio](https://aistudio.google.com/). Documentation was
rechecked on 2026-10-17; presence of a key is not proof of credentials or free quota.

Candidate requests now use a JSON schema derived from the shared visual action
contract, including coordinates in `[0,1]` and the requested candidate count.
Prompt `vision-exploration-v5` requires scrolling before proposing offscreen
controls. A provider response can still be rejected: the local validator remains
authoritative and never clamps coordinates or accepts a partially invalid batch.
The token, request, step and hop limits are unchanged. A session ending after
setup with `model_output_invalid` has no valid next action; increasing hop limits
does not address that failure. Start a new session after deploying the fix;
terminal sessions retain their original evidence.

Only run a live canary when requested with a ready key, safe target and tenant:
one synthetic session, `max_steps=3`, `max_requests_per_minute=5`,
`max_session_seconds=120`, bounded Gemini transient HTTP retries as above and no
provider fallback. Do not enable billing.
Check recipient/model, a subsequent action if the model proposes one, before/after
evidence and audit. Record quota/output failures honestly. The existing 1000-token
candidate response cap has only mocked-output validation; thinking/output may
exhaust it in a real call. Do not silently raise guards or change models.

Local guards do not account for the shared Google project's quota or reserve
money. `max_cost_usd` remains metadata. General text generation is unchanged:
an HF 402 during draft generation is a separate result, even if Vision succeeded.
No generated source executes without the existing explicit approval.

### Safe failures and evidence

Open `/agent?vision=<session_id>` for saved progress, partial trace, replay and
metadata export. Use correlation IDs and safe audit codes when investigating.
Never log provider request bodies, image data, key values or raw error bodies.

| Code | Meaning / response |
| --- | --- |
| `provider_not_configured` | Server key absent; configure the intended services before enabling. |
| `provider_auth_failed` | Access rejected (401/403); operator checks key and permissions. |
| `provider_billing_required` | Provider returned 402; stop, do not automatically enable billing. |
| `provider_rate_limited` | 429 quota/rate rejection; inspect account limits, no automatic retry. |
| `provider_model_unavailable` | Selected model unavailable (404); no fallback. |
| `provider_timeout` | Request/session deadline reached. |
| `provider_unavailable`, `model_unavailable` | Transport/provider failure or legacy generic reason. |
| `model_output_invalid` | Invalid JSON, refusal, truncation, schema or coordinates; no derived action. |
| `policy_disabled` | Current policy, consent or recipient changed (legacy sessions also check allowed origins). |
| `vision_policy_changed` | Submission confirmation is stale; refresh and confirm again. |
| `image_delivery_auth_required` | HF Drive grant must be renewed; Gemini does not use this path. |

Partial evidence remains available after failure. Unknown browser outcomes are
not replayed. Raw image retention in private RustFS and seven-day encrypted debug
retention are unchanged, as are project read permissions and tenant-admin deletion.
Policy updates atomically store scoped before/after config snapshots referenced
by the audit entity ID, including actor/correlation and no secrets.

### Disablement and binary rollback

Disable the affected tenant policy first; drain or stop active sessions using the
existing lifecycle. Do not replay unknown actions. Preserve evidence and audit.
On the new binary, the tenant may stay disabled or explicitly choose HF with its
previous model and freshly accepted HF consent. Never reinterpret Google consent
as HF consent or redirect an already-created session.

Before deploying an old API/worker binary with `extra=forbid`:

1. Back up affected non-secret `agent.runtime.v1` overrides, tenant IDs and prior
   HF model choices. Prepare each scoped replacement on the new binary, preserving
   all unrelated runtime sections.
2. Set `vision.enabled=false`, `vision.provider=huggingface`, the previous valid
   HF model and `raw_screenshot_transfer_accepted=false`. Remove
   `raw_screenshot_transfer_provider` from the replacement JSON immediately before
   downgrade; saving through the new API normalizes it back into the new schema.
   Use the existing authorized configuration maintenance workflow for that removal.
3. Reset Gemini environment provider/model defaults and remove the new binding
   setting from the old deployment. Keep Vision disabled. Verify a copy of every
   replacement deserializes with the exact target binary before downgrading API
   and worker together. Do not point old workers at new policy JSON.
4. Verify historical `gemini` sessions remain readable as stored strings and retain
   their operations, artifacts, drafts and audit. Record the rollback; do not drop
   tables, rewrite sessions or remove history. Enabling HF afterward needs new consent.

Reproducible fixture commands and measured results are in the
[Gehihi evaluation record](../benchmark/vision/gehihi/README.md).
