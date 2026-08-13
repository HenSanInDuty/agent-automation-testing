# Luồng hệ thống kiểm thử

Sơ đồ dưới đây mô tả luồng hiện tại từ khi hệ thống nhận yêu cầu đến khi một
test run và các kết quả advisory sau run kết thúc.

```mermaid
flowchart TD
    U["Người dùng / Dashboard / API client"]
    U --> A{"Loại yêu cầu"}

    %% Generated-test path
    A -->|"Yêu cầu tạo test bằng ngôn ngữ tự nhiên"| G1["Control Plane API"]
    G1 --> G2["Kiểm tra RBAC<br/>origin policy<br/>redact secret/PII<br/>idempotency"]
    G2 --> G3["Lưu Generation Request<br/>state: queued<br/>+ audit + outbox event"]
    G3 --> G4["Temporal worker / Outbox publisher"]
    G4 --> G5["Generation Planner Agent"]
    G5 --> G6{"Đầu ra hợp lệ<br/>và an toàn?"}
    G6 -->|"Không"| G7["Đánh dấu generation failed<br/>lý do đã redacted"]
    G6 -->|"Có"| G8["Lưu Generated Draft<br/>state: pending_review"]
    G8 --> H["Người duyệt"]
    H --> D{"Quyết định"}
    D -->|"Từ chối"| R["Draft rejected<br/>kết thúc"]
    D -->|"Phê duyệt"| C1["Tạo Test Case versioned<br/>+ tạo Test Run v1"]

    %% Existing-test path
    A -->|"Chạy test có sẵn"| C1

    %% Deterministic execution
    C1 --> C2["Control Plane lưu Run<br/>TestExecutionRequest<br/>+ audit + outbox event"]
    C2 --> C3["Temporal Workflow"]
    C3 --> C4["Playwright Worker"]
    C4 --> C5["Chạy test xác định<br/>theo revision đã pin"]
    C5 --> C6["TestExecutionResult<br/>passed / failed / errored / skipped"]
    C6 --> C7["Lưu kết quả và artifacts<br/>trace, screenshot, video, log..."]

    %% Post-run agents
    C7 --> RP["Reporting Agent<br/>mọi run đã có kết quả"]
    C7 --> F{"Run failed<br/>hoặc errored?"}
    F -->|"Có"| T["Failure Triage Agent"]
    F -->|"Không"| E["Hoàn tất"]
    RP --> RP2["Báo cáo advisory<br/>không đổi verdict"]
    T --> T2["Proposal phân tích nguyên nhân<br/>advisory, có audit"]
    T2 --> HP["Self-healing: xếp hạng<br/>đề xuất sửa locator"]
    HP --> H2["Người duyệt proposal"]
    H2 --> E
    RP2 --> E
```

## Nguyên tắc kiểm soát

- Playwright Worker là thành phần duy nhất quyết định verdict của test.
- Generation, Triage và Reporting Agent chỉ tạo draft, báo cáo hoặc proposal advisory.
- Test do AI sinh và đề xuất self-healing cần được người dùng phê duyệt trước khi có hiệu lực.
- `correlation_id`, audit event và artifacts được giữ xuyên suốt để truy vết.
