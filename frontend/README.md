# Auto-AT Frontend

> **Auto-AT** — Multi-Agent Automated Testing System
> Next.js 15 · React 19 · Tailwind CSS v4 · TypeScript · WebSocket + SSE · Zustand

---

## Overview

Auto-AT Frontend is the browser interface for the Auto-AT pipeline. It lets you upload a requirements document, watch all AI crews work in real time, inspect generated test cases, review execution logs, and download the final report. It also provides a live chat interface for direct LLM interaction, plus admin panels for managing LLM profiles, agent configurations, and pipeline stage configurations.

Built with:

- **Next.js 15** (App Router, standalone output)
- **React 19**
- **Tailwind CSS v4** with a custom dark design-token theme
- **TypeScript** throughout
- **TanStack Query v5** for server-state management
- **Zustand v5** with `persist` middleware for global pipeline session state (V2)
- **React Hook Form + Zod** for form validation
- **WebSocket** client for live pipeline progress (singleton manager with auto-reconnect)
- **SSE (Server-Sent Events)** via native `fetch` for streaming chat
- **Lucide React** icons
- **@dnd-kit** for drag-and-drop stage reordering (V2)

---

## V2 Features 🆕

V2 introduces seven major frontend enhancements:

### 1. Report Export (V2)

New `ExportButtons` component on the results viewer. Users can download pipeline reports as **HTML** or **DOCX** via backend endpoints.

### 2. Per-Stage Results Display (V2)

New `StageResultsPanel` component progressively shows results as each pipeline stage completes — no more waiting until the end. Sub-components: `IngestionResults`, `TestCaseResults`, `ExecutionResults`, `ReportingResults`, and `GenericStageResults` (for custom stages). Results appear incrementally during pipeline execution.

### 3. Persistent Pipeline Session (V2)

Local React state and the `usePipelineWebSocket` hook are replaced with:

- **Zustand store** (`store/pipelineStore.ts`) with `persist` middleware (sessionStorage) — pipeline state survives route changes.
- **Singleton WebSocket manager** (`lib/wsManager.ts`) that lives outside React and survives navigation.
- Pipeline continues running when the user navigates to `/admin` or `/chat`.
- Sidebar shows a `PipelineStatusBadge` when a pipeline is active.
- When returning to `/pipeline`, state is restored from the store.

> ⚠️ `hooks/usePipelineWebSocket.ts` is **deprecated** in favour of the Zustand store + singleton WS manager. It remains in the codebase for reference but is no longer used by any page.

### 4. Dynamic Agent Management UI (V2)

- "Add Agent" button on the `AgentList` page.
- New `AddAgentDialog` modal for creating custom agents.
- Delete button on custom agent cards (built-in agents can only be disabled).
- New hooks: `useCreateAgentConfig`, `useDeleteAgentConfig`.

### 5. Dynamic Stage Admin Page (V2)

New route `/admin/stages` with full stage configuration management:

- Drag-and-drop reorder using `@dnd-kit/sortable`.
- `StageCard` — single stage row with edit / delete / enable toggle.
- `StageDialog` — create / edit stage modal.
- New hooks: `useStageConfigs`, `useCreateStage`, `useUpdateStage`, `useDeleteStage`, `useReorderStages`.
- Sidebar updated with a "Stages" nav item under the Admin group.

### 6. Pipeline Controls (V2)

New `PipelineControls` component with:

- **Pause** button (when running) → calls `POST /pause`
- **Resume** button (when paused) → calls `POST /resume`
- **Cancel** button (when running or paused) → calls `POST /cancel`
- New hooks: `usePausePipeline`, `useResumePipeline`.
- Updated status badges: `paused` (amber) and `cancelled` (gray).

### 7. Updated Types (V2)

New and updated TypeScript types:

- `StageConfig`, `StageConfigCreate`, `StageConfigUpdate`, `StageReorderRequest`
- `AgentConfigCreate` (for POST)
- `PipelineStatus` now includes `'paused'` | `'cancelled'`
- `WSEventType` now includes `'run.paused'` | `'run.resumed'` | `'run.cancelled'`

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

