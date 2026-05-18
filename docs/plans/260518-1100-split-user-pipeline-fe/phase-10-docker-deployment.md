---
phase: 10
title: "Docker & Deployment"
status: pending
priority: P2
effort: "4h"
dependencies: [3, 8, 9]
---

# Phase 10: Docker & Deployment

## Overview
Cập nhật `docker-compose.yml`, `Dockerfile`, `start.bat`/`stop.bat` để spin up cả `admin-app` (3001) và `user-app` (3002). Sản phẩm: chạy `docker compose up` → 3 service FE/BE healthcheck pass.

## Requirements
- Functional:
  - Dockerfile riêng cho user-app (mirror admin), build từ context `apps/user-app`.
  - docker-compose: service `admin-app` (rename từ `frontend`), service `user-app` (mới).
  - Env mỗi service tự đọc `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL`, `PORT`.
  - `start.bat` / `stop.bat` cập nhật tên service.
  - Admin Dockerfile / user Dockerfile dùng workspaces install (`npm ci` ở root + COPY apps).
- Non-functional:
  - Build cache hiệu quả: COPY `package*.json` trước, install, rồi copy src.
  - Image size không tăng quá 1.5x so với hiện tại.

## Architecture
```
docker-compose.yml
├── mongodb
├── minio
├── kafka
├── clickhouse
├── backend (port 8000)
├── admin-app (port 3001)     ← rename frontend
└── user-app  (port 3002)     ← MỚI
```

Dockerfile pattern (workspaces-aware):
```dockerfile
# apps/user-app/Dockerfile (tương tự admin)
FROM node:20-alpine AS deps
WORKDIR /repo
COPY package.json package-lock.json ./
COPY apps/user-app/package.json apps/user-app/
COPY apps/admin-app/package.json apps/admin-app/
COPY packages/shared/package.json packages/shared/
RUN npm ci

FROM node:20-alpine AS dev
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY . .
WORKDIR /repo/apps/user-app
EXPOSE 3002
CMD ["npm","run","dev"]
```

## Related Code Files
- Create:
  - `apps/user-app/Dockerfile`
- Modify:
  - `apps/admin-app/Dockerfile` (chuyển sang workspaces-aware pattern)
  - `docker-compose.yml` (rename frontend → admin-app, thêm user-app, update ALLOWED_ORIGINS)
  - `start.bat`, `stop.bat`
  - `apps/admin-app/package.json` / `apps/user-app/package.json` (scripts đảm bảo PORT bind)
- Read: `frontend/Dockerfile` cũ để mirror

## Implementation Steps
1. Refactor `apps/admin-app/Dockerfile` về pattern workspaces-aware (build từ root context).
2. Tạo `apps/user-app/Dockerfile` tương tự admin (port 3002).
3. Cập nhật `docker-compose.yml`:
   ```yaml
   admin-app:
     build: { context: ., dockerfile: apps/admin-app/Dockerfile, target: dev }
     ports: ["3001:3001"]
     environment:
       - NEXT_PUBLIC_API_URL=http://localhost:8000
       - PORT=3001
     volumes:
       - ./apps/admin-app/src:/repo/apps/admin-app/src
       - ./packages/shared/src:/repo/packages/shared/src
   user-app:
     build: { context: ., dockerfile: apps/user-app/Dockerfile, target: dev }
     ports: ["3002:3002"]
     environment:
       - NEXT_PUBLIC_API_URL=http://localhost:8000
       - PORT=3002
     volumes:
       - ./apps/user-app/src:/repo/apps/user-app/src
       - ./packages/shared/src:/repo/packages/shared/src
   ```
4. Backend env `ALLOWED_ORIGINS=http://localhost:3001,http://localhost:3002`.
5. `start.bat` / `stop.bat` echo URL cả 2 app.
6. Test:
   - `docker compose build`
   - `docker compose up -d`
   - `curl http://localhost:3001` và `http://localhost:3002` → 200.
   - Login user via 3002, run pipeline → WS connect tới 8000 OK.

## Success Criteria
- [ ] `docker compose up` đưa cả 2 FE service lên healthy.
- [ ] Image size user-app ~ admin-app.
- [ ] Hot reload: sửa file trong `packages/shared/src` → cả 2 app reload.

## Risk Assessment
- **R**: Mount volume `packages/shared/src` vào 2 container → race/lock trên Windows.
  **Mitigation**: file watcher mỗi container độc lập; OK trên Docker Desktop.
- **R**: `npm ci` ở root copy nhiều file lock → cache invalidate dễ.
  **Mitigation**: chỉ COPY `package*.json` ở stage `deps`, source ở stage sau.
