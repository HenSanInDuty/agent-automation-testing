# Phase 04 — Visual replay dashboard

## Objective

Add an accessible, privacy-aware visual replay viewer to the existing Vision
session panel, using only the authorized API from Phase 03.

## Scope and prerequisites

- Requires the replay list/image/delete API from Phase 03.
- Reuses the dashboard's cookie credentials and session selection; no browser
  talks directly to RustFS or the Vision provider.

## Exact paths

- Change `apps/dashboard/app/vision-dashboard.tsx`.
- Change `apps/dashboard/app/generation-api.ts` and
  `apps/dashboard/app/generation-types.ts`.
- Add focused presentation/model components under
  `apps/dashboard/app/components/` and their tests.
- Change `apps/dashboard/app/globals.css` only for the responsive viewer,
  overlay, keyboard focus, and empty/deleted states.
- Update dashboard route/API contract tests such as
  `tests/test_dashboard_route_contracts.py` if route exposure is asserted.

## Detailed behavior and data flow

1. Load replay metadata whenever a selected exploration changes and refresh it
   after the existing safe progress event indicates a state capture. Do not
   poll image bytes or preload all full-size frames.
2. Show an ordered frame strip/tree with state sequence, hop, captured time,
   checksum prefix, and retained/deleted status. Display a clear empty state
   for historic sessions with no retained frames.
3. On selection, request the one authorized image endpoint with cookie
   credentials, render it as a blob/object URL, revoke that object URL on frame
   change/unmount, and handle 404/integrity failures without leaking route or
   storage details.
4. Use the frame's grouped safe action candidates to overlay scaled click/type
   coordinates and show non-coordinate actions (scroll/wait/stop) in a nearby
   list. Label every marker “model proposal”; never show action text, hidden
   reasoning, or imply the action executed a test.
5. Let tenant admins explicitly delete a frame or all replay frames via the
   Phase 03 endpoint and the existing confirmation-dialog pattern. Other roles
   see view-only controls. Refresh metadata after delete and show an
   unambiguous deleted state.
6. Add a privacy disclosure: images may include target-page data, are retained
   until an authorized deletion, are accessible only to authenticated project
   readers, and remain unrelated to the deterministic test verdict.

## Contract/API/schema changes

- Add TypeScript types for metadata-safe replay frames and grouped candidates;
  no local type includes an object-storage URI or screenshot base64.

## Tests and validation

- Component/model tests for grouping/order, normalized coordinate scaling,
  frame switching/object-URL cleanup, empty/deleted/error states, and
  viewer-vs-admin controls.
- API-client tests must assert session-scoped routes and cookie/CSRF behavior.
- Run repository dashboard tests, typecheck, lint, and production build via the
  existing `pnpm`/`corepack` scripts, plus `git diff --check`.

## Acceptance criteria

A permitted user can select an exploration and visually inspect each saved
state and its safe candidate markers without any screenshot appearing in
activity/timeline text or any direct storage URL reaching the browser.

## Risks and non-goals

No video scrubber, browser interaction, response caching, public share control,
or model-output transcript is included.

## Execution record

Status: completed 2026-09-06 19:41 ICT.

The Vision dashboard now lists frames in capture order and fetches only the
selected authorized PNG as a cookie-authenticated blob. It revokes object URLs
before replacement and when the selection disappears. Safe coordinate markers
are normalized against each image's intrinsic dimensions, while scroll, wait,
and stop proposals remain in the nearby safe list. The viewer discloses the
private, until-deletion retention policy, distinguishes retained evidence from
the empty historic/deleted state, and renders deletion controls only for a
tenant administrator after an explicit confirmation dialog. No direct storage
route, image base64, typed text, prompt, or provider output reaches the UI.

Validation: dashboard test suite (19 passed), TypeScript typecheck, ESLint,
production build, and `git diff --check` passed. Next.js workspace-root and
Node module-type warnings were non-failing. No deviations or deferred work
within this phase.
