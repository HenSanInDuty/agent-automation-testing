# Phase 01 — Safe progress events

## Objective

## Completion record

**Status:** completed (2026-09-06 15:43 ICT)

Implemented the nullable `visual_exploration_session_id` scope, indexed
session-timeline lookup, and nullable per-session `progress_key` uniqueness for
replayed deliveries. `ActivityEvent.create_vision_progress` is a closed safe
event builder that rejects non-allow-listed metadata. The Vision submit and
processor paths emit configured milestones around observed operations.

Changed paths: `apps/control-plane/domain/activity.py`,
`apps/control-plane/application/vision.py`,
`apps/control-plane/application/vision_events.py`,
`apps/control-plane/infrastructure/persistence/models.py`,
`apps/control-plane/infrastructure/persistence/repositories.py`,
`migrations/versions/f6a7b8c9d0e1_add_vision_session_activity_progress.py`, and
`tests/test_vision_progress.py`.

Validation passed: `uv run ruff check apps/control-plane tests
migrations/versions/f6a7b8c9d0e1_add_vision_session_activity_progress.py`;
`uv run pytest tests/test_activity.py tests/test_vision_event_processor.py
tests/test_vision_progress.py` (17 passed); and `git diff --check`.

No deviations, runner-contract changes, or deferred work. Existing user edits
outside these paths were preserved.

Persist a truthful, ordered, idempotent, redaction-safe progress record for each
significant Visual Exploration operation, scoped to its exploration session.

## Scope and prerequisites

This phase builds on the current `ActivityEvent` append-only model. It requires
no provider or prompt change and must not make a new model request. Before starting,
review the current dirty files listed by `git status --short`; they are user changes
and are not part of this phase.

## Exact paths

Change:

- `apps/control-plane/domain/activity.py`
- `apps/control-plane/infrastructure/persistence/models.py`
- `apps/control-plane/infrastructure/persistence/repositories.py`
- `apps/control-plane/application/vision.py`
- `apps/control-plane/application/vision_events.py`
- `migrations/versions/<new>_add_vision_session_to_activity_events.py`

Add or extend:

- `tests/test_activity.py`
- `tests/test_vision_event_processor.py`
- `tests/test_vision_progress.py`

## Implementation and data flow

1. Extend the domain activity value and SQLAlchemy `activity_events` model with
   nullable `visual_exploration_session_id: UUID | None`. Add a foreign key to
   `visual_exploration_sessions`, a tenant/session/timestamp index, and repository
   filtering by this identifier. Keep `run_id` and correlation fields unchanged so
   all existing activity callers remain compatible.
2. Add a forward-only Alembic migration that creates the nullable column/index. Do
   not backfill old rows, change retention, or remove any activity data.
3. Define an allow-listed Vision progress vocabulary in the application/domain
   boundary, not in dashboard code. Emit only concrete outcomes, for example:
   `queued`, `started`, `state.captured`, `candidate.requested`,
   `candidate.received`, `action.recorded`, `limit.reached`, `draft.handoff`,
   `completed`, and `unavailable`. Choose names that map one-to-one to observed
   code transitions in `VisionEventProcessor`.
4. Update `SubmitVisualExploration.execute` to tag its existing queued event with
   the new session ID. In `VisionEventProcessor.execute`, append progress only after
   or immediately before the corresponding real operation: mark running, record a
   verified browser state, describe a model request without payload data, record an
   accepted candidate count, record every successfully persisted action, report
   bounded traversal stopping, report handoff result, and report terminal state.
   Ensure `unavailable` includes only the existing safe reason/summary semantics.
5. For action events, allow only session ID, state/hop or sequence, action kind,
   bounded numeric confidence/coordinates/scroll/wait values, candidate count, and
   checksum only if it is already safe evidence metadata. Never include `TypeAction`
   text, replay path, task intent, screenshot data/URL, prompt version text,
   provider body/response, exception string, credentials, or diagnostic payload.
6. Preserve at-least-once safety: associate progress with deterministic stage plus
   state/action sequence and enforce one persisted record per logical transition
   (via a persisted idempotency field/index or a repository-level existing-record
   check selected during implementation). Do not let duplicate outbox processing
   create duplicate user-visible actions or completion events.
7. Keep audit records correlated and append terminal/action audit events as today;
   add safe audit codes only where needed to distinguish session started/completed
   from unavailable. Progress remains advisory and must never alter session result,
   a generation draft, a runner request, or an execution verdict.

## Contract/API/schema impact

- Internal persistence/domain schema only: nullable `visual_exploration_session_id`
  on activity records and a session-scoped repository query.
- No changes to `packages/contracts/.../execution.py`, runner worker contracts, or
  public `VisualExplorationResult` in this phase.

## Tests and validation

- Verify sensitive-key validation still rejects nested secret-shaped metadata.
- Verify each Vision milestone carries its session ID and only allow-listed safe
  metadata; assert sentinels for typed text, intent, URL, provider response, and
  secret cannot appear in event serialization.
- Verify a model failure records an unavailable event without exception/provider
  detail, and a repeated processor delivery does not duplicate logical events.
- Run: `uv run pytest tests/test_activity.py tests/test_vision_event_processor.py tests/test_vision_progress.py`
- Run: `uv run ruff check apps/control-plane tests`

## Acceptance criteria

New explorations produce safe, ordered, session-scoped progress records and all
existing activity records remain valid/readable without a schema backfill.

## Risks and non-goals

The principal risk is accidentally treating telemetry as a debug channel. Avoid it
with a closed event builder and negative tests. This phase does not expose an endpoint
or modify dashboard behavior.
