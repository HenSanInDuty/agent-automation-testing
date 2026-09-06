# Vision advisory-session progress stream

## Goal

Make the **Advisory session** area of the Vision Agent dashboard show a live,
safe account of what a visual exploration is doing. The UI must receive
server-authoritative progress as it happens, append newly proposed action
candidates without a full-page refresh, and continue to show a usable polling
fallback if SSE is unavailable.

## Acceptance criteria

1. Starting a Vision exploration produces an ordered, session-scoped progress
   timeline covering queueing, start, safe browser-state capture, model-candidate
   request/result, each persisted candidate action, terminal completion or safe
   unavailability, and generated-draft handoff outcome where applicable.
2. An authenticated reader of the exploration's project sees new progress and
   newly persisted candidate actions over SSE while the session is active;
   the dashboard falls back to bounded polling after a stream failure.
3. A user cannot retrieve a Vision session's progress by guessing its UUID,
   crossing tenants, or reusing a correlation ID from another project.
4. Progress events never expose screenshot bytes/URLs, task intent, typed action
   text, prompts, model/provider response text, credentials, or exception detail.
   The deterministic test verdict and existing human draft-approval boundary are
   unchanged.
5. Existing activity/run APIs and the versioned `TestExecutionRequest` /
   `TestExecutionResult` contract remain compatible; this work does not alter a
   runner contract.

## Request and decisions

| Item | Status |
| --- | --- |
| Request | “Advisory session ở phần vision agent. Phải stream thao tác cho user biết agent đang làm gì.” |
| Confirmed design | Use a Vision-session-scoped SSE/read API, rather than treating a client-supplied correlation ID as an authorization scope. |
| Confirmed design | Reuse the append-only safe activity-event model and existing EventSource/polling UX pattern, with a nullable Vision-session foreign key for safe filtering. |
| Assumption | “Thao tác” means user-facing milestones and safe action candidates—not screenshots, model chain-of-thought, typed text, prompts, or raw provider output. |
| Assumption | No new provider, model, cloud service, retention policy, or paid capability is selected. Existing tenant Vision policy and configured Hugging Face path remain authoritative. |
| Unresolved | None material for planning. Product copy can be finalized during implementation without changing API/security behavior. |

## Scout findings

- `apps/dashboard/app/vision-dashboard.tsx` renders Advisory session, polls the
  selected session and action list every two seconds, and embeds the generic
  `ActivityTimeline`. It has no Vision-specific live-action subscription.
- `apps/control-plane/application/vision.py` creates a queued session and one
  safe activity event. `apps/control-plane/application/vision_events.py` performs
  tree-state capture/model calls/action persistence, but emits its normal action
  activity only after the entire session completes; unavailable is likewise only
  terminal.
- `apps/control-plane/api/v1/routes/activities.py` already supplies an SSE endpoint
  with history, `Last-Event-ID`, five-second discovery polling, and keepalives.
  Its correlation authorization intentionally admits only events with a readable
  `run_id`; Vision events have no run ID, so the generic correlation timeline
  cannot safely or reliably deliver Vision progress.
- `apps/control-plane/domain/activity.py` rejects sensitive metadata keys and
  `apps/control-plane/infrastructure/persistence/models.py` / `repositories.py`
  persist append-only activity records. The table has correlation and optional run
  identifiers, but no visual-session identifier usable for scope-safe querying.
- `apps/control-plane/api/v1/routes/vision.py` already authorizes session and action
  reads against the session's project. `packages/contracts/src/auto_at/contracts/vision.py`
  is explicitly advisory-only and separate from execution contracts.
- `apps/dashboard/app/components/activity-timeline.tsx` establishes the dashboard
  convention: EventSource with cookie credentials, server events as authority, and
  polling fallback. `tests/test_activity.py` verifies basic stream resume behavior.

## Applicable constraints

- Preserve control-plane layering: domain defines safe activity values, application
  emits them, infrastructure persists/queries them, routes handle HTTP/SSE and
  authorization, and dashboard remains an API client.
- Vision runs only under tenant policy/consent and the existing model/provider,
  cost, rate, step, screenshot-size, and session-time caps. This feature must not
  issue additional model calls or change those limits.
- Session intent is encrypted; raw screenshot transfers are consent-gated and
  transient. Stream metadata must be independently redaction-safe and not rely on
  browser-side filtering.
- Audit trail remains append-only and correlated. Persisted progress is operational
  evidence only, not approval, execution evidence, or a verdict.
