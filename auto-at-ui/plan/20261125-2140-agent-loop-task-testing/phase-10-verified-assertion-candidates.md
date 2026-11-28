---
phase: 10
title: Ứng viên assertion do controller kiểm chứng từ chữ trang đã thấy
status: completed
owner: be-developer
qa: required
dependencies: [phase-08]
---

# Phase 10 — Ứng viên assertion kiểm chứng (ADR-047, phase B3; Q8)

## Mục tiêu

Hiện bản nháp chỉ có thể assert `visible/enabled` của control sắp bấm (`contracts/generation.py:128-134`,
`vision_source_renderer.py:88-93`); kỳ vọng của task (thông báo lỗi, tiêu đề, bộ đếm) chỉ có dạng câu chữ model viết trong
`checks[].expectation/evidence` (`contracts/codex_bridge.py:469-483`). Phase này để **controller** (không phải model) tạo
"ứng viên assertion": khi phiên kết thúc, đối chiếu các trích dẫn trong `evidence` của check `met` với chữ trang
(`page_text`) và tên control mà chính phiên đã quan sát (đã qua `validate_locator_value`, tối đa 160 ký tự/mục), chỉ giữ
trích dẫn khớp. Model không được tự đặt chữ kỳ vọng.

Lưu trữ (quyết định thiết kế của phase này, vì chữ trang không được lưu ở nơi nào khác): thêm ứng viên vào dict
`task_assessment` bằng khoá phụ cộng thêm (đề xuất `verified_text`) ở **`vision_agent_loop.py` ngay trước `uow.finish(...)`**
(`vision_agent_loop.py:475`), không sửa `domain/vision_task_assessment.py` (`schema_version` giữ `v1`, người đọc cũ bỏ qua
khoá lạ) và không migration; `finish` redact trước khi lưu (`vision_unit_of_work.py:159-161`). Nếu thực hiện thấy cách này
không khả thi (ví dụ TS dashboard parse chặt), dừng và ESCALATE cho PM; không tự thêm cột/bảng.

## Tiêu chí xong (kiểm chứng được)

1. Trong vòng agent, giữ trong bộ nhớ (bị chặn kích thước, ví dụ tối đa 200 mục, không ghi DB) tập chữ đã quan sát: mục
   `page_text` (kind, text) và tên control, từ observation của mọi bước; không giữ giá trị field nhập.
2. Khi kết thúc bằng `task_result`, với mỗi check `met`: trích các đoạn trong dấu nháy (`"…"`, `“…”`, `'…'`) của `evidence`
   (và `expectation`); một đoạn thành ứng viên khi khớp chính xác (chuẩn hoá khoảng trắng, phân biệt hoa/thường) một mục chữ
   đã quan sát hoặc nằm trong một mục `page_text`. Ứng viên ghi `kind` nguồn (`alert|status|heading|paragraph|control_name`),
   `text`, `check_index`. Đoạn không khớp bị bỏ và đếm (`dropped`).
3. Chỉ check `met`; `not_met`/`not_checked` không bao giờ sinh ứng viên. Phiên không kết thúc bằng `task_result` (bare stop,
   step limit) không có ứng viên.
4. Test: (a) trích dẫn khớp → có ứng viên; (b) trích dẫn do model bịa (không có trên trang) → bị loại; (c) trích dẫn có từ nhạy
   cảm (vd "Password") đã bị lọc phía worker nên không khớp → loại; (d) page text chứa "ignore previous instructions" vẫn chỉ
   là dữ liệu; (e) quá trần số mục → cắt và đánh dấu; (f) không có `page_text` (observation cũ) → danh sách rỗng, không lỗi.
5. Không đổi hành vi vòng agent: số lượt gọi model, retry, ngân sách (`vision_agent_loop.py`), định dạng
   `task_result`, prompt `agent-loop-v4` đều giữ nguyên; test hồi quy
   `tests/test_vision_agent_loop.py`, `tests/test_agent_loop_prompt.py`, `tests/test_qa_r11_agent_loop_prompt.py`,
   `tests/test_vision_agent_loop_qa.py`, `tests/test_vision_agent_task_assessment.py`, `tests/test_qa_p3_page_text_snapshot.py`
   qua (`CODEX_BRIDGE_ENABLED=false uv run pytest ... -q --basetemp=.pytest-artifacts/tmp-p10 -p no:cacheprovider`; cần container
   postgres theo plan.md, thiếu thì ghi rõ test nào skip).
