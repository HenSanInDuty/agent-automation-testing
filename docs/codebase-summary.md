# Codebase Summary — Auto-AT v3

> Snapshot cấu trúc project. Cập nhật khi có thay đổi lớn về structure.

---

## Tổng quan

| Thông tin | Giá trị |
|-----------|---------|
| Tên project | Auto-AT |
| Version | v3 |
| Loại | Monorepo (npm workspaces) |
| Backend | Python 3.11+ · FastAPI · CrewAI · Beanie ODM |
| Frontend | TypeScript · Next.js 14 · React Flow · Zustand · TanStack Query |
| Package manager | npm (frontend) · uv (backend) |
| Containerization | Docker Compose |

---

## Project Tree

```
auto-at/
│
├── apps/                          # Frontend applications
│   ├── admin-app/                 # Next.js — Pipeline Builder & Admin UI (port 3001)
│   │   └── src/
│   │       ├── app/               # Next.js App Router pages
│   │       │   ├── login/         # Auth page
│   │       │   ├── pipelines/     # Pipeline list + builder + run pages (V3)
│   │       │   ├── pipeline/      # (deprecated — V2)
│   │       │   ├── admin/         # LLM profiles, agent configs
│   │       │   └── chat/          # LLM chat interface
│   │       ├── components/
│   │       │   ├── pipeline/      # Run viewer, output, node cards
│   │       │   ├── pipeline-builder/  # React Flow DAG canvas (V3)
│   │       │   ├── pipelines/     # Template list / cards
│   │       │   ├── admin/         # LLM & Agent config forms
│   │       │   ├── chat/          # Chat UI
│   │       │   ├── layout/        # Sidebar, navbar, shell
│   │       │   └── ui/            # Design system primitives
│   │       ├── hooks/             # TanStack Query + WebSocket hooks
│   │       ├── lib/               # api.ts, wsManager.ts, queryClient.ts
│   │       ├── store/             # Zustand: pipelineStore, builderStore
│   │       └── types/             # Shared TypeScript types
│   │
│   └── user-app/                  # Next.js — User-facing Run View (port 3002)
│       └── src/
│           ├── app/               # Simplified run viewer pages
│           └── components/        # Run-focused components
│
├── backend/                       # FastAPI application (port 8000)
│   └── app/
│       ├── main.py                # FastAPI app, lifespan, router registration
│       ├── config.py              # Pydantic Settings (env vars)
│       │
│       ├── api/v1/                # REST routers
│       │   ├── auth/              # Login, user management
│       │   ├── pipeline/          # Run CRUD, pause/resume/cancel
│       │   ├── pipeline_templates/ # Template CRUD + DAG validation
│       │   ├── agent_configs/     # Agent catalog CRUD
│       │   ├── llm_profiles.py    # LLM profile CRUD
│       │   ├── chat.py            # LLM chat endpoint
│       │   ├── tools.py           # Tool listing
│       │   ├── websocket.py       # WS /ws/pipeline/{run_id}
│       │   └── deps.py            # FastAPI dependencies (auth)
│       │
│       ├── core/                  # DAG engine
│       │   ├── dag_resolver.py    # Topological sort, cycle detection
│       │   ├── dag_pipeline_runner.py  # Parallel layer execution, retry
│       │   ├── pipeline_runner.py # Legacy sequential runner (V2)
│       │   ├── agent_factory.py   # Builds CrewAI Agent instances
│       │   ├── llm_factory.py     # LiteLLM abstraction, 5-tier priority
│       │   ├── signal_manager.py  # Pause / resume / cancel signals
│       │   └── playwright_output_parser.py
│       │
│       ├── crews/                 # CrewAI crew implementations
│       │   ├── ingestion_crew.py       # Document parsing + chunking
│       │   ├── testcase_crew.py        # Test case generation
│       │   ├── api_test_case_crew.py   # API-specific TC generation
│       │   ├── execution_crew.py       # Test execution
│       │   ├── api_test_runner_crew.py # API test runner
│       │   ├── reporting_crew.py       # Report generation
│       │   ├── artifact_crew.py        # Artifact collection
│       │   ├── export_crew.py          # Export (HTML/DOCX)
│       │   ├── md_spec_verifier_crew.py
│       │   ├── report_verifier_crew.py
│       │   ├── test_level_classifier_crew.py
│       │   ├── dynamic_crew.py         # DynamicCrewAICrew (custom nodes)
│       │   └── base_crew.py            # Base class
│       │
│       ├── tools/                 # CrewAI tool implementations
│       │   ├── registry.py             # ToolRegistry — name → instance
│       │   ├── api_runner.py           # HTTP request tool
│       │   ├── document_parser.py      # PDF/DOCX/TXT parser
│       │   ├── text_chunker.py         # Overlapping chunk splitter
│       │   ├── config_loader.py        # YAML/JSON loader
│       │   ├── test_file_renderer.py   # Playwright file generator
│       │   ├── md_api_spec_validator.py
│       │   ├── api_test_case_generator.py
│       │   ├── api_test_runner.py
│       │   ├── report_verifier.py
│       │   └── test_level_tagger.py
│       │
│       ├── services/              # Business services
│       │   ├── auth_service.py    # bcrypt + JWT
│       │   ├── event_bus.py       # Kafka producer (fire-and-forget)
│       │   ├── export_service.py  # HTML / DOCX export
│       │   ├── storage_service.py # MinIO S3 operations
│       │   └── docx_builder.py    # DOCX generation helper
│       │
│       ├── db/                    # Database
│       │   └── (MongoDB init, Beanie models)
│       ├── schemas/               # Pydantic schemas & enums
│       ├── agents/                # Agent config seeders
│       ├── middleware/            # ObservabilityMiddleware (Kafka)
│       ├── tasks/                 # Background task helpers
│       └── templates/             # Jinja2 templates (export)
│
├── packages/
│   └── shared/                    # Shared TypeScript types (npm workspace)
│
├── infra/
│   └── clickhouse/                # ClickHouse DDL: Kafka Engine + MV
│
├── docs/                          # Architecture & design docs
│   ├── index.md                   # Doc index
│   ├── architecture.md            # Mermaid system diagram
│   ├── pipeline-execution.md      # DAG execution flow
│   ├── api-flow.md                # API request lifecycle
│   ├── data-models.md             # MongoDB ER diagram
│   ├── observability.md           # Kafka + ClickHouse flow
│   ├── agent-llm.md               # Agent & LLM factory flow
│   ├── codebase-summary.md        # This file
│   ├── changelog.md               # Version history
│   ├── Flow/                      # Flow diagrams & contracts
│   ├── Ref/                       # Reference specs
│   ├── journals/                  # Dev decision journals
│   └── plans/                     # Completed implementation plans
│
├── TodoCode/                      # Target app used for testing
│   ├── backend/                   # Go (Gin + GORM + SQLite) — port 8080
│   ├── frontend/                  # Frontend stub
│   ├── testing/                   # Test scripts
│   ├── api_spec.md                # API spec fed to Auto-AT pipelines
│   └── api_documentation.md       # Full API docs
│
├── plans/                         # Agent planning & implementation records
│   ├── reports/                   # Execution reports
│   └── templates/                 # Plan templates
│
├── docker-compose.yml             # Full stack: infra + backend + frontends
├── package.json                   # npm workspace root
├── tsconfig.base.json             # Shared TS config
├── start.bat                      # Windows: docker compose up
├── stop.bat                       # Windows: docker compose down
├── README.md                      # Project overview & quick start
└── AGENTS.md                      # AI agent instructions
```

