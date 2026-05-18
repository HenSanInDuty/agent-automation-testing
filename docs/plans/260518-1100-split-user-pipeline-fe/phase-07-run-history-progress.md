---
phase: 7
title: "Run History & Progress"
status: pending
priority: P2
effort: "1d"
dependencies: [6]
---

# Phase 7: Run History & Progress

## Overview
Port trang lịch sử run + chi tiết run (xem stage results, export HTML/DOCX) sang user-app.

## Requirements
- Functional:
  - `/pipelines/[id]/runs` — list run của template (paginate, filter status).
  - `/runs/[runId]` (hoặc `/pipelines/[id]/runs/[runId]`) — chi tiết 1 run: stage results, timing, log, link export.
  - Cho phép download export HTML/DOCX.
  - End-user chỉ thấy run của chính họ (nếu backend có user_id; nếu chưa, thấy tất cả — note trong report).
- Non-functional:
  - Reuse `RunHistory`, `PipelineRunDetailPage`, `ResultsViewer`, `StageResultsPanel` qua shared.

## Architecture
```
apps/user-app/src/app/
├── pipelines/[id]/runs/
│   ├── page.tsx          # list runs of template
│   └── [runId]/page.tsx  # run detail
```

Hooks:
- `useRunHistory(templateId)`
- `useRun(runId)` (existing `usePipelineRun`)
- `useExportRun(runId, format)`

## Related Code Files
- Create:
  - `apps/user-app/src/app/pipelines/[id]/runs/page.tsx`
  - `apps/user-app/src/app/pipelines/[id]/runs/[runId]/page.tsx`
- Modify (move sang shared):
  - `packages/shared/src/components/pipeline/RunHistory.tsx`
  - `packages/shared/src/components/pipeline/PipelineRunDetailPage.tsx`
  - `packages/shared/src/components/pipeline/ResultsViewer.tsx`
  - `packages/shared/src/components/pipeline/StageResultsPanel.tsx`
  - `packages/shared/src/components/pipeline/PrettyOutput.tsx`
- Modify:
  - `apps/admin-app/src/components/pipeline/*` → re-export hoặc xoá khi confirm
- Read for reference:
  - `apps/admin-app/src/components/pipeline/RunHistory.tsx`
  - `apps/admin-app/src/components/pipeline/PipelineRunDetailPage.tsx`

## Implementation Steps
1. Move 5 component history/results sang `packages/shared/src/components/pipeline/`.
2. Move `usePipelineRunHistory` hook (nếu có) sang shared.
3. User-app `/pipelines/[id]/runs/page.tsx` → render `<RunHistory templateId={id} />`.
4. User-app `/pipelines/[id]/runs/[runId]/page.tsx` → render `<PipelineRunDetailPage runId={runId} />`.
5. Kiểm tra link export — endpoint `/api/v1/pipeline/runs/{id}/export` cho phép VIEWER không? Nếu không, xin phase 9 mở quyền.
6. Smoke test: chạy 1 pipeline → xem `/pipelines/[id]/runs` → click vào 1 run → thấy stage results + download export.

## Success Criteria
- [ ] User-app xem được run list + run detail.
- [ ] Download export HTML/DOCX hoạt động.
- [ ] Admin app sau move sang shared vẫn xem history bình thường.

## Risk Assessment
- **R**: Endpoint export trả binary qua proxy axios → CORS/file-download tricky.
  **Mitigation**: dùng `window.open(url + token)` hoặc `fetch + blob`.
- **R**: User-app chưa filter run theo `user_id` nếu backend không lưu → mọi user xem mọi run.
  **Mitigation**: chấp nhận giai đoạn này; ghi note vào phase 9 để bổ sung user_id ở `PipelineRun` document nếu cần.
