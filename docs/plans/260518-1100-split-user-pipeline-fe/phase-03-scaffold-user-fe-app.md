---
phase: 3
title: "Scaffold User FE App"
status: pending
priority: P1
effort: "4h"
dependencies: [2]
---

# Phase 3: Scaffold User FE App

## Overview
Tạo Next.js app `apps/user-app` (port 3002), copy nền tảng UI (Tailwind v4, Inter, theme dark `#101622`) từ admin-app để đồng nhất design, link `@auto-at/shared`.

## Requirements
- Functional:
  - `npm run dev:user` → mở `http://localhost:3002` thấy trang trống "Auto-AT".
  - Tailwind 4 hoạt động, dùng được mọi class util.
  - Import được hook/type từ `@auto-at/shared`.
  - `.env.local` cấu hình `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL`.
- Non-functional:
  - **Không** copy folder `app/admin/`, `app/pipelines/new/`, `app/pipelines/[id]/page.tsx` (builder), `components/pipeline-builder/`, `components/admin/`.
  - Giữ size repo nhỏ — chỉ những file cần thiết.

## Architecture
```
apps/user-app/
├── package.json          # name: @auto-at/user-app, dep: @auto-at/shared
├── next.config.ts        # transpilePackages: ["@auto-at/shared"]
├── tsconfig.json         # extends ../../tsconfig.base.json
├── postcss.config.mjs
├── public/
└── src/
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx          # redirect → /pipelines
    │   ├── globals.css
    │   ├── providers.tsx
    │   └── login/page.tsx
    └── components/
        └── (chỉ những gì cần, port từ admin tới đâu sửa tới đó)
```

## Related Code Files
- Create:
  - `apps/user-app/package.json`
  - `apps/user-app/next.config.ts`
  - `apps/user-app/next-env.d.ts`
  - `apps/user-app/tsconfig.json`
  - `apps/user-app/postcss.config.mjs`
  - `apps/user-app/src/app/layout.tsx`
  - `apps/user-app/src/app/page.tsx`
  - `apps/user-app/src/app/globals.css`
  - `apps/user-app/src/app/providers.tsx`
  - `apps/user-app/public/favicon.ico`
- Read for reference: `apps/admin-app/package.json`, `apps/admin-app/src/app/layout.tsx`, `apps/admin-app/src/app/providers.tsx`, `apps/admin-app/src/app/globals.css`, `apps/admin-app/next.config.ts`
- Modify: (none)

## Implementation Steps
1. Copy `apps/admin-app/package.json` → `apps/user-app/package.json`. Đổi `name: "@auto-at/user-app"`, đổi `dev`/`start` port → 3002.
2. Copy `next.config.ts`, `postcss.config.mjs`, `tsconfig.json` → user-app; chỉnh `tsconfig.extends`.
3. Copy `src/app/globals.css` y nguyên (giữ design token).
4. Copy `src/app/layout.tsx`; **chỉnh metadata** title → `Auto-AT — Run Pipelines`, mô tả ngắn hơn.
5. Tạo `src/app/page.tsx` redirect `/pipelines`.
6. Copy `src/app/providers.tsx` (React Query + Toast).
7. Tạo `.env.local.example`:
   ```
   NEXT_PUBLIC_API_URL=http://localhost:8000
   NEXT_PUBLIC_WS_URL=ws://localhost:8000
   PORT=3002
   ```
8. Trong root `package.json`, đảm bảo có script `dev:user`.
9. Smoke test: `npm run dev:user` → 3002 hiển thị trang trống không lỗi hydration.

## Success Criteria
- [ ] `apps/user-app` build và dev được trên port 3002.
- [ ] Tailwind class hoạt động (test bằng 1 div bg).
- [ ] Import từ `@auto-at/shared` không lỗi TS.
- [ ] Không có file builder/admin nào sót lại trong user-app.

## Risk Assessment
- **R**: Copy nhầm file admin → vô tình lộ UI builder.
  **Mitigation**: tạo file mới minimal, **không** dùng `cp -r`; chỉ port khi tới phase tương ứng.
- **R**: Tailwind v4 cần `@tailwindcss/postcss` — quên cài lại trong user-app.
  **Mitigation**: copy `postcss.config.mjs` + chạy `npm install` ở root để hoist.