6. Kết quả `GET .../result` (`vision_results.py:166-200`) vẫn trả `task_assessment`; khoá mới không làm vỡ test dashboard
   (`apps/dashboard/app/components/vision-task-assessment-model.ts` và test cùng tên; chạy `npm run typecheck` và `npm test` trong `apps/dashboard` nếu đổi kiểu).
7. Chạy thật 2 task có chữ kết quả (`todo-add`, `search-empty`) × 1 lần trên fixture: có ứng viên đúng chữ trên trang. Cần stack +
   token bridge còn hạn; thiếu thì ghi rõ chưa chạy và để phase 16 chạy.
8. `uv run ruff check .` sạch; `python .pytest-artifacts/refresh_manifest.py` đã chạy nếu đổi file có hash ghim và
   `tests/test_codex_bridge_benchmark.py` qua; `hgraph check --changed` sạch; graph `vision-agent-loop` cập nhật.

## File liên quan (phạm vi được đụng; ngoài đó cấm)

- Sửa: `apps/control-plane/application/vision_agent_loop.py` (thu thập chữ đã thấy, đối chiếu lúc kết thúc, gắn khoá vào
  `assessment`), có thể một module mới `apps/control-plane/domain/verified_text.py` (hàm thuần: trích dẫn, đối chiếu) để
  `vision_agent_loop.py` chỉ gọi.
- Mới: `tests/test_vision_verified_text.py`.
- Sửa test hiện có nếu bị ảnh hưởng: `tests/test_vision_agent_loop.py`, `tests/test_vision_agent_task_assessment.py`.
- Đọc (không sửa): `apps/control-plane/domain/vision_task_assessment.py`, `packages/contracts/src/auto_at/contracts/codex_bridge.py`,
  `apps/control-plane/infrastructure/persistence/vision_unit_of_work.py`, `apps/control-plane/application/vision_results.py`,
  worker TS (`workers/playwright/src/vision-dom.ts`).
- Convention: `AGENTS.md` — `domain/` thuần, không import ngược; test tập trung; model không tự đặt chữ kỳ vọng. Graph phải đọc:
  `docs/graphs/vision-agent-loop.md`, `docs/graphs/playwright-vision-worker.md` (chỉ đọc); cập nhật: `vision-agent-loop`,
  `agent-task-draft`. Chạy `hgraph impact`/`brief` cho `vision_agent_loop.py` trước khi bắt đầu.
- Tham chiếu: `docs/adr/047-assessment-to-playwright-draft.md` ("Quyết định" mục 4, bảng Q8, AC1).

## Không làm

- Không đổi prompt (không cần), planner v4, `domain/vision_task_assessment.py`, contract worker/bridge, không migration.
- Không lưu `page_text` thô vào DB (chỉ các đoạn trích dẫn đã khớp); không lưu giá trị gõ.
- Không để model đề xuất chữ kỳ vọng; không biến ứng viên thành verdict.
- Không nới bộ lọc nhạy cảm (Q4 giữ nguyên).

## Rủi ro / việc cần user duyệt

- Chữ do trang tạo là dữ liệu không tin cậy; ứng viên là chữ trang thật nên không phải chỉ dẫn, nhưng renderer (phase 11) phải
  chuỗi hoá bằng literal an toàn.
- Cách trích dẫn dựa vào dấu nháy trong `evidence` mong manh nếu model không dùng dấu nháy; thực nghiệm (tiêu chí 7) cho
  biết tỉ lệ có ứng viên. Nếu quá thấp, ghi số và đề xuất sửa prompt (cần user duyệt, ngoài phase này).
- Ứng viên chỉ tồn tại với phiên chạy sau phase này; phiên cũ không có (draft từ phiên cũ chỉ có assertion nền).
