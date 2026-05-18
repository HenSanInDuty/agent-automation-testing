# Frontend Route & Component Audit
## Split FE into admin-app (3001) + user-app (3002)

**Date:** 2026-05-18 | **Scope:** d:/CV/auto-at/frontend/src

---

## 1. Routes (src/app/**/page.tsx)

| Route | Type | Classification | Purpose |
|-------|------|-----------------|---------|
| `/` (home) | page.tsx | both | Redirects to /login or dashboard |
| `/login` | page.tsx | both | Auth entry; shared |
| `/pipelines` | page.tsx | user | Read-only list of templates |
| `/pipelines/new` | page.tsx | admin-only | Create new pipeline template (builder) |
| `/pipelines/[templateId]` | page.tsx | both | Detail view + builder entry point |
| `/pipelines/[templateId]/run` | page.tsx | user | Run pipeline with file upload + WS monitor |
| `/pipelines/[templateId]/runs` | page.tsx | user | History of runs for a template |
| `/pipelines/[templateId]/runs/[runId]` | page.tsx | user | Run detail + results viewer |
| `/chat` | page.tsx | user | Chat interface (if user has access) |
| `/admin/llm` | page.tsx | admin-only | LLM profile management |
| `/admin/agents` | page.tsx | admin-only | Agent config UI |
| `/admin/users` | page.tsx | admin-only | User management (CRUD) |

**Note:** Bearer token + role checks (admin/qa/dev) enforced at backend; FE relies on AuthContext.isAdmin flag.

---

## 2. Components (src/components/*)

