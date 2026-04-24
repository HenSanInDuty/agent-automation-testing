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
Người dùng upload tài liệu
          │
          ▼
    POST /api/v1/pipeline/runs
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
