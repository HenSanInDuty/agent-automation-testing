---
phase: 6
title: "Pipeline Run Flow"
status: pending
priority: P1
effort: "1.5d"
dependencies: [5]
---

# Phase 6: Pipeline Run Flow

## Overview
Port luồng "Run Pipeline" (upload document, chọn LLM profile, bấm Run, theo dõi WS realtime) từ admin sang user-app. Bỏ những control không cần thiết cho end-user.

## Requirements
- Functional:
  - Route `/pipelines/[id]/run` cho phép:
    - Upload file (DOCX/PDF/TXT) optional.
    - Chọn LLM profile từ danh sách active.
    - Bấm `Run` → tạo run, redirect/navigate `/runs/[runId]` hoặc inline progress.
  - Hiển thị WS progress (executionLayers, nodeStatuses, currentNode, logs) y như admin.
  - Cho phép Pause / Resume / Cancel run đang active (quyền QA+).
  - Khi terminal → hiển thị TerminalSummaryCard + link tới Run History.
- Non-functional:
  - Tái sử dụng `PipelineRunView` (React Flow read-only visualization), `PipelineControls`, `LogsPanel`, `DocumentUpload`, `LLMProfileSelector` — port qua shared hoặc per-app.
  - `pipelineStore` (Zustand) chuyển vào `packages/shared`.

## Architecture
- `packages/shared/src/store/pipelineStore.ts` — single source of truth cho store + WS connector.
- `packages/shared/src/hooks/usePipeline.ts` — `useStartDagPipeline`, `usePipelineRun`, `useLLMProfiles`.
- `packages/shared/src/components/pipeline/` — DAG view + progress, dùng cả 2 app.
- `apps/user-app/src/app/pipelines/[id]/run/page.tsx` → render `<RunPipelineView templateId={id} />`.

Data flow giữ nguyên backend:
```
User-app  ──POST /api/v1/pipeline/runs──▶ Backend  ──WS /ws/pipeline/{run_id}──▶ User-app
                                          ─emit Kafka─▶ ClickHouse
```

## Related Code Files
- Create:
  - `apps/user-app/src/app/pipelines/[id]/run/page.tsx`
  - `apps/user-app/src/components/pipeline/RunPipelineView.tsx` (composition wrapper gọn cho user)
- Modify (move vào shared):
  - `packages/shared/src/store/pipelineStore.ts` ← từ `frontend/src/store/pipelineStore.ts`
  - `packages/shared/src/hooks/usePipeline.ts` ← từ `frontend/src/hooks/usePipeline.ts`
  - `packages/shared/src/components/pipeline/PipelineRunView.tsx`
  - `packages/shared/src/components/pipeline/PipelineControls.tsx`
  - `packages/shared/src/components/pipeline/PipelineProgress.tsx`
  - `packages/shared/src/components/pipeline/DocumentUpload.tsx`
  - `packages/shared/src/components/pipeline/LLMProfileSelector.tsx`
- Modify (admin re-export):
  - `apps/admin-app/src/components/pipeline/*.tsx` → re-export hoặc import từ shared
  - `apps/admin-app/src/store/pipelineStore.ts` → re-export
  - `apps/admin-app/src/hooks/usePipeline.ts` → re-export
- Delete: (sau khi confirm admin chạy OK với import từ shared)

## Implementation Steps
1. Move `pipelineStore.ts` + WS connector vào shared. Verify admin chạy được.
2. Move `usePipeline.ts` (mutations + queries) sang shared. Endpoint paths đặt trong `packages/shared/src/api/endpoints.ts`.
3. Move `PipelineRunView`, `PipelineControls`, `DocumentUpload`, `LLMProfileSelector` sang shared.
4. Trong user-app tạo `RunPipelineView.tsx`: cô đọng từ `PipelineRunPage.tsx` của admin:
   - Bỏ link "Back to builder".
   - Header chỉ có tên template + History link.
   - 2-column như admin (controls trái, DAG + progress phải).
   - Reuse `LogsPanel` từ shared.
5. Route `/pipelines/[id]/run/page.tsx` → render wrapper.
6. Verify cả 2 app cùng chạy 1 pipeline → store độc lập (per app instance) nhưng UI giống nhau.

## Success Criteria
- [ ] User end-to-end: login → list → click Run → upload file → bấm Run → thấy WS progress realtime → terminal screen.
- [ ] Pause/Resume/Cancel hoạt động (role QA+).
- [ ] Admin app vẫn run pipeline được sau khi move sang shared.
- [ ] Không duplicate code WS connector giữa 2 app.

## Risk Assessment
- **R**: WS URL khác nhau giữa env dev/prod → user-app không kết nối được.
  **Mitigation**: AuthProvider/StoreProvider truyền `wsBaseUrl` xuống store.
- **R**: React Flow lib bundle size lớn.
  **Mitigation**: dynamic import `PipelineRunView` (read-only) chỉ ở route run.
- **R**: Store singleton (`zustand create`) bị share giữa 2 Next dev server → state leak.
  **Mitigation**: zustand store là module-scoped, mỗi app process riêng → OK; chỉ cần check khi đóng gói SSR.
