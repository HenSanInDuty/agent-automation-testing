---
phase: 1
title: "Research & Architecture"
status: pending
priority: P1
effort: "4h"
dependencies: []
---

# Phase 1: Research & Architecture

## Overview
Khảo sát code FE hiện tại, xác định ranh giới admin / user-facing và chốt phương án monorepo + shared package trước khi đụng code.

## Requirements
- Functional:
  - Liệt kê tất cả route/component thuộc về user-flow vs admin-flow.
  - Quyết định cấu trúc workspaces, naming, port, env.
  - Định nghĩa boundary code share (types, api client, hooks, UI).
- Non-functional:
  - Không tạo `enhanced` file; sửa trực tiếp khi cần.
  - Document tóm tắt < 150 dòng để dev sau đọc nhanh.

## Architecture
Audit map (xuất ra report):

| Route hiện tại | Phân loại | Đi đâu |
|---|---|---|
| `/login` | both | shared, cả 2 app dùng |
| `/pipelines` (list) | user + admin | user-app: read-only; admin-app: full |
| `/pipelines/[id]` (builder) | admin-only | giữ ở admin-app |
| `/pipelines/[id]/run` | user | port qua user-app, admin giữ |
| `/pipelines/[id]/runs` | both | shared logic |
| `/pipelines/new` | admin-only | admin-app |
| `/chat` | user | port qua user-app (nếu user có quyền) |
| `/admin/llm`, `/admin/agents`, `/admin/users` | admin-only | admin-app |
| `/pipeline` (legacy đơn run) | TBD | confirm bỏ hay giữ |

Component map:
- `components/pipelines/` → user (list read-only) + admin (CRUD)
- `components/pipeline-builder/` → **admin-only**
- `components/pipeline/` → user (run page, progress, results)
- `components/admin/` → **admin-only**
- `components/auth/`, `components/layout/`, `components/ui/`, `components/chat/` → shared

## Related Code Files
- Read: `frontend/src/app/**`, `frontend/src/components/**`, `frontend/src/hooks/**`, `frontend/src/lib/**`, `frontend/src/types/**`, `frontend/src/store/**`, `docker-compose.yml`, `backend/app/main.py`, `backend/app/api/**`, `docs/architecture.md`, `docs/api-flow.md`
- Create: `plans/260518-1100-split-user-pipeline-fe/research/route-classification.md`
- Modify: (none)

## Implementation Steps
1. Đọc toàn bộ `frontend/src/app` và phân loại từng route theo bảng trên.
2. Đọc `auth-context.tsx` để xác định flag role (`isAdmin`, `canCreatePipeline`, `canUseChat`) — confirm còn dùng được hay phải refactor.
3. Đọc `hooks/*` và `lib/api*` để xác định module nào dùng cho user vs admin.
4. Liệt kê tất cả endpoint backend FE đang gọi (grep `axios.` / `fetch(`).
5. Cross-check với backend `app/api/v1/*` để xác định endpoint nào cần `require_admin` mà chưa có.
6. Viết `research/route-classification.md` chốt boundary; nếu phát hiện lệch so với plan.md → cập nhật plan.md.
7. Quyết định version: Next 15.3 + React 19 (mirror admin) cho user-app.

## Success Criteria
- [ ] File `research/route-classification.md` tồn tại, liệt kê đầy đủ route/component và đích đến.
- [ ] Danh sách endpoint user-app cần gọi được liệt kê + RBAC role tối thiểu.
- [ ] Không phát hiện shared-state ẩn (Zustand store, global var) chặn việc tách app.
- [ ] Plan.md updated nếu phát hiện edge case mới.

## Risk Assessment
- **R**: Zustand `pipelineStore` đang lưu state run hiện tại — user-app cần copy hay share?
  **Mitigation**: store là client-only, mỗi app có instance riêng; chuyển định nghĩa store sang `packages/shared` nếu logic giống hệt.
- **R**: WebSocket logic gắn chặt với store.
  **Mitigation**: share luôn WS connector qua `packages/shared`.
