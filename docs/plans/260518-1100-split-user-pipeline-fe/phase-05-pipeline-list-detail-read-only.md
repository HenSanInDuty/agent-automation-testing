---
phase: 5
title: "Pipeline List & Detail (read-only)"
status: pending
priority: P1
effort: "1d"
dependencies: [4]
---

# Phase 5: Pipeline List & Detail (read-only)

## Overview
Cài route `/pipelines` (list) và `/pipelines/[id]` (detail read-only) cho user-app. **Loại bỏ** mọi nút Clone/Archive/Delete/Edit/New; chỉ giữ `Run` và `History`.

## Requirements
- Functional:
  - List template available (gọi `GET /api/v1/pipeline-templates`).
  - Search + filter built-in/archived như admin (nhưng không có nút Archive toggle nếu role không phải admin).
  - Click card → `/pipelines/[id]` xem **chi tiết template** (read-only: tên, mô tả, node count, danh sách stage).
  - Nút "Run" lớn → `/pipelines/[id]/run`.
- Non-functional:
  - **Không** import `components/pipeline-builder/*`.
  - Type & hook lấy từ `@auto-at/shared`.

## Architecture
```
apps/user-app/src/
├── app/pipelines/
│   ├── page.tsx                # list
│   └── [id]/
│       └── page.tsx            # read-only detail (no React Flow editor)
└── components/pipelines/
    ├── PipelineListView.tsx    # adapted: bỏ menu CRUD
    ├── PipelineCardRunOnly.tsx # bỏ Clone/Archive/Delete
    └── PipelineDetailView.tsx  # read-only summary
```

Hooks dùng chung từ `@auto-at/shared/hooks`:
- `usePipelineTemplates({ include_archived })`
- `usePipelineTemplate(id)`

## Related Code Files
- Create:
  - `apps/user-app/src/app/pipelines/page.tsx`
  - `apps/user-app/src/app/pipelines/[id]/page.tsx`
  - `apps/user-app/src/components/pipelines/PipelineListView.tsx`
  - `apps/user-app/src/components/pipelines/PipelineCardRunOnly.tsx`
  - `apps/user-app/src/components/pipelines/PipelineDetailView.tsx`
- Modify:
  - `packages/shared/src/hooks/usePipelineTemplates.ts` (move từ admin)
  - `packages/shared/src/index.ts`
- Read for reference:
  - `apps/admin-app/src/components/pipelines/PipelineListPage.tsx`
  - `apps/admin-app/src/components/pipelines/PipelineTemplateCard.tsx`
  - `apps/admin-app/src/hooks/usePipelineTemplates.ts`
- Delete: (none)

## Implementation Steps
1. Move `usePipelineTemplates.ts` từ admin → `packages/shared/src/hooks/`. Trong admin, re-export từ shared.
2. Tạo `PipelineCardRunOnly`: chỉ có icon, tên, mô tả, node count, badge last_run_status, nút **Run** + **History**.
3. `PipelineListView`: header "Available Pipelines", search box, grid card. Bỏ filter `Archived`, bỏ nút "New Pipeline".
4. `PipelineDetailView`: hiển thị:
   - Header: name, version, description.
   - Stats: số node, tags.
   - Bảng đơn giản các stage/node (id + label + agent_id), **không** render React Flow.
   - CTA: nút `Run` link `/pipelines/[id]/run` + nút `History` link `/pipelines/[id]/runs`.
5. Route `app/pipelines/page.tsx` → `<PipelineListView />`.
6. Route `app/pipelines/[id]/page.tsx` → `<PipelineDetailView id={...} />`.
7. Smoke: login viewer/qa → mở `/pipelines` → thấy danh sách, click card vào detail, **không** có icon edit/clone/delete.

## Success Criteria
- [ ] User-app `/pipelines` hiện đầy đủ template.
- [ ] Card không có menu 3-chấm (Clone/Archive/Delete).
- [ ] `/pipelines/[id]` chỉ read-only, không có React Flow builder.
- [ ] Hook `usePipelineTemplates` đã chuyển vào shared, admin-app vẫn dùng OK.

## Risk Assessment
- **R**: Endpoint list trả về cả `archived` → user thấy template không nên dùng.
  **Mitigation**: user-app **luôn** truyền `include_archived=false`; không có toggle.
- **R**: Type `PipelineTemplateListItem` thay đổi khi move sang shared.
  **Mitigation**: copy nguyên type vào shared, không refactor; chỉ thay import path.
