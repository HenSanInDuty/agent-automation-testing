# Local Codex exploration bridge

This opt-in development adapter uses the existing ChatGPT login and the selected
`gpt-6-luna` model to propose Web UI actions. Playwright verifies and executes each
action. Drafts still require human approval, and only the deterministic runner
sets a test verdict. API and game execution contracts remain unchanged.

DOM text goes to OpenAI. The local spool is transport, not offline inference.
Use approved synthetic sites until actual model access and quality are validated.
Screenshot transfer requires separate permission and an explicit model request;
DOM-only jobs contain no image. Each image escalation consumes another call within
the same session deadline. There is no provider/model/account fallback, automatic
CLI retry, billing enablement, or strict dollar ceiling. Existing account usage
and rate limits apply. Model access remains unverified after an offline doctor.

**Current release gate (2026-10-24):** CLI 0.164.0 is qualified with an immutable
model catalogue that removes tool capabilities. The complete wire probes declare
zero tools; unknown custom calls are unsupported. Doctor verifies the catalogue,
centralized proposal instructions, outer container protections and existing login. JSONL still omits
rejected unknown custom calls, so it is not a complete tool-attempt audit.
The v6 YOLO DOM canary passed: one call, no image, and one independently verified
Toggle modal action in 9.156 seconds. The verified response schema is supplied as
prompt text instead of CLI `--output-schema`; strict local parsing, scope checks
and browser verification remain mandatory. This establishes the synthetic DOM
gate, not general site quality. Default submissions remain disabled until explicit
local activation; live screenshot validation remains unverified and disabled.
See the [evaluation record](../benchmark/vision/codex/README.md)
for measured results and the isolated, single-call canary command.

## Container-only YOLO mode

At the user's explicit request, the bridge invokes `codex exec --yolo` inside the
dedicated container. This bypasses CLI approvals and its inner filesystem/network
sandbox. Doctor requires a non-root process, read-only container root, zero effective
capabilities, no-new-privileges and an active seccomp filter. The fixed launchers
retain limited mounts, resource limits and separate ephemeral runtime storage.
The immutable catalogue still exposes zero model tools; Playwright alone executes
proposed actions. The credential is readable by the trusted CLI for authentication,
not protected from arbitrary container processes by YOLO. Do not enable model tools
or run this invocation on the host. Existing fallback sandbox checks verify only
that profile's compatibility; they are not effective `--yolo` restrictions.

## Qualify the container

Run from the repository root with Docker Desktop using Linux containers:

```powershell
docker build -t auto-at-codex-bridge:0.164.0 -f docker/codex-bridge/Dockerfile .
uv run python docker/codex-bridge/qualify.py
uv run python docker/codex-bridge/check_mount.py
uv run python docker/codex-bridge/container.py doctor --auth-file "$env:USERPROFILE/.codex/auth.json"
```

Run the synthetic qualification and mount probes before using the real credential.
Doctor uses no networking or inference and prints only safe readiness metadata.
It requires the qualified 0.164.0 pin and exact build-generated catalogue/prompt files.
Only a qualified pin proceeds to version/feature checks and the separate fallback
profile probes for denied reads/writes/networking. YOLO relies on the outer boundary.
The [container notes](../docker/codex-bridge/README.md) document its seccomp profile.
Do not add privileged mode or broader host mounts to make qualification pass.

Only the existing `auth.json` is mounted read-only. The container has a separate
temporary home and cannot modify host login. Token refresh can therefore fail;
renew the existing login outside the bridge, rerun doctor and start a new session.
Never copy credentials into the spool, repository, image or logs.

## Prepare local paths and scope

Use one trusted local tenant per bridge. Create a dedicated spool outside the
repository and credential directory, for example
`C:/Users/<user>/AppData/Local/AutoAT/codex-jobs`. Restrict its Windows ACL to the
signed-in user and the access Docker Desktop needs. Do not share it with other
users. Use C: on this machine: the qualified Docker Desktop installation rejects
D: bind mounts. Re-run the mount probe after changing Docker/file-sharing settings.

Add these non-secret settings locally; replace the placeholders explicitly:

```dotenv
CODEX_BRIDGE_ENABLED=true
VISION_TRACE_V4_ENABLED=true
CODEX_BRIDGE_ID=<new-UUID>
CODEX_BRIDGE_ALLOWED_TENANT=<existing-local-tenant-id>
CODEX_BRIDGE_HOST_SPOOL=C:/Users/<user>/AppData/Local/AutoAT/codex-jobs
CODEX_BRIDGE_AUTH_FILE=C:/Users/<user>/.codex/auth.json
```

