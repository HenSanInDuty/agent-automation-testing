# Auto-AT Admin App

> **Auto-AT** — Multi-Agent Automated Testing System
> Next.js 15 · React 19 · Tailwind CSS v4 · TypeScript · WebSocket + SSE · Zustand · @xyflow/react

---

## 🆕 V4 Changes (Phases 3–5: Adaptive API Testing Pipeline)

V4 extends the admin app with support for the adaptive multi-agent planner and review coverage gates:

| # | Feature | Summary |
|---|---------|---------|
| 1 | **Adaptive Planner Node Config UI** | Node properties panel for `adaptive_planner` node now exposes config fields: `min_planner_agents` (1-5), `max_planner_agents` (1-5), `coverage_threshold_percent` (0-100), `max_review_iterations` (0-5), `continue_on_review_exhaustion` (bool). Bounded input validation prevents invalid configurations. |
| 2 | **Admin-Only Node Config** | Adaptive planner config is editable **in admin app only**. User app (`auto-at/apps/user-app`) exposes read-only run progress and structured validator errors via shared components. |
| 3 | **PDF Export** | Shared export controls now include PDF download button alongside HTML/DOCX (Phase 4). Gate status and review-coverage advisory visible on run-detail page. |
| 4 | **Structured Validator Errors** | New `ValidatorFailureChecklist` shared component displays missing required fields with guidance when doc validation fails. Admin sees full error detail; fallback for legacy runs. |

**UI Components Added (Shared):**

- `PlanningReviewSummary.tsx` — Compact display of complexity decision, agent count, iteration/coverage, and exhaustion warning.
- `ValidatorFailureChecklist.tsx` — Checklist of missing required fields for MD spec validation failures.
- Gated PDF button in `ReportVerificationCard.tsx`.

---

## Overview

Auto-AT Frontend is the browser interface for the Auto-AT pipeline. It lets you design visual DAG-based pipeline templates, upload a requirements document, watch all AI crews work in real time via a live DAG visualization, inspect generated test cases, review execution logs, and download the final report. It also provides a live chat interface for direct LLM interaction, plus admin panels for managing LLM profiles and agent configurations.

Built with:

- **Next.js 15** (App Router, standalone output)
- **React 19**
- **Tailwind CSS v4** with a custom dark design-token theme
- **TypeScript** throughout
- **TanStack Query v5** for server-state management
- **Zustand v5** with `persist` middleware for global pipeline session state and builder state (V3)
- **React Hook Form + Zod** for form validation
- **@xyflow/react** for visual DAG pipeline builder and live run visualization (V3)
- **WebSocket** client for live pipeline progress (singleton manager with auto-reconnect)
- **SSE (Server-Sent Events)** via native `fetch` for streaming chat
- **Lucide React** icons

---

## 🆕 V3 Changes

V3 is a major release introducing a fully visual, DAG-based pipeline management system. Here is a summary of the most important changes:

### 1. Multi-Pipeline Management (`/pipelines`)

A new `/pipelines` page replaces the old single `/pipeline` runner. Users now manage a library of named pipeline **templates** — each with its own nodes, edges, versioning, and run history. Templates can be created, cloned, archived, exported, and imported as JSON.

### 2. Visual DAG Pipeline Builder (`/pipelines/[templateId]`)

A full-screen canvas powered by **`@xyflow/react`** (formerly React Flow) lets users construct pipelines by dragging agents from a sidebar onto the canvas and connecting them with edges. The builder includes undo/redo, DAG validation, and a node properties panel.

### 3. Live DAG Visualization During Runs (`/pipelines/[templateId]/run`)

The new `PipelineRunView` component renders the pipeline graph in real time during execution, coloring nodes by status (pending → running → completed → failed) as WebSocket events arrive.

### 4. Pipeline Template CRUD Operations

New API namespace `pipelineTemplatesApi` and a full suite of TanStack Query hooks (`usePipelineTemplates`, `usePipelineTemplate`, `useCreateTemplate`, `useUpdateTemplate`, `useCloneTemplate`, `useDeleteTemplate`, `useValidateTemplate`, `useExportTemplate`, `useImportTemplate`) back every template management action.

### 5. `/admin/stages` Page Deprecated

The stage-configuration admin page (`/admin/stages`) has been **deprecated**. It now shows a migration notice. Pipeline structure is configured inside the visual DAG builder instead.

### 6. `/pipeline` Route Deprecated

The old `/pipeline` route now **redirects to `/pipelines`**. All deep-linked bookmarks continue to work.

### 7. New Zustand `builderStore`

A second Zustand store (`store/builderStore.ts`) manages the pipeline builder's ephemeral state: React Flow nodes and edges, undo/redo history stacks, unsaved-changes flag, and DAG validation results.

### 8. `@xyflow/react` Replaces `@dnd-kit`

`@xyflow/react` is the primary interactive-canvas dependency. The `@dnd-kit/*` packages used for stage drag-and-drop in V2 have been removed (along with the stages feature they powered).

---

## V2 Features (History)

> The sections below document the features introduced in V2. All V2 features are still present in V3 unless explicitly marked deprecated.

### 1. Report Export (V2)

`ExportButtons` component on the results viewer. Users can download pipeline reports as **HTML** or **DOCX** via backend endpoints.

### 2. Per-Stage Results Display (V2)

`StageResultsPanel` progressively shows results as each pipeline stage completes. In V3 this is being evolved into per-node results via `PipelineRunView`.

