# Phase 03 — Live Advisory session UI

## Objective

## Completion record

**Status:** completed (2026-09-06 16:00 ICT)

Implemented a dedicated session-scoped progress component with server-safe event
parsing, stable ordering/deduplication, accessible connection state, and polling
fallback. Activity receipt refreshes the selected exploration and safe action
list. Validation passed: dashboard tests (18), typecheck, lint, and build.

Make the Vision dashboard render the server-owned session progress live and refresh
the selected session/action candidates when a safe Vision activity arrives.

## Scope and prerequisites

Phase 02's routes must be available. Follow the established dashboard client pattern:
EventSource with `withCredentials`, no browser-side redaction/authorization, clear
connection state, and polling fallback.

## Exact paths

Change:

- `apps/dashboard/app/vision-dashboard.tsx`
- `apps/dashboard/app/generation-api.ts`
- `apps/dashboard/app/generation-types.ts`
- `apps/dashboard/app/components/activity-timeline.tsx` and
  `apps/dashboard/app/components/activity-timeline-model.ts` if generalized safely
- `apps/dashboard/app/globals.css` only for minimal live-progress presentation

Add:

- `apps/dashboard/app/components/vision-progress-timeline.tsx` (preferred if a
  session-scoped component is clearer than overloading run/correlation behavior)
- `apps/dashboard/app/components/vision-progress-timeline-model.ts`
- `apps/dashboard/app/components/vision-progress-timeline-model.test.ts`
- `apps/dashboard/app/vision-dashboard.test.ts`

## Implementation and data flow

1. Add typed client methods for the Vision session activity snapshot and stream URL.
   Use a distinct `VisionProgressActivity` type or the shared safe `Activity` type;
   do not cast untrusted event JSON into action or policy types.
2. In the selected Advisory session, replace the correlation-based generic timeline
   with a session-scoped progress component. On mount/session change, read history,
   then open EventSource to the new stream while the session is non-terminal.
3. On each valid `activity` event, de-duplicate by event ID, order by timestamp/ID,
   render its safe summary/stage/status, and refresh `getVisualExploration` plus
   `listVisualActions` for that selected session. This makes newly persisted action
   candidates appear promptly without relying on the old two-second list polling.
4. Use friendly, explicit copy that distinguishes agent work from authority, e.g.
   “Capturing a permitted page state”, “Requesting advisory candidates”, and
   “Candidate action recorded”. Render action kind/confidence/coordinates only from
   the already safe action API; never render type text, screenshots, provider detail,
   or prompt content.
5. Show accessible live connection status with `aria-live="polite"`: connecting,
   live updates connected, and reconnecting/polling fallback. When SSE errors or
   EventSource is unavailable, poll the session progress/action endpoints only while
   active; stop timers and close the source on terminal state/unmount.
6. Preserve existing controls: confirmation dialog, tenant policy edit, project
   policy display, draft-review link, diagnostics RBAC/no-store behavior, and status
   badge. Do not turn activity clicks into a way to control execution.

## Contract/API/schema impact

- Dashboard-only typed client additions for Phase 02 routes.
- No runner/agent prompt/model/execution contract change. UI treats server events as
  display-only advisory evidence.

## Tests and validation

- Unit-test ordering, duplicate suppression, event parsing rejection, terminal-state
  shutdown, and polling fallback decision logic.
- Test mapping of safe stage names to user copy and ensure forbidden type text/model
  payload fields are not part of render types.
- Test the Vision dashboard selected-session behavior: history is shown, a synthetic
  activity refreshes action candidates, and the selected session—not another session—
  supplies the endpoint ID.
- Run from `apps/dashboard`: `pnpm test`, `pnpm typecheck`, `pnpm lint`, and
  `pnpm build`.

## Acceptance criteria

During an active exploration, users see live, comprehensible, safe progress and
candidate action updates; a failed/unavailable SSE connection visibly switches to
polling without losing the current history or allowing browser-side data disclosure.

## Risks and non-goals

Avoid a rerender loop caused by refreshing a selected session on every event. Keep
the refresh scoped and cancel stale requests on selection change. This phase does not
add controls to pause/cancel/explore further or expose visual evidence.
