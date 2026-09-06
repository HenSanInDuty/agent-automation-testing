# Phase 02 — Authorized session stream

## Objective

## Completion record

**Status:** completed (2026-09-06 15:52 ICT)

Added the session-scoped history and SSE route pair under the Vision router. Both
load the tenant-scoped session and require project READ before filtering solely
by visual_exploration_session_id; correlation IDs remain outside this
authorization path. The SSE implementation sends named activity messages,
honors Last-Event-ID, checks every five seconds, emits keepalives, and ends on
refresh failure for the dashboard fallback.

Changed paths: apps/control-plane/api/v1/routes/vision.py,
tests/test_vision_routes.py, and tests/test_dashboard_route_contracts.py.

Validation passed: uv run ruff check apps/control-plane tests; uv run pytest
tests/test_vision_routes.py tests/test_activity.py tests/test_dashboard_route_contracts.py
(21 passed); git diff --check. No deviations or execution-contract changes.

Expose the persisted Vision progress history and new records through a resumable,
session-scoped SSE endpoint that applies tenant/project RBAC before data leaves the
control plane.

## Scope and prerequisites

Phase 01 migration and repository support must be available. Reuse the behavior of
the existing activity SSE endpoint—history first, `Last-Event-ID`, five-second
checks, keepalive, cookie credentials—but do not authorize using correlation ID.

## Exact paths

Change:

- `apps/control-plane/api/v1/routes/vision.py`
- `apps/control-plane/api/v1/routes/activities.py` (only if common serializer/SSE
  helpers are safely extracted)
- `apps/control-plane/infrastructure/persistence/repositories.py`

Add or extend:

- `tests/test_vision_routes.py`
- `tests/test_activity.py`
- `tests/test_dashboard_route_contracts.py`

## Implementation and data flow

1. Add a read-only route pair under the existing Vision router, for example
   `GET /api/v1/vision/explorations/{session_id}/activities` and
   `GET /api/v1/vision/explorations/{session_id}/activities/stream`. Return the
   existing safe activity response shape, including id, stage, status, safe summary,
   allow-listed metadata, and timestamp.
2. For both routes, first load the session tenant-scoped, then require `Permission.READ`
   against `record.project_id`, matching `get_exploration` and `list_actions`.
   Only then query events where `visual_exploration_session_id == session_id` and
   tenant matches. Never query all records by correlation ID as a substitute.
3. Implement SSE history/resume and keepalives consistently with
   `activities.stream_activities`: emit named `activity` events, honor a valid
   `Last-Event-ID` without replaying it, discover inserts every five seconds, and
   set `text/event-stream`. Extract a private shared formatter only if it does not
   pull persistence/authentication responsibilities across API route boundaries.
4. Return the same not-found response for missing and unauthorized sessions to avoid
   resource discovery. On disconnect, close the iterator; on database/network
   failure, end the stream so the browser can activate its safe polling fallback.
5. Keep the generic `/activities?correlation_id=` semantics unchanged in this feature.
   The new stream deliberately fixes Vision visibility without weakening correlation
   isolation for any existing agent flow.

## Contract/API/schema impact

- Adds two additive dashboard-facing Vision API routes and named SSE `activity`
  messages. Existing API responses are unchanged.
- The message data is a server-owned safe activity DTO, not a new LLM, runner, or
  execution contract. Document the event/stage vocabulary in the route/module
  docstring or relevant API documentation.

## Tests and validation

- Unauthenticated calls return the existing 401/422 behavior; missing, wrong-tenant,
  and wrong-project calls return 404 and emit no stream data.
- Authorized history includes only records for the requested session even when another
  session reuses the same correlation ID.
- Test `Last-Event-ID` resume, initial ordering, named event format, and keepalive.
- Test that the response contains no sensitive action text or redacted sentinel.
- Run: `uv run pytest tests/test_vision_routes.py tests/test_activity.py tests/test_dashboard_route_contracts.py`
- Run: `uv run ruff check apps/control-plane tests`

## Acceptance criteria

An authorized project reader can open a resumable stream for exactly one Vision
session, while no request can use the stream to infer another tenant/project/session.

## Risks and non-goals

Long-lived HTTP streams consume connections, so retain the existing lightweight
poll/keepalive design and do not introduce a broker or new infrastructure. This phase
does not modify the dashboard and does not stream screenshots or model output.
