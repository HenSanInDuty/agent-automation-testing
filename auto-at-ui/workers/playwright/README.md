# Playwright worker

This worker is an execution adapter, not the orchestration core. It receives the versioned `TestExecutionRequest` contract, runs a pinned Playwright image, and returns artifacts plus a `TestExecutionResult`.

The HTTP server accepts deterministic execution v1 and private visual exploration
v1/v3/v4. Playwright stays pinned at 1.50.1. The v4 worker capability is opt-in;
the control-plane v4 writer is a separate rollout phase.

## Private visual operation protocol v4

Every route requires `x-auto-at-vision-worker-secret`, matching the configured
`VISION_WORKER_SECRET`. JSON bodies are limited to 64 KiB. Open with
`POST /visual-explorations` and a `VisualWorkerOpen` body; the browser starts on a
blank page. The absolute deadline includes browser launch, model waits, captures,
actions and restores. The operation cap is `1 + max_states * (2 * max_hops + 3)`;
state, hop and screenshot byte limits are enforced separately.

All paths below start with `/visual-explorations/{session_id}`:

| Method/path | Contract and behavior |
| --- | --- |
| POST `/operations/prepare` | `VisualWorkerPrepare`: compare the current state, capture the actual before frame and ground a locator. Returns operation/evidence metadata and an opaque prepared handle. |
| GET `/operations/{operation_id}/frames/{frame_id}` | Private PNG bytes with checksum metadata from the operation; never returns a filesystem path. |
| POST `/operations/{operation_id}/execute` | `VisualWorkerExecute`: caller must first persist the before bytes and metadata, then acknowledge the exact frame ID/checksum/handle. A duplicate returns the recorded result. |
| GET `/operations/{operation_id}` | Reconcile a lost response. `unknown` must not be re-executed. |
| POST `/operations/{operation_id}/ack` | `VisualWorkerAck`: after all returned evidence is persisted, acknowledge every frame ID to remove this operation's staging files. |
| GET `/checkpoints/{checkpoint_id}` | Read safe invariants and compare them to the live browser, including form values held only in RAM. |
| DELETE session root | Close browser and discard runtime state. ACK evidence before closing; unacknowledged files are retained, but the closed session cannot serve them over HTTP. |

GET/DELETE additionally require `x-auto-at-vision-tenant-id`,
`x-auto-at-vision-project-id` and `x-auto-at-vision-fencing-token` headers.
POST identities are required in their body and must match the path. A changed
fencing token cannot take over the old browser context. Closed session IDs cannot
be reopened within the process; worker restart requires control-plane reconciliation
and does not recover browser RAM.

Setup navigation, back, popup closure and every replay step use the same
prepare/execute protocol. `restore_checkpoint_id` requests verification after one
primitive; mismatch returns `state_restore_failed` and blocks dependent actions.
To try back followed by a replay fallback, inspect the checkpoint after back
without asserting a final restore first; submit each verified replay primitive
separately and assert the final checkpoint. Replay requires a completed, replayable
source operation and the same action/locator. Arbitrary buttons, typing and unknown
outcomes are not replayable. Navigation cannot undo server-side mutations.

Locators are descriptors, never executable source. Role/name, label, test ID and
bounded stable CSS candidates must resolve uniquely to the hit-tested DOM element.
Same-origin iframe and open shadow scopes are explicit. Cross-origin frames,
transformed iframe coordinates, closed shadow roots, canvas and credential inputs
are unresolved with reasons. Sensitive locator identities are rejected. Typing
appends; values and checkpoint form state remain in RAM and are omitted from
operation JSON. Screenshots remain private evidence under existing consent.

## Contract and browser validation

From `auto-at-ui/`, regenerate types/schema with
`uv run python packages/contracts/export_vision_worker.py`; use `--check` in CI.
Python contracts own the shape, while shared accepted/rejected fixtures exercise
both parsers and their semantic validators.

From this directory:

```text
npm.cmd run typecheck
npm.cmd test -- src/vision.spec.ts src/vision-locators.spec.ts src/vision-operations.spec.ts --workers=1
```

The fixture server binds loopback and never uses a model/provider. Use the matching
Playwright 1.50.1 browser locally or the pinned worker image. For a local browser
install, set `PLAYWRIGHT_SKIP_BROWSER_GC=1` before
`npm.cmd exec playwright install chromium` to preserve other cached browser builds.