### 3. Persistent Pipeline Session (V2)

- **Zustand store** (`store/pipelineStore.ts`) with `persist` middleware (sessionStorage) — pipeline state survives route changes.
- **Singleton WebSocket manager** (`lib/wsManager.ts`) — lives outside React, survives navigation.
- Sidebar shows a `PipelineStatusBadge` when a pipeline is active.

> ⚠️ `hooks/usePipelineWebSocket.ts` was **deprecated in V2** in favour of the Zustand store + singleton WS manager. It remains in the codebase for reference but is no longer used by any page.

### 4. Dynamic Agent Management UI (V2)

- "Add Agent" button → `AddAgentDialog` for creating custom agents.
- Delete button on custom agent cards.
- Hooks: `useCreateAgentConfig`, `useDeleteAgentConfig`.

### 5. Dynamic Stage Admin Page (V2 → Deprecated in V3)

`/admin/stages` provided drag-and-drop stage reorder via `@dnd-kit/sortable`. **Replaced by the visual DAG builder in V3.**

### 6. Pipeline Controls (V2)

`PipelineControls` component with **Pause**, **Resume**, and **Cancel** buttons. Hooks: `usePausePipeline`, `useResumePipeline`.

### 7. Updated Types (V2)

`StageConfig*` types, `AgentConfigCreate`, `PipelineStatus` extended with `'paused' | 'cancelled'`, `WSEventType` extended with `'run.paused' | 'run.resumed' | 'run.cancelled'`.

---

## Prerequisites

| Tool      | Minimum Version | Notes                  |
|-----------|----------------|------------------------|
| Node.js   | 20+            | 20 LTS recommended     |
| npm       | 10+            | Bundled with Node 20   |

---

## Quick Start

```bash
# 1. Enter the frontend directory
cd auto-at/frontend

# 2. Install dependencies
npm install

# 3. Copy and configure environment variables
cp .env.local.example .env.local
# Edit .env.local — set NEXT_PUBLIC_API_URL to your backend address

# 4. Start the development server
npm run dev
```

The app will be available at **http://localhost:3001**. The root path (`/`) redirects automatically to `/pipelines`.

> Make sure the backend is running on port **8000** before starting the frontend, or update `NEXT_PUBLIC_API_URL` accordingly.

---

## Environment Variables

Create a `.env.local` file in the `frontend/` directory.

| Variable               | Default (dev)           | Description                                       |
|------------------------|------------------------|---------------------------------------------------|
| `NEXT_PUBLIC_API_URL`  | `http://localhost:8000` | Base URL of the Auto-AT backend REST API          |
| `NEXT_PUBLIC_WS_URL`   | `ws://localhost:8000`   | Base URL for WebSocket connections                |

> Both variables are prefixed with `NEXT_PUBLIC_` and are inlined at build time. In production (Docker), these are injected via the `docker-compose.yml` `environment` block.