The app will be available at **http://localhost:3001**. The root path (`/`) redirects automatically to `/pipeline`.

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

| URL              | Component          | Layout                                           | Status      |
|------------------|--------------------|--------------------------------------------------|-------------|
| `/`              | Redirect           | Root → `/pipeline`                               | No change   |
| `/pipeline`      | `PipelinePage`     | Pipeline layout (Sidebar + Navbar + breadcrumbs)  | **Updated** (V2) |
| `/chat`          | `ChatPage`         | Chat layout (Sidebar + Navbar, no scroll wrapper) | No change   |
| `/admin/llm`     | `LLMProfileList`   | Admin layout (Sidebar + Navbar + breadcrumbs)     | No change   |
| `/admin/agents`  | `AgentList`        | Admin layout                                     | **Updated** (V2) |
| `/admin/stages`  | `StageConfigList`  | Admin layout                                     | 🆕 **NEW** (V2) |

### `/pipeline` — Pipeline Runner (Updated V2)

The main page. Provides the end-to-end workflow:

1. **Upload** — Drag-and-drop or browse for a requirements document (PDF, DOCX, XLSX, TXT up to 50 MB).
2. **Configure** — Optional LLM profile override for the run.
3. **Run / Pause / Resume / Cancel** — Start a new pipeline run, pause/resume it, or cancel an in-progress one. (V2) 🆕
4. **Monitor** — Live WebSocket progress view with a stage timeline (Ingestion → Test-Case → Execution → Reporting), per-agent status badges, and a real-time log stream (capped at 100 messages). Pipeline state is persisted in the Zustand store — navigating away and back restores progress. (V2) 🆕
5. **Per-Stage Results** — Results appear incrementally as each stage completes, not just at the end. (V2) 🆕
6. **Results** — Tabbed viewer: **Summary** / **Test Cases** / **Execution** / **Report** with **Export** buttons for HTML and DOCX download. (V2) 🆕
7. **History** — Collapsible table of past pipeline runs with status (including paused/cancelled), timestamps, and delete-with-confirmation. (V2) 🆕

### `/chat` — LLM Chat Interface

A full streaming chat UI for direct LLM interaction:

- **LLM profile selector** — choose which configured profile to chat with.
- **Settings panel** — customise the system prompt before or during a conversation.
- **Welcome state** — suggestion chips to get started quickly.
- **Streaming messages** — assistant responses are rendered token-by-token via SSE (Server-Sent Events) using native `fetch`.
- **Auto-growing textarea** — `Enter` to send, `Shift+Enter` for a newline.
- User and assistant message bubbles with distinct styling.

### `/admin/llm` — LLM Profiles

Admin panel for managing named LLM configurations:

- Grid of provider-accented cards showing all configured profiles.
- **Create / Edit** — modal form (React Hook Form + Zod) for any provider supported by LiteLLM (OpenAI, Anthropic, Azure OpenAI, Ollama, Groq, etc.).
- **Test connection** — sends a lightweight probe prompt and displays measured latency.
- **Set global default** — the profile used by all agents without an explicit override.
- **Delete** with inline confirmation.

### `/admin/agents` — Agent Configurations (Updated V2)

Admin panel for customising individual CrewAI agents:

- **Search** and **stage filter** to quickly find agents.
- Collapsible accordion sections per pipeline stage.
- Per-agent inline **enable / verbose** toggles.
- **Edit modal** — role, goal, backstory, and per-agent LLM profile override.
- **Reset** individual agent or **Reset All** to factory defaults.
- 🆕 **Add Agent** button — opens `AddAgentDialog` to create a custom agent. (V2)
- 🆕 **Delete** button on custom agent cards (built-in agents can only be disabled). (V2)
- Changes take effect on the next pipeline run — no restart required.

### `/admin/stages` — Stage Configurations 🆕 (V2)

Admin panel for managing pipeline stages:

