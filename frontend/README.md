# Auto-AT Frontend

> **Auto-AT** — Multi-Agent Automated Testing System  
> Next.js 15 · Tailwind CSS v4 · TypeScript · Real-time WebSocket UI

---

## Overview

Auto-AT Frontend is the browser interface for the Auto-AT pipeline. It lets you upload a requirements document, watch all four AI crews work in real time, inspect generated test cases, review execution logs, and download the final report — all from a single-page experience.

Built with:

- **Next.js 15** (App Router, Server Components)
- **Tailwind CSS v4** with a custom dark design-token theme
- **TypeScript** throughout
- **WebSocket** client for live pipeline progress
- **Lucide React** icons

---

## Prerequisites

| Tool | Minimum Version | Notes |
|------|----------------|-------|
| Node.js | 20+ | 20 LTS recommended |
| npm | 10+ | Bundled with Node 20 |

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

The app will be available at **http://localhost:3000**. The root path (`/`) redirects automatically to `/pipeline`.

> Make sure the backend is running on port **8000** before starting the frontend, or update `NEXT_PUBLIC_API_URL` accordingly.

---

## Environment Variables

Create a `.env.local` file in the `frontend/` directory.

| Variable | Default (dev) | Description |
|----------|--------------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Base URL of the Auto-AT backend REST API |
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:8000` | Base URL for WebSocket connections |

> Both variables are prefixed with `NEXT_PUBLIC_` and are inlined at build time. In production (Docker), these are injected via the `docker-compose.yml` `environment` block.

---

## Pages

### `/pipeline` — Pipeline Runner

The main page. Provides the end-to-end workflow:

1. **Upload** — Drag-and-drop or browse for a requirements document (PDF, DOCX, XLSX, TXT up to 50 MB).
2. **Configure** — Optional per-run settings (LLM override, crew timeouts, mock mode).
3. **Monitor** — Live progress view with a stage timeline (Ingestion → Test-Case → Execution → Reporting), real-time log stream via WebSocket, and per-stage status badges.
4. **Results** — Browse generated test cases in a sortable/filterable table, view execution outcomes, and download the final Markdown/JSON report.
5. **History** — List of past pipeline runs with status, timestamps, and quick-access links.

### `/admin/llm` — LLM Profiles

Admin panel for managing named LLM configurations:

- Create profiles for any provider supported by LiteLLM (OpenAI, Anthropic, Azure OpenAI, Ollama, Groq, etc.)
- Store API keys securely (masked in the UI, optionally encrypted at rest in the backend)
- Set a **global default** profile used by all agents that don't have an explicit override
- **Test connectivity** — sends a lightweight probe prompt and displays latency

### `/admin/agents` — Agent Configurations

Admin panel for customising individual CrewAI agents:

- Edit each agent's **role**, **goal**, and **backstory** prompt text
- Assign a per-agent **LLM profile override** (overrides the global default for that agent only)
- **Reset to defaults** — restores factory role/goal/backstory for all agents
- Changes take effect on the next pipeline run — no restart required

---

## Project Structure

```
frontend/
├── src/
│   ├── app/                      Next.js App Router pages & layouts
│   │   ├── layout.tsx            Root layout (font, providers, metadata)
│   │   ├── page.tsx              Root redirect → /pipeline
│   │   ├── providers.tsx         Client-side context providers
│   │   ├── globals.css           Design tokens + Tailwind v4 theme
│   │   ├── pipeline/
│   │   │   └── page.tsx          Pipeline runner page
│   │   └── admin/
│   │       ├── layout.tsx        Admin section layout (tab nav)
│   │       ├── llm/page.tsx      LLM profiles admin page
│   │       └── agents/page.tsx   Agent configs admin page
│   │
│   ├── components/
│   │   ├── ui/                   Reusable, project-scoped UI primitives
│   │   │   ├── Button.tsx        Button with variants, sizes, loading state
│   │   │   ├── Input.tsx         Text/number input with label + error state
│   │   │   ├── Select.tsx        Styled native select
│   │   │   ├── Modal.tsx         Modal, ModalHeader, ModalBody, ModalFooter, ConfirmDialog
│   │   │   ├── Toast.tsx         Toast notification system
│   │   │   ├── Skeleton.tsx      Shimmer loading placeholders
│   │   │   └── ErrorBoundary.tsx React error boundary + withErrorBoundary HOC
│   │   ├── layout/               Shell components (Sidebar, TopBar, etc.)
│   │   └── admin/                Feature components for admin pages
│   │
│   ├── hooks/                    Custom React hooks
│   ├── lib/                      Utilities (cn, formatters, API client)
│   └── types/                    Shared TypeScript type definitions
│
├── public/                       Static assets
├── package.json
├── next.config.ts                Next.js configuration (standalone output)
├── tsconfig.json
├── Dockerfile                    Production container image (multi-stage)
└── README.md                     This file
```

---

## Development Commands

```bash
# Start dev server with hot-reload (Turbopack)
npm run dev

# Type-check without emitting
npm run type-check        # or: npx tsc --noEmit

# Lint with ESLint
npm run lint

# Format with Prettier (if configured)
npm run format

# Production build
npm run build

# Start the production server locally (after build)
npm start

# Analyse bundle size (requires @next/bundle-analyzer)
ANALYZE=true npm run build
```

---

## Design System

All colours, spacing radii, and shadows are defined as CSS custom properties in `src/app/globals.css` and mapped into Tailwind v4 via `@theme inline`. The palette is a dark navy theme:

| Token | Value | Usage |
|-------|-------|-------|
| `--bg` | `#101622` | Page background |
| `--surface` | `#18202F` | Cards, panels |
| `--surface-elevated` | `#1e2a3d` | Elevated surfaces, table headers |
| `--border` | `#2b3b55` | Default borders |
| `--primary` | `#135bec` | Buttons, focus rings, active states |
| `--danger` | `#ef4444` | Destructive actions, errors |
| `--success` | `#22c55e` | Passing tests, success states |
| `--warning` | `#f59e0b` | In-progress, caution states |
| `--text-primary` | `#ffffff` | Primary text |
| `--text-secondary` | `#92a4c9` | Supporting text |

The `skeleton` CSS class (defined in `globals.css`) provides a shimmer animation used by all `Skeleton*` components.

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

The standalone output (`output: "standalone"` in `next.config.ts`) bundles everything needed to run the app without `node_modules`, keeping the final image small.

See [`docker-compose.yml`](../docker-compose.yml) at the project root for the full configuration.

---

## License

MIT © Auto-AT Project