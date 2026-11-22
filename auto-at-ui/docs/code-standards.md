# Code standards

Nguồn convention chính thức của repo là [`AGENTS.md`](../AGENTS.md). File này chỉ là chỉ mục để công cụ
(`hgraph conventions`, bộ skill `h-*`) tìm thấy; **không thêm luật riêng ở đây**. Muốn đổi quy định thì sửa
`AGENTS.md` (cần user duyệt).

## Mục lục `AGENTS.md`

| Mục | Nội dung |
|---|---|
| Product direction | Python bắt buộc dùng `uv`; TypeScript chỉ cho dashboard và worker Playwright; runner-neutral; thực thi test deterministic |
| Code organization rules | Phụ thuộc một chiều `main` / `config` / `api` / `application` / `domain` / `infrastructure` / `agents` / `runners`; prompt chỉ ở `agents/prompts/`; contract chung ở `packages/contracts/`; thay đổi hành vi phải kèm test |
| Required checks before helping | Đọc README/ADR, `git status --short`, `uv run ruff check .`, `uv run pytest`, giữ contract `TestExecutionRequest`/`TestExecutionResult` |
| Assistant token budget and round handoff | Polling bằng một script, log để trên đĩa, giới hạn ảnh, bàn giao sau mỗi round benchmark |
| Boundaries requiring user direction | Những lựa chọn phải hỏi user (cloud, LLM provider/model, auth, Temporal, retention…) |
| Current scaffold status | Trạng thái khung hiện tại |

## Tài liệu liên quan

- Kiến trúc: [`architecture.md`](architecture.md), [`architecture-implementation.md`](architecture-implementation.md)
- Quyết định kiến trúc: [`adr/`](adr/)
- Graph quan hệ file: [`graphs/`](graphs/README.md)
- Prompt agent: `apps/control-plane/agents/prompts/README.md`
