# Phase 3 - live trajectory API and dashboard

## Objective

Expose an authorized redacted graph snapshot and render it as a live, trajectory-first Exploration evidence view that users can understand during and after agent work.

## Scope and prerequisites

Requires persisted edge outcomes and safe activity events from Phases 1-2. The dashboard fetches private frame bytes only through existing run/session-scoped no-store endpoints.

## Source paths to change

- `apps/control-plane/api/v1/routes/vision.py`
- `apps/control-plane/application/vision_replay.py` or a new read-only `application/vision_trajectory.py`
- `apps/control-plane/domain/ports.py`
- `apps/control-plane/infrastructure/persistence/repositories.py`
- `tests/test_vision_routes.py`, `tests/test_dashboard_route_contracts.py`, and replay/trajectory query tests
- `apps/dashboard/app/generation-types.ts`
- `apps/dashboard/app/generation-api.ts` and `apps/dashboard/app/generation-api.test.ts`
- `apps/dashboard/app/components/vision-replay-model.ts` and its test file
- New `apps/dashboard/app/components/vision-trajectory.tsx` plus focused model/component tests
- `apps/dashboard/app/components/vision-progress-timeline-model.ts`
- `apps/dashboard/app/vision-dashboard.tsx`
- dashboard styles file(s) located during implementation

## Detailed behavior and data flow

1. Add one read-only `GET /api/v1/vision/explorations/{session_id}/trajectory` response, authorized exactly like frame/activities reads. Return the session-safe summary, state metadata (ID, parent ID, hop, sequence, captured time, thumbnail/frame reference ID only), proposals, and immutable edges as one consistent graph snapshot. Exclude raw image bytes and all forbidden content.
2. Keep existing `replay-frames` and blob endpoints compatible for deletion/read audit. Stop coupling their response to `actions` as the primary replay model; retain that field only with a documented compatibility period or remove it in a deliberately versioned client migration.
3. Represent historical edge-less sessions as `trajectory_available: false` with an explicit legacy/gallery label. Do not derive action results solely from parent/child ordering.
4. Add pure dashboard model functions for graph validation, ordered sibling alternatives, deterministic default-path selection, prev/next navigation, keyboard shortcuts (`ArrowLeft`, `ArrowRight`, Home, End), selected transition, and a safe marker label such as `1. Click proposed` / `Observed`. Unit-test all calculations separately from React.
5. Replace the primary **Visual replay** heading with **Exploration evidence**. While active, show connection state, latest captured state thumbnail/frame, current stage, counts, and an accessible `aria-live` text update driven by progress/SSE. Refresh the trajectory snapshot when `state.captured`, `edge.*`, terminal, or polling fallback events arrive; retain the last coherent snapshot during a refresh failure.
6. For the selected default path, show a transition card with before thumbnail/image, an action card (kind, safe coordinates/scroll/wait, confidence, proposal/attempt/outcome label, duration and safe code), and after thumbnail/image or an explicit unavailable/terminal panel. Load only the selected frame at full size; thumbnails should use bounded/lazy requests and revoke blob URLs on change/unmount.
7. Add previous/next buttons, keyboard navigation, path scrubber/thumbnails, current `Step i of n`, and a compact minimap/tree. Siblings are clickable alternatives under their parent, displaying confidence/status and whether a child was observed. Render just one selected coordinate marker, numbered and named; no coordinate marker for scroll/wait/stop.
8. Surface limit, policy, navigation, capture, candidate, and draft-handoff statuses at their affected edge/session. Preserve the separate tenant-admin diagnostic-evidence interaction and never place diagnostic payload into the trajectory.
9. Retain existing session selection, policy controls, explicit image-transfer consent, delete controls, and generated-draft link. Update all copy to say advisory evidence and not execution replay.

## Contract/API changes

- New redacted trajectory read model and endpoint; TypeScript types are generated/maintained manually according to existing conventions.
- Existing activity stream receives only safe `edge.*` stage labels/metadata and remains server-authorized.
- Frame bytes remain behind existing `Cache-Control: private, no-store` route and audit behavior.

## Tests and validation

- HTTP tests cover unauthenticated/cross-tenant/service access, project readers, legacy sessions, stable graph ordering, redaction, and private/no-store frame behavior.
- API client tests assert credentials, endpoint path, safe payload parsing, and errors.
- Replay-model tests cover sibling alternatives, coordinate and non-coordinate actions, default path/tie-breakers, failed/null-child edge, missing frame, keyboard boundary navigation, and no simultaneous proposal markers.
- Component tests or DOM-level tests cover live state refresh, polling fallback label, selected state emphasis, tree branch switch, unavailable image, and accessible labels.
- Run `npm.cmd test` and `npm.cmd run typecheck` in `apps/dashboard`; run focused Python Ruff/Pytest route/query suites.

## Acceptance criteria

At any point in a running session, a reader sees the last persisted state plus truthful safe progress. At completion, they can navigate a selected branch step-by-step and inspect alternatives without confusing unexecuted proposals with observations.

## Risks and non-goals

Avoid eager loading full screenshot galleries and accidental browser caching. This is not a video player, co-browsing surface, or universal shared debug link; it must not bypass current authorization/deletion controls.

## Execution record

- Status: completed 2026-09-07 22:04 +07:00.
- Implemented: a cookie-authenticated project-reader trajectory snapshot; it is redacted and uses a clear edge-less legacy state rather than inventing outcomes. The dashboard reloads it on existing safe activity signals, provides selected-path navigation, alternatives, keyboard controls, safe outcome labels, and an Exploration evidence heading.
- Validation: focused Ruff; 21 focused route/contract tests; dashboard typecheck; 9 focused dashboard API/model tests; `git diff --check`.
