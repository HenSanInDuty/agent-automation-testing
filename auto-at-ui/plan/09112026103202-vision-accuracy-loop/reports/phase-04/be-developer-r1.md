STATUS: BLOCKED

# Agent loop round 01 r5 - be-developer r1

```
CONTEXT_CHECK
- conventions: docs/code-standards.md (chỉ mục) -> AGENTS.md (đã đọc: code organization, token budget/round handoff, boundaries)
- graphs: không graph nào phủ .pytest-artifacts/agent_loop_round.py và benchmark/vision/accuracy/run.py (hgraph brief); docs/graphs/vision-agent-loop.md liên quan nhưng chưa cần
- blast radius: 0 file bị phụ thuộc / 1 file phụ thuộc (metrics.py) (từ hgraph)
```

Không có thay đổi source, không submit session, không import/collect/evaluate. Dừng ở BƯỚC 1 theo đúng chỉ thị ("lệch -> dừng, BLOCKED, đừng rebuild").

## Kết quả BƯỚC 1 (`uv run python .pytest-artifacts/agent_loop_round.py check`, exit 1)

Đã so: control-plane 163 `*.py`, temporal-worker 163, claude-bridge 163, playwright-worker 48 `*.ts`.
Mismatch: 1.

| service | file | trạng thái |
| --- | --- | --- |
| claude-bridge | apps/control-plane/application/vision_agent_loop.py | differs |

Chi tiết:
- Container `auto-at-ui-claude-bridge-1` (image `auto-at-claude-bridge:2.1.328`, id `sha256:dc8bf866...`, created 2026-11-20T14:50:09Z) có file 34122 byte, sha256 `b8313494...`, mtime 14:41 ngày 20/11.
- Cây source: 34760 byte, sha256 `09c165c9...`, sửa lúc 2026-11-20 22:16 +07 (= 15:16 UTC), tức SAU lúc build image bridge. Đây là fix parent tracking + lease của r4, đã có trong control-plane và temporal-worker (khớp) nhưng chưa có trong claude-bridge (image dựng từ r3).
- Đánh giá tác động (chỉ để phiên chính quyết định, tôi không tự miễn): `codex_bridge_cli.py` (entrypoint bridge) không import `vision_agent_loop`; các module import nó chỉ là `api/v1/routes/vision.py`, `application/vision.py`, `application/vision_reload.py`, `application/vision_publisher.py`, `config.py` (grep thật), không nằm trong chuỗi import của bridge. Nên khả năng cao file lệch này là vô hại về hành vi live (bridge chỉ chạy prompt `agent_loop` + `BridgeService`, đều khớp). Nhưng chỉ thị yêu cầu 0 mismatch nên chưa chạy phiên.
- Stack hiện: tất cả 10 container Up (control-plane, postgres, redis, temporal-postgres healthy). Không có container nào bị tôi dừng/tạo.

## Việc cần phiên chính chọn

1. (Chặt) rebuild + recreate `claude-bridge` từ cây source rồi chạy lại `check` -> 0 mismatch, hoặc
2. (Nới) xác nhận bằng văn bản rằng mismatch ở `claude-bridge` / `vision_agent_loop.py` được chấp nhận (file không nằm trong đường import của bridge), rồi gọi lại tôi để chạy BƯỚC 2 trở đi.

Nhớ: sau khi rebuild bridge, token/heartbeat cần online lại trước khi submit.

```
NEEDS_USER_INPUT
- câu hỏi: chấp nhận mismatch vô hại ở claude-bridge (vision_agent_loop.py, bridge không import) hay rebuild bridge trước?
- mở khoá: BƯỚC 2-6 (xác nhận bridge online, submit đúng một phiên r5, poll, import/collect/evaluate, ghi handoff)
- đã làm tới đâu: BƯỚC 1 xong (1 mismatch); chưa động tới session file, chưa submit
```

## Chưa làm (để lượt sau)
- Chuyển `.pytest-artifacts/agent-loop-session.json` -> `agent-loop-session.r4.json` (chưa chuyển; file vẫn nguyên).
- Submit phiên r5, poll, import/collect/review/evaluate.
- Mục r5 trong `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md` và handoff "Agent loop round 01 r5" trong README plan (chưa ghi vì không có phiên mới).

```
GRAPH_UPDATE
- graph đã cập nhật: không cần — không thêm/xoá file, không đổi quan hệ import
- file mới đã đưa vào graph: không có
- hgraph check --changed: chưa chạy (không sửa file nào ngoài báo cáo này và .log)
```