The same spool and bridge identity are used by the API, workflow worker and bridge.
Application containers receive `/codex-jobs`; only the bridge receives the auth
file. The bridge has its own egress network, no application credentials, Docker
socket, repository bind mount, host home or browser profile. The default Compose
file starts no Codex service, and `.env.example` keeps both flags false.

Inspect `docker compose --env-file .env.example -f docker-compose.yml -f
docker-compose.codex.yml --profile codex config --quiet` with the required path/ID
variables supplied in the shell. This validates configuration without starting
services. Avoid publishing full expanded Compose configuration: application
environment values can include secrets.

## Deploy locally and enable deliberately

First finish or cancel active explorations; replacing their worker loses browser
state. Back up the local database and keep the previous application revision.
Build compatible images before replacing services:

```powershell
docker compose -f docker-compose.yml -f docker-compose.codex.yml --profile codex config --quiet
docker compose -f docker-compose.yml -f docker-compose.codex.yml --profile codex build control-plane temporal-worker playwright-worker dashboard benchmark-target codex-bridge
docker compose -f docker-compose.yml -f docker-compose.codex.yml --profile codex up -d --wait postgres redis temporal-postgres rustfs
docker compose -f docker-compose.yml -f docker-compose.codex.yml --profile codex run --rm --no-deps --entrypoint uv control-plane run --no-sync alembic upgrade head
docker compose -f docker-compose.yml -f docker-compose.codex.yml --profile codex up -d --wait --wait-timeout 180
docker compose -f docker-compose.yml -f docker-compose.codex.yml --profile codex ps
curl.exe --noproxy "*" --fail http://127.0.0.1:7000/healthz
```

Use this same sequence after source changes. A plain `docker compose restart`
does not rebuild images or apply changed environment/mount settings. Keep the
same Compose files, bridge UUID, tenant and spool for an existing installation.
Do not remove named volumes to restart. If startup fails, inspect the affected
service's logs locally; do not publish credentials or expanded configuration.

Apply migrations through `d1e2f3a4b5c6` before accepting Codex sessions. They add
nullable input-policy/binding metadata and the scoped job registry; historical
sessions are not rewritten. Keep existing worker shared secrets, intent encryption
and tenant RBAC configured. The bridge runs its doctor before consuming jobs.

In **Agent → Vision settings**, a tenant administrator selects **Codex (existing
account)**, accepts page-element/text transfer to OpenAI and enables exploration.
Leave optional image transfer unchecked for a DOM-only canary. A viewer can inspect
settings but cannot save them. Saving does not change historical sessions; New or
Reload creates a session after confirmation of the saved model and consent.

### View images every second without sending images to Codex

Open the active v4 session in the dashboard and select **Follow live**. The screen
component fetches `/api/v1/vision/explorations/{session_id}/screen` immediately,
then waits 1,000 ms after each completed request before fetching again. The worker
shares one in-flight capture across viewers and caches a completed preview for
one second. This avoids overlapping capture requests; it is not a fixed 1 FPS
stream, since capture and network latency also take time.

These authenticated preview images go to the dashboard. They do not consume a
Codex model call or grant OpenAI image-transfer consent. Keep **optional image
transfer unchecked** while testing DOM proposals with live preview. The separate
live screenshot canary remains unverified and disabled. An image request from
the model without consent safely stops rather than transferring a screenshot.

To check preview behavior, start an authorized DOM exploration, keep Follow live
selected, and inspect successful `/screen` requests in the browser Network panel.
The displayed image should update while the session runs, including while waiting
for Codex. Terminal session status stops live polling; selecting an operation
shows retained before/after evidence. A 503 shows a retry state; 401/403/404 stops
polling. A missing preview does not change any action or test verdict.

Do not run the standalone `container.py run` launcher and the Compose bridge
together. The consumer lock prevents concurrent use of one spool. The standalone
launcher is available for diagnostics; Compose is the documented application path.

## Read progress and diagnose safe failures

