# Phase 06 — Codex settings and Website activity

Status: **completed**. Started: 2026-10-24 13:16 +07:00. Completed: 2026-10-24 13:35 +07:00. Dependencies: phase 5 API and activity contracts.

## Completion record

Codex settings consume API capabilities, distinguish readiness/login/model access,
and keep DOM and screenshot permissions separate. Provider changes clear both
permissions. New/reloaded sessions submit the frozen saved input-policy fingerprint;
409 responses refresh settings and require a fresh disclosure confirmation.
Readiness polling updates availability without overwriting unsaved policy edits.
Website progress displays safe stages and recorded call/elapsed counters, keeps
selected history frames intact, and gives terminal activity precedence over late
progress or an eventually consistent result response. Confirmed highlights remain
bound to worker evidence. Historical provider labels are retained.

Changed paths:
- `apps/dashboard/app/{generation-types.ts,generation-api.ts,vision-dashboard.tsx}`
- `apps/dashboard/app/components/{vision-provider-model.ts,vision-provider-model.test.ts,vision-provider-settings.tsx}`
- `apps/dashboard/app/components/{vision-progress-timeline-model.ts,vision-progress-timeline-model.test.ts,vision-progress-timeline.tsx}`
- `apps/dashboard/app/components/{vision-live-screen.tsx,vision-session-detail.tsx}`
- `workers/playwright/src/vision-dashboard.spec.ts`
- `docs/vision-agent-operations.md`

Existing click model/overlay/tests and CSS edits were preserved; no additional
phase-specific styling or fabricated click geometry was needed.

Validation:
- `npm.cmd --prefix apps/dashboard run typecheck`: passed.
- `npm.cmd --prefix apps/dashboard test`: **43 passed**, no skips.
- `npm.cmd --prefix workers/playwright run typecheck`: passed.
- `NEXT_PUBLIC_CONTROL_PLANE_URL=http://127.0.0.1:3107 NEXT_TELEMETRY_DISABLED=1 npm.cmd --prefix apps/dashboard run build` (PowerShell environment assignment): passed.
- Owned production fixture on loopback 3107; `VISION_DASHBOARD_URL=http://127.0.0.1:3107 npx.cmd --no-install playwright test src/vision-dashboard.spec.ts --workers=1`: **47 passed**, no skips, 1.4 minutes. Includes eleven new Codex scenarios and existing browser/highlight/approval regression coverage.
- `git diff --check`: passed; execution v1 has no diff.

Initial focused browser run: 9 passed, 2 failed because a test's generic alert
selector also matched the Next.js route announcer. Scoped that selector; the full
47-test run above passed. Windows PowerShell blocks npm.ps1, so validation uses
npm.cmd/npx.cmd. Existing module-type, Next.js workspace-root/ESLint and color-env
warnings remain nonfatal. No Python behavior changed in this phase; full Python
regression remains phase 07. No inference, real tenant changes or deployment.

## Objective

Make provider readiness, data transfer and current agent work understandable in the existing Agent Website view. Preserve the confirmed-click highlight and saved-screen behavior.

## Exact paths

Change:
- `apps/dashboard/app/generation-types.ts`.
- `apps/dashboard/app/components/vision-provider-settings.tsx`.
- `apps/dashboard/app/components/vision-provider-model.ts`, `apps/dashboard/app/components/vision-provider-model.test.ts`.
- `apps/dashboard/app/components/vision-progress-timeline-model.ts`, `apps/dashboard/app/components/vision-progress-timeline-model.test.ts`.
- `apps/dashboard/app/components/vision-progress-timeline.tsx`.
- `apps/dashboard/app/components/vision-live-screen.tsx`, `apps/dashboard/app/components/vision-session-detail.tsx`.
- `apps/dashboard/app/vision-dashboard.tsx` for create/reload input-policy fingerprint.
- `apps/dashboard/app/globals.css` only for necessary state styling.
- `workers/playwright/src/vision-dashboard.spec.ts`.
- `docs/vision-agent-operations.md` for user-facing state meanings.

Inspect and preserve `apps/dashboard/app/components/vision-click-model.ts`, `apps/dashboard/app/components/vision-click-overlay.tsx` and their tests; do not synthesize target outlines from unverified model predictions.

## Behavior

1. Add Codex (existing account) with Luna to the provider picker, supplied by API capabilities. Show concise bridge status: disconnected, ready, login required, model access unverified/unavailable, incompatible CLI or busy. Do not show account email, credential paths, raw subprocess errors or a fake “API key configured” indicator.
2. Show separate permissions: sanitized DOM/text sent to OpenAI; optional screenshots sent to OpenAI when needed. Explain that local files do not mean offline model processing. DOM-only operation must not force image consent.
3. Switching provider resets enablement and both consent scopes. Saving requires existing tenant-admin permissions; read-only users can inspect effective settings. Preserve unsaved-changes behavior.
4. Confirmation/reload submits exact saved provider/model/input-policy fingerprint. A stale response refreshes settings and asks the user to review the changed disclosure, following current conflict behavior. Do not silently enable image transfer.
5. Website activity maps safe stages to short messages: waiting for Codex bridge, reading page elements, image needed, analyzing screenshot, checking proposed action, performing verified action and stopped reason. A model-wait state is distinct from a performed browser operation.
6. Display elapsed time/call count from safe authoritative timestamps/metadata when available. Do not manufacture a percentage, countdown beyond the actual deadline, token estimate or raw chain-of-thought.
7. Integrate with SSE and polling fallback; order/deduplicate events and ignore delayed stage updates after terminal state. A past selected operation still shows its saved before/after frame; latest agent stage must not pretend that selected history is live.
8. Keep target highlight grounded in verified operation/locator/frame evidence. Proposals may be labeled as proposed text only. “Show action” continues to select the appropriate before frame.
9. Terminal failures clearly distinguish host offline, expired login, model access/quota, interrupted job, timeout, stale page and invalid output. Preserve last saved screen and Reload semantics.
10. A stopped historical Gemini session is not relabeled as a Codex run. New provider selection applies through a new confirmed exploration.

## API/schema impact

Consume phase 5 additive provider/status/policy/job progress fields. No raw file viewer/download, shell controls, arbitrary model selector, billing screen or client-side filesystem API. All authorization and redaction remain server-owned.

## Tests and commands

- `npm --prefix apps/dashboard run typecheck`
- `npm --prefix apps/dashboard test`
- `npm --prefix apps/dashboard run build`
- From `workers/playwright`: `npx playwright test src/vision-dashboard.spec.ts` with mocked API/event data; no live model or configured application mutations.

Tests cover separate consent toggles, recipient reset, DOM-only enablement, readiness states, expired login, stale submit/reload, SSE-to-polling fallback, duplicate/out-of-order stages, terminal precedence, selection of older frames, desktop/mobile layout and retained confirmed highlight. New fixture stages must not invalidate historical test fixtures.

## Acceptance and risks

A user can identify what the agent is doing without opening technical details, and distinguish host/login problems from model unavailability. UI never claims local-only data or unlimited/free usage. Historical sessions and existing highlights retain their behavior. Avoid implementation details such as raw job paths in the normal user flow.
