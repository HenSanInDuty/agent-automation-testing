---
phase: 15c
title: Sửa lỗi e2e của phase 16 (F1 traceparent, F2 assertion trạng thái cũ, F3 danh sách nơi lưu)
status: completed
owner: be-developer
qa: required
dependencies: [phase-15b]
---

# Phase 15c — Sửa lỗi phát hiện ở e2e phase 16 r1

Nguồn: `reports/phase-16/be-developer-r1.md` (STATUS: ESCALATE), mục "Lỗi code sản phẩm tìm thấy". User quyết 2026-11-28
(`reports/phase-16/user-answers-r1.md`): lập phase sửa này rồi chạy lại phase 16 vòng r2.

## Mục tiêu

1. **F1**: test đã duyệt chạy lại được qua `POST /api/v1/runs`. Hiện `apps/control-plane/api/v1/routes/runs.py:268` luôn thêm
   `runner_config["traceparent"]`, còn worker `workers/playwright/src/contract.ts:85` đòi đúng 4 khoá của chế độ
   `playwright_test_source` (`mode`, `playwright_test_source`, `source_hash`, `allowed_origins`), nên run `errored`
   ("invalid playwright_test_source runner configuration"). Chọn một phía để sửa (ladder; ưu tiên thay đổi nhỏ nhất, không làm
   yếu kiểm khoá của worker cho khoá lạ khác): ví dụ worker chấp nhận `traceparent` tuỳ chọn có kiểm định dạng, hoặc control plane
   không ghi `traceparent` vào `runner_config` của chế độ source. Ghi lý do chọn. Nếu cách chọn đổi contract chung
   (`packages/contracts`, `vision-contract.generated.ts`) thì regenerate và nêu trong báo cáo.
2. **F2** (user chọn: renderer chỉ assert chữ sau thao tác cuối): `apps/control-plane/application/agent_task_renderer.py:61-72`
   (`_candidate_lines`) chỉ được sinh assertion sau thao tác cuối cho ứng viên `verified_text` mà chữ của nó **thấy được ở quan sát
   sau thao tác cuối**; chữ chỉ có ở trạng thái trước (vd "2 việc, 1 đã xong" của `todo-add`) không được assert. Không đổi contract
   `AgentTaskTrace` / `trace_hash` (không thêm nhãn trước/sau vào phase 10). Nếu renderer không có đủ dữ liệu trong gói vết để
   biết chữ nào thấy sau thao tác cuối mà không đổi contract → `ESCALATE` kèm đề xuất, không tự đổi contract.
3. **F3** (user chọn: chấp nhận, cập nhật danh sách): cập nhật tài liệu và test ghim danh sách nơi lưu giá trị:
   - ADR-047 dòng nơi 9 (`docs/adr/047-assessment-to-playwright-draft.md:170`) và đoạn Q11: thêm rằng khi trang gửi request, giá trị
     gõ còn nằm trong `0-trace.network` (`postData`) và `resources/<sha1>.dat` của trace zip (spike phase 07 không thấy vì dùng trang
     `data:`); nơi 9 vẫn là trace zip, không thêm loại artifact mới.
   - Ghi rõ điều kiện: giá trị test chỉ nhập ở request tạo bản nháp; nếu chính câu task chứa giá trị thì model chép lại vào chữ tự do
     của phiên (`task_assessment`, `visual_agent_steps`) và đó là ngoài danh sách. Đây là điều kiện sử dụng (ghi ở ADR-047 mục Rủi ro),
     không thêm code che.
   - Cập nhật danh sách ghim trong `tests/test_agent_task_draft_e2e.py` và nguồn danh sách trong `scripts/run_agent_task_draft_e2e.py`
     (file của phase 16) cho khớp, để lần quét r2 của phase 16 đối chiếu đúng.
4. Ca (i) của phase 16 (user chấp nhận): ô nhãn "Password" cho phiên `blocked` → `assessment_not_achieved` là kết quả đúng trên stack
   thật. Sửa kỳ vọng ở tiêu chí 3(i) của `phase-16-end-to-end-fixture.md` và ở script/test nếu chúng ghim `locator_unavailable` cho
   ca chạy thật (ca DB của `locator_unavailable` giữ nguyên).

## Tiêu chí xong (kiểm chứng được)

1. Unit test mới cho F1 (route + worker contract spec) và F2 (renderer: ứng viên chỉ thấy trước thao tác cuối không thành assertion;
   ứng viên thấy sau vẫn assert) — fail trên code cũ, pass trên code mới. Dán output.
2. Các test liên quan qua: test phase 08-15b, `tests/test_agent_task_draft_e2e.py`, worker `npm.cmd run typecheck` và spec contract
   liên quan; `uv run ruff check .`. Nếu đổi hash nguồn ghim trong `benchmark/vision/codex/manifest.json` thì chạy
   `python .pytest-artifacts/refresh_manifest.py`.
3. ADR-047 cập nhật theo mục tiêu 3; phase-16 tiêu chí 3(i) cập nhật theo mục tiêu 4.
4. `hgraph check --changed` sạch (hoặc false positive tiền tố `auto-at-ui/` ghi nguyên văn); graph liên quan cập nhật nếu đổi import.
5. Không chạy model thật ở phase này; xác nhận trên stack thật là việc của phase 16 r2.

## File liên quan (phạm vi được đụng; ngoài đó cấm)

- F1: `apps/control-plane/api/v1/routes/runs.py`, `workers/playwright/src/contract.ts` (+ spec của nó), test route runs liên quan
  (tìm bằng `hgraph brief`), contract chung chỉ nếu bắt buộc.
- F2: `apps/control-plane/application/agent_task_renderer.py`, test renderer hiện có (`tests/test_agent_task_renderer*.py` hoặc tương
  đương). **Mở rộng (user duyệt 2026-11-28, `reports/phase-15c/user-answers-r1.md`):** `apps/control-plane/application/vision_agent_loop.py`
  (`ObservedText` chỉ verify theo quan sát cuối trước khi model kết luận) + `tests/test_vision_verified_text.py` / `tests/test_vision_agent_loop*.py`.
- F3/ca (i): `docs/adr/047-assessment-to-playwright-draft.md`, `tests/test_agent_task_draft_e2e.py`, `scripts/run_agent_task_draft_e2e.py`,
  `plan/.../phase-16-end-to-end-fixture.md` (chỉ tiêu chí 3(i)).
- Graph: `docs/graphs/agent-task-draft.md`, `docs/graphs/playwright-vision-worker.md` nếu đổi import.

## Không làm

- Không sửa F4 (`search-results` ra 0 ứng viên nên test không assert kết quả) — ghi nợ, chờ user.
- Không đổi contract `AgentTaskTrace`, không đổi chính sách redaction, không thêm che chữ tự do của phiên.
- Không rebuild/restart stack (phase 16 r2 lo). Không DB/migration.

## Rủi ro

- Worker image trên stack phải build lại cho F1 trước phase 16 r2 (phiên chính chuẩn bị).
- F2 có thể giảm số assertion của các task khác; test đã duyệt cũ (draft phase 16 r1) vẫn mang source cũ.