- **Drag-and-drop reorder** — reorder stages via `@dnd-kit/sortable` with visual drag handles.
- **Stage cards** — each row shows stage name, type, enabled state with toggle, plus edit/delete buttons.
- **Create / Edit** — `StageDialog` modal form for stage configuration.
- **Delete** with confirmation for custom stages.
- Changes take effect on the next pipeline run.

---

## Project Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── globals.css              ← Design tokens + Tailwind v4 theme
│   │   ├── layout.tsx               ← Root layout (Inter + JetBrains Mono fonts, Providers)
│   │   │                               Updated (V2): PipelineSessionProvider integration
│   │   ├── page.tsx                 ← Root redirect → /pipeline
│   │   ├── providers.tsx            ← QueryClientProvider + Toaster + RQ DevTools
│   │   ├── admin/
│   │   │   ├── layout.tsx           ← Admin shell (Sidebar + Navbar + breadcrumbs)
│   │   │   ├── agents/page.tsx      ← Renders <AgentList />
│   │   │   ├── llm/page.tsx         ← Renders <LLMProfileList />
│   │   │   └── stages/             🆕 (V2)
│   │   │       └── page.tsx         ← Renders <StageConfigList />
│   │   ├── chat/
│   │   │   ├── layout.tsx           ← Chat shell (Sidebar + Navbar, no scroll wrapper)
│   │   │   └── page.tsx             ← Renders <ChatPage />
│   │   └── pipeline/
│   │       ├── layout.tsx           ← Pipeline shell (Sidebar + Navbar + breadcrumbs)
│   │       └── page.tsx             ← Renders <PipelinePage />
│   │
│   ├── components/
│   │   ├── layout/
│   │   │   └── Sidebar.tsx          ← Collapsible (w-56 ↔ w-16) sidebar
│   │   │                               4 nav groups (V2):
│   │   │                               • Main — Chat, Pipeline
│   │   │                               • Admin — LLM Profiles, Agent Configs,
│   │   │                                         Stages 🆕
│   │   │                               • Dev — API Docs
│   │   │                               Tooltip labels in icon-only (collapsed) mode
│   │   │                               🆕 PipelineStatusBadge when pipeline active
│   │   ├── chat/
│   │   │   └── ChatPage.tsx         ← Full streaming chat UI: ProfileSelector,
│   │   │                               SettingsPanel, WelcomeState, MessageBubble,
│   │   │                               ChatInput; SSE stream token-by-token
│   │   ├── pipeline/
│   │   │   ├── PipelinePage.tsx     ← Main orchestrator (2-col layout)
│   │   │   │                           Left: upload + LLM selector + Run/Pause/Resume/Cancel
│   │   │   │                           Right: Progress / Results / placeholder
│   │   │   │                           Bottom: collapsible RunHistory
│   │   │   │                           Updated (V2): Uses Zustand store instead of local state
│   │   │   ├── DocumentUpload.tsx   ← Drag-and-drop file upload zone
│   │   │   ├── LLMProfileSelector.tsx ← Profile <select> for pipeline runs
│   │   │   ├── PipelineProgress.tsx ← Live WebSocket stage/agent progress view
│   │   │   │                           Updated (V2): Paused state rendering
│   │   │   ├── PipelineControls.tsx 🆕 (V2)
│   │   │   │                        ← Pause / Resume / Cancel buttons
│   │   │   │                           Pause (when running) → POST /pause
│   │   │   │                           Resume (when paused) → POST /resume
│   │   │   │                           Cancel (when running or paused) → POST /cancel
│   │   │   ├── StageResultsPanel.tsx 🆕 (V2)
│   │   │   │                        ← Progressive per-stage results display
│   │   │   │                           Sub-components: IngestionResults,
│   │   │   │                           TestCaseResults, ExecutionResults,
│   │   │   │                           ReportingResults, GenericStageResults
│   │   │   ├── ExportButtons.tsx    🆕 (V2)
│   │   │   │                        ← HTML / DOCX report download buttons
│   │   │   ├── ResultsViewer.tsx    ← Tabbed results: Summary / Test Cases /
│   │   │   │                           Execution / Report
│   │   │   │                           Updated (V2): +ExportButtons
│   │   │   └── RunHistory.tsx       ← Past runs table with delete confirmation
│   │   │                               Updated (V2): Paused/cancelled status badges
│   │   ├── admin/
│   │   │   ├── agents/
│   │   │   │   ├── AgentList.tsx        ← Full agent admin: search, stage filter,
│   │   │   │   │                           reset-all
│   │   │   │   │                           Updated (V2): +Add Agent button
│   │   │   │   ├── AgentGroupSection.tsx← Collapsible accordion per stage
│   │   │   │   ├── AgentCard.tsx        ← Single agent row (inline toggles +
│   │   │   │   │                           edit/reset)
│   │   │   │   │                           Updated (V2): +Delete button for custom agents
│   │   │   │   ├── AgentDialog.tsx      ← Edit modal (react-hook-form + zod)
│   │   │   │   └── AddAgentDialog.tsx   🆕 (V2)
│   │   │   │                            ← Create new agent modal
│   │   │   ├── stages/             🆕 (V2)
│   │   │   │   ├── StageConfigList.tsx  ← Drag-and-drop stage list (@dnd-kit)
│   │   │   │   ├── StageCard.tsx        ← Stage row (edit/delete/enable toggle)
│   │   │   │   └── StageDialog.tsx      ← Create/edit stage modal
│   │   │   └── llm/
│   │   │       ├── LLMProfileList.tsx   ← Grid of profile cards with full CRUD
│   │   │       ├── LLMProfileCard.tsx   ← Provider-accented card (edit / delete /
│   │   │       │                           set-default / test)
│   │   │       └── LLMProfileDialog.tsx ← Create/edit modal with test-connection
│   │   └── ui/
│   │       ├── Button.tsx           ← Variants: primary / secondary / danger /
│   │       │                           ghost / outline / success; sizes xs–lg;
│   │       │                           loading state
│   │       ├── Input.tsx            ← Input, Textarea, FormField,
│   │       │                           TextareaField, Label
│   │       ├── Select.tsx           ← Select, SelectField, Badge, Toggle
│   │       ├── Modal.tsx            ← Modal, ModalHeader, ModalBody,
│   │       │                           ModalFooter, ConfirmDialog
│   │       ├── Skeleton.tsx         ← Skeleton, SkeletonText, SkeletonCard,
│   │       │                           SkeletonTable
│   │       ├── Toast.tsx            ← Module-level event bus (no React context)
│   │       │                           toast.success/error/warning/info()
│   │       │                           max 5 toasts, auto-dismiss with countdown
│   │       │                           progress bar; Toaster component
│   │       └── ErrorBoundary.tsx    ← Class ErrorBoundary + withErrorBoundary HOC
│   │
│   ├── store/                      🆕 (V2)
│   │   └── pipelineStore.ts         ← Zustand v5 store with `persist` middleware
│   │                                   (sessionStorage). Holds global pipeline
│   │                                   session: runId, status, stages, agent
│   │                                   statuses, log messages, per-stage results.
│   │                                   Survives route changes. Connected to the
│   │                                   singleton WS manager. Replaces local React
│   │                                   state + usePipelineWebSocket pattern.
│   │
│   ├── hooks/
│   │   ├── useAgentConfigs.ts       ← useAgentConfigsGrouped, useAgentConfig,
│   │   │                               useUpdateAgentConfig, useResetAgentConfig,
│   │   │                               useResetAllAgentConfigs,
│   │   │                               useCreateAgentConfig 🆕 (V2),
│   │   │                               useDeleteAgentConfig 🆕 (V2)
│   │   ├── useLLMProfiles.ts        ← useLLMProfiles, useLLMProfile,
│   │   │                               useCreateLLMProfile, useUpdateLLMProfile,
│   │   │                               useDeleteLLMProfile, useSetDefaultLLMProfile,
│   │   │                               useTestLLMProfile
│   │   ├── usePipeline.ts           ← usePipelineRuns, usePipelineRun,
│   │   │                               useStartPipeline, useCancelPipeline,
│   │   │                               useDeletePipelineRun,
│   │   │                               usePausePipeline 🆕 (V2),
│   │   │                               useResumePipeline 🆕 (V2)
│   │   ├── usePipelineWebSocket.ts  ← ⚠️ DEPRECATED (V2) — Replaced by Zustand
│   │   │                               store + singleton WS manager. Retained for
│   │   │                               reference only. Was: WS hook; auto-reconnect
│   │   │                               ×3 with exponential backoff; tracked
│   │   │                               agentStatuses, agentProgress, currentStage,
│   │   │                               logMessages
│   │   └── useStageConfigs.ts       🆕 (V2)
│   │                                ← useStageConfigs, useCreateStage,
│   │                                   useUpdateStage, useDeleteStage,
│   │                                   useReorderStages
│   │
│   ├── lib/
│   │   ├── api.ts                   ← Axios client (30s timeout, error interceptor)
│   │   │                               + API namespaces:
│   │   │                               • llmProfilesApi
│   │   │                               • agentConfigsApi
│   │   │                               • pipelineApi — Updated (V2): +pause, +resume,
│   │   │                                   +exportHTML, +exportDOCX
│   │   │                               • healthApi
│   │   │                               • chatApi (sendStream uses native fetch/SSE)
│   │   │                               • stageConfigsApi 🆕 (V2) — CRUD + reorder
│   │   ├── wsManager.ts             🆕 (V2)
│   │   │                            ← Singleton WebSocket manager that lives outside
│   │   │                               React. Survives route changes and re-renders.
│   │   │                               Auto-reconnect ×3 with exponential backoff
│   │   │                               (1s / 2s / 4s). Dispatches events to the
│   │   │                               Zustand pipelineStore. Handles run.completed,
│   │   │                               run.failed, run.paused, run.resumed, and
│   │   │                               run.cancelled events.
│   │   ├── queryClient.ts           ← QueryClient: 60s staleTime, 5min gcTime,
│   │   │                               2 retries with exp backoff (10s cap),
│   │   │                               refetch-on-window-focus only in prod;
│   │   │                               queryKeys factory
│   │   └── utils.ts                 ← cn(), formatDateTime, formatRelativeTime,
│   │                                   truncate, snakeToTitle, sleep, getInitials
│   │
│   └── types/
│       └── index.ts                 ← All shared TS types:
│                                       LLMProvider enum,
│                                       LLMProfileResponse/Create/Update/Test,
│                                       AgentStage, AgentConfigSummary/Response/
│                                       Grouped/Update,
│                                       AgentConfigCreate 🆕 (V2),
│                                       PipelineStatus (+'paused'|'cancelled') (V2),
│                                       AgentRunStatus, PipelineRunCreate/Response,
│                                       WSEventType (+'run.paused'|'run.resumed'|
│                                       'run.cancelled') (V2), WSEvent,
│                                       StageConfig, StageConfigCreate,
│                                       StageConfigUpdate, StageReorderRequest 🆕 (V2),
│                                       ChatMessage/Request/ProfileItem,
│                                       ApiError, PaginationParams
│
├── public/
├── package.json
├── next.config.ts               ← standalone output, /api/v1/* rewrite proxy
├── tsconfig.json
├── Dockerfile                   ← 3-stage: deps → builder → runner
└── README.md                    ← This file
```

---

## Key Dependencies

| Package                        | Version   | Purpose                                    |
|--------------------------------|-----------|--------------------------------------------|
| `next`                         | ^15.3.3   | Framework (App Router, standalone output)  |
| `react` / `react-dom`          | ^19.0.0   | UI library                                 |
| `@tanstack/react-query`        | ^5.80.0   | Async server-state management              |
| `zustand`                      | ^5.0.0    | 🆕 (V2) Global state with persist middleware |
| `react-hook-form`              | latest    | Form state management                      |
| `@hookform/resolvers`          | latest    | Zod resolver bridge                        |
| `zod`                          | latest    | Schema validation                          |
| `axios`                        | ^1.9.0    | HTTP client (REST calls)                   |
| `lucide-react`                 | ^0.513.0  | Icon set                                   |
| `@dnd-kit/core`                | ^6.3.0    | 🆕 (V2) Drag-and-drop primitives          |
| `@dnd-kit/sortable`            | ^10.0.0   | 🆕 (V2) Sortable list utilities           |
| `@dnd-kit/utilities`           | ^3.2.0    | 🆕 (V2) DnD helper utilities              |
| `tailwindcss`                  | v4        | Utility-first CSS                          |
| `tailwind-merge`               | latest    | Merge Tailwind class strings safely        |
| `clsx`                         | latest    | Conditional class name composition         |

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

| Token                  | Value       | Usage                                      |
|------------------------|-------------|--------------------------------------------|
| `--bg`                 | `#101622`   | Page background                            |
| `--surface`            | `#18202F`   | Cards, panels                              |
| `--surface-elevated`   | `#1e2a3d`   | Table headers, elevated surfaces           |
| `--border`             | `#2b3b55`   | Default borders                            |
| `--border-focus`       | `#135bec`   | Focused input rings                        |
| `--text-primary`       | `#ffffff`   | Primary text                               |
| `--text-secondary`     | `#92a4c9`   | Supporting / label text                    |
| `--text-muted`         | `#3d5070`   | Muted / placeholder text                  |
| `--primary`            | `#135bec`   | Buttons, active states, focus rings        |
| `--primary-hover`      | `#1a6aff`   | Button hover state                         |
| `--success`            | `#22c55e`   | Pass states, success toasts                |
| `--warning`            | `#f59e0b`   | In-progress, caution states, paused badge (V2) |
| `--danger`             | `#ef4444`   | Errors, destructive actions                |
| `--info`               | `#06b6d4`   | Informational highlights                   |

**Radii:** `--radius-sm` (6px) through `--radius-2xl` (20px)
**Shadows:** 5 elevation levels
**Transitions:** `--transition-fast`, `--transition-base`, `--transition-slow`

The `skeleton` CSS class (defined in `globals.css`) provides a shimmer animation used by all `Skeleton*` components.

---

## Architecture Notes

### API Client (`lib/api.ts`)

A single Axios instance (30s timeout, centralised error interceptor) exposes namespaced API objects:

- `llmProfilesApi` — CRUD + test-connection for LLM profiles
- `agentConfigsApi` — read, update, reset, **create, delete** (V2) for agent configurations
- `pipelineApi` — start, cancel, delete, list/get runs, **pause, resume, exportHTML, exportDOCX** (V2)
- `healthApi` — backend health probe
- `chatApi` — chat history and `sendStream`, which uses the native **`fetch` API** (not Axios) to consume SSE token streams
- 🆕 `stageConfigsApi` (V2) — CRUD + reorder for pipeline stage configurations

### Zustand Pipeline Store (`store/pipelineStore.ts`) 🆕 (V2)

A global Zustand store with `persist` middleware (sessionStorage) that replaces per-component React state for pipeline execution:

- **State:** `runId`, `status`, `stages`, `agentStatuses`, `agentProgress`, `currentStage`, `logMessages`, per-stage results
- **Persistence:** sessionStorage — state survives route changes within the same tab
- **WebSocket integration:** The singleton WS manager dispatches events directly to the store
- **Selectors:** Components subscribe to specific slices (e.g. `useStore(s => s.status)`) to avoid unnecessary re-renders
- **Actions:** `startRun`, `reset`, `updateFromWSEvent`, etc.

### WebSocket Manager (`lib/wsManager.ts`) 🆕 (V2)

A singleton WebSocket manager that lives **outside** the React component tree:

- **Survives route changes** — pipeline progress continues when navigating to `/admin` or `/chat`
- **Auto-reconnect** up to 3 times with exponential backoff (1 s → 2 s → 4 s)
- Dispatches events directly to the Zustand pipeline store
- Handles terminal events: `run.completed`, `run.failed`, `run.paused`, `run.resumed`, `run.cancelled`
- **Replaces** the old `usePipelineWebSocket` React hook pattern

### WebSocket Hook (`hooks/usePipelineWebSocket.ts`) — ⚠️ Deprecated

> **Deprecated in V2.** Replaced by the Zustand store + singleton WS manager (`lib/wsManager.ts`). Retained in the codebase for reference.

Previously connected to the pipeline run's WebSocket endpoint and drove all live-progress UI:

- Auto-reconnect up to 3 times with exponential backoff (1 s → 2 s → 4 s)
- Tracked `agentStatuses`, `agentProgress`, `currentStage`, and `logMessages`
- Log message buffer was capped at 100 entries; event feed was capped at 500
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

### Data Fetching & Mutation Hooks

| Hook                         | File                     | Purpose                                     |
|------------------------------|--------------------------|---------------------------------------------|
| `useLLMProfiles`             | `useLLMProfiles.ts`      | Fetch all LLM profiles                     |
| `useLLMProfile`              | `useLLMProfiles.ts`      | Fetch single LLM profile                   |
| `useCreateLLMProfile`        | `useLLMProfiles.ts`      | Create LLM profile                         |
| `useUpdateLLMProfile`        | `useLLMProfiles.ts`      | Update LLM profile                         |
| `useDeleteLLMProfile`        | `useLLMProfiles.ts`      | Delete LLM profile                         |
| `useSetDefaultLLMProfile`    | `useLLMProfiles.ts`      | Set global default LLM profile             |
| `useTestLLMProfile`          | `useLLMProfiles.ts`      | Test LLM connection                        |
| `useAgentConfigsGrouped`     | `useAgentConfigs.ts`     | Fetch agents grouped by stage              |
| `useAgentConfig`             | `useAgentConfigs.ts`     | Fetch single agent config                  |
| `useUpdateAgentConfig`       | `useAgentConfigs.ts`     | Update agent config                        |
| `useResetAgentConfig`        | `useAgentConfigs.ts`     | Reset agent to defaults                    |
| `useResetAllAgentConfigs`    | `useAgentConfigs.ts`     | Reset all agents to defaults               |
| `useCreateAgentConfig`       | `useAgentConfigs.ts`     | 🆕 (V2) Create custom agent               |
| `useDeleteAgentConfig`       | `useAgentConfigs.ts`     | 🆕 (V2) Delete custom agent               |
| `usePipelineRuns`            | `usePipeline.ts`         | Fetch pipeline run history                 |
| `usePipelineRun`             | `usePipeline.ts`         | Fetch single pipeline run                  |
| `useStartPipeline`           | `usePipeline.ts`         | Start pipeline run                         |
| `useCancelPipeline`          | `usePipeline.ts`         | Cancel pipeline run                        |
| `useDeletePipelineRun`       | `usePipeline.ts`         | Delete pipeline run                        |
| `usePausePipeline`           | `usePipeline.ts`         | 🆕 (V2) Pause running pipeline            |
| `useResumePipeline`          | `usePipeline.ts`         | 🆕 (V2) Resume paused pipeline            |
| `useStageConfigs`            | `useStageConfigs.ts`     | 🆕 (V2) Fetch all stage configs           |
| `useCreateStage`             | `useStageConfigs.ts`     | 🆕 (V2) Create stage config               |
| `useUpdateStage`             | `useStageConfigs.ts`     | 🆕 (V2) Update stage config               |
| `useDeleteStage`             | `useStageConfigs.ts`     | 🆕 (V2) Delete stage config               |
| `useReorderStages`           | `useStageConfigs.ts`     | 🆕 (V2) Reorder stages (drag-and-drop)    |

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