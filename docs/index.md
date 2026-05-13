# Auto-AT — Tài liệu kiến trúc

> Tài liệu này mô tả toàn bộ luồng hoạt động của hệ thống Auto-AT v3.

## Mục lục

| Tài liệu | Nội dung |
|----------|----------|
| [architecture.md](architecture.md) | Kiến trúc tổng thể — các tầng và thành phần |
| [pipeline-execution.md](pipeline-execution.md) | Luồng thực thi DAG pipeline từ đầu đến cuối |
| [api-flow.md](api-flow.md) | Luồng xử lý API — request → response |
| [data-models.md](data-models.md) | Mô hình dữ liệu MongoDB (ER diagram) |
| [observability.md](observability.md) | Luồng Kafka + ClickHouse observability |
| [agent-llm.md](agent-llm.md) | Luồng tạo Agent và phân giải LLM profile |

---

## Tổng quan hệ thống

Auto-AT là một hệ thống **multi-agent tự động tạo test case** từ tài liệu yêu cầu.
Pipeline chạy theo mô hình **DAG (Directed Acyclic Graph)** — các node thực thi song song theo lớp.

```
Người dùng đăng nhập (JWT)
          │
          ▼
    POST /api/v1/auth/login → Bearer token
          │
          ▼
Người dùng upload tài liệu
          │
          ▼
    POST /api/v1/pipeline/runs
          │
          ▼
  File → MinIO (S3-compatible)
          │
          ▼
  DAGPipelineRunner (V3)
  ┌──────────────────────────────────────────────┐
  │  Layer 0 → Layer 1 → ... → Layer N           │
  │  Mỗi layer: các node độc lập chạy song song  │
  └──────────────────────────────────────────────┘
          │
          ▼
  WebSocket broadcast tiến độ real-time
  Kafka emit events (observability)
  MongoDB lưu kết quả
```

## Các thành phần hạ tầng

| Service | Image | Port | Mục đích |
|---------|-------|------|---------|
| MongoDB | mongo:7 | 27017 | Lưu trữ dữ liệu chính (Beanie ODM) |
| MinIO | minio/minio:latest | 9000/9090 | Object storage cho file upload & artifacts |
| Kafka | apache/kafka:3.9.0 | 9092 | Event streaming (KRaft, không cần Zookeeper) |
| ClickHouse | clickhouse-server:24.8 | 8123/9001 | OLAP analytics từ Kafka events |
| Backend | FastAPI (Python) | 8000 | API server chính |
| Frontend | Next.js | 3000 | React Flow UI |

## Tính năng chính (v3)

- **JWT Authentication** — đăng nhập, phân quyền ADMIN / QA / VIEWER
- **DAG Pipeline Builder** — kéo thả node/edge trên React Flow canvas
- **MinIO Storage** — file upload và Playwright test artifacts lưu S3-compatible
- **5-tier LLM Priority** — per-node → per-agent → per-run → default profile → ENV fallback
- **Parallel DAG Execution** — topological sort, layer-parallel với retry + backoff
- **Real-time WebSocket** — broadcast node/layer/run events đến frontend
- **Observability** — 4 Kafka topics → ClickHouse MergeTree (fire-and-forget)
- **Tool Registry** — `api_runner`, `document_parser`, `text_chunker`, `config_loader`, `test_file_renderer`
- **Orphan Recovery** — tự động khôi phục run bị gián đoạn khi restart
