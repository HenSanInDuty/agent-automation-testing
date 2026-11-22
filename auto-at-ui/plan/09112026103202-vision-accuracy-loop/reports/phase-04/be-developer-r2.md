STATUS: FAIL

# Agent loop round 01 r5 - be-developer r2 (continuation after the bridge rebuild)

```
CONTEXT_CHECK
- conventions: docs/code-standards.md -> AGENTS.md (đã đọc ở lượt r1; round handoff + token budget áp dụng)
- graphs: không graph nào phủ .pytest-artifacts/agent_loop_round.py, benchmark/vision/accuracy/run.py; docs/graphs/vision-agent-loop.md liên quan tới lỗi nhưng không sửa source
- blast radius: 0 file bị phụ thuộc / 1 file phụ thuộc (metrics.py) (từ hgraph, lượt r1)
```

Phiên r5 terminal bằng lỗi tích hợp (`origin_blocked`, không phải lý do terminal của agent) -> theo prompt: KHÔNG import, KHÔNG chấm điểm. Không sửa source.

## Các bước

1. `agent_loop_round.py check`: exit 0, mismatches `[]` (control-plane 163, temporal-worker 163, claude-bridge 163, playwright-worker 48).
2. Bridge: `.heartbeat.json` recorded_at 23:40:41Z (trễ 2 s so với `date -u`), `online:true, authenticated:true, capabilities_qualified:true`, model claude-opus-5-5. Không session non-terminal (115 session: 107 unavailable, 8 completed), không `codex_bridge_jobs` non-terminal.
3. `mv agent-loop-session.json agent-loop-session.r4.json`, `submit` một lần: HTTP 202, session `b77691e6-90ee-4676-884c-8d6547af2d4e` (correlation `2747325e-8e43-4de1-8b05-bbebb4a48ffb`). Không submit lần hai.
4. Poll bằng `scripts/watch_vision_session.py` (1 lệnh): `running` -> `terminal unavailable`. Không restart, không đổi code/policy/prompt/oracle.
5. Terminal không hợp lệ -> chỉ chẩn đoán (dưới), không `run.py import/collect/evaluate`.
6. Ghi `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md` (mục r5) và nối handoff vào `plan/.../README.md`.

## Kết quả phiên

| Mục | Giá trị |
| --- | --- |
| State / reason | `unavailable` / `origin_blocked` (không thuộc agent_done, agent_stopped, agent_step_limit, session_timeout) -> AC6 không đạt |
| Thời gian | khoảng 159 s (tạo 23:40:49Z, op cuối bị reject 23:43:28Z) |
| Model calls (bridge jobs) | 11, tất cả completed, 0 schema rejection |
| Token in / out | 56,686 / 4,668 |
| Browser operations | 13: setup navigate, 8 explore click (seq 2-6, 9, 10, 12), 1 back, 2 close_popup, seq 13 setup wait (rejected) |
| Step log | 11 hàng, 15 action, 12 thực thi, `batch_stopped` x4 |
| Blocked action theo code | 0 (không `sensitive_action_blocked`, không `stale_ref`/`invalid_ref`) |
| Vi phạm an toàn | không ghi nhận (không action bị chặn; click đều trên link/tab điều hướng) |
| C / A / P / R | không chấm (không import) |
| ID oracle thiếu | không áp dụng (không chấm); 11 call mới chạm khoảng 8/47 mục tiêu nên K1 (20 call đủ?) chưa đo được |

## Nguyên nhân gốc (control-plane, không phải kết quả model)

`apps/control-plane/application/vision_agent_loop.py` `_observe` (khoảng dòng 427-448):
- Sau click của step 11 (op 12, link HO TRO, x=0.92 y=0.04, `url_change=changed`, trang rời origin cho phép), `observe_dom` với fingerprint cũ bị worker trả `state_mismatch` (`dom_observation`, 422, 23:43:28.461Z).
- `_observe` phát một `wait` đọc-chỉ `purpose=setup` + `refresh_observation=True` (op 13). Worker từ chối mọi action off-origin ngoại trừ `close_popup`/`back`: `operation_prepare: origin_blocked` (23:43:28.508Z).
- `refreshed.operation.status != "completed"` -> `VisualOperationStopped("origin_blocked")` -> session finish `origin_blocked`.
- Đây là race giữa redirect và lần observe DOM đầu; các lần off-origin trước (steps 5-6, 9-10) không dính vì fingerprint đã ổn định.

Đề xuất sửa nhỏ (chưa làm, ngoài phạm vi): khi trang off-origin và cần refresh, retry `observe_dom` (đọc-chỉ, sleep ngắn phía control-plane) thay vì phát `wait`; hoặc cho phép worker làm mới fingerprint off-origin cho wait đọc-chỉ `purpose=setup`. Thêm test: `FakeWorker` trả `state_mismatch` ở lần observe đầu sau click off-origin và áp quy tắc off-origin cho wait refresh; test phải đỏ trên code cũ, xanh trên code mới. Sau đó cần rebuild control-plane + temporal-worker và quyết định của người dùng cho phiên kế tiếp.

Điểm tích cực để ghi nhận: model tự phục hồi khi rời origin (`back` ở step 6, `close_popup` ở steps 7 và 10); fix parent tracking + lease của r4 hoạt động (không `worker_result_mismatch`, không lease lapse trong 159 s).

## Evidence
- `.pytest-artifacts/agent-loop-r5-evidence.log` (18 dòng: warn/error của playwright-worker + control-plane/temporal-worker liên quan session).
- DB (đọc-chỉ): `visual_operations`, `visual_agent_steps`, `codex_bridge_jobs` cho session `b77691e6-...`.
- Không có thư mục `benchmark/vision/accuracy/runs/<id>` mới (không import).

## File đã ghi
- `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md` (mục r5 + bảng; file này đang untracked trong git status, đã tồn tại từ trước)
- `plan/09112026103202-vision-accuracy-loop/README.md` (nối "Agent loop round 01 r5 handoff - 2026-11-21")
- `.pytest-artifacts/agent-loop-session.r4.json` (đổi tên), `.pytest-artifacts/agent-loop-session.json` (r5), `.pytest-artifacts/agent-loop-r5-evidence.log`
- Báo cáo này và `.log`; `be-developer-r1.md` giữ nguyên.
- Lưu ý quy trình: phần nối vào hai file markdown trên dùng `cat >> ... <<EOF` (heredoc) thay vì Edit/Write; lệnh chạy xong ngay, không treo. Nội dung chỉ thêm vào cuối, không sửa phần cũ.

## Tiến trình / stack
Không mở tiến trình hay container nào. Stack compose của dự án giữ nguyên chạy (10 container `auto-at-ui-*` Up; claude-bridge online). Không commit.

```
GRAPH_UPDATE
- graph đã cập nhật: không cần — không thêm/xoá file mã nguồn, không đổi quan hệ import
- file mới đã đưa vào graph: không có
- hgraph check --changed: không chạy (không sửa source; chỉ file markdown/artifact)
```
