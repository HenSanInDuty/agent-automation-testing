---
phase: 11
title: Renderer tuyến tính + provenance additive cho bản nháp từ vết task
status: completed
owner: be-developer
qa: required
dependencies: [phase-08, phase-10]
---

# Phase 11 — Renderer tuyến tính và provenance (ADR-047, phase B4; Q1, Q2, Q8)

## Mục tiêu

Một hàm xác định, **không gọi model**, biến `AgentTaskTrace` (phase 08) + ứng viên assertion (phase 10) + giá trị test do người
yêu cầu cung cấp thành `GeneratedTestPlannerOutput` (source Playwright, assumptions, stop_conditions) đi vào bảng draft hiện
có. Selector chỉ từ locator `verified` của worker (Q2), dùng lại `locator_expression`/`literal`
(`vision_source_renderer.py:12-31`). Assertion kết quả chỉ từ ứng viên đã kiểm chứng (Q8). Giá trị test (Q1) là tham số của hàm,
chỉ xuất hiện trong source trả về.

Đồng thời thêm trường provenance **additive** vào `PlanningProvenance` (`contracts/generation.py:116-125`, `extra="forbid"`):
`agent_trace_source{session_id, trace_hash}`, `contains_test_values`, `owned_test_target` (giá trị cờ lúc tạo), `requested_by`.

## Tiêu chí xong (kiểm chứng được)

1. Hàm render hỗ trợ `navigate`, `click`, `type`, `scroll`, `wait` theo đúng thứ tự gói vết; mỗi bước `click`/`type` dùng
   locator `verified`; bước thiếu locator hoặc `dom_path` → lỗi `locator_unavailable` nêu đúng bước (kể cả ô nhãn "Password",
   Q4 giữ nguyên chính sách).
2. `type` nhận giá trị từ tham số theo thứ tự bước; thiếu → `input_value_missing`; độ dài ≠ `text_chars` của bước →
   `input_value_mismatch`; giá trị làm `validate_playwright_test_source` (`contracts/execution.py:13-37`) từ chối (ví dụ có từ
   `process`, `fetch`) → `input_value_rejected_by_source_policy` (mã lý do, không in giá trị).
3. Assertion kết quả: mỗi ứng viên thành `expect(page.getByText(literal(text))).toBeVisible()` (hoặc dạng tương đương theo
   `kind`) đặt sau bước cuối; text đi qua `literal` (JSON, `ensure_ascii`), test chuỗi có dấu nháy/backslash/ký tự điều khiển.
   Không có ứng viên → chỉ assertion nền `visible/enabled` đã có, và `stop_conditions` ghi rõ "kết quả task chưa được assert".
4. Source qua `validate_playwright_test_source` và `PlaywrightTestSourceMode` hợp lệ (hash khớp, `allowed_origins` canonical);
   test snapshot source cho `login-success`, `todo-add`, `search-results` dựng từ dữ liệu mẫu.
5. Giá trị test không xuất hiện ở **bất kỳ** trường nào khác của đầu ra (assumptions, stop_conditions, tiêu đề, provenance,
   thông báo lỗi); test quét đầu ra bằng giá trị mẫu duy nhất.
6. Provenance mới là trường tuỳ chọn: draft/provenance cũ vẫn validate; có test hợp đồng cũ và mới
   (`tests/test_generation_contracts.py`, `tests/test_codex_generation.py` qua, không đổi hash planner); `contains_test_values`
   đúng khi có bước `type`.
7. Render là hàm thuần, xác định: cùng đầu vào cho cùng source và cùng `source_hash` (test hai lần).
8. `uv run ruff check .` sạch; `tests/test_vision_source_renderer.py`, `tests/test_vision_handoff.py`,
   `tests/test_generation_event_processor.py` không hồi quy; `hgraph check --changed` sạch; graph `agent-task-draft` cập nhật.

## File liên quan (phạm vi được đụng; ngoài đó cấm)

- Mới: `apps/control-plane/application/agent_task_renderer.py` (import `locator_expression`, `literal` từ
  `application/vision_source_renderer.py` mà **không sửa** file đó), `tests/test_agent_task_renderer.py`.
- Sửa (contract chung, additive): `packages/contracts/src/auto_at/contracts/generation.py` (`PlanningProvenance`), test
  `tests/test_generation_contracts.py`.
- Đọc (tồn tại): `apps/control-plane/application/vision_source_renderer.py`, `packages/contracts/src/auto_at/contracts/execution.py`,
  `packages/contracts/src/auto_at/contracts/agent_task_trace.py` (phase 08), `apps/control-plane/domain/agent_task_trace.py`
  (phase 08), `apps/control-plane/application/generation_events.py`, `tests/test_vision_source_renderer.py`.
- Convention: `AGENTS.md` — contract chung ở `packages/contracts/`, version rõ khi đổi, `TestExecutionRequest/Result`
  không đổi hình dạng; "agents return structured proposals"; test tập trung. Graph phải đọc: `docs/graphs/agent-task-draft.md`,
  `docs/graphs/vision-exploration.md`; cập nhật: `agent-task-draft`. Nếu `PlanningProvenance` chạm file ngoài graph,
  chạy `hgraph brief`.
- Tham chiếu: `docs/adr/047-assessment-to-playwright-draft.md` ("Quyết định" mục 3-4, "Giá trị test (Q1)", "Dùng lại và làm mới").

## Không làm

- Không sửa `vision_source_renderer.py`, `build_vision_handoff`, planner v4; không gọi model; không viết prompt mới.
- Không lưu/ghi giá trị ngoài source trả về; không persist gì (phase 14 làm).
- Không đổi `TestExecutionRequest/Result`, `PlaywrightTestSourceMode`, worker, runner; không migration.
- Không sinh bước/locator khi bằng chứng thiếu (từ chối, không suy đoán).

## Rủi ro / việc cần user duyệt

- Assertion chữ chỉ tốt bằng chất lượng ứng viên (phase 10); khi thiếu ứng viên, test yếu (chỉ nền): ghi rõ ở
  `stop_conditions` để người duyệt thấy.
- Test trên fixture có thể pass nhầm nếu assertion yếu; ca âm `/broken` ở phase 16 là chốt.
- Việc cần user duyệt: không (đã duyệt qua ADR-047); sửa contract provenance là additive, nhưng nếu phát sinh thay đổi không
  tương thích ngược thì ESCALATE.