> API calls from the browser are proxied through the Next.js dev server: any request to `/api/v1/*` is rewritten to `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).

---

## Pages & Routes

| URL                               | Component                  | Layout                                              | Status                        |
|-----------------------------------|----------------------------|-----------------------------------------------------|-------------------------------|
| `/`                               | Redirect                   | Root → `/pipelines`                                 | **Updated** (V3)              |
| `/pipelines`                      | `PipelineListPage`         | Pipelines layout (Sidebar + Navbar + breadcrumbs)   | 🆕 **NEW** (V3)               |
| `/pipelines/new`                  | `PipelineBuilderPage`      | Builder layout (full-screen canvas)                 | 🆕 **NEW** (V3)               |
| `/pipelines/[templateId]`         | `PipelineBuilderPage`      | Builder layout (full-screen canvas)                 | 🆕 **NEW** (V3)               |
| `/pipelines/[templateId]/run`     | `PipelineRunPage`          | Run layout (Sidebar + Navbar + breadcrumbs)         | 🆕 **NEW** (V3)               |
| `/pipelines/[templateId]/runs`    | `PipelineRunHistoryPage`   | Run layout (Sidebar + Navbar + breadcrumbs)         | 🆕 **NEW** (V3)               |
| `/pipeline`                       | Redirect → `/pipelines`    | —                                                   | ⚠️ **DEPRECATED** (V2 → V3) |
| `/chat`                           | `ChatPage`                 | Chat layout (Sidebar + Navbar, no scroll wrapper)   | No change                     |
| `/admin/llm`                      | `LLMProfileList`           | Admin layout (Sidebar + Navbar + breadcrumbs)       | No change                     |
| `/admin/agents`                   | `AgentList`                | Admin layout                                        | **Updated** (V3) — Agent Catalog |
| `/admin/stages`                   | `DeprecatedNotice`         | Admin layout                                        | ⚠️ **DEPRECATED** (V3)       |

---

### `/pipelines` — Pipeline Templates List 🆕 (V3)

The new home page. Displays a grid of pipeline template cards. From here users can:

1. **Browse** all templates (including built-in defaults and user-created ones).
2. **Create** a new pipeline — opens `CreatePipelineDialog` to name and describe the template, then navigates to the builder.
3. **Clone** any existing template to use it as a starting point.
4. **Archive / Restore** templates to keep the list tidy.
5. **View run history** for a specific template via the card's "Runs" link.
6. **Navigate to the builder** to edit a template's DAG.

### `/pipelines/new` — Create New Pipeline 🆕 (V3)

Opens the visual DAG builder with an empty canvas. Equivalent to clicking "Create" from the list page.

### `/pipelines/[templateId]` — Pipeline Builder 🆕 (V3)

Full-screen visual pipeline editor powered by **`@xyflow/react`**:

1. **Agent Catalog Sidebar** — drag agents from the sidebar onto the canvas to create `AgentNode` instances.
2. **Canvas** — connect nodes with edges to define data-flow dependencies.
3. **Node Properties Panel** — click any node to configure its label, timeout, retry count, LLM profile override, and other settings.
4. **Validation Panel** — real-time DAG validation showing errors, warnings, estimated parallel layers, and speedup factor.
5. **Builder Toolbar** — Save, Validate, Run, Undo, Redo actions.
6. **Undo / Redo** — full history managed in `builderStore`.

### `/pipelines/[templateId]/run` — Pipeline Run 🆕 (V3)

The execution page for a specific template:

1. **Upload** — drag-and-drop or browse for a requirements document (PDF, DOCX, XLSX, TXT up to 50 MB).
2. **Configure** — optional LLM profile override for the run.
3. **Run / Pause / Resume / Cancel** — start, pause, resume, or cancel the pipeline run.
4. **Live DAG View** — `PipelineRunView` renders the template's graph with real-time node status colors driven by WebSocket events (`node.started`, `node.completed`, `node.failed`, `layer.started`, `layer.completed`).
5. **Per-Node Results** — results appear incrementally as each node completes.
6. **Results** — tabbed viewer: **Summary** / **Test Cases** / **Execution** / **Report** with **Export** buttons for HTML and DOCX download.

### `/pipelines/[templateId]/runs` — Run History 🆕 (V3)

Collapsible table of all past runs for this pipeline template, with status badges (including paused/cancelled), timestamps, duration, and delete-with-confirmation.

### `/pipeline` — ⚠️ Deprecated (V3)

The old single-pipeline runner route. Now performs a server-side redirect to `/pipelines`. All deep-linked bookmarks continue to work without any user action.

### `/chat` — LLM Chat Interface

A full streaming chat UI for direct LLM interaction:

- **LLM profile selector** — choose which configured profile to chat with.
- **Settings panel** — customise the system prompt before or during a conversation.
- **Welcome state** — suggestion chips to get started quickly.
- **Streaming messages** — assistant responses rendered token-by-token via SSE using native `fetch`.
- **Auto-growing textarea** — `Enter` to send, `Shift+Enter` for a newline.
- User and assistant message bubbles with distinct styling.

### `/admin/llm` — LLM Profiles

Admin panel for managing named LLM configurations:

- Grid of provider-accented cards showing all configured profiles.
- **Create / Edit** — modal form (React Hook Form + Zod) for any provider supported by LiteLLM (OpenAI, Anthropic, Azure OpenAI, Ollama, Groq, etc.).
- **Test connection** — sends a lightweight probe prompt and displays measured latency.
- **Set global default** — the profile used by all agents without an explicit override.
- **Delete** with inline confirmation.

### `/admin/agents` — Agent Catalog (Updated V3)

Admin panel for customising individual CrewAI agents. In V3 agents are no longer grouped by pipeline stage — they are a flat catalog of reusable building blocks for any pipeline template:

- **Search** to quickly find agents by name, role, or goal.
- Per-agent inline **enable / verbose** toggles.
- **Edit modal** — role, goal, backstory, and per-agent LLM profile override.
- **Reset** individual agent or **Reset All** to factory defaults.
- **Add Agent** button — opens `AddAgentDialog` to create a custom agent. (V2)
- **Delete** button on custom agent cards (built-in agents can only be disabled). (V2)
- Changes take effect on the next pipeline run — no restart required.

### `/admin/stages` — ⚠️ Deprecated (V3)

This page previously provided drag-and-drop stage configuration management. In V3 pipeline structure is defined entirely within the visual DAG builder. The page now renders a **migration notice** (`DeprecatedNotice` component) directing users to the pipeline builder.

---

## Project Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── globals.css              ← Design tokens + Tailwind v4 theme
│   │   ├── layout.tsx               ← Root layout (Inter + JetBrains Mono fonts, Providers)
│   │   ├── page.tsx                 ← Root redirect → /pipelines  (V3)
│   │   ├── providers.tsx            ← QueryClientProvider + Toaster + RQ DevTools
│   │   │
│   │   ├── pipelines/              🆕 (V3)
│   │   │   ├── layout.tsx           ← Pipelines shell (Sidebar + Navbar + breadcrumbs)
│   │   │   ├── page.tsx             ← Renders <PipelineListPage />
│   │   │   ├── new/
│   │   │   │   └── page.tsx         ← Renders <PipelineBuilderPage /> (blank canvas)
│   │   │   └── [templateId]/
│   │   │       ├── page.tsx         ← Renders <PipelineBuilderPage /> (edit existing)
│   │   │       ├── run/
│   │   │       │   └── page.tsx     ← Renders <PipelineRunPage />
│   │   │       └── runs/
│   │   │           └── page.tsx     ← Renders <PipelineRunHistoryPage />
│   │   │
│   │   ├── pipeline/               ⚠️ DEPRECATED (V3)
│   │   │   ├── layout.tsx           ← Redirect to /pipelines
│   │   │   └── page.tsx             ← Redirect to /pipelines
│   │   │
│   │   ├── admin/
│   │   │   ├── layout.tsx           ← Admin shell (Sidebar + Navbar + breadcrumbs)
│   │   │   │                           Updated (V3): removed "Stages" tab
│   │   │   ├── agents/page.tsx      ← Renders <AgentList /> (now "Agent Catalog")
│   │   │   ├── llm/page.tsx         ← Renders <LLMProfileList />
│   │   │   └── stages/page.tsx      ← ⚠️ DEPRECATED — renders <DeprecatedNotice />
│   │   │
│   │   └── chat/
│   │       ├── layout.tsx           ← Chat shell (Sidebar + Navbar, no scroll wrapper)
│   │       └── page.tsx             ← Renders <ChatPage />
│   │
│   ├── components/
│   │   ├── layout/
│   │   │   └── Sidebar.tsx          ← Collapsible (w-56 ↔ w-16) sidebar
│   │   │                               Updated (V3): "Pipelines" replaces "Pipeline";
│   │   │                               "Stages" nav item removed; nav groups:
│   │   │                               • Main — Chat, Pipelines
│   │   │                               • Admin — LLM Profiles, Agent Catalog
│   │   │                               • Dev — API Docs
│   │   │                               PipelineStatusBadge when a run is active
│   │   │
│   │   ├── pipelines/              🆕 (V3)
│   │   │   ├── PipelineListPage.tsx    ← Grid of pipeline template cards
│   │   │   ├── PipelineTemplateCard.tsx← Card for a single template (name, node/edge
│   │   │   │                              count, last run status, clone/archive actions)
│   │   │   └── CreatePipelineDialog.tsx← Modal to create a new template (name + desc)
│   │   │
│   │   ├── pipeline-builder/       🆕 (V3)
│   │   │   ├── PipelineBuilder.tsx     ← Main builder: React Flow canvas + sidebar +
│   │   │   │                              properties panel + toolbar
│   │   │   ├── AgentCatalogSidebar.tsx ← Draggable agent list; drag onto canvas to
│   │   │   │                              create AgentNode
│   │   │   ├── NodePropertiesPanel.tsx ← Right panel: selected node configuration
│   │   │   │                              (label, timeout, retry, LLM override, etc.)
│   │   │   ├── BuilderToolbar.tsx      ← Save, Run, Validate, Undo, Redo buttons
│   │   │   ├── ValidationPanel.tsx     ← DAG validation results: errors, warnings,
│   │   │   │                              execution layers, speedup estimate
│   │   │   └── nodes/
│   │   │       ├── AgentNode.tsx       ← Custom React Flow node for AI agents
│   │   │       ├── InputNode.tsx       ← Input source node (document ingestion)
│   │   │       └── OutputNode.tsx      ← Output sink node (report generation)
│   │   │
│   │   ├── pipeline/
│   │   │   ├── PipelinePage.tsx        ← UPDATED (V3): now hosts PipelineRunView
│   │   │   │                              (DAG) instead of stage-based progress
│   │   │   ├── PipelineRunPage.tsx     🆕 (V3) ← Run start page for a template
│   │   │   ├── PipelineRunHistoryPage.tsx 🆕 (V3) ← Run history for a template
│   │   │   ├── PipelineRunView.tsx     🆕 (V3) ← Live DAG visualization during run;
│   │   │   │                              colors nodes by WS event status
│   │   │   ├── PipelineControls.tsx    ← Pause / Resume / Cancel buttons (V2)
│   │   │   ├── PipelineProgress.tsx    ← UPDATED (V3): node-based progress instead
│   │   │   │                              of stage-based
│   │   │   ├── DocumentUpload.tsx      ← Drag-and-drop file upload zone
│   │   │   ├── LLMProfileSelector.tsx  ← Profile <select> for pipeline runs
│   │   │   ├── StageResultsPanel.tsx   ← Progressive per-stage results (V2)
│   │   │   ├── ResultsViewer.tsx       ← UPDATED (V3): per-node results tabs
│   │   │   ├── ExportButtons.tsx       ← HTML / DOCX report download buttons (V2)
│   │   │   └── RunHistory.tsx          ← UPDATED (V3): grouped by template
│   │   │
│   │   ├── admin/
│   │   │   ├── agents/
│   │   │   │   ├── AgentList.tsx        ← Updated (V3): "Agent Catalog" mode,
│   │   │   │   │                           no stage grouping
│   │   │   │   ├── AgentGroupSection.tsx← Updated (V3): groups by category, not stage
│   │   │   │   ├── AgentCard.tsx        ← Single agent row (inline toggles + edit/reset)
│   │   │   │   │                           Updated (V2): +Delete for custom agents
│   │   │   │   ├── AgentDialog.tsx      ← Edit modal (react-hook-form + zod)
│   │   │   │   └── AddAgentDialog.tsx   ← Create new agent modal (V2)
│   │   │   ├── stages/                 ⚠️ DEPRECATED (V3)
│   │   │   │   └── DeprecatedNotice.tsx ← Migration notice component
│   │   │   └── llm/
│   │   │       ├── LLMProfileList.tsx   ← Grid of profile cards with full CRUD
│   │   │       ├── LLMProfileCard.tsx   ← Provider-accented card
│   │   │       └── LLMProfileDialog.tsx ← Create/edit modal with test-connection
│   │   │
│   │   ├── chat/
│   │   │   └── ChatPage.tsx            ← Full streaming chat UI: ProfileSelector,
│   │   │                                  SettingsPanel, WelcomeState, MessageBubble,
│   │   │                                  ChatInput; SSE stream token-by-token
│   │   │
│   │   └── ui/
│   │       ├── Button.tsx              ← Variants: primary / secondary / danger /
│   │       │                              ghost / outline / success; sizes xs–lg;
│   │       │                              loading state
│   │       ├── Input.tsx               ← Input, Textarea, FormField,
│   │       │                              TextareaField, Label
│   │       ├── Select.tsx              ← Select, SelectField, Badge, Toggle
│   │       ├── Modal.tsx               ← Modal, ModalHeader, ModalBody,
│   │       │                              ModalFooter, ConfirmDialog
│   │       ├── Skeleton.tsx            ← Skeleton, SkeletonText, SkeletonCard,
│   │       │                              SkeletonTable
│   │       ├── Toast.tsx               ← Module-level event bus; toast.success /
│   │       │                              error / warning / info; max 5 toasts,
│   │       │                              auto-dismiss with countdown progress bar;
│   │       │                              Toaster component
│   │       └── ErrorBoundary.tsx       ← Class ErrorBoundary + withErrorBoundary HOC
│   │
│   ├── store/
│   │   ├── pipelineStore.ts            ← Zustand v5 store with `persist` middleware
│   │   │                                  (sessionStorage). Updated (V3):
│   │   │                                  nodeStatuses replaces agentStatuses;
│   │   │                                  currentNode replaces currentStage;
│   │   │                                  executionLayers added.
│   │   └── builderStore.ts             🆕 (V3) ← Pipeline builder state: React Flow
│   │                                      nodes & edges, undo/redo history stacks,
│   │                                      unsaved-changes flag, DAG validation result.
│   │
│   ├── hooks/
│   │   ├── usePipelineTemplates.ts     🆕 (V3) ← TanStack Query hooks for template
│   │   │                                  CRUD: usePipelineTemplates, usePipelineTemplate,
│   │   │                                  useCreateTemplate, useUpdateTemplate,
│   │   │                                  useCloneTemplate, useDeleteTemplate,
│   │   │                                  useValidateTemplate, useExportTemplate,
│   │   │                                  useImportTemplate
│   │   ├── useAgentConfigs.ts          ← useAgentConfigsGrouped, useAgentConfig,
│   │   │                                  useUpdateAgentConfig, useResetAgentConfig,
│   │   │                                  useResetAllAgentConfigs,
│   │   │                                  useCreateAgentConfig (V2),
│   │   │                                  useDeleteAgentConfig (V2).
│   │   │                                  Updated (V3): stage filter now optional
│   │   ├── useLLMProfiles.ts           ← useLLMProfiles, useLLMProfile,
│   │   │                                  useCreateLLMProfile, useUpdateLLMProfile,
│   │   │                                  useDeleteLLMProfile, useSetDefaultLLMProfile,
│   │   │                                  useTestLLMProfile
│   │   ├── usePipeline.ts              ← usePipelineRuns, usePipelineRun,
│   │   │                                  useStartPipeline, useCancelPipeline,
│   │   │                                  useDeletePipelineRun,
│   │   │                                  usePausePipeline (V2),
│   │   │                                  useResumePipeline (V2).
│   │   │                                  Updated (V3): template_id in run creation
│   │   ├── useStageConfigs.ts          ← ⚠️ DEPRECATED (V3). Previously: useStageConfigs,
│   │   │                                  useCreateStage, useUpdateStage,
│   │   │                                  useDeleteStage, useReorderStages
│   │   └── usePipelineWebSocket.ts     ← ⚠️ DEPRECATED (V2). Replaced by Zustand
│   │                                      store + singleton WS manager. Retained for
│   │                                      reference only.
│   │
│   ├── lib/
│   │   ├── api.ts                      ← Axios client (30s timeout, error interceptor)
│   │   │                                  + API namespaces:
│   │   │                                  • llmProfilesApi
│   │   │                                  • agentConfigsApi
│   │   │                                  • pipelineApi — +pause, +resume,
│   │   │                                      +exportHTML, +exportDOCX (V2)
│   │   │                                  • pipelineTemplatesApi 🆕 (V3) — template
│   │   │                                      CRUD, clone, archive, validate,
│   │   │                                      export/import
│   │   │                                  • healthApi
│   │   │                                  • chatApi (SSE via native fetch)
│   │   │                                  • stageConfigsApi — ⚠️ DEPRECATED (V3)
│   │   ├── wsManager.ts                ← Singleton WebSocket manager (V2).
│   │   │                                  Updated (V3): handles node.* and layer.*
│   │   │                                  events in addition to run.* events
│   │   ├── queryClient.ts              ← QueryClient: 60s staleTime, 5min gcTime,
│   │   │                                  2 retries with exp backoff (10s cap),
│   │   │                                  refetch-on-window-focus only in prod;
│   │   │                                  queryKeys factory
│   │   └── utils.ts                    ← cn(), formatDateTime, formatRelativeTime,
│   │                                      truncate, snakeToTitle, sleep, getInitials
│   │
│   └── types/
│       └── index.ts                    ← All shared TS types. V3 additions:
│                                          PipelineNodeConfig, PipelineEdgeConfig,
│                                          PipelineTemplate, PipelineTemplateListItem,
│                                          PipelineTemplateCreate, PipelineTemplateUpdate,
│                                          DAGValidationResult;
│                                          PipelineRun updated: template_id,
│                                          currentNode, completedNodes, failedNodes,
│                                          nodeStatuses, executionLayers;
│                                          WSEventType extended with layer.* and
│                                          node.* events;
│                                          AgentConfig.stage now optional;
│                                          StageConfig* types deprecated.
│
├── public/
├── package.json                        ← +@xyflow/react; removed @dnd-kit/*
├── next.config.ts                      ← standalone output, /api/v1/* rewrite proxy
├── tsconfig.json
├── Dockerfile                          ← 3-stage: deps → builder → runner
└── README.md                           ← This file
```

