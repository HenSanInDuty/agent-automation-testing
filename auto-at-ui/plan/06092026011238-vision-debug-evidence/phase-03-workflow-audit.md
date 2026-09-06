# Phase 03 — Workflow capture and audit trail

## Objective

Capture a redacted encrypted debug record exactly when a Vision model response is
rejected, while preserving the workflow's current fail-closed and at-least-once-safe
semantics.

## Scope and prerequisites

Depends on Phases 01–02. Relevant ownership remains application orchestration in
`application/vision_events.py`; routes and workers must not bypass repositories.

## Changes

1. Update `VisionEventProcessor` to receive the debug repository/use case through its
   existing construction in `infrastructure/workflows/temporal_worker.py`.
2. On an `execute_visual_candidate_batch` unavailable result, construct the bounded
   redacted payload from Phase 01, persist it before calling `_unavailable`, and use a
   deterministic idempotency identity based on session/state/model-attempt.
3. If capture/redaction/encryption fails, leave the exploration unavailable with the
   existing generic safe failure; record a safe capture-failed audit/activity code. Do
   not write model content to exception logs and do not retry the model call.
4. Add safe activity metadata only: `session_id`, diagnostic code, capture availability,
   and correlation ID. Do not add encrypted data, payload checksum, model text, prompt,
   image URL, or key material to Grafana activity/log events.
5. Append immutable audit events for capture outcome and workflow failure; keep actor as
   `vision-worker`, entity as the debug record/session, and correlation ID intact.
6. Ensure the outer broad exception path also classifies only a safe workflow category
   and cannot mask a successful persisted record or cause a second capture on replay.

## Tests and validation

- Extend `tests/test_vision_event_processor.py` for malformed candidate output,
  duplicate outbox delivery, capture persistence, capture failure, terminal session
  no-op, and cleanup behavior.
- Verify activities/audits contain no raw sentinel secret, model text, image URL, or
  ciphertext; assert deterministic status remains `unavailable`.
- Run `uv run pytest tests/test_vision_event_processor.py tests/test_vision_executor.py`
  and the relevant Temporal-worker tests.

## Acceptance criteria

One rejected batch creates at most one debug record per attempt and retains the current
safe session response. Worker retry cannot make a failed exploration pass or alter an
action/test verdict.

## Risks and non-goals

Do not make debug capture an operational dependency of model execution. No provider
retry policy, cost/rate-limit change, or replay behavior change is included.

## Completion record

- Status: completed 2026-09-06T12:24:54+07:00.
- Capture is idempotent by session/state/attempt, occurs before the unchanged safe
  unavailable result, and produces payload-free activity/audit events.
- Validation: `tests/test_vision_event_processor.py`, executor, and crypto tests passed.
