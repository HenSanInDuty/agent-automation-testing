---
phase: 17
title: Ứng viên assertion chứa chữ đã gõ (F5) và task tìm kiếm không assert kết quả (F4)
status: completed
owner: be-developer
qa: required
dependencies: [phase-16]
---

# Phase 17 — Sửa F5 và F4 (nợ của phase 16)

Nguồn: `reports/phase-16/be-developer-r2.md` (F4, F5), `reports/phase-16/leader-r1.md` mục (5), `reports/phase-16/qa-r1.md`
(`test_f4_01`, `test_f5_01` trong `tests/test_qa_p16_e2e.py`). User quyết 2026-11-28: lập phase sửa F5 + F4 theo đề xuất của leader
(phương án (i), chấp nhận thêm một cờ vào contract của phase 10).

## Mục tiêu

1. **F5**: hiện `apps/control-plane/application/agent_task_renderer.py:61-75` (`_candidate_lines`) ghép nguyên văn `verified_text`
   của phiên làm assertion, kể cả chữ chứa giá trị agent đã gõ ở phiên (vd `hoàn thành: <tên việc>`). Người yêu cầu nhập giá trị khác
   lúc xin draft thì test sinh ra `failed` sai (draft `81267bb8`, run `ea7cbb7a`). Sửa theo phương án (i) của leader:
   - Nơi dựng ứng viên `verified_text` (phase 10, `domain/verified_text.py` và chỗ gọi trong `vision_agent_loop.py`) đánh dấu ứng
     viên có chứa chữ đã gõ trong phiên bằng một cờ boolean (vd `derived_from_typed`), **không lưu giá trị gõ**. Cờ đi vào contract
     đóng của `AgentTaskAssessmentCopy` / `AgentTaskTrace` (phase 08/10), tuỳ chọn, mặc định false, để phiên cũ vẫn đọc được.
   - Renderer loại ứng viên có cờ, và ghi trong `stop_conditions` (hoặc `assumptions`) rằng kết quả chứa giá trị nhập không được
     assert.
   - Nêu rõ hệ quả với `trace_hash` (phiên mới đổi hash vì có thêm trường; phiên cũ không có trường thì hash giữ nguyên nếu trường bị
     bỏ khi false/rỗng, theo cách phase 02 đã làm cho `page_text`). Nếu không giữ được hash của phiên cũ → ESCALATE.
2. **F4**: `search-results` cho 2 ứng viên nhưng cả hai là tên điều khiển ("Từ khoá", "Tìm"), test không assert kết quả tìm ("Balo
   laptop" có trên trang). Điều tra vì sao chữ kết quả không thành ứng viên (agent không trích, bộ lọc `verified_text` loại, hay F2
   reset `ObservedText` ở 15c). Chỉ sửa nếu nằm trong controller/renderer và không đổi prompt (đổi prompt = đổi version + đo lại
   fixture, ngoài phạm vi). Ngược lại → ESCALATE kèm nguyên nhân có bằng chứng và đề xuất.
3. Ghi F4/F5 vào ADR-047 (mục Rủi ro hoặc giới hạn đã biết) theo kết quả sửa.

## Tiêu chí xong (kiểm chứng được)

1. Unit test F5: ứng viên chứa chữ đã gõ có cờ; renderer không sinh assertion cho nó và có ghi chú; ứng viên không chứa chữ đã gõ vẫn
   assert. `test_f5_01` (QA phase 16) chuyển trạng thái tương ứng (cập nhật kỳ vọng nếu nó ghim hành vi lỗi). Fail trên code cũ, pass
   trên code mới.
2. Test contract: phiên cũ (không có cờ) đọc được, `trace_hash` của phiên cũ không đổi.
3. F4: báo cáo có nguyên nhân kèm bằng chứng; nếu sửa thì có test và `test_f4_01` cập nhật.
4. `uv run ruff check` sạch cho các file đụng; test phase 08–16 + QA liên quan qua; regenerate file contract sinh tự động nếu contract
   chung đổi; refresh `benchmark/vision/codex/manifest.json` nếu hash lệch.
5. Xác nhận trên stack thật (cần build lại control-plane + temporal-worker, phiên chính chuẩn bị): chạy lại bước marker của
   `scripts/run_agent_task_draft_e2e.py` (giá trị khác giá trị task) → run `passed`; ba test chính vẫn `passed`. Lượt nhỏ, không chạy
   lại toàn bộ phase 16.
6. `hgraph check` sạch; graph `agent-task-draft` cập nhật nếu đổi import/file.

## File liên quan (phạm vi được đụng; ngoài đó cấm)

- `apps/control-plane/domain/verified_text.py`, `apps/control-plane/application/vision_agent_loop.py` (chỗ gọi verify),
  `apps/control-plane/application/agent_task_renderer.py`, `packages/contracts/src/auto_at/contracts/agent_task_trace.py`,
  `apps/control-plane/domain/agent_task_trace.py` và test của chúng (`tests/test_vision_verified_text.py`,
  `tests/test_agent_task_renderer*.py`, `tests/test_agent_task_trace*.py` hoặc tương đương), `tests/test_qa_p16_e2e.py`
  (chỉ kỳ vọng `test_f4_01`/`test_f5_01`), `scripts/run_agent_task_draft_e2e.py` (chỉ nếu bước marker cần), `docs/adr/047-...md`.
- Graph: `docs/graphs/agent-task-draft.md`, `docs/graphs/vision-agent-loop.md`.

## Không làm

- Không đổi prompt agent (`agent-loop-v4`), không đổi chính sách redaction, không lưu giá trị gõ ở đâu mới.
- Không sửa E501 `benchmark/vision/accuracy/run.py:292` (thuộc phần ADR-043).
- Không build lại dashboard.

## Rủi ro

- Cờ mới đổi `trace_hash` của phiên mới: draft cũ vẫn giữ provenance cũ (không ảnh hưởng replay theo `session_id` + `trace_hash`).
- F4 có thể chỉ sửa được bằng prompt → ESCALATE, user quyết phase riêng có đo lại fixture.
