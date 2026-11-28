---
phase: 07
title: Kiểm chứng giả định của ADR-047 (spike, không đổi code)
status: completed
owner: none
qa: skip
dependencies: [phase-06]
---

# Phase 07 — Spike: kiểm chứng giả định trước khi dựng gói vết (ADR-047, phase B0)

## Mục tiêu

ADR-047 dựa trên vài suy luận từ đọc source chưa chạy thử. Phase này **không đổi code**: chạy và đo để các phase 08-16 dựa
vào số thật. Đầu ra là một báo cáo có số, không phải code.

Cần kết luận (mỗi mục một câu trả lời kèm bằng chứng):

1. **Handoff cây so với chuỗi agent.** Với phiên agent-loop thật (ít nhất `login-success`, `todo-add`, `search-results`
   của `benchmarks/task-ui/tasks.v1.json`), chạy `build_vision_handoff` (`application/vision_handoff.py:11-99`) trên dữ
   liệu của phiên (đọc `visual_operations`, `visual_locator_evidence` của DB cục bộ) và ghi số nhánh, trạng thái/`reason_code`
   mỗi nhánh, bước nào còn trong nhánh. Xác nhận hay bác giả thuyết "mỗi action thành nhánh rời `navigate -> action`, mất
   các bước trước" (ADR-047, mục "Cái gì đã có, cái gì thiếu", điểm 2).
2. **Locator của bước `type` và `click`:** locator `verified` có tồn tại cho ô nhập và nút của ba task trên không; strategy
   nào (`role|label|test_id|css|dom_path`)? Có bước nào bị `ephemeral_locator` (`vision_handoff.py:52-55`)?
3. **Giá trị gõ có lọt vào artifact của run không (nơi 9, 10 của bảng ADR-047).** Chạy một spec Playwright mẫu tự viết
   (workspace tạm trong `.pytest-artifacts/`, không qua nền tảng) có `fill` một giá trị mẫu duy nhất, với trace/video/
   screenshot/`line` reporter bật như worker (`workers/playwright/src/execute.ts:259-263`), rồi quét trace zip, output
   text, video metadata tìm giá trị mẫu. Nếu có trong `playwright-output`, ghi rõ để phase 13 loại excerpt khỏi evidence gửi model
   (`agents/shared/evidence.py:24,70-90`).
4. **Retention thật:** (a) có mã nào xoá hàng `outbox_events` đã publish không (grep toàn repo + `docker-compose*.yml`/job
   nền), (b) retention namespace của Temporal cục bộ (cấu hình trong compose hoặc `docs/adr/002-local-temporal-workflow-backend.md`),
   (c) `ArtifactPolicy.retain_days` mặc định 30 (`contracts/execution.py:62`) có thực sự xoá artifact không.
5. **Cần bảng lưu gói vết không?** Gói vết dựng theo yêu cầu từ `visual_agent_steps` (ADR-047, quyết định 1). Kết luận
   "không cần bảng" hay "cần" (khi có phiên mà bằng chứng hết hạn trước khi người dùng yêu cầu draft).
6. **`visual_agent_steps.operation_ids` và `visual_operations.sequence`** có tái dựng được thứ tự chuỗi tuyến tính đầy đủ
   không (kể cả bước bị skip/blocked, step có nhiều action).

## Tiêu chí xong (kiểm chứng được)

1. Có báo cáo `reports/phase-07/` trả lời đủ 6 mục trên, mỗi mục có số liệu hoặc dòng lệnh + trích kết quả, nói rõ
   câu nào không kết luận được và vì sao.
2. Mỗi giả định của ADR-047 gắn nhãn "chưa kiểm chứng" (nơi 4, 5, 9, 10; giả định 2) đều được chuyển thành "đã kiểm chứng:
   đúng/sai" hoặc "không kiểm được".
3. Nếu bất kỳ kết luận nào làm sai thiết kế của ADR-047 (ví dụ handoff vẫn dùng được, hoặc cần bảng gói vết), báo cáo
   nêu rõ phase nào đổi và PM sửa ADR/phase trước khi phase 08 bắt đầu (ESCALATE, không tự sửa phase khác).
4. `git status` sau phase: không file nguồn/test/migration/contract nào đổi; chỉ file trong `reports/phase-07/` và
   scratch trong `.pytest-artifacts/` (gitignore).

## File liên quan (phạm vi được đụng; ngoài đó cấm)

- Ghi: `plan/20261125-2140-agent-loop-task-testing/reports/phase-07/` và scratch trong `.pytest-artifacts/` (spike script
  nằm ngoài repo hoặc trong `.pytest-artifacts/`, không commit).
- Đọc (tồn tại): `apps/control-plane/application/vision_handoff.py`, `apps/control-plane/application/vision_source_renderer.py`,
  `apps/control-plane/infrastructure/persistence/vision_unit_of_work.py`, `.../repositories.py`,
  `apps/control-plane/application/vision_agent_loop.py`, `workers/playwright/src/execute.ts`,
  `workers/playwright/src/vision-operations.ts`, `apps/control-plane/agents/shared/evidence.py`,
  `apps/control-plane/infrastructure/workflows/temporal.py`, `docker-compose*.yml`, `docs/adr/002-local-temporal-workflow-backend.md`,
  `benchmarks/task-ui/tasks.v1.json`.
- Đọc DB cục bộ: chỉ `SELECT` (stack cục bộ theo "Cách chạy" của plan.md). Cần chạy 3 phiên agent mới nếu DB chưa còn:
  `scripts/run_task_stability.py` (token bridge còn hạn).
- Convention: `AGENTS.md` (ranh giới tầng; không dùng `pip`, dùng `uv`), `docs/code-standards.md`. Graph phải đọc:
  `docs/graphs/vision-agent-loop.md`, `docs/graphs/vision-exploration.md`. Không cập nhật graph, không lập graph mới.
- Đối chiếu: `docs/adr/047-assessment-to-playwright-draft.md`, mục "Cái gì đã có, cái gì thiếu", bảng "Giá trị test (Q1)" và "Phần ADR-002 phải sửa".

## Không làm

- Không sửa source, test, migration, contract, ADR; không sửa `plan.md` (báo cáo cho phiên chính).
- Không `INSERT/UPDATE/DELETE` DB, không `docker compose down -v`, không đụng `.env*`/token.
- Không tạo draft hay test case thật; không chạy trên FE thật (phase 05).

## Rủi ro / việc cần user duyệt

- Cần stack + token bridge còn hạn để có phiên mới (mỗi phiên gọi model thật qua bridge, tốn thời gian/chi phí nhỏ).
  Nếu thiếu, ghi BLOCKED kèm lệnh cần chạy, không tự thay token.
- Kết quả có thể đảo thiết kế (xem tiêu chí 3); khi đó cần user duyệt lại phần bị đổi.
