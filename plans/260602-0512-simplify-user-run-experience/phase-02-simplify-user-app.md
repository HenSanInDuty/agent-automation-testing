---
phase: 2
title: Simplify User App
status: completed
priority: P1
effort: 1.5h
dependencies:
  - 1
---

# Phase 2: Simplify User App

## Overview

Bật chế độ đơn giản ở `user-app`: trang chạy truyền props mới (Phase 1) và trang danh sách bỏ thanh search. Đây là các file **chỉ thuộc user-app** (không shared) → không ảnh hưởng admin.

## Requirements

- Functional:
  - Trang `/pipelines/[id]/run` của user truyền `hideLlmProfile`, `hideRunControls`, `showResultsInline` = `true`.
  - Trang `/pipelines` của user bỏ ô search; hiển thị toàn bộ pipeline dạng card; vẫn giữ trạng thái loading/empty/error.
- Non-functional: giữ layout/responsive hiện tại; không tạo file "enhanced" mới — sửa trực tiếp.

## Architecture

- `apps/user-app/src/app/pipelines/[id]/run/page.tsx` đã render `<PipelineRunPage templateId={...} />` (16 dòng). Chỉ thêm 3 prop.
- `apps/user-app/src/app/pipelines/page.tsx` (491 dòng) chứa `HeroHeader` (có `<input type="search">`), state `query`, `filtered` useMemo, và `EmptyState` có nút clear-search. Gỡ phần search, đơn giản hoá còn list-all.

## Related Code Files

- Modify: `apps/user-app/src/app/pipelines/[id]/run/page.tsx`
- Modify: `apps/user-app/src/app/pipelines/page.tsx`
- Read for context: `packages/shared/src/components/pipeline/PipelineRunPage.tsx` (props mới từ Phase 1)

## Implementation Steps

### A. Trang chạy (`pipelines/[id]/run/page.tsx`)

1. Sửa lời gọi component:
   ```tsx
   <PipelineRunPage
     templateId={templateId}
     hideLlmProfile
     hideRunControls
     showResultsInline
   />
   ```
2. Cập nhật comment hiện có cho khớp (đang ghi chú về DAG admin-only).

### B. Trang danh sách (`pipelines/page.tsx`)

3. `HeroHeader`: bỏ prop `query`/`onQueryChange` và toàn bộ block `<input type="search">` (dòng ~327-346) + import `Search` icon nếu không còn dùng. Giữ tiêu đề + badge tổng số. Có thể sửa câu mô tả "Select a pipeline to run…" → bỏ chữ "Select" cho hợp ngữ cảnh (vd "Chạy một pipeline để thực hiện quy trình kiểm thử tự động.").
4. Trong `PipelinesPage`: bỏ state `query`, bỏ `filtered` useMemo, render trực tiếp `templates` thay cho `filtered`.
5. `EmptyState`: bỏ nhánh `isFiltered`/nút "Clear search" (vì không còn search). Chỉ giữ thông điệp "No pipelines yet". Có thể đơn giản hoá props (bỏ `query`/`onClearQuery`).
6. Dọn import lucide không còn dùng (`Search`) để tránh lỗi lint no-unused.

## Todo List

- [ ] Run page truyền `hideLlmProfile` + `hideRunControls` + `showResultsInline`
- [ ] Bỏ `<input search>` khỏi `HeroHeader`
- [ ] Bỏ state `query` + `filtered`, render trực tiếp `templates`
- [ ] Đơn giản hoá `EmptyState` (bỏ clear-search)
- [ ] Dọn import thừa (Search icon…)

## Success Criteria

- [ ] User mở `/pipelines/[id]/run`: KHÔNG còn dropdown LLM Profile, KHÔNG còn nút Pause/Cancel; vẫn còn Document upload + nút Run.
- [ ] Run xong: kết quả đầy đủ (ResultsViewer) hiện ngay tại trang, không cần bấm đi đâu.
- [ ] `/pipelines`: không còn thanh search; list pipeline hiển thị đầy đủ.
- [ ] `npm run build:user` (hoặc lint) không lỗi import/unused.

## Risk Assessment

- **Lint no-unused-vars** sau khi gỡ search → nhớ xoá import/biến thừa (`Search`, `query`, `EmptyState` props).
- **Admin list page** dùng search riêng → đảm bảo CHỈ sửa file trong `apps/user-app/` (không phải shared component).
