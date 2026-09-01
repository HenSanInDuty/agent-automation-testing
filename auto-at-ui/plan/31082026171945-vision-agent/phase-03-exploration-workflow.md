# Phase 3 — Isolated visual exploration workflow

## Objective

Let the `web_ui` Playwright worker perform a bounded observe → propose →
execute-in-sandbox → observe loop, producing a reviewable candidate rather than
a test verdict.

## Scope and prerequisites

- Complete Phases 1–2 and use the existing Temporal/outbox patterns in
  `apps/control-plane/infrastructure/workflows/`.
- Keep all live browser operations in `workers/playwright/`; the control plane
  remains orchestration only.

## Execution record

**Status:** completed — 2026-08-31 20:55 ICT

**Completion record:** Implemented the authenticated shared-mount worker
protocol, disposable browser context, bounded observation/action loop,
checksum-only action persistence, safe terminal cleanup, outbox event
processor, encrypted 60-day intent retention, and generated-draft handoff.
No deterministic execution request/result contracts were changed. The only
result of a completed visual session is a reviewable generated draft; the
existing human approval flow controls any versioned deterministic rerun.

**Validation:** focused Ruff passed; `uv run pytest
tests/test_vision_event_processor.py tests/test_vision_intent.py
tests/test_vision_executor.py tests/test_vision_contracts.py` passed (8);
`npm.cmd run typecheck` in `workers/playwright` passed. The optional
Compose-backed visual scenario was skipped because services were not started.

**Decision recorded:** use a shared ephemeral artifact mount. The disposable
worker writes session-addressed screenshot files below the configured shared
artifact root; the control plane reconstructs the path from the session ID,
verifies byte count and checksum, and exposes bytes only transiently to the
server-side Hugging Face adapter. Files are removed on terminal completion,
timeout, or failure. The public artifact model remains unused because its
run-scoped URI is not appropriate for provider-input screenshots.

**Decision recorded:** retain the original task intent internally for up to 60
days so a visual session can be retried and its advisory draft can be created.
It is encrypted at rest using a dedicated configuration-secret key. Application
logs, activity events, audit payloads, and browser responses retain only the
intent hash and correlation metadata; credential-bearing requests remain
rejected before storage.

**Safe work completed:** reconciled the completed Phase 1–2 contracts and
policy, the worker HTTP boundary, the outbox/Temporal processor pattern, and
the immutable generated-draft flow. No Phase 3 implementation was begun,
because choosing either transport changes the raw-image security boundary and
the semantic-draft data shape.

## Exact paths and changes

- Add a versioned visual-exploration worker endpoint/message in
  `workers/playwright/` that accepts only `VisualExplorationRequest`.  It must
  pin browser/viewport, use a fresh non-persistent context, block origins not
  allowed for that project, clear storage at completion, disable downloads and
  uploads, and never mount user profiles or credentials.
- Implement the loop in a new worker module: capture a screenshot, persist it
  through the configured artifact policy, await one validated candidate action,
  enforce normalized coordinate bounds/viewport translation, execute at most
  one allowlisted action, and capture the resulting screenshot/state.  Enforce
  max actions, wall-clock timeout, screenshot bytes, and blocked navigation.
- Add workflow activities and an event processor in
  `apps/control-plane/application/vision_events.py` and
  `apps/control-plane/infrastructure/workflows/` following
  `application/reporting_events.py`: at-least-once idempotency, correlation,
  safe unavailable status, and no model call on duplicate terminal session.
- Add `apps/control-plane/application/vision.py` to translate final visual
  action candidates into a reviewable generation/healing proposal.  An accepted
  proposal creates a new generated Playwright draft using semantic locator and
  observable assertions where possible; it must not execute coordinate clicks
  directly in an existing test revision.
- Reuse `AgentProposalModel`, approval, audit, activity, and outbox mechanics
  where compatible.  Add new persistence tables only for session/action history
  that cannot be represented safely in the generic proposal payload.
- Update `apps/control-plane/api/v1/routes/runs.py`/artifact integration only
  as needed to make visual-session artifacts authorized and run/session scoped;
  never return provider image inputs through a public artifact endpoint.

## Data flow

1. A queued session is dispatched to a disposable `web_ui` worker context.
2. The worker captures evidence; the control plane verifies and passes the
   bounded raw image to the vision executor.
3. The model returns one candidate action.  The worker rejects unsafe/out of
   bounds actions and otherwise performs it in the disposable context.
4. On `stop`, exhaustion, error, or timeout, the workflow persists the observed
   action history/checksums and a candidate proposal.  A human reviews it;
   approval goes through the existing immutable generated-draft flow and the
   normal deterministic Playwright run supplies the only verdict.

## Tests and validation

- Add TypeScript worker unit/contract tests for viewport normalization,
  allowed action mapping, blocked origin/navigation/download/upload, context
  cleanup, timeout/step exhaustion, and no-action-on-invalid-model-output.
- Add Python event-processor/use-case tests for duplicate events, cancellation,
  policy disablement after queueing, unavailable model, tenant isolation,
  correlation/activity/audit metadata, and approval-to-draft handoff.
- Extend `tests/test_playwright_worker_compose.py` with an isolated local
  compose scenario using a fake vision endpoint; assert that the deterministic
  run status is unchanged.
- Run `npm.cmd test --workspace @auto-at/dashboard` only if dashboard tests are
  affected, `uv run pytest` for control-plane tests, and the focused worker
  test command documented in `workers/playwright/package.json`.

## Acceptance criteria

- No visual action may leave the disposable worker context, bypass an allowed
  origin, exceed a guard, or mutate an approved revision.
- A human-approved result produces a new versioned test draft and only its
  normal deterministic rerun can pass/fail.

## Risks and non-goals

- Coordinate actions are discovery evidence, not a stable final locator.
- Do not support login/MFA/payment flows or autonomous retries in this phase.
