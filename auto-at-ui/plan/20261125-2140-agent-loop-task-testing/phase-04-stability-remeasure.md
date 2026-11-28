---
phase: 04
title: Đo lại độ ổn định 10 task × 3–5 lần trên code cuối
status: completed
owner: none
qa: skip
dependencies: [phase-03]
---

# Phase 04 — Đo lại độ ổn định trên code cuối

## Mục tiêu

Có **một lượt đo đầy đủ** 10 task × 3–5 lần trên fixture cục bộ (`task-target`) bằng code cuối của nhánh (sau phase
02–03) để trả lời: engine agent-loop có "ổn định" theo tiêu chí của bộ đo hay không. Hiện chỉ có r1 (10 phiên),
r2 (20 phiên, code cũ) và r3 (3 phiên xác nhận); chưa có lượt đầy đủ trên code cuối.

Phase này chạy script, không viết code; không có dev. QA skip vì kết quả chính là số đo.

## Tiêu chí xong (kiểm chứng được)

1. Stack đang chạy bằng code của nhánh sau phase 03 (4 file compose + `--profile claude`, xem plan.md "Cách chạy");
   `docker compose ... up -d --wait --wait-timeout 240`, đợi vài giây rồi mới gửi phiên (worker không có healthcheck).
   Ghi lại `git rev-parse HEAD` và version prompt trong báo cáo.
2. Lệnh đo đã chạy xong với `--repeat 5` (tối thiểu 3):
   ```bash
   uv run python scripts/run_task_stability.py run --project "Task UI fixture" \
     --base-url http://task-target:7300 --repeat 5 --out .pytest-artifacts/task-stability/r4
   uv run python scripts/run_task_stability.py report --out .pytest-artifacts/task-stability/r4
   ```
   `runs.jsonl` có đủ 10 × N dòng; không dòng nào bị thiếu do dừng giữa chừng (script resume khi chạy lại cùng lệnh).
3. Báo cáo ghi các số: số phiên, `completed` %, nhất quán %, đúng kỳ vọng %, thời gian/phiên, số lượt gọi model/phiên,
   danh sách phiên không `completed` kèm `safe_failure_reason`.
4. **Ngưỡng ổn định: `completed` ≥ 90% và nhất quán ≥ 90%** (đúng như bộ đo trong `benchmark/task_ui/stability.py`).
   Đạt → ghi "ổn định" vào plan.md. Không đạt → liệt kê từng nguyên nhân gốc (phân nhóm theo reason) và đề xuất
   phase sửa mới; **không** hạ ngưỡng và không tự sửa code trong phase này.
5. Đo tài nguyên worker sau lượt chạy (đỉnh pids/memory, `memory.events` — lệnh trong plan.md) và ghi vào báo cáo;
   dùng làm số đầu vào cho quyết định giới hạn container ở phase 05.
6. Cập nhật mục "Kết quả đo trên fixture" trong plan.md bằng hàng r4 (chỉ thêm hàng, không xoá hàng cũ).

## File liên quan (phạm vi được đụng; ngoài đó cấm)

- Chạy (không sửa): `scripts/run_task_stability.py`, `benchmark/task_ui/stability.py`,
  `benchmarks/task-ui/tasks.v1.json`, `benchmarks/targets/task-ui/`, compose `docker-compose.yml`,
  `docker-compose.codex.yml`, `docker-compose.agent-loop.yml`, `docker-compose.spool-volume.yml`.
- Ghi: `.pytest-artifacts/task-stability/r4/` (gitignore), báo cáo trong
  `plan/20261125-2140-agent-loop-task-testing/reports/phase-04/`, một hàng trong bảng đo ở `plan.md`.
- Cần có sẵn: token bridge còn hạn (`CLAUDE_BRIDGE_TOKEN_DIR=C:/Users/hen/.auto-at/claude-bridge-secrets`; hết hạn thì
  `uv run python scripts/export_claude_bridge_token.py <dir>` — chạm secret, chỉ phiên chính làm), file header
  `.pytest-artifacts/accuracy-local-headers.json`.
- **Cấm** sửa source, đọc/in token, ghi file `.env*`.
- Convention/graph: không áp dụng đổi code; không cập nhật graph.

## Không làm

- Không đo trên site bên thứ ba hoặc production; không đổi `tasks.v1.json` giữa các lượt (đổi bộ task = đo lại từ đầu).
- Không chạy bộ test Python đầy đủ cùng lúc (làm chậm stack và nhiễu số đo).
- Không đổi giới hạn container worker (256 pids, 1 GiB) trong phase này.
- Không diễn giải lỗi `test_vision_page_batch` (`invalid_step_deadline`) như lỗi của engine.

## Rủi ro / việc cần user duyệt

- **Chi phí**: mỗi phiên gọi model thật qua bridge (~3 lần, 25–61 s). 10 × 5 = 50 phiên ≈ 25–50 phút, vượt trần
  một lệnh 9 phút: chạy lại cùng lệnh nhiều lần (mỗi lần `timeout` ≤ 540 s, script resume) hoặc chạy ở phiên mới.
  Cần user đồng ý số lần (3 hay 5) vì tiêu tốn quota model (AGENTS.md: hỏi trước việc có thể phát sinh chi phí đáng kể).
- Token bridge hết hạn/thu hồi (`bridge_model_unavailable`) làm lượt đo hỏng giữa chừng: kiểm token trước khi chạy,
  và coi phiên lỗi do hạ tầng (bridge/worker khởi động) tách riêng khỏi lỗi engine khi báo cáo.
- Hàng tranh chấp spool/heartbeat đã sửa nhưng chưa có lượt đo xác nhận: nếu `bridge_offline` xuất hiện lại, báo ngay.
- **Quyết định chờ user "Giới hạn container worker"** (256 pids, 1 GiB): fixture chỉ dùng 120 pids / 394 MiB; số
  đo ở đây không đại diện cho trang nặng. Đừng kết luận về giới hạn từ phase này.
- Số đo chỉ áp dụng cho `claude_cli / claude-opus-5-5` (model hiện dùng); đổi model/provider phải hỏi user.