---

## Key Dependencies

| Package                        | Version   | Purpose                                              |
|--------------------------------|-----------|------------------------------------------------------|
| `next`                         | ^15.3.3   | Framework (App Router, standalone output)            |
| `react` / `react-dom`          | ^19.0.0   | UI library                                           |
| `typescript`                   | ^5.x      | Static typing                                        |
| `@tanstack/react-query`        | ^5.80.0   | Async server-state management                        |
| `zustand`                      | ^5.0.0    | Global state with persist middleware                 |
| `@xyflow/react`                | latest    | 🆕 (V3) Visual DAG builder + live run visualization |
| `react-hook-form`              | latest    | Form state management                                |
| `@hookform/resolvers`          | latest    | Zod resolver bridge                                  |
| `zod`                          | latest    | Schema validation                                    |
| `axios`                        | ^1.9.0    | HTTP client (REST calls)                             |
| `lucide-react`                 | ^0.513.0  | Icon set                                             |
| `tailwindcss`                  | v4        | Utility-first CSS                                    |
| `tailwind-merge`               | latest    | Merge Tailwind class strings safely                  |
| `clsx`                         | latest    | Conditional class name composition                   |

> **Removed in V3:** `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities` — these powered the V2 stage drag-and-drop feature which has been superseded by the DAG builder.