- SSE must be tenant/project authorized at connection and every refresh. A generic
  correlation is not an ownership boundary because the submit caller provides it.

## Phases

| Phase | Objective | Status | Dependencies | Validation |
| --- | --- | --- | --- | --- |
| [01](phase-01-safe-progress-events.md) | Persist safe, granular Vision progress with a session scope. | completed — 2026-09-06 15:43 ICT | Existing activity schema and Vision processor | Focused Python domain/application/repository tests passed (17 tests) |
| [02](phase-02-authorized-session-stream.md) | Expose authorized history and resumable SSE for one Vision session. | completed - 2026-09-06 15:52 ICT | Phase 01 | Focused FastAPI/SSE/RBAC tests passed (21 tests) |
| [03](phase-03-live-advisory-session-ui.md) | Render live progress and action updates in Advisory session with fallback. | completed - 2026-09-06 16:00 ICT | Phases 01-02 | Dashboard tests, typecheck, lint, and build passed |
| [04](phase-04-operational-validation.md) | Document and exercise safe rollout, observability, and regression checks. | completed - 2026-09-06 16:05 ICT | Phases 01-03 | Focused, baseline Python, dashboard tests/typecheck/lint/build passed |

## Risks and rollout

- **Data exposure:** emitting action `type.text`, task intent, image references,
  or provider diagnostics would violate the existing Vision boundary. Use a
  closed, tested event vocabulary with allow-listed metadata only.
- **Authorization regression:** a correlation-wide stream can mix resources. Scope
  database reads and route authorization to `visual_exploration_session_id`.
- **Duplicate events:** Vision processing is at-least-once. Add idempotency for a
  progress stage/sequence (or tolerate and de-duplicate via a deterministic event
  key) before publishing to clients.
- **Long-lived SSE:** retain existing keepalives and fallback; do not use an SSE
  connection to invoke work, mutate a session, or bypass request authorization.
- **Migration:** add a nullable indexed column so existing non-Vision activity rows
  and history remain readable. Deploy migration before code that writes the field;
  no backfill is needed for old Vision sessions, which retain their existing view.

Roll out disabled behind the existing Vision policy. Validate against synthetic
Vision fixtures before a consenting canary tenant. Monitor stream connections,
fallback activation, emitted safe-stage counts, unauthorized attempts, and activity
write/query failures using non-sensitive aggregate labels only. No retention change
is proposed.

## Out of scope

- Streaming raw screenshots, LLM tokens, reasoning, prompts, action text, or
  unredacted diagnostics.
- Changing selected Vision provider/model, tenant consent, cost/rate limits,
  encryption, retention, project-origin policy, or RBAC roles.
- Changing test generation, approval, runner dispatch, or deterministic results.
- A generic cross-resource correlation stream redesign.

## Execution progress

Overall status: completed (2026-09-06 16:05 ICT).

Phase 01 completed at 2026-09-06 15:43 ICT. Added nullable session scope and a
deduplication key to append-only activity records, including the forward-only
`f6a7b8c9d0e1` migration. Vision orchestration now records only a closed,
allow-listed vocabulary at actual state capture, candidate, action, limit,
handoff, completion, and unavailable transitions. The repository ignores a
replayed progress key for the same session.

Changed paths: `apps/control-plane/domain/activity.py`,
`apps/control-plane/application/vision.py`,
`apps/control-plane/application/vision_events.py`,
`apps/control-plane/infrastructure/persistence/models.py`,
`apps/control-plane/infrastructure/persistence/repositories.py`,
`migrations/versions/f6a7b8c9d0e1_add_vision_session_activity_progress.py`,
and `tests/test_vision_progress.py`.

Validation passed: `uv run ruff check apps/control-plane tests
migrations/versions/f6a7b8c9d0e1_add_vision_session_activity_progress.py`;
`uv run pytest tests/test_activity.py tests/test_vision_event_processor.py
tests/test_vision_progress.py` (17 passed); and `git diff --check`. No runner
or execution-contract change was made by this phase. Existing unrelated dirty
dashboard, worker, and contract edits were preserved. Phase 02 is unblocked.

Phase 02 added project-authorized session history and resumable SSE. Phase 03
replaced the generic correlation timeline with the session stream, safe progress
copy, refresh-on-activity action updates, and polling fallback. Phase 04 updated
the Vision runbook and API examples. Final validation passed: focused Python
suite (21 tests), uv run ruff check ., uv run pytest (214 collected), and
dashboard pnpm test (18 passed), typecheck, lint, and build via corepack.
