# Auto-AT v3

Hệ thống **multi-agent tự động tạo và thực thi test case** từ tài liệu yêu cầu (API spec / PRD).
Pipeline chạy theo mô hình **DAG (Directed Acyclic Graph)** — các node thực thi song song theo lớp, điều phối bởi CrewAI.

---

## Kiến trúc tổng quan

```
┌─────────────────────────────────────────────────────────┐
│  Next.js Frontend (Admin App)  —  React Flow DAG Builder │
│  Next.js Frontend (User App)   —  Run view               │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP/REST + WebSocket
┌──────────────────────▼──────────────────────────────────┐
│  FastAPI Backend  (Python)                               │
│  DAGPipelineRunner → CrewAI Agents → Tools               │
│  JWT Auth  ·  MinIO Storage  ·  WebSocket broadcast      │
└───┬────────────────────────────┬────────────────────────┘
    │                            │
┌───▼──────┐  ┌──────────┐  ┌───▼─────────────────────┐
│ MongoDB  │  │  MinIO   │  │  Kafka → ClickHouse      │
│ (Beanie) │  │ (S3)     │  │  (Observability)         │
└──────────┘  └──────────┘  └─────────────────────────┘
```

## Tính năng chính

| Tính năng | Mô tả |
|-----------|-------|
| **DAG Pipeline Builder** | Kéo thả node/edge trên React Flow canvas |
| **Multi-Agent Execution** | Ingestion → TC Generation → Execution → Reporting |
| **Parallel DAG Runner** | Topological sort, layer-parallel, retry + timeout |
| **5-tier LLM Priority** | Per-node → per-agent → per-run → default profile → ENV |
| **Real-time WebSocket** | Broadcast tiến độ node/layer/run đến frontend |
| **JWT Auth + RBAC** | ADMIN / QA / VIEWER |
| **MinIO Storage** | File upload & Playwright test artifacts |
| **Observability** | 4 Kafka topics → ClickHouse MergeTree |
| **Orphan Recovery** | Tự khôi phục run bị gián đoạn khi restart |

---

## Monorepo Structure

```
auto-at/
├── apps/
│   ├── admin-app/          # Next.js — Pipeline Builder & Admin UI (port 3001)
│   └── user-app/           # Next.js — User-facing Run View (port 3002)
├── backend/                # FastAPI + CrewAI (port 8000)
├── packages/
│   └── shared/             # Shared TypeScript types
├── infra/
│   └── clickhouse/         # ClickHouse schema & Kafka consumer config
├── docs/                   # Tài liệu kiến trúc & thiết kế
├── TodoCode/               # Target app dùng để test (Go backend + frontend)
├── plans/                  # Agent planning docs & implementation reports
├── docker-compose.yml      # MongoDB · MinIO · Kafka · ClickHouse · Backend · Frontend
├── start.bat               # Windows: khởi động toàn bộ stack
└── stop.bat                # Windows: dừng stack
```

Xem chi tiết tại [`docs/codebase-summary.md`](docs/codebase-summary.md).

---

## Quick Start

### 1. Yêu cầu

- Docker Desktop
- Node.js ≥ 18
- Python ≥ 3.11 + [uv](https://docs.astral.sh/uv/)

### 2. Chạy toàn bộ stack (Docker)

```bash
# Khởi động infra + backend + frontend
docker compose up -d

# Hoặc trên Windows
start.bat
```

### 3. Chạy dev riêng lẻ

```bash
# Backend
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000

# Admin Frontend
npm run dev:admin        # http://localhost:3001

# User Frontend
npm run dev:user         # http://localhost:3002
```

### 4. Tài khoản mặc định

| Field | Value |
|-------|-------|
| Username | `admin` |
| Password | xem `SEED_ADMIN_PASSWORD` trong `backend/.env` |

---

## Cấu hình môi trường

Copy và chỉnh `backend/.env`:

```bash
cp backend/.env.example backend/.env
```

Các biến quan trọng: `MONGODB_URL`, `MINIO_*`, `KAFKA_BOOTSTRAP_SERVERS`, `JWT_SECRET_KEY`, `DEFAULT_LLM_*`.

Xem đầy đủ tại [`backend/README.md`](backend/README.md#environment-variables).

---

## Tài liệu

| File | Nội dung |
|------|----------|
| [`docs/architecture.md`](docs/architecture.md) | Kiến trúc tổng thể — sơ đồ Mermaid |
| [`docs/pipeline-execution.md`](docs/pipeline-execution.md) | Luồng thực thi DAG |
| [`docs/api-flow.md`](docs/api-flow.md) | Luồng xử lý API |
| [`docs/data-models.md`](docs/data-models.md) | MongoDB data models |
| [`docs/observability.md`](docs/observability.md) | Kafka + ClickHouse |
| [`docs/agent-llm.md`](docs/agent-llm.md) | Agent & LLM factory |
| [`docs/codebase-summary.md`](docs/codebase-summary.md) | Project structure đầy đủ |
| [`backend/README.md`](backend/README.md) | Backend API reference |
| [`apps/admin-app/README.md`](apps/admin-app/README.md) | Frontend reference |

---

## Hạ tầng (Docker services)

| Service | Image | Port |
|---------|-------|------|
| MongoDB | `mongo:7` | 27017 |
| MinIO | `minio/minio:latest` | 9000 / 9090 |
| Kafka | `apache/kafka:3.9.0` | 9092 |
| ClickHouse | `clickhouse-server:24.8` | 8123 / 9001 |
| Backend | FastAPI (Python) | 8000 |
| Admin App | Next.js | 3001 |
| User App | Next.js | 3002 |
| Kafka UI | provectuslabs/kafka-ui | 8090 |