---

## Development Commands

```bash
# Start dev server with hot-reload (Turbopack) on port 3001
npm run dev

# Type-check without emitting
npm run type-check        # or: npx tsc --noEmit

# Lint with ESLint
npm run lint

# Production build
npm run build

# Start the production server locally (after build)
npm start
```

---

## Design System

All colours, radii, shadows, and transitions are defined as CSS custom properties in `src/app/globals.css` and mapped into Tailwind v4 via `@theme inline {}`. Every token is usable as a Tailwind utility (e.g. `bg-surface`, `text-text-secondary`, `border-border-focus`).

The palette is a dark navy theme:

| Token                  | Value       | Usage                                          |
|------------------------|-------------|------------------------------------------------|
| `--bg`                 | `#101622`   | Page background                                |
| `--surface`            | `#18202F`   | Cards, panels                                  |
| `--surface-elevated`   | `#1e2a3d`   | Table headers, elevated surfaces               |
| `--border`             | `#2b3b55`   | Default borders                                |
| `--border-focus`       | `#135bec`   | Focused input rings                            |
| `--text-primary`       | `#ffffff`   | Primary text                                   |
| `--text-secondary`     | `#92a4c9`   | Supporting / label text                        |
| `--text-muted`         | `#3d5070`   | Muted / placeholder text                       |
| `--primary`            | `#135bec`   | Buttons, active states, focus rings            |
| `--primary-hover`      | `#1a6aff`   | Button hover state                             |
| `--success`            | `#22c55e`   | Pass states, success toasts, completed nodes   |
| `--warning`            | `#f59e0b`   | In-progress, caution states, paused badge      |
| `--danger`             | `#ef4444`   | Errors, destructive actions, failed nodes      |
| `--info`               | `#06b6d4`   | Informational highlights, running nodes        |

