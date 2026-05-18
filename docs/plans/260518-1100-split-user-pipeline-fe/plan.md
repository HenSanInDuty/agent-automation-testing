---
title: "Split User Pipeline FE from Admin FE"
description: ""
status: pending
priority: P2
branch: "develop"
tags: []
blockedBy: []
blocks: []
created: "2026-05-18T15:05:34.043Z"
createdBy: "ck:plan"
source: skill
---

# Split User Pipeline FE from Admin FE

## Overview

Tách Next.js frontend hiện tại thành **2 app riêng biệt** trong một npm workspaces monorepo:

- **`apps/user-app`** (port 3002) — End-user FE mới: chỉ duyệt template, chạy pipeline, xem progress + run history. **Không có** trang builder/admin.
- **`apps/admin-app`** (port 3001, kế thừa `frontend/` hiện tại) — Admin Console: quản lý templates (builder), LLM profiles, agent configs, users.
- **`packages/shared`** — types, API client (axios), auth context, hooks và UI primitives dùng chung để tránh duplicate.

Backend FastAPI đã có JWT + RBAC (`ADMIN | QA | VIEWER`); chỉ cần siết RBAC một chút (chặn write template từ user-app) và bổ sung CORS cho port 3002.

## Goals & Non-goals

**Goals**
- End-user truy cập một URL riêng (port 3002) chỉ thấy luồng "chạy pipeline" — không có nút chỉnh sửa template, không có menu Admin.
- Admin (cũ) giữ nguyên 100% chức năng builder/management ở port 3001.
- Share code tối đa giữa 2 app (types, hooks, API client) qua `packages/shared`.
- Hot-reload, Docker, env config độc lập cho từng app.

**Non-goals**
- KHÔNG viết lại backend; chỉ điều chỉnh CORS + thêm decorator RBAC ở vài endpoint write.
- KHÔNG xây UI builder/chỉnh sửa template trên user-app — read-only hoàn toàn.
- KHÔNG đụng tới Mongo schema, DAG runner, hay Crews.

## Architecture (monorepo)

```
auto-at/
├── apps/
│   ├── admin-app/      ← di chuyển từ frontend/ (port 3001) — admin/builder
│   └── user-app/       ← MỚI (port 3002) — end-user run pipeline
├── packages/
│   └── shared/         ← MỚI — types, api-client, auth-context, hooks, ui primitives
├── backend/            ← unchanged (chỉ CORS + RBAC tweak)
├── docker-compose.yml  ← thêm service user-app, đổi tên frontend → admin-app
└── package.json        ← workspaces root
```

## Key Decisions

| Decision | Choice | Lý do |
|----------|--------|-------|
| Monorepo tool | npm workspaces (built-in) | KISS — Next 15 + npm 10 đủ dùng, không cần Turborepo/pnpm |
| User-app stack | Next 15 + React 19 + Tailwind 4 (mirror admin) | Tận dụng kiến thức team, reuse `packages/shared` dễ |
| Shared package | TypeScript source-only, no build step | Next transpilePackages = `["@auto-at/shared"]` |
| Port mapping | admin 3001, user 3002 | Tránh xung đột, giữ admin nguyên |
| Auth | Cùng JWT, cùng `/auth/login`, role-based redirect | Chỉ admin được vào admin-app; viewer/qa được vào user-app |
| Routing | `/` (list) → `/pipelines/{id}/run` → `/runs/{runId}` | Bỏ hẳn `/pipelines/{id}` builder route trên user-app |

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Research & Architecture](./phase-01-research-architecture.md) | Pending |
| 2 | [Workspace & Shared Package Setup](./phase-02-workspace-shared-package-setup.md) | Pending |
| 3 | [Scaffold User FE App](./phase-03-scaffold-user-fe-app.md) | Pending |
| 4 | [Auth & Layout](./phase-04-auth-layout.md) | Pending |
| 5 | [Pipeline List & Detail (read-only)](./phase-05-pipeline-list-detail-read-only.md) | Pending |
| 6 | [Pipeline Run Flow](./phase-06-pipeline-run-flow.md) | Pending |
| 7 | [Run History & Progress](./phase-07-run-history-progress.md) | Pending |
| 8 | [Admin FE Cleanup](./phase-08-admin-fe-cleanup.md) | Pending |
| 9 | [Backend Adjustments (RBAC tightening)](./phase-09-backend-adjustments-rbac-tightening.md) | Pending |
| 10 | [Docker & Deployment](./phase-10-docker-deployment.md) | Pending |
| 11 | [Testing & QA](./phase-11-testing-qa.md) | Pending |

## Risk Summary

- **R1 — Type drift giữa apps**: nếu không nghiêm shared package, mỗi app sẽ duplicate types. *Mitigation:* eslint rule cấm import cross-app, chỉ qua `@auto-at/shared`.
- **R2 — Auth bypass**: user-app có thể gọi endpoint write nếu chỉ ẩn UI. *Mitigation:* backend phải enforce `require_admin()` server-side cho mọi write template/LLM/agent.
- **R3 — CORS rò rỉ**: thêm origin mới nhưng quên enforce. *Mitigation:* duy nhất `ALLOWED_ORIGINS` env var, validated ở startup.
- **R4 — Reload code nặng**: 2 next dev cùng chạy hot reload tốn RAM. *Mitigation:* document chạy độc lập; chỉ enable user-app khi cần.

## Estimated Effort

~3–5 ngày cho 1 dev: 1 ngày scaffold + shared, 2 ngày port UI + auth, 1 ngày docker/test/cleanup.

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Research & Architecture](./phase-01-research-architecture.md) | Pending |
| 2 | [Workspace & Shared Package Setup](./phase-02-workspace-shared-package-setup.md) | Pending |
| 3 | [Scaffold User FE App](./phase-03-scaffold-user-fe-app.md) | Pending |
| 4 | [Auth & Layout](./phase-04-auth-layout.md) | Pending |
| 5 | [Pipeline List & Detail (read-only)](./phase-05-pipeline-list-detail-read-only.md) | Pending |
| 6 | [Pipeline Run Flow](./phase-06-pipeline-run-flow.md) | Pending |
| 7 | [Run History & Progress](./phase-07-run-history-progress.md) | Pending |
| 8 | [Admin FE Cleanup](./phase-08-admin-fe-cleanup.md) | Pending |
| 9 | [Backend Adjustments (RBAC tightening)](./phase-09-backend-adjustments-rbac-tightening.md) | Pending |
| 10 | [Docker & Deployment](./phase-10-docker-deployment.md) | Pending |
| 11 | [Testing & QA](./phase-11-testing-qa.md) | Pending |

## Dependencies

<!-- Cross-plan dependencies -->
