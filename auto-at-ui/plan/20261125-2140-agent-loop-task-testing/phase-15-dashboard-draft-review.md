---
phase: 15
title: Dashboard — yêu cầu và duyệt bản nháp từ phiên agent-loop
status: completed
owner: fe-developer
qa: required
dependencies: [phase-14]
---

# Phase 15 — Dashboard duyệt bản nháp (ADR-047, phase B8)

## Mục tiêu

Dashboard là client mỏng (`docs/architecture.md`, mục "Governed generation experience"): không áp luật redaction hay phân quyền ở
trình duyệt. Thêm vào màn kết quả phiên agent-loop và màn duyệt draft:

- Nút "Tạo bản nháp test" hiện cạnh panel đánh giá task (`vision-task-assessment.tsx`) chỉ khi API cho phép; hiển thị báo cáo
  nhất quán (số phiên, phân bố trạng thái, đồng thuận) và lý do không đủ điều kiện.
- Form liệt kê các bước `type` theo thứ tự (tên locator, độ dài mong đợi) để người yêu cầu nhập giá trị test; giá trị không lưu
  ở `localStorage`/URL, xoá khỏi state sau khi gửi.
- Màn duyệt draft: source, hash, assessment (đánh dấu advisory), check + evidence, nhất quán, danh sách bước bị loại, ghi rõ nguồn
  giá trị test, hộp xác nhận "tài khoản dùng một lần" (gửi `acknowledge_disposable_credentials`), lý do từ chối của API
  (người duyệt trùng người yêu cầu, thiếu quyền).

## Tiêu chí xong (kiểm chứng được)

1. Panel + form hoạt động với dữ liệu giả của dashboard (mẫu `app/components/fixtures/`): đủ trạng thái eligible/không đủ, có/không
   bước `type`, lỗi API (`assessment_inconsistent`, `input_value_mismatch`, `input_value_not_allowed`, `credentials_in_source`).
2. Giá trị test không xuất hiện trong URL, `localStorage`/`sessionStorage`, log console, hay state sau khi gửi (test đơn vị cho model
   state; kiểm tay ghi trong báo cáo QA).
3. Hộp xác nhận bắt buộc khi draft `contains_test_values`; nút duyệt vô hiệu khi chưa tick; không có nút "chạy" nào ngoài đường duyệt
   hiện có (không tạo đường chạy mới).
4. Kiểu API mới cập nhật `app/generation-types.ts`/`app/generation-api.ts` và test (`generation-api.test.ts`,
   `generation-dashboard.test.ts`) qua; dashboard không giữ bản sao luật nghiệp vụ.
5. Trong `apps/dashboard`: `npm run typecheck`, `npm run lint`, `npm test` sạch; spec dashboard
   `workers/playwright/src/vision-dashboard.spec.ts` (thêm ca cho panel mới; chạy `cd workers/playwright && npx.cmd playwright test
   src/vision-dashboard.spec.ts` trên Windows) qua với dữ liệu giả; `uv run pytest tests/test_dashboard_route_contracts.py` qua.
6. `hgraph check --changed` sạch; graph `vision-dashboard` cập nhật (thêm file mới vào graph).

## File liên quan (phạm vi được đụng; ngoài đó cấm)

- Sửa (tồn tại): `apps/dashboard/app/generation-types.ts`, `apps/dashboard/app/generation-api.ts`,
  `apps/dashboard/app/generation-dashboard.tsx`, `apps/dashboard/app/vision-dashboard.tsx`,
  `apps/dashboard/app/components/vision-task-assessment.tsx`, `apps/dashboard/app/components/vision-task-assessment-model.ts`
  (chỉ nếu cần để gắn nút), `apps/dashboard/app/generation-api.test.ts`, `apps/dashboard/app/generation-dashboard.test.ts`,
  `workers/playwright/src/vision-dashboard.spec.ts` (chỉ thêm ca cho panel mới).
- Mới: `apps/dashboard/app/components/agent-task-draft-panel.tsx`, `apps/dashboard/app/components/agent-task-draft-model.ts`,
  `apps/dashboard/app/components/agent-task-draft-model.test.ts` (tên tạm).
- Đọc: `apps/dashboard/app/components/fixtures/`, `apps/dashboard/app/reviews/reviews-dashboard.tsx`,
  `apps/dashboard/app/api-client.ts`, `docs/graphs/vision-dashboard.md`.
- Convention: `AGENTS.md` — TypeScript chỉ cho dashboard và worker Playwright; dashboard là client mỏng, không thực thi luật phân quyền/
  redaction ở trình duyệt; `docs/code-standards.md`. Graph phải đọc: `docs/graphs/vision-dashboard.md`,
  `docs/graphs/agent-task-draft.md`; cập nhật: `vision-dashboard`.
- Tham chiếu: `docs/adr/047-assessment-to-playwright-draft.md` ("Business flow", "Ranh giới duyệt").

## Không làm

- Không sửa phía Python/contract/worker; không thêm đường chạy test ngoài đường duyệt; không tự duyệt thay người dùng.
- Không lưu giá trị test ở client ngoài state tạm; không gọi model từ dashboard.
- Không đổi phần dashboard của planner v4/accuracy.

## Rủi ro / việc cần user duyệt

- Giá trị test đi qua trình duyệt: cần chắc form `autocomplete` không lưu và không gửi sang bên thứ ba (kiểm trong QA).
- Người duyệt phải thấy rõ giá trị nằm trong source; đừng ẩn giá trị khỏi màn duyệt (ADR-047: duyệt thấy source đầy đủ).
- Việc cần user duyệt: không; bố cục mới theo quy ước dashboard hiện có.