**Radii:** `--radius-sm` (6px) through `--radius-2xl` (20px)  
**Shadows:** 5 elevation levels  
**Transitions:** `--transition-fast`, `--transition-base`, `--transition-slow`

The `skeleton` CSS class (defined in `globals.css`) provides a shimmer animation used by all `Skeleton*` components.

---

## Architecture Notes

### API Client (`lib/api.ts`)

A single Axios instance (30s timeout, centralised error interceptor) exposes namespaced API objects:

- `llmProfilesApi` — CRUD + test-connection for LLM profiles
- `agentConfigsApi` — read, update, reset, create, delete for agent configurations
- `pipelineApi` — start, cancel, delete, list/get runs, pause, resume, exportHTML, exportDOCX
- `pipelineTemplatesApi` 🆕 (V3) — full template CRUD, clone, archive, validate (DAG), export as JSON, import from JSON
- `healthApi` — backend health probe
- `chatApi` — chat history and `sendStream`, which uses the native **`fetch` API** (not Axios) to consume SSE token streams
- `stageConfigsApi` — ⚠️ Deprecated (V3)

### Zustand Pipeline Store (`store/pipelineStore.ts`)

A global Zustand store with `persist` middleware (sessionStorage) that holds pipeline execution state:

- **V3 State:** `runId`, `templateId`, `status`, `nodeStatuses`, `currentNode`, `completedNodes`, `failedNodes`, `executionLayers`, `logMessages`, per-node results
- **Persistence:** sessionStorage — state survives route changes within the same tab
- **WebSocket integration:** The singleton WS manager dispatches events directly to the store
- **Selectors:** Components subscribe to specific slices (e.g. `useStore(s => s.status)`) to avoid unnecessary re-renders
- **Actions:** `startRun`, `reset`, `updateFromWSEvent`, etc.

