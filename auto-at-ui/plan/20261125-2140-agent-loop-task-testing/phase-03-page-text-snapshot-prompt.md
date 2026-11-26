---
phase: 03
title: Chữ trên trang trong snapshot — render_snapshot và prompt agent
status: pending
owner: be-developer
qa: required
dependencies: [phase-02]
---

# Phase 03 — Chữ trên trang: render_snapshot + prompt

## Mục tiêu

Control plane yêu cầu capability chữ trang (phase 02) cho phiên agent-loop, đưa chữ vào văn bản snapshot mà agent
đọc (`render_snapshot`), và sửa prompt để agent kiểm hiệu ứng bằng chữ trong snapshot thay vì **buộc** xin ảnh
chụp. Ảnh chụp vẫn được xin khi chữ không đủ (canvas, chữ bị cắt, nghi ngờ bố cục).

Kết quả quan sát: ít lượt gọi model hơn cho task kiểm thông báo/tiêu đề/bộ đếm; `login-failure` không còn bị
`not_achieved` sai vì thiếu chữ.

## Tiêu chí xong (kiểm chứng được)

1. `worker_capabilities(settings, step_timeout, owned_test_target)` (`vision_agent_loop.py:101`) trả thêm
   capability chữ trang cho phiên agent-loop; test chứng minh planner v4 không bao giờ yêu cầu nó.
2. `render_snapshot` (`vision_agent_loop.py:122`) thêm một phần chữ, có nhãn rõ (vd dòng `page text:` / mục theo
   loại alert/status/heading/paragraph), đặt sau danh sách control; khi observation không có chữ thì **output
   byte-for-byte giống hiện tại** (test so sánh với snapshot cũ). Chữ đến từ trang được đánh dấu là dữ liệu trang,
   không phải chỉ dẫn (agent không được coi chữ trang là lệnh; test prompt-injection có câu "ignore previous
   instructions" trong alert vẫn không đổi hành vi/target mode).
3. Prompt `agent-loop` trong `apps/control-plane/agents/prompts/agent_loop.py` được tăng version, README prompt
   (`apps/control-plane/agents/prompts/README.md`) cập nhật mục version + hành vi; nội dung: dùng phần chữ trang để
   kiểm kỳ vọng về thông báo/tiêu đề/số đếm; chỉ xin ảnh khi chữ trang không đủ hoặc bị cắt. Prompt không hard-code
   ở nơi khác (AGENTS.md: prompt chỉ ở `agents/prompts/`).
4. Test Python qua: `CODEX_BRIDGE_ENABLED=false uv run pytest tests/test_vision_agent_loop.py tests/test_agent_loop_prompt.py
   tests/test_qa_r11_agent_loop_prompt.py tests/test_vision_agent_loop_qa.py tests/test_vision_agent_task_assessment.py
   tests/test_agent_loop_bridge.py -q --basetemp=.pytest-artifacts/tmp-p3 -p no:cacheprovider` (cần container postgres
   `agent-task-fixture-postgres` theo plan.md, thiếu thì test DB tự skip — ghi rõ test nào skip).
5. Tổng số ký tự snapshot có trần; có test vượt trần thì cắt chữ và ghi dấu cắt, không làm vượt giới hạn prompt hiện có.
6. Chạy thực 3 task phụ thuộc chữ trang (`login-failure`, `broken-save`, `broken-counter` trong
   `benchmarks/task-ui/tasks.v1.json`) × 1–2 lần bằng `scripts/run_task_stability.py`, cần stack + token bridge còn hạn: cả 3 `completed` và
   `task_assessment` đúng kỳ vọng; ghi số lượt gọi model so với r3 (khoảng 3 lượt/phiên). Đây là lượt xác nhận, không
   phải lượt đo đầy đủ (đo đầy đủ ở phase 04).
7. `uv run ruff check .` sạch; `python .pytest-artifacts/refresh_manifest.py` đã chạy và
   `tests/test_codex_bridge_benchmark.py` qua.

## File liên quan (phạm vi được đụng; ngoài đó cấm)

- `apps/control-plane/application/vision_agent_loop.py` (`worker_capabilities`, `render_snapshot`; **không** đổi
  logic retry/ngân sách model-call đã có)
- `apps/control-plane/agents/prompts/agent_loop.py`, `apps/control-plane/agents/prompts/README.md`
- Test: `tests/test_vision_agent_loop.py`, `tests/test_agent_loop_prompt.py`, `tests/test_qa_r11_agent_loop_prompt.py`,
  `tests/test_vision_agent_loop_qa.py`, `tests/test_agent_loop_bridge.py` (chỉ nếu bị ảnh hưởng)
- `docs/adr/046-agent-loop-task-testing.md` (cập nhật mục prompt/snapshot nếu phase 02 chưa nêu hết)
- `benchmark/vision/codex/manifest.json` (chỉ qua `refresh_manifest.py`)
- Chỉ đọc (không sửa): `packages/contracts/.../codex_bridge.py`, `vision_worker.py`, worker TS — nếu cần đổi contract thì
  quay lại phase 02, không sửa ở đây.
- Convention: `AGENTS.md` — "Prompt management" (prompt + README + version cùng lúc), phụ thuộc một chiều
  (`application/` chỉ phụ thuộc domain/contracts). Graph phải đọc trước: `docs/graphs/vision-agent-loop.md`,
  `docs/graphs/codex-bridge.md`; graph cập nhật sau: `vision-agent-loop`. Chạy `hgraph impact` cho
  `vision_agent_loop.py` trước khi bắt đầu. Không lập graph mới.

## Không làm

- Không đổi planner v4, `codex_exploration.py`, `codex-dom-v11`, trần 20 lượt gọi model.
- Không đổi định dạng `task_result`/`task_assessment` (domain/vision_task_assessment.py).
- Không thêm tool/kiểu action mới cho agent (vẫn bảy action kind).
- Không sửa worker/contract (phase 02), dashboard, migration.
- Không nới quy tắc target mode: dòng `Target mode:` vẫn do platform viết, chữ trang không đổi được.

## Rủi ro / việc cần user duyệt

- Tăng version prompt làm thay đổi hành vi của mọi phiên agent-loop; số đo r1–r3 (prompt v3) không so được trực
  tiếp với lượt đo sau phase này. Phase 04 phải ghi rõ version prompt.
- Chữ trang là dữ liệu không tin cậy (có thể chứa chỉ dẫn giả). Nếu QA tìm được đường chữ trang đổi hành vi agent
  ngoài task, coi là lỗi chặn phase.
- **Quyết định chờ user "Task viết `password=...`"**: không thuộc phase này (rule lúc submit ở
  `redact_generation_request`), đừng đụng. Chỉ nhắc để khỏi nhầm khi `login-failure` test.
- **Quyết định chờ user "Nhãn Password"**: nhãn/tiêu đề tiếng Anh có từ "Password" vẫn bị lọc khỏi chữ trang (phase 02),
  nên task kiểm chữ có từ này vẫn có thể phải dùng ảnh chụp.