---

## Backend — Key Entry Points

| File | Mục đích |
|------|---------|
| `backend/app/main.py` | FastAPI app, lifespan startup/shutdown |
| `backend/app/core/dag_pipeline_runner.py` | DAG execution engine |
| `backend/app/core/dag_resolver.py` | Topological sort, cycle detection |
| `backend/app/core/agent_factory.py` | Xây dựng CrewAI agents |
| `backend/app/core/llm_factory.py` | 5-tier LLM resolution |
| `backend/app/tools/registry.py` | Tool name → instance mapping |
| `backend/app/services/event_bus.py` | Kafka fire-and-forget |

## Frontend — Key Entry Points

| File | Mục đích |
|------|---------|
| `apps/admin-app/src/app/pipelines/` | Pipeline list + builder + run view |
| `apps/admin-app/src/components/pipeline-builder/` | React Flow DAG canvas |
| `apps/admin-app/src/store/builderStore.ts` | Zustand: DAG node/edge state |
| `apps/admin-app/src/store/pipelineStore.ts` | Zustand: run progress state |
| `apps/admin-app/src/lib/wsManager.ts` | WebSocket connection manager |
| `apps/admin-app/src/lib/api.ts` | Typed API client |

---

## Infra Dependencies

```
MongoDB 7          ← Beanie ODM — pipeline runs, templates, users, agents
MinIO (S3)         ← uploads/{run_id}/ · runs/{run_id}/playwright/
Kafka 3.9 (KRaft)  ← auto_at.api_requests · auto_at.pipeline_events · ...
ClickHouse 24.8    ← Kafka Engine + Materialized View (OLAP)
```

## Ports

| Service | Port |
|---------|------|
| Backend (FastAPI) | 8000 |
| Admin App (Next.js) | 3001 |
| User App (Next.js) | 3002 |
| MongoDB | 27017 |
| MinIO API | 9000 |
| MinIO Console | 9090 |
| Kafka | 9092 |
| Kafka UI | 8090 |
| ClickHouse HTTP | 8123 |
| ClickHouse Native | 9001 |
| TodoCode backend (Go) | 8080 |
