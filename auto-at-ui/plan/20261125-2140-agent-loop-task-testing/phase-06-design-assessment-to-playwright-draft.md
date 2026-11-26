---
phase: 06
title: Thiết kế nối task assessment sang bản nháp test Playwright
status: pending
owner: none
qa: skip
dependencies: [phase-01]
---

# Phase 06 — Thiết kế: assessment → bản nháp test Playwright

## Mục tiêu

plan.md ghi việc này "chưa thiết kế". Phase này **chỉ ra tài liệu thiết kế**, không viết code sản phẩm: cách biến một
phiên agent-loop đã `completed` + `task_assessment` thành **bản nháp test Playwright** để được duyệt và chạy
deterministic, từ đó mới có **verdict thật** (ADR-001, ADR-002: model không bao giờ tự đưa verdict; assessment chỉ là
advisory và `business_outcome` giữ `unverified`).

Đầu ra mong muốn là một tài liệu mà user duyệt được và các phase code sau (ngoài kế hoạch này) dựa vào đó.

## Tiêu chí xong (kiểm chứng được)

1. Có tài liệu thiết kế (đề xuất `docs/adr/047-assessment-to-playwright-draft.md`, trạng thái `proposed`, hoặc
   mục trong plan nếu user thích nhẹ hơn) gồm:
   - Contract 4 trường: Outcome / Constraints / Non-goals / Acceptance criteria của tính năng.
   - **Business flow**: actor, tiền điều kiện (phiên `completed` + assessment), bước, điểm rẽ nhánh, đường lỗi (assessment
     `not_achieved`/`blocked`/`inconclusive`, nhiều phiên không nhất quán), hậu điều kiện (bản nháp ở trạng thái chờ duyệt).
   - **Data flow**: dữ liệu từ `visual_exploration_sessions` (steps/operations/frames/assessment) → bước nào biến đổi
     → bản nháp → duyệt → chạy runner deterministic → `TestExecutionResult`; nêu chỗ side effect, transaction boundary,
     redaction (giá trị đã gõ không được lưu, chỉ độ dài: phải xử lý bản nháp cần giá trị test).
   - Khớp với cơ chế đã có: đọc `proposal`/`approval` hiện tại (`apps/control-plane/domain/proposals.py`, ADR-002
     generated-test-authority, `agents/` tạo proposal, `runners/` target-neutral `TestExecutionRequest`/`TestExecutionResult`) và nêu phần nào dùng lại, phần
     nào mới.
   - Cách dùng **nhiều phiên nhất quán** (đầu ra phase 04) làm bằng chứng tăng độ tin cậy; xử lý khi assessment mâu thuẫn.
   - Ranh giới duyệt: ai duyệt (RBAC, `MANAGE_PROJECT` hay vai khác), audit trail, không bao giờ tự chạy/thay suite khi chưa duyệt.
   - Chia phase đề xuất cho giai đoạn code (mỗi phase có outcome/owner/qa), kèm danh sách graph cần đọc/lập mới.
2. Mọi chỗ không trả lời được từ source được liệt kê thành câu hỏi có phương án và khuyến nghị (khối
   `NEEDS_USER_INPUT` trong báo cáo của PM); không tự quyết nghiệp vụ.
3. Tài liệu dẫn chứng file:line cho mọi khẳng định về hệ thống hiện tại (đọc source, không suy từ mô tả).
4. User duyệt thiết kế (bằng lời) hoặc chọn không làm tiếp; nếu duyệt, plan.md có thêm các phase code mới (do PM lập).

## File liên quan (phạm vi được đụng; ngoài đó cấm)

- Ghi: `docs/adr/047-assessment-to-playwright-draft.md` (mới) hoặc tài liệu trong thư mục plan; báo cáo trong
  `plan/20261125-2140-agent-loop-task-testing/reports/phase-06/`.
- Đọc: `docs/adr/001-platform-architecture.md`, `docs/adr/002-generated-test-authority.md`, `docs/adr/046-agent-loop-task-testing.md`,
  `docs/architecture.md`, `docs/architecture-implementation.md`,
  `apps/control-plane/domain/vision_task_assessment.py`, `apps/control-plane/domain/proposals.py`,
  `apps/control-plane/runners/`, `packages/contracts/src/auto_at/contracts/codex_generation.py`, `packages/contracts/src/auto_at/contracts/execution.py`,
  `apps/control-plane/infrastructure/persistence/models.py`.
- **Cấm** sửa source/test/migration/contract ở phase này.
- Convention: `AGENTS.md` ("agents return structured proposals, never change suites or verdicts without approval",
  "Add focused tests with each behavior change" cho giai đoạn code sau); graph đọc: `docs/graphs/vision-agent-loop.md`,
  `docs/graphs/vision-exploration.md`; dùng `hgraph brief` cho vùng proposal/runners khi lập thiết kế. Có thể đề xuất
  graph mới cho tính năng này ở giai đoạn code, không lập trong phase này.

## Không làm

- Không viết code, không migration, không đổi contract, không tạo test Playwright thật.
- Không để assessment thành verdict; không đổi `exploration_conclusion.business_outcome` khỏi `unverified`.
- Không gộp vào phase 02/03; không phụ thuộc vào việc chạy trên FE thật (phase 05).
- Không chọn dùng framework/runner mới (ví dụ thay Playwright) mà không hỏi user.

## Rủi ro / việc cần user duyệt

- Đây là phase thiết kế duy nhất cần **user duyệt** trước khi có bất kỳ phase code nào. Tính năng này đụng ranh giới
  kiến trúc (model sinh test → cần approval) nên mọi quyết định về ai duyệt, lưu giá trị test, độ rộng sinh test
  đều thuộc user.
- Một số câu hỏi dự kiến chặn thiết kế (PM sẽ leo thang bằng `NEEDS_USER_INPUT` khi bắt đầu): giá trị test (tài khoản)
  lưu ở đâu khi phiên chỉ giữ độ dài giá trị; selector/locator sinh từ element ref của agent hay từ locator đã bind
  của worker; bản nháp sinh từ một phiên hay từ nhiều phiên nhất quán.
- Quyết định chờ user về policy redaction ("Password", `password=...`) ảnh hưởng thiết kế dữ liệu test (cách lưu
  thông tin đăng nhập cho test lặp lại): thiết kế phải nêu phương án với mỗi kết quả quyết định, không giả định.
- Route policy chưa ghi audit event (quyết định chờ user): thiết kế về audit trail của bản nháp phải nêu rõ
  phụ thuộc vào việc này.
