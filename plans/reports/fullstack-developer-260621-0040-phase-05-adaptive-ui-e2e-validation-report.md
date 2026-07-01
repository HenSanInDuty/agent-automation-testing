# Phase 05 Implementation Report — Integrate UI and End-to-End Validation

## Executed Phase
- Phase: phase-05-integrate-ui-and-end-to-end-validation
- Plan: D:/CV/auto-at/plans/260620-2257-adaptive-api-testing-pipeline/
- Status: completed

## Files Modified

### packages/shared
| File | Change |
|------|--------|
| `src/types/index.ts` | Added `MDSpecValidationFieldError`, `PlannerCoverageGap`, `PlannerReviewIteration`, `PlannerReviewGate`, `PlannerComplexity`, `PlannerObligation`, `TestCaseNodeOutput`, `ReviewCoverageExtra`; added `pdf_url` to `ReportVerificationResponse`; added `review_coverage` component key; added `planner.review_iteration` to `WSEventType` |
| `src/api/client.ts` | Added `downloadExportPdf(runId, force?)` — same gated blob-download pattern as html/docx |
| `src/components/pipeline/ReportVerificationCard.tsx` | Added gated PDF download button + force-PDF for admin; added `review_coverage` to component label map (skips render when absent for legacy runs) |
| `src/components/pipeline/ResultsViewer.tsx` | Added `PlanningReviewSummary` import + `TestCaseNodeOutput` type; added `planningData` useMemo to extract complexity/review_gate from `nodeResultsRaw`; injected `<PlanningReviewSummary>` at top of Report tab (additive, public props UNCHANGED) |
| `src/components/pipeline/PipelineRunPage.tsx` | Added imports for `ValidatorFailureChecklist`, `PlanningReviewSummary`, `MDSpecValidationErrorPayload`, `TestCaseNodeOutput`, `pipelineApi`, `useQuery`; added `useQuery` for nodeResults (enabled on terminal runs only); added `structuredError` useMemo parsing JSON from `run.error_message`; added `planningData` useMemo from node results; extended `TerminalSummaryCard` props to accept `structuredError` + `planningData`; replaced plain error block with `<ValidatorFailureChecklist>`; added `<PlanningReviewSummary>` in terminal card; wired both `TerminalSummaryCard` call sites |
| `src/components/pipeline/index.ts` | Exported `PlanningReviewSummary` and `ValidatorFailureChecklist` |
| `src/index.ts` | Exported `PlanningReviewSummary` and `ValidatorFailureChecklist` |

### packages/shared — new files
| File | Purpose |
|------|---------|
| `src/components/pipeline/PlanningReviewSummary.tsx` | Additive component: complexity score, agent count+roles, review iterations, coverage %, verdict badge, exhaustion warning, planner warnings. Renders nothing when no planning data present (legacy-safe). |
| `src/components/pipeline/ValidatorFailureChecklist.tsx` | Structured MDSpecValidationErrorPayload renderer: missing_sections / missing_fields / field_errors as checklist with hints; generic fallback for non-structured errors. |
| `src/components/pipeline/__tests__/planning-review-summary.test.tsx` | 8 vitest component tests: empty render, agent count, score, roles, coverage, verdict, exhaustion, warnings |
| `src/components/pipeline/__tests__/validator-failure-checklist.test.tsx` | 9 vitest component tests: empty render, raw fallback, code badge, detail, sections, fields, field errors, counts, structuredError preference |

### apps/admin-app
| File | Change |
|------|---------|
| `src/components/pipeline-builder/NodePropertiesPanel.tsx` | Added `AdaptivePlannerConfig` inline component; renders bounded config fields (min_planner_agents 1–5, max_planner_agents 1–5, coverage_threshold_percent 0–100, max_review_iterations 0–5, continue_on_exhaustion bool) with clamp validation; only rendered when `agentId === "adaptive_api_test_planner"` |

## Tasks Completed

- [x] Added backward-compatible optional types (pdf_url, review_coverage, TestCaseNodeOutput, PlannerReviewGate, etc.)
- [x] Added `downloadExportPdf` to API client
- [x] Added gated PDF download + force-PDF admin path to `ReportVerificationCard`
- [x] Additive planning/review summary in `ResultsViewer` Report tab — public props UNCHANGED
- [x] Structured validator-failure checklist in `PipelineRunPage` via `ValidatorFailureChecklist`
- [x] Compact planning status in `TerminalSummaryCard` via `PlanningReviewSummary`
- [x] Node results fetched from persisted API (not WS events) after terminal — source-of-truth after refresh
- [x] JSON parse of `error_message` to detect MDSpecValidationErrorPayload; generic fallback for other errors
- [x] Admin `NodePropertiesPanel`: adaptive node config with bounded validation (clamp + cross-field min≤max)
- [x] User app stays read-only (no changes)
- [x] Component tests written for both new components (vitest, awaiting harness setup)

## Typecheck / Build Results

| Check | Result |
|-------|--------|
| `admin-app npx tsc --noEmit` source errors | **0** (only pre-existing `.next/types/…/compare/page.ts` error — Next.js 15 `PageProps` Promise compat, present before this phase) |
| `user-app npx tsc --noEmit` | **EXIT:0 — clean** |
| `admin-app npm run build` | Fails on same pre-existing `.next/types` error (confirmed by stash test) |
| `user-app npm run build` | Not run (user-app has no changes) |

## Tests

- **Component tests**: 17 tests across 2 files written for vitest + @testing-library/react
- **Test runner status**: No vitest/jest harness configured in repo. Tests are spec-correct and will run once `vitest`, `jsdom`, and `@testing-library/react` are added to `packages/shared`. E2E harness (Playwright) also absent — E2E fixture notes deferred per spec instruction.
- **Existing tests**: No existing tests to break (repo has no test runner at shared/app level).

## Constraints Satisfied

- `ResultsViewerProps` public interface: **unchanged** — verified by grep
- All new fields on shared types: **optional** — no existing callers need updating
- `ReportVerificationCard` `review_coverage` component: skips render when absent (legacy-safe)
- `PlanningReviewSummary` returns null when no planning data present
- `ValidatorFailureChecklist` returns null when no error data
- Admin adaptive config: only renders when `agentId === "adaptive_api_test_planner"` — zero effect on other nodes
- Header values NOT exposed (no `request_headers` rendering in new components)

## Pre-existing Issue (Not Introduced)

The admin-app `next build` fails on `.next/types/app/pipelines/[templateId]/runs/compare/page.ts:34` — a Next.js 15 `PageProps` params-as-Promise breaking change. Confirmed present on clean `git stash` before my changes. Requires updating `apps/admin-app/src/app/pipelines/[templateId]/runs/compare/page.tsx` to `Promise`-unwrap `params`.

**Status:** DONE_WITH_CONCERNS
**Summary:** All phase-05 frontend requirements implemented — types, PDF export, verification card PDF button, planning/review summary in ResultsViewer + PipelineRunPage, structured validator checklist, admin adaptive node config with bounds validation. Both apps typecheck clean at source level.
**Concerns:** (1) No test runner configured — 17 component tests written but cannot execute. (2) Admin `next build` fails on pre-existing Next.js 15 `PageProps` compat error unrelated to this phase; that page needs `params: Promise<{ templateId: string }>` + `use(params)` to fix.
