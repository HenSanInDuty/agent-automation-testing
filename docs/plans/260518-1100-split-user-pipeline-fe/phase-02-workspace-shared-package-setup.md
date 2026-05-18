---
phase: 2
title: "Workspace & Shared Package Setup"
status: pending
priority: P1
effort: "4h"
dependencies: [1]
---

# Phase 2: Workspace & Shared Package Setup

## Overview
Khởi tạo npm workspaces ở root, di chuyển `frontend/` → `apps/admin-app/`, tạo `packages/shared` rỗng có TS config phù hợp.

## Requirements
- Functional:
  - Root `package.json` khai báo `workspaces: ["apps/*", "packages/*"]`.
  - Di chuyển `frontend/` → `apps/admin-app/`, app vẫn build và chạy được ở port 3001.
  - Tạo `packages/shared` với `package.json`, `tsconfig.json`, export rỗng.
  - Admin app import được `@auto-at/shared` (smoke test bằng 1 type/util đơn giản).
- Non-functional:
  - Không động vào logic admin; chỉ là rename + wire workspaces.
  - Dùng `transpilePackages` thay vì pre-build (KISS).

## Architecture
```
auto-at/
├── package.json                   # workspaces root
├── tsconfig.base.json             # paths cho @auto-at/shared
├── apps/
│   └── admin-app/                 # ← frontend/ cũ
│       ├── package.json           # name: @auto-at/admin-app
│       ├── next.config.ts         # transpilePackages: ["@auto-at/shared"]
│       └── ...
└── packages/
    └── shared/
        ├── package.json           # name: @auto-at/shared, main: src/index.ts
        ├── tsconfig.json
        └── src/index.ts
```

## Related Code Files
- Create:
  - `package.json` (root)
  - `tsconfig.base.json`
  - `packages/shared/package.json`
  - `packages/shared/tsconfig.json`
  - `packages/shared/src/index.ts`
- Modify:
  - `apps/admin-app/package.json` (đổi `name`, add `@auto-at/shared` dep workspace)
  - `apps/admin-app/next.config.ts` (thêm `transpilePackages`)
  - `apps/admin-app/tsconfig.json` (extends `../../tsconfig.base.json`, add path mapping)
  - `docker-compose.yml` (đổi context `./frontend` → `./apps/admin-app`)
  - `.gitignore` (thêm `node_modules` ở mọi workspace)
- Delete: (none — rename, không xoá)

## Implementation Steps
1. `git mv frontend apps/admin-app` (Windows: dùng `Move-Item`).
2. Tạo root `package.json`:
   ```json
   {
     "name": "auto-at",
     "private": true,
     "workspaces": ["apps/*", "packages/*"],
     "scripts": {
       "dev:admin": "npm --workspace @auto-at/admin-app run dev",
       "dev:user": "npm --workspace @auto-at/user-app run dev",
       "build": "npm --workspaces --if-present run build"
     }
   }
   ```
3. Tạo `tsconfig.base.json` với `paths: { "@auto-at/shared/*": ["packages/shared/src/*"] }`.
4. Đổi `apps/admin-app/package.json.name` → `@auto-at/admin-app`; thêm dep `"@auto-at/shared": "*"`.
5. Sửa `apps/admin-app/next.config.ts`:
   ```ts
   export default { transpilePackages: ["@auto-at/shared"] };
   ```
6. Tạo `packages/shared/package.json`:
   ```json
   { "name": "@auto-at/shared", "version": "0.0.0", "private": true,
     "main": "src/index.ts", "types": "src/index.ts" }
   ```
7. Tạo `packages/shared/src/index.ts` với 1 export smoke test:
   ```ts
   export const SHARED_VERSION = "0.0.0";
   ```
8. Cập nhật `docker-compose.yml`: service `frontend` → `admin-app`, `context: ./apps/admin-app`, giữ port 3001.
9. Chạy `npm install` ở root, verify `apps/admin-app/node_modules` không sinh ra (do hoist).
10. Smoke test: `npm run dev:admin` → mở `http://localhost:3001` thấy UI cũ; import `SHARED_VERSION` vào 1 file admin, console.log để verify.

## Success Criteria
- [ ] Root `package.json` có `workspaces`.
- [ ] `npm run dev:admin` chạy được, UI giống hệt trước rename.
- [ ] Admin app import được `@auto-at/shared` không lỗi TS.
- [ ] Docker build admin-app từ path mới thành công.
- [ ] Không file nào còn ref đường dẫn `frontend/`.

## Risk Assessment
- **R**: Windows `git mv` đôi khi giữ case sai → mismatch trên Linux CI.
  **Mitigation**: verify bằng `git ls-files` sau khi mv.
- **R**: `node_modules` cũ trong `frontend/` rò sang sau khi rename.
  **Mitigation**: xoá `node_modules` toàn repo, install lại từ root.
- **R**: Next 15 transpilePackages không pick up TS path khi monorepo.
  **Mitigation**: dùng `transpilePackages` + `tsconfig paths`; nếu vẫn lỗi, fallback `tsup` build shared.
