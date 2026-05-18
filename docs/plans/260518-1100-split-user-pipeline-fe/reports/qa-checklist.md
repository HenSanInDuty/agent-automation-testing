# QA Checklist — Split User Pipeline FE

**Date:** 2026-05-18
**Plan:** [260518-1100-split-user-pipeline-fe](../plan.md)

## Build verification ✅

| App | Command | Result |
|-----|---------|--------|
| `@auto-at/admin-app` | `npm --workspace @auto-at/admin-app run build` | ✅ PASS — 14 routes |
| `@auto-at/user-app` | `npm --workspace @auto-at/user-app run build` | ✅ PASS — 7 routes |

Backend was not rebuilt (no breaking change beyond auth deps).

## User-app (port 3002) — manual smoke

> Run with `npm run dev:user` after `npm install` at repo root, then visit http://localhost:3002

- [ ] `/` redirects to `/pipelines`
- [ ] Unauthenticated → redirect to `/login`
- [ ] Login as **admin** / **qa** / **dev** all succeed (existing users from backend init)
- [ ] After login → `/pipelines` shows template grid
- [ ] **No** "New Pipeline" button
- [ ] **No** clone / archive / delete menu on cards
- [ ] Card has only **Run** and **History** buttons
- [ ] Click card body → `/pipelines/[id]` read-only detail
  - [ ] No React Flow builder rendered
  - [ ] Shows: name, version, description, node count, tags, stage/node table
  - [ ] Run + History CTA work
- [ ] Click **Run** → `/pipelines/[id]/run`
  - [ ] LLM profile selector, document upload, Run button present
  - [ ] Start run → WS progress streams realtime
  - [ ] Pause / Resume / Cancel buttons available (admin/qa only — dev returns 403)
- [ ] Terminal status → TerminalSummaryCard appears
- [ ] `/pipelines/[id]/runs` shows history list
- [ ] Click a run → `/pipelines/[id]/runs/[runId]` shows stage results
- [ ] Export HTML / DOCX buttons work (open new tab)
- [ ] Logout from TopNav → redirect `/login`

## Admin-app (port 3001) — regression smoke

- [ ] Login as admin → sidebar shows brand **"Auto-AT Admin / Pipeline Console"**
- [ ] Sidebar **Dev** group has **Open User Portal** link → http://localhost:3002
- [ ] `/pipelines` list + builder unchanged (clone/archive/delete still work)
- [ ] `/pipelines/new` create + DAG validator unchanged
- [ ] `/pipelines/[templateId]` opens React Flow builder
- [ ] `/pipelines/[templateId]/run` still works
- [ ] `/admin/llm` CRUD works (admin only)
- [ ] `/admin/agents` CRUD works (admin only)
- [ ] `/admin/users` CRUD works (admin only)
- [ ] `/chat` works (admin + dev only, qa is denied per `require_not_qa`)

## Backend RBAC — pytest (manual run if not in CI)

> Test cases (write `backend/tests/test_rbac_enforcement.py` if time permits)

- [ ] `dev` user → `POST /api/v1/pipeline-templates` → **403**
- [ ] `qa` user → `POST /api/v1/pipeline-templates` → **403** (admin-only after tightening)
- [ ] `admin` user → `POST /api/v1/pipeline-templates` → **201**
- [ ] `dev` user → `POST /api/v1/pipeline/runs` → **403** (`require_not_dev`)
- [ ] `qa` user → `POST /api/v1/pipeline/runs` → **201**
- [ ] `admin` user → `DELETE /api/v1/pipeline/runs/{id}` → **200**
- [ ] `qa` user → `DELETE /api/v1/pipeline/runs/{id}` → **403** (admin-only)
- [ ] `dev` user → `POST /api/v1/admin/llm-profiles` → **403**
- [ ] `qa` user → `POST /api/v1/admin/llm-profiles` → **403**
- [ ] `admin` user → `POST /api/v1/admin/llm-profiles` → **200**
- [ ] CORS preflight from `http://localhost:3002` → allowed

## Docker — smoke (optional)

- [ ] `docker compose build admin-app user-app` succeeds
- [ ] `docker compose up -d backend admin-app user-app`
- [ ] `curl -I http://localhost:3001` → 200
- [ ] `curl -I http://localhost:3002` → 200
- [ ] Login via user-app → WS connects to backend at 8000 (no CORS error in DevTools console)

## Known limitations / follow-ups

- **PipelineRunView (React Flow DAG visualization) stayed in admin-app** — user-app does not render the DAG graph because it would pull React Flow + builder nodes into the user bundle. `PipelineRunPage` accepts an optional `renderDagView` prop; admin passes it, user-app does not.
- Admin paths under `src/hooks`, `src/lib`, `src/components/ui`, `src/components/pipeline`, and `src/components/pipelines` still contain **thin re-export shims** to `@auto-at/shared`. Clean removal (and updating admin imports to use `@auto-at/shared` directly) is left for a follow-up cleanup pass to avoid churn.
- `PipelineRun` Mongo document was **not** extended with `triggered_by` field — defer until product wants "my runs" filtering.
- Backend RBAC pytest **not yet written** — the checklist above lists the cases.