### Zustand Builder Store (`store/builderStore.ts`) 🆕 (V3)

Manages the ephemeral state of the visual pipeline builder:

- **State:** React Flow `nodes` and `edges` arrays, `undoStack`, `redoStack`, `isDirty` (unsaved-changes flag), `validationResult` (`DAGValidationResult | null`)
- **Undo / Redo:** every node/edge mutation pushes onto `undoStack`; undo/redo swaps between stacks
- **Validation:** `validationResult` is populated after a call to `useValidateTemplate` and cleared on any canvas edit
- **Not persisted** — builder state is intentionally ephemeral and is reset on page navigation

### WebSocket Manager (`lib/wsManager.ts`)

A singleton WebSocket manager that lives **outside** the React component tree (introduced in V2, extended in V3):

- **Survives route changes** — pipeline progress continues when navigating to `/admin` or `/chat`
- **Auto-reconnect** up to 3 times with exponential backoff (1 s → 2 s → 4 s)
- Dispatches events directly to the Zustand pipeline store
- V2 terminal events: `run.completed`, `run.failed`, `run.paused`, `run.resumed`, `run.cancelled`
- 🆕 V3 events: `layer.started`, `layer.completed`, `node.started`, `node.completed`, `node.failed`, `node.skipped`, `node.progress`
- **Replaces** the old `usePipelineWebSocket` React hook pattern (deprecated V2)

### WebSocket Hook (`hooks/usePipelineWebSocket.ts`) — ⚠️ Deprecated (V2)

> **Deprecated in V2.** Replaced by the Zustand store + singleton WS manager (`lib/wsManager.ts`). Retained in the codebase for reference only.

Previously connected to the pipeline run's WebSocket endpoint and drove all live-progress UI:

- Auto-reconnect up to 3 times with exponential backoff (1 s → 2 s → 4 s)
- Tracked `agentStatuses`, `agentProgress`, `currentStage`, and `logMessages`
- Log message buffer capped at 100 entries; event feed capped at 500
- Closed the socket cleanly on `run.completed` and `run.failed` events

### Query Client (`lib/queryClient.ts`)

TanStack Query is configured with:

- **60 s staleTime** — data is considered fresh for 1 minute
- **5 min gcTime** — inactive queries are garbage-collected after 5 minutes
- **2 retries** with exponential backoff (max 10 s between retries)
- `refetchOnWindowFocus` enabled in production only
- A centralised `queryKeys` factory for consistent cache key management

### Toast System (`components/ui/Toast.tsx`)

Implemented as a **module-level event bus** (not React context). Call `toast.success()`, `toast.error()`, `toast.warning()`, or `toast.info()` from anywhere — hooks, utility functions, API interceptors — without needing access to a React tree. Maximum 5 simultaneous toasts; each auto-dismisses with an animated countdown progress bar.

---

## Hooks Reference

### Pipeline Template Hooks 🆕 (V3)

| Hook                    | File                      | Purpose                                         |
|-------------------------|---------------------------|-------------------------------------------------|
| `usePipelineTemplates`  | `usePipelineTemplates.ts` | Fetch list of all pipeline templates            |
| `usePipelineTemplate`   | `usePipelineTemplates.ts` | Fetch a single template by ID                   |
| `useCreateTemplate`     | `usePipelineTemplates.ts` | Create a new pipeline template                  |
| `useUpdateTemplate`     | `usePipelineTemplates.ts` | Update template (save from builder)             |
| `useCloneTemplate`      | `usePipelineTemplates.ts` | Clone an existing template                      |
| `useDeleteTemplate`     | `usePipelineTemplates.ts` | Delete a pipeline template                      |
| `useValidateTemplate`   | `usePipelineTemplates.ts` | Validate DAG (returns `DAGValidationResult`)    |
| `useExportTemplate`     | `usePipelineTemplates.ts` | Export template as JSON                         |
| `useImportTemplate`     | `usePipelineTemplates.ts` | Import template from JSON                       |

### Builder Store Hook 🆕 (V3)

| Hook              | File                | Purpose                                                   |
|-------------------|---------------------|-----------------------------------------------------------|
| `useBuilderStore` | `store/builderStore.ts` | Access pipeline builder state (nodes, edges, undo/redo, validation) |

### Pipeline Run Hooks

| Hook                    | File               | Purpose                                    |
|-------------------------|--------------------|--------------------------------------------|
| `usePipelineRuns`       | `usePipeline.ts`   | Fetch pipeline run history                 |
| `usePipelineRun`        | `usePipeline.ts`   | Fetch single pipeline run                  |
| `useStartPipeline`      | `usePipeline.ts`   | Start pipeline run (requires template_id)  |
| `useCancelPipeline`     | `usePipeline.ts`   | Cancel pipeline run                        |
| `useDeletePipelineRun`  | `usePipeline.ts`   | Delete pipeline run                        |
| `usePausePipeline`      | `usePipeline.ts`   | Pause running pipeline (V2)               |
| `useResumePipeline`     | `usePipeline.ts`   | Resume paused pipeline (V2)               |

### LLM Profile Hooks