| Display | Meaning and next action |
| --- | --- |
| Bridge disconnected | Missing/stale heartbeat, wrong scope, or stopped service; check the configured bridge and spool. |
| Login required | Existing ChatGPT login is missing/expired; renew it outside the bridge. |
| Compatible CLI needed | Version, immutable catalogue/prompt, or isolation checks failed. Rebuild the pinned 0.164.0 image and rerun qualification; do not relax the gate. |
| Model access unverified | Local checks passed; no successful live model-access evidence is claimed. |
| Model unavailable / request unavailable | Check selected-account access, quota and provider availability; never substitute a model. |
| Bridge busy / waiting | One child is active; queue time consumes the same session deadline. |
| Reading page elements / analyzing screenshot | The model is working; no browser action is implied. |
| Checking proposed action | Result validation is pending; only subsequent verified worker evidence supports a highlight. |
| Stale page / invalid proposal | Output was discarded; start a fresh exploration if appropriate. |
| Interrupted / timed out | Owned child is stopped and the job is not relaunched. Reload creates a new session. |
| Cleanup pending | Cancellation is durable; temporary-file cleanup has not been acknowledged. Keep the spool private and investigate the consumer. |

Heartbeat cadence is two seconds, stale after ten. Cancellation is observed within
two seconds and owned process-group termination has a further three-second budget.
These are local acceptance targets. The usual 120-second session deadline includes
queue, CLI startup, calls and browser work. A single call may contain internal CLI
turns; call count is not a hard token or cost cap. Safe activity exposes stage,
correlation/job identity, elapsed time and available aggregate usage, never raw
prompts, output transcripts, credentials or local paths.

Temporary payloads are removed after acknowledgement, cancellation or expiry.
Restart cleanup never relaunches an already claimed job. DB metadata and retained
browser evidence continue under existing policies; no new production retention
period is introduced. A selected historical frame remains selected during progress
updates. Terminal events stop live polling even if the result endpoint lags.

## Validation and release gates

```powershell
uv run python benchmark/vision/codex/run_offline.py -q --tb=short
uv run ruff check .
uv run python packages/contracts/export_vision_worker.py --check
```

The [evaluation record](../benchmark/vision/codex/README.md) separates synthetic
results from live model evidence. The harness builds a credential-free image with
no real Codex executable, creates its own PostgreSQL container on a network with
loopback only, and runs Python/Node/Chromium in that same network namespace. No
application volume, port or Docker socket is shared. It removes its owned containers
and writes a safe count/duration report under `.pytest-artifacts/`.

`tests/test_playwright_worker_compose.py` is explicitly excluded because it writes
to a configured stack and can invoke its provider. The isolated browser/SQL tests
cover the exploration → draft → approval → execution path and existing reporting.
An offline pass does not certify account access, real model quality or latency.
The separate live gate is bounded to one DOM-only session and, with explicit image
consent, one image-escalation session, each at most three calls and 120 seconds.

## Stop and rollback

1. Disable Vision for the affected tenant through its normal administrator policy
   API/UI and revoke transfer consent. Let current jobs cancel/drain; inspect safe
   terminal status and cleanup acknowledgement before removing spool access.
2. Stop the dedicated bridge with `docker compose -f docker-compose.yml -f
   docker-compose.codex.yml --profile codex stop codex-bridge`. Keep compatible API
   readers while retained Codex/HF/Gemini evidence is needed.
3. For parser downgrade, export the affected tenant's **non-secret**
   `agent.runtime.v1` configuration override and preserve the original backup.
   Prepare a disabled legacy policy using that tenant's previous provider/model:

   ```powershell
   uv run python docker/codex-bridge/rollback_policy.py tenant-runtime.json tenant-runtime-rollback.json --provider huggingface --model "<previous-HF-model>"
   ```

   The helper writes a new review file only. It removes Codex keys, clears transfer
   consent, disables new exploration and preserves other runtime sections/limits.
   Review and apply it only to the exact tenant/config key through an audited
   maintenance transaction. Do not replace all tenant configuration or rewrite
   session, proposal, audit or execution records. Use `--provider gemini` with the
   actual previous Gemini model where appropriate.
4. Set `CODEX_BRIDGE_ENABLED=false`, stop using the override, and redeploy compatible
   older writers only after the configuration is readable by their policy parser.
   Retain the additive schema and compatible historical readers; destructive schema
   downgrade is unnecessary. Default Compose must not mount credentials or spool.
5. Clean only acknowledged/expired job payloads beneath a verified spool root.
   Do not remove an active consumer's files, credential store, database or evidence
   volumes. Existing browser/artifact retention remains unchanged.