| Folder/Component | Type | Classification | Purpose |
|---|---|---|---|
| **ui/** (Button, Modal, Input, etc.) | lib | shared | Generic UI primitives |
| **auth/** AuthGuard.tsx | lib | shared | Role-based component wrapper |
| **layout/** Sidebar.tsx | layout | shared | Navigation; route-aware |
| **chat/** ChatPage.tsx | page | user | SSE streaming chat interface |
| **pipeline-builder/** | feature | admin-only | React Flow DAG editor (nodes, toolbar, validation) |
| **pipeline/** PipelinePage.tsx | page | user | Run page wrapper |
| **pipeline/** PipelineRunPage.tsx | page | user | Execute + monitor + results |
| **pipeline/** PipelineRunView.tsx | comp | user | WS listener + render stages/nodes |
| **pipeline/** PipelineRunHistoryPage.tsx | page | user | Paginated runs table for template |
| **pipeline/** PipelineRunDetailPage.tsx | page | user | Single run + artifact export |
| **pipeline/** PipelineControls.tsx | comp | user | Cancel/Pause/Resume buttons |
| **pipeline/** PipelineProgress.tsx | comp | user | Node/layer progress UI |
| **pipeline/** StageResultsPanel.tsx | comp | user | Stage results + summary display |
| **pipeline/** ResultsViewer.tsx | comp | user | Node output + artifact downloads |
| **pipeline/** DocumentUpload.tsx | comp | user | File picker for pipeline run |
| **pipeline/** LLMProfileSelector.tsx | comp | user | Dropdown to override LLM |
| **pipeline/** RunHistory.tsx | comp | user | Tabular run history |
| **pipelines/** PipelineListPage.tsx | page | user | Template list + search + filter |
| **pipelines/** PipelineTemplateCard.tsx | comp | user | Card for template in list |
| **pipelines/** CreatePipelineDialog.tsx | comp | admin-only | New template dialog (builder entry) |
| **admin/llm/** LLMProfileList.tsx | page | admin-only | Admin LLM profile management |
| **admin/llm/** LLMProfileCard.tsx | comp | admin-only | Single profile card |
| **admin/llm/** LLMProfileDialog.tsx | comp | admin-only | Create/edit dialog |
| **admin/agents/** AgentList.tsx | page | admin-only | Agent config UI |
| **admin/agents/** AgentCard.tsx | comp | admin-only | Single agent card |
| **admin/agents/** AgentDialog.tsx | comp | admin-only | Agent config editor |
| **admin/agents/** PipelineGroupSection.tsx | comp | admin-only | Agents grouped by pipeline |
| **admin/agents/** AgentGroupSection.tsx | comp | admin-only | Agents grouped by stage |
| **admin/agents/** AddAgentDialog.tsx | comp | admin-only | New agent form |
| **admin/agents/** AddStageForm.tsx | comp | admin-only | New stage config |
| **admin/users/** UserManagementPage.tsx | page | admin-only | User CRUD |

**Shared UI:** Button, Input, Select, Modal, Toast, Skeleton, ErrorBoundary, ErrorState.

---

## 3. Hooks (src/hooks/*)

| Hook | Purpose | Classification |
|------|---------|-----------------|
| `usePipeline.ts` | Query/mutation wrappers for pipelineApi (list/get/start runs) | shared |
| `usePipelineTemplates.ts` | Query templates; mutations for create/update/delete/archive/export | admin-only (mutations) + shared (queries) |
| `usePipelineWebSocket.ts` | WS connect/disconnect wrapper (calls wsManager) | user (run monitoring) |
| `useAgentConfigs.ts` | Query/mutation agent configs (grouped, list, by-pipeline) | admin-only |
| `useLLMProfiles.ts` | Query/mutation LLM profiles (list, create, test, set-default) | admin-only |
| `useStageConfigs.ts` | Query/mutation stage configs (list, create, reorder) | admin-only |
| `useTools.ts` | Query tool definitions + agent-tool assignments | admin-only |

---

## 4. Global Stores (src/store/*)

| Store | Purpose | Scope | Concerns |
|-------|---------|-------|----------|
| `pipelineStore.ts` | Zustand store for active run session state (WS events, node status, logs, results) | user | **Singleton WS socket** (wsManager) — must be managed carefully across app instances. Persists to sessionStorage (activeRunId, nodeStatuses, etc.) |
| `builderStore.ts` | Zustand store for pipeline builder state (React Flow nodes/edges, validation, undo/redo) | admin-only | Self-contained DAG editor; no external sockets |

**Warning:** Single wsManager instance lives outside React. Both apps connect to same /ws/pipeline/{runId} endpoint. If both admin-app and user-app run simultaneously, socket conflicts possible — mitigate via app-level connection guards.

---

## 5. Lib Files (src/lib/*)

| File | Purpose | Classification |
|------|---------|-----------------|
| `api.ts` | Axios client + all API endpoints (llm, agents, pipeline, chat, auth, tools, stage configs, templates) | shared |
| `auth-context.tsx` | React Context for user (username, role, token) + login/logout + perms flags (canCreatePipeline, canUseChat, isAdmin) | shared |
| `queryClient.ts` | React Query client setup + queryKeys factory | shared |
| `utils.ts` | Helper utilities (cn, formatDate, etc.) | shared |
| `wsManager.ts` | Module-level WebSocket singleton for /ws/pipeline/{runId} with auto-reconnect + event callbacks | user |

---

## 6. API Endpoints (Unique Paths from api.ts)

**Admin-only (40 endpoints):**
- /api/v1/admin/llm-profiles/* (CRUD, set-default, test)
- /api/v1/admin/agent-configs/* (CRUD, reset, by-pipeline)
- /api/v1/admin/stage-configs/* (CRUD, reorder)
- /api/v1/admin/tools/* (GET, agent mappings)
- /api/v1/auth/users/* (CRUD — admin only)

**Shared (20+ endpoints):**
- /api/v1/auth/login, /api/v1/auth/me
- /api/v1/pipeline-templates/* (list read-only for user; CRUD for admin)
- /api/v1/pipeline/runs/* (list, get, cancel, pause, resume, results, export)
- /api/v1/chat/* (profiles, send via SSE)
- /health

**WebSocket:**
- /ws/pipeline/{runId} — user monitoring only

---

## 7. Storage & Singletons

| Item | Scope | Location | Risk |
|------|-------|----------|------|
| wsManager | Module-level | src/lib/wsManager.ts | Shared WS — both apps cannot simultaneously run same runId |
| pipelineStore (Zustand) | Per-browser-tab | sessionStorage | Safe; tab-isolated persistence |
| builderStore (Zustand) | Per-browser-tab | Memory | Safe; ephemeral |
| AuthContext (React) | Per-app | localStorage (auto_at_token, auto_at_user) | Safe; shared storage key means token shared across apps in same browser |
| queryClient (React Query) | Per-app | Memory | Safe; independent per app instance |

---

## 8. Routes by Classification

**Admin-Only (5):**
/pipelines/new, /admin/llm, /admin/agents, /admin/users, + builder entry from detail

**User (7):**
/pipelines, /pipelines/[id]/run, /pipelines/[id]/runs, /pipelines/[id]/runs/[runId], /chat

**Both (2):**
/, /login, /pipelines/[id] (detail view + builder entry)

---

## 9. Migration Tasks

**Phase 1: Extract Shared**
- [ ] Create packages/shared/src
- [ ] Move auth-context.tsx, api.ts, wsManager.ts, utils.ts, queryClient.ts
- [ ] Update all imports in remaining code

**Phase 2: User-App**
- [ ] Scaffold Next 15 on port 3002
- [ ] Copy /pipeline/*, /pipelines/*, /chat/* components
- [ ] Copy pipelineStore, usePipeline, usePipelineWebSocket hooks
- [ ] Update env vars (NEXT_PUBLIC_API_URL, NEXT_PUBLIC_WS_URL)
- [ ] Sidebar: hide admin routes

**Phase 3: Admin-App**
- [ ] Rename frontend → apps/admin-app
- [ ] Remove shared lib files (import from @auto-at/shared)
- [ ] Keep builder, /admin/*, template editor
- [ ] Sidebar: hide user-only routes (/chat)

**Phase 4: Backend**
- [ ] CORS: Add port 3002
- [ ] RBAC: Enforce admin-only on /admin/*, /api/v1/auth/users
- [ ] Test cross-origin token refresh

---

## Summary

| Metric | Value |
|--------|-------|
| Routes | 12 |
| Components | 49 |
| Hooks | 7 |
| Stores | 2 |
| Lib Files | 5 |
| API Endpoints | 60+ |
| Admin Routes | 5 |
| User Routes | 7 |
| Shared Routes | 2 |
