---
phase: 4
title: "Auth & Layout"
status: pending
priority: P1
effort: "1d"
dependencies: [2, 3]
---

# Phase 4: Auth & Layout

## Overview
Đưa auth (JWT login/logout, AuthContext, AuthGuard) và API client vào `@auto-at/shared`; user-app dùng lại. Tạo layout gọn cho user-app: chỉ có navbar (logo + user menu), không có sidebar admin.

## Requirements
- Functional:
  - User login bằng cùng `/api/v1/auth/login`; lưu token vào localStorage.
  - Role `admin` đăng nhập vào user-app vẫn được phép (admin có thể xem cả 2 UI), nhưng user-app **không** show menu admin.
  - Role `viewer`/`qa` không được phép vào admin-app (đã có sẵn); ngược lại, user-app cho phép cả 3.
  - Logout xoá token, redirect `/login`.
  - 401 từ API → tự logout + redirect login.
- Non-functional:
  - `AuthContext` định nghĩa một lần ở `@auto-at/shared`, cả 2 app import.
  - API client (axios instance) cũng nằm trong shared, đọc `NEXT_PUBLIC_API_URL` từ caller (truyền vào constructor).

## Architecture
```
packages/shared/src/
├── auth/
│   ├── auth-context.tsx     # AuthProvider, useAuth (từ admin-app cũ)
│   ├── auth-guard.tsx       # AuthGuard component
│   └── types.ts             # AuthUser, UserRole
├── api/
│   ├── client.ts            # axios instance factory (cấu hình baseURL từ caller)
│   └── endpoints.ts         # constants (LOGIN_URL, etc.)
└── index.ts                 # re-export

apps/user-app/src/components/layout/
└── TopNav.tsx               # minimal navbar (no sidebar)
```

Role gate đơn giản cho user-app:
```ts
// chỉ chặn user-app không cho gọi endpoint write
// (UI vẫn open cho cả admin để admin test luồng end-user)
```

## Related Code Files
- Create:
  - `packages/shared/src/auth/auth-context.tsx`
  - `packages/shared/src/auth/auth-guard.tsx`
  - `packages/shared/src/auth/types.ts`
  - `packages/shared/src/api/client.ts`
  - `packages/shared/src/api/endpoints.ts`
  - `apps/user-app/src/app/login/page.tsx`
  - `apps/user-app/src/components/layout/TopNav.tsx`
- Modify:
  - `packages/shared/src/index.ts` (export auth + api)
  - `apps/admin-app/src/lib/auth-context.tsx` → re-export từ `@auto-at/shared/auth`
  - `apps/admin-app/src/lib/api*.ts` → re-export `createApiClient` từ shared
  - `apps/user-app/src/app/layout.tsx` (wrap với AuthProvider + AuthGuard)
  - `apps/user-app/src/app/providers.tsx`
- Delete:
  - các file `auth-context.tsx`, `api*.ts` trùng lặp ở admin-app sau khi confirm shared hoạt động

## Implementation Steps
1. Đọc `apps/admin-app/src/lib/auth-context.tsx` và `lib/api*.ts`, port sang `packages/shared/src/auth/` và `packages/shared/src/api/`.
2. `createApiClient(baseURL, getToken)` trả về axios instance — caller (mỗi app) truyền `NEXT_PUBLIC_API_URL` và hàm đọc token.
3. Trong `auth-context.tsx`, **xoá hardcode** `process.env.NEXT_PUBLIC_API_URL`; nhận `apiBaseUrl` prop từ `AuthProvider`.
4. Update admin-app: import `AuthProvider` từ `@auto-at/shared`, pass `apiBaseUrl={process.env.NEXT_PUBLIC_API_URL}`.
5. Tạo `user-app/src/components/layout/TopNav.tsx`: logo + tên app + user dropdown (username, role, logout). Không có sidebar.
6. User-app `layout.tsx`: wrap `<AuthProvider apiBaseUrl=...><AuthGuard><TopNav />{children}</AuthGuard></AuthProvider>`.
7. User-app `login/page.tsx`: copy từ admin (form bcrypt login). Sau login redirect `/pipelines`.
8. Test 3 role:
   - `admin` login → vào được user-app, TopNav hiện role badge "ADMIN".
   - `qa` login → vào được, không thấy chức năng admin.
   - `viewer` login → vào được, chỉ thấy nút Run (logic ở phase sau).

## Success Criteria
- [ ] User login + logout hoạt động trên user-app port 3002.
- [ ] Admin app vẫn login + logout bình thường sau refactor.
- [ ] `auth-context` chỉ tồn tại trong `packages/shared`, không có duplicate trong app.
- [ ] 401 response → auto redirect login ở cả 2 app.
- [ ] User-app **không** có sidebar.

## Risk Assessment
- **R**: Cookie/localStorage key trùng giữa 2 app cùng origin (localhost) → conflict.
  **Mitigation**: dùng cùng key `auto_at_token` (mong muốn SSO giữa 2 app). Nếu cần tách → đổi key per app via env.
- **R**: AuthContext SSR hydration mismatch.
  **Mitigation**: giữ `"use client"`, hydrate trong `useEffect`.
- **R**: User-app cho QA truy cập nhưng QA cũng có quyền view admin → mơ hồ.
  **Mitigation**: chốt — user-app open cho mọi role authenticated; ngăn write bằng backend RBAC (phase 9).