| Hook                      | File                | Purpose                          |
|---------------------------|---------------------|----------------------------------|
| `useLLMProfiles`          | `useLLMProfiles.ts` | Fetch all LLM profiles           |
| `useLLMProfile`           | `useLLMProfiles.ts` | Fetch single LLM profile         |
| `useCreateLLMProfile`     | `useLLMProfiles.ts` | Create LLM profile               |
| `useUpdateLLMProfile`     | `useLLMProfiles.ts` | Update LLM profile               |
| `useDeleteLLMProfile`     | `useLLMProfiles.ts` | Delete LLM profile               |
| `useSetDefaultLLMProfile` | `useLLMProfiles.ts` | Set global default LLM profile   |
| `useTestLLMProfile`       | `useLLMProfiles.ts` | Test LLM connection + latency    |

### Agent Config Hooks

| Hook                      | File                  | Purpose                                          |
|---------------------------|-----------------------|--------------------------------------------------|
| `useAgentConfigsGrouped`  | `useAgentConfigs.ts`  | Fetch agents grouped (by category in V3)         |
| `useAgentConfig`          | `useAgentConfigs.ts`  | Fetch single agent config                        |
| `useUpdateAgentConfig`    | `useAgentConfigs.ts`  | Update agent config                              |
| `useResetAgentConfig`     | `useAgentConfigs.ts`  | Reset agent to defaults                          |
| `useResetAllAgentConfigs` | `useAgentConfigs.ts`  | Reset all agents to defaults                     |
| `useCreateAgentConfig`    | `useAgentConfigs.ts`  | Create custom agent (V2)                        |
| `useDeleteAgentConfig`    | `useAgentConfigs.ts`  | Delete custom agent (V2)                        |

### Deprecated Hooks

| Hook                      | File                        | Status                                             |
|---------------------------|-----------------------------|----------------------------------------------------|
| `useStageConfigs`         | `useStageConfigs.ts`        | ⚠️ Deprecated (V3) — replaced by template builder  |
| `useCreateStage`          | `useStageConfigs.ts`        | ⚠️ Deprecated (V3)                                 |
| `useUpdateStage`          | `useStageConfigs.ts`        | ⚠️ Deprecated (V3)                                 |
| `useDeleteStage`          | `useStageConfigs.ts`        | ⚠️ Deprecated (V3)                                 |
| `useReorderStages`        | `useStageConfigs.ts`        | ⚠️ Deprecated (V3)                                 |
| `usePipelineWebSocket`    | `usePipelineWebSocket.ts`   | ⚠️ Deprecated (V2) — replaced by wsManager + store |

---

## TypeScript Types Reference (V3)

Key additions and changes in `src/types/index.ts` for V3:

```typescript
// Pipeline Template types

interface PipelineNodeConfig {
  node_id: string;
  node_type: 'input' | 'output' | 'agent' | 'pure_python';
  agent_id?: string;
  label: string;
  description: string;
  position_x: number;
  position_y: number;
  timeout_seconds: number;
  retry_count: number;
  enabled: boolean;
  config_overrides: Record<string, unknown>;
}

interface PipelineEdgeConfig {
  edge_id: string;
  source_node_id: string;
  target_node_id: string;
  source_handle?: string;
  target_handle?: string;
  label?: string;
  animated: boolean;
}

interface PipelineTemplate {
  id: string;
  template_id: string;
  name: string;
  description: string;
  version: number;
  nodes: PipelineNodeConfig[];
  edges: PipelineEdgeConfig[];
  is_builtin: boolean;
  is_archived: boolean;
  tags: string[];
  node_count: number;
  edge_count: number;
  created_at: string;
  updated_at: string;
}

interface DAGValidationResult {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
  execution_layers: string[][];
  total_layers: number;
  total_nodes: number;
  estimated_parallel_speedup?: number;
}

// Updated PipelineRun (V3)
interface PipelineRun {
  id: string;
  run_id: string;
  template_id: string;           // NEW in V3
  document_name: string;
  status: PipelineStatus;
  current_node?: string;          // was current_stage
  completed_nodes: string[];      // was completed_stages
  failed_nodes: string[];         // NEW in V3
  node_statuses: Record<string, string>; // NEW in V3
  execution_layers: string[][];   // NEW in V3
  duration_seconds?: number;
  error_message?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  paused_at?: string;
  resumed_at?: string;
}

// Extended WSEventType (V3)
type WSEventType =
  | 'run.started' | 'run.completed' | 'run.failed'
  | 'run.paused' | 'run.resumed' | 'run.cancelled'
  | 'layer.started' | 'layer.completed'      // NEW in V3
  | 'node.started' | 'node.completed'         // NEW in V3
  | 'node.failed' | 'node.skipped'            // NEW in V3
  | 'node.progress'                            // NEW in V3
  | 'log';

// DEPRECATED in V3:
// StageConfig, StageConfigCreate, StageConfigUpdate, StageReorderRequest
```

---

## Docker

```bash
# Build and start the full stack (backend + frontend)
docker compose up --build

# Frontend only (requires backend already running)
docker compose up frontend

# View frontend logs
docker compose logs -f frontend
```

The production image uses a **3-stage build**:

1. `deps` — installs `node_modules` via `npm ci`
2. `builder` — runs `npm run build` to produce the Next.js standalone output
3. `runner` — minimal `node:20-alpine` image that runs `node server.js`

The standalone output (`output: "standalone"` in `next.config.ts`) bundles everything needed to run the app without a full `node_modules` directory, keeping the final image lean.

See [`docker-compose.yml`](../docker-compose.yml) at the project root for the full configuration.

---

## License

MIT © Auto-AT Project