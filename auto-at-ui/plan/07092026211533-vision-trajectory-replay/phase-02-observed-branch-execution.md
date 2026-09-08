# Phase 2 - observed branch execution

## Objective

Make the worker and event processor record what actually happened to each BFS branch and announce safe, incremental trajectory changes while preserving sibling isolation.

## Scope and prerequisites

Requires Phase 1's edge contract/repository. The worker remains a disposable, isolated Playwright adapter and does not become a persistent interactive browser session.

## Source paths to change

- `workers/playwright/src/vision.ts`
- `workers/playwright/src/contract.ts` and `workers/playwright/src/contract.spec.ts` if the internal worker route schema is defined there
- `workers/playwright/src/server.ts` or the route-registration file found during implementation
- `apps/control-plane/application/vision_events.py`
- `apps/control-plane/domain/activity.py`
- `apps/control-plane/infrastructure/persistence/repositories.py` only for Phase-1 repository integration
- `tests/test_vision_event_processor.py`
- `tests/test_vision_progress.py`
- worker Vision spec files discovered by `rg --files workers/playwright/src`

## Detailed behavior and data flow

1. Before issuing a node's model request, retain the current private frame/state as today and publish `state.captured` with only state sequence, hop, parent availability, and child/alternative counts when known.
2. When a candidate batch arrives, persist each proposal and its immutable `proposed` edge before it is queued. Emit a safe per-edge `edge.proposed` progress event containing state sequence, proposal sequence, kind, confidence, and coordinate availability—not text or expected outcome.
3. Give every queued non-stop branch the proposal/edge identity that created it. The queue item still contains only the in-memory replay path; execution context/cookies remain isolated.
4. Extend `observeVisualTreeState`'s internal v2 response with safe observation metadata calculated in the worker: capture start/end or duration, a hash/fingerprint of the final URL rather than URL text, and a boolean/change classification versus the parent observation supplied by the control plane. Do not return title, DOM, cookies, raw URL, or an artifact path.
5. When a branch node is successfully captured, atomically create its state/frame and finalize its originating edge with child state/frame checksum, observed/no-meaningful-change classification, duration, and URL-change classification. Emit `edge.observed` only after persistence succeeds, then `state.captured`.
6. On worker navigation/capture/origin/timeout failure, policy/limit exclusion, invalid candidate batch, or stop action, finalize the relevant edge (nullable child) with the safe code before the session terminal record. Emit `edge.failed` or `edge.terminal` and keep encrypted admin diagnostics in the existing separate path.
7. Treat draft handoff as a session-level terminal activity and, when a final selected path exists, optionally attach only a safe `draft_handoff` status to the terminal trajectory summary—not a verdict and not generated source.
8. Preserve idempotency: retries reload existing state/proposal/edge identity and do not issue a new model/worker call after a terminal session. Clean temporary worker files on all existing paths.

## Contract/API changes

- Version the internal worker tree observation request/response deliberately (for example v3) if adding parent fingerprint/edge correlation; keep v2 compatibility only for an in-flight coordinated deploy if required by worker/control-plane rollout order.
- Add safe activity stages/metadata in the server-side activity schema; no public route change in this phase.

## Tests and validation

- Worker specs cover click/scroll/wait, stop, no-coordinate action, origin escape, navigation/capture error, byte cap, and fresh-context sibling isolation with only safe metadata returned.
- Processor tests prove edge creation before queueing, success linkage to exactly one child, no-change classification, terminal limit/stop/failure edges, event ordering, redaction, and at-least-once duplicate safety.
- Progress tests parse the new safe stages and reject typed text/raw URL/provider content.
- Run focused `uv run ruff check ...`, `uv run pytest tests/test_vision_event_processor.py tests/test_vision_progress.py <trajectory tests>`, plus `npm.cmd run typecheck` in `workers/playwright`.

## Acceptance criteria

For every branch the worker considers, persisted evidence can truthfully answer which state proposed it, whether it was observed, what child resulted if any, and why it stopped or failed—without leaking private data.

## Risks and non-goals

Do not replace BFS with a linear browser session, calculate semantic page diffs from raw content, expose a live browser/remote debugger, or let outcomes influence deterministic execution or approval.

## Execution record

- Status: completed 2026-09-07 21:50 +07:00.
- Implemented: worker v3 returns bounded duration, SHA-256 final URL fingerprint, and a safe change classification only. The processor persists a proposal and `proposed` edge before queueing, retains its identity through isolated replay, and finalizes after child capture or safe `model_stop`, `state_limit`, `hop_limit`, or capture-failure outcomes. Added closed safe activity stages for proposed, observed, failed, and terminal edges.
- Changed: `workers/playwright/src/vision.ts`, `workers/playwright/src/vision.spec.ts`, `apps/control-plane/application/vision_events.py`, `apps/control-plane/domain/activity.py`, `apps/control-plane/domain/entities.py`, `apps/control-plane/infrastructure/persistence/repositories.py`, `tests/test_vision_event_processor.py`, and `tests/test_vision_trajectory_repository.py`.
- Validation passed: focused Ruff; focused Pytest (18 passed); `npm.cmd run typecheck`; `npm.cmd test -- vision.spec.ts` (2 passed); `uv run alembic heads`; and `git diff --check`.
- Deviation: storage permits one bounded proposed-to-final outcome transition while preserving immutable tenant/session/proposal/action identity and rejecting divergent or repeated finals. This reconciles the planned pre-queue `proposed` write with its required observed-outcome finalization without a schema change.
