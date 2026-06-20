---
phase: 5
title: "Integrate UI and end-to-end validation"
status: pending
priority: P1
dependencies: [4]
---

# Phase 5: Integrate UI and end-to-end validation

## Overview

Expose fail-fast validation, planning/review progress, coverage warnings, and PDF download in both apps without breaking shared run flows.

## Requirements

- User sees exact missing document fields immediately after validator failure.
- Run view shows selected agent count, review iteration, coverage score/threshold, and exhaustion warning.
- Existing HTML/DOCX behavior remains; PDF is added.
- Admin may configure template defaults; run overrides are validated and role-protected.

## Architecture

Extend shared types/API client/hooks and existing export controls. Avoid changing `ResultsViewer` public props because GitNexus reports CRITICAL upstream impact. Consume persisted results/events through current run-detail data flow.

## Related Code Files

- Modify: `D:/CV/auto-at/packages/shared/src/types/index.ts` — validation, planning audit, review gate, and PDF URL types.
- Modify: `D:/CV/auto-at/packages/shared/src/api/client.ts` — PDF download and config fields.
- Modify: `D:/CV/auto-at/packages/shared/src/components/pipeline/ResultsViewer.tsx` — render additive planning/review summary only.
- Modify: `D:/CV/auto-at/packages/shared/src/components/pipeline/ReportVerificationCard.tsx` — add gated PDF action.
- Modify: `D:/CV/auto-at/packages/shared/src/components/pipeline/PipelineRunPage.tsx` — structured validator/review progress presentation.
- Modify targeted admin pipeline-builder config UI for bounded defaults; user app remains read-only.
- Add shared component tests and admin/user E2E fixtures for valid, invalid, retry, exhaustion, and export flows.
- Update `D:/CV/auto-at/docs/pipeline-execution.md`, `docs/data-models.md`, `docs/api-flow.md`, and backend/admin READMEs.

## Implementation Steps

1. Add backward-compatible optional response fields and event payloads.
2. Render missing-field errors as a checklist with contract guidance; retain generic fallback for legacy runs.
3. Add compact planning status: complexity reason, `agents selected`, iteration, coverage, senior verdict, and warning state.
4. Add PDF to existing verified export controls and force-export admin path.
5. Add accessible loading/error/disabled states and avoid exposing header values.
6. Test both admin and user routes because shared `ResultsViewer` has five affected execution flows.
7. Run backend tests, shared typecheck/tests, both app builds, and browser E2E against one valid and one invalid fixture.
8. Update architecture/API/data-model docs after contracts stabilize.

## Success Criteria

- [ ] Invalid spec presents all required corrections and no downstream progress.
- [ ] User can follow agent selection and review iterations in real time and after refresh.
- [ ] Exhausted gate is prominent but does not hide available results.
- [ ] PDF and HTML downloads work from admin and user run-detail pages.
- [ ] Existing callers of `ResultsViewer` compile without prop changes.
- [ ] `uv run pytest`, shared package checks, admin/user builds, and E2E acceptance suite pass.

## Risk Assessment

CRITICAL UI blast radius across admin and user routes. Keep changes additive, verify all five graph-identified flows, and use feature fixtures before release. WebSocket events can arrive out of order; UI must rely on persisted run data as source of truth after refresh.
