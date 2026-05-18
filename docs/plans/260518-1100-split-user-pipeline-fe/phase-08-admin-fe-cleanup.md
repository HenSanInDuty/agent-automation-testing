---
phase: 8
title: "Admin FE Cleanup"
status: pending
priority: P2
effort: "4h"
dependencies: [4, 5, 6, 7]
---

# Phase 8: Admin FE Cleanup

## Overview
Sau khi user-app đã port xong end-user flow, gọn lại admin-app: bỏ wrapper/import trùng lặp, đảm bảo admin chỉ giữ feature **không thể có** trên user-app (builder, LLM mgmt, agent mgmt, user mgmt, chat — nếu thuộc admin).

## Requirements
- Functional:
  - Admin-app vẫn build/run trên port 3001 không lỗi.
  - Mọi component đã chuyển vào shared phải được import từ `@auto-at/shared`, không còn duplicate trong admin.
  - Route `/pipelines/[id]/run`, `/pipelines/[id]/runs/*` vẫn hoạt động trong admin (admin được test luồng).
  - Sidebar admin: gắn nhãn "Admin Console", thêm link "Open User Portal" → `http://localhost:3002`.
- Non-functional:
  - Không xoá feature nào hiện có.
  - Code smell cleanup: dead import, type mơ hồ.

## Architecture
```
apps/admin-app/src/
├── components/
│   ├── pipeline/        → giảm: chỉ giữ wrapper hoặc thin re-export
│   ├── pipelines/       → giữ full (builder list có Clone/Archive/Delete)
│   ├── pipeline-builder/ → giữ nguyên (admin-only)
│   ├── admin/           → giữ
│   ├── chat/            → giữ (admin có thể chat)
│   └── layout/
│       └── Sidebar.tsx  → cập nhật label
└── hooks/ + lib/        → re-export shared, xoá duplicate
```

## Related Code Files
- Modify:
  - `apps/admin-app/src/components/layout/Sidebar.tsx` (rebrand "Admin Console", thêm link user portal)
  - `apps/admin-app/src/app/layout.tsx` (metadata title "Auto-AT Admin")
  - `apps/admin-app/src/hooks/*` re-export → xoá file gốc nếu unused
  - `apps/admin-app/src/lib/*` tương tự
- Delete (sau kiểm tra):
  - duplicate `components/pipeline/*` đã có ở shared
  - duplicate `store/pipelineStore.ts`
  - duplicate `lib/auth-context.tsx`
- Create: (none)

## Implementation Steps
1. Grep `frontend/src/components/pipeline/` (giờ `apps/admin-app/...`) — file nào không còn ref ngoài shared → xoá.
2. Cập nhật `Sidebar.tsx`:
   - Đổi brand từ "Auto-AT" → "Auto-AT Admin".
   - Thêm `Dev` group item: `Open User Portal` → external link `process.env.NEXT_PUBLIC_USER_APP_URL || "http://localhost:3002"`.
3. Đổi metadata `layout.tsx` title → `Auto-AT Admin – Pipeline Management`.
4. Chạy `npm run build` trong admin-app → zero error/warning new.
5. Chạy `eslint` trên cả 2 app — sửa dead import.

## Success Criteria
- [ ] Admin app build sạch (0 warning new).
- [ ] Sidebar có nhãn Admin + link User Portal.
- [ ] Không file nào trong admin-app duplicate code đã move sang shared.
- [ ] User-flow trong admin (test only) vẫn chạy.

## Risk Assessment
- **R**: Xoá quá tay — admin mất file đang dùng.
  **Mitigation**: trước khi delete, grep usage trong cả admin-app + user-app + shared.
- **R**: Sidebar redirect cross-origin → CORS với localhost OK, nhưng prod cần CORS frontend domain.
  **Mitigation**: phase 10 docker sẽ wire env var.
