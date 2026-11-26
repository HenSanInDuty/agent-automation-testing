---
phase: 05
title: Chạy trên FE thật của người dùng
status: pending
owner: none
qa: skip
dependencies: [phase-01, phase-04]
---

# Phase 05 — Chạy trên FE thật của người dùng

## Mục tiêu

Chứng minh engine chạy được task UI trên **FE do người dùng sở hữu** (dev/staging), không chỉ trên fixture:
tạo project, đặt allowed origin, bật cờ FE test, chạy 2–3 task thật, đo tài nguyên worker để quyết định có nâng
giới hạn container worker hay không.

Toàn bộ phase cần user: URL/origin FE, tài khoản test dùng-một-lần, đồng ý bật cờ, task cần thử. Không có dev/QA.

## Tiêu chí xong (kiểm chứng được)

1. User đã cung cấp: origin (scheme+host+port, **không phải production**), 2–3 task bằng ngôn ngữ tự nhiên, tài
   khoản test dùng-một-lần nếu task cần đăng nhập (viết thành câu, không `password=...`, theo ADR-046 mục 5).
2. Project mới tồn tại trong tenant `demo-tenant` với allowed origin = origin FE của user (qua dashboard tab
   Vision/project policy hoặc `scripts/run_task_stability.py prepare` — chỉ nếu script hỗ trợ origin ngoài
   `task-target`; nếu không, làm qua dashboard, không sửa script ở phase này).
3. Cờ `vision_owned_test_target` bật cho project đó **chỉ sau khi user xác nhận bằng lời** đây là môi trường test
   của họ; `GET` policy xác nhận giá trị `true`; ghi lại thời điểm bật.
4. Worker container truy cập được origin FE (từ trong Docker: `localhost` của máy chủ **không** truy cập được từ
   container; dùng host gateway/tên mạng hợp lệ và thêm đúng origin tương ứng vào allowlist). Kiểm bằng một phiên
   thử mở trang.
5. 2–3 task chạy xong, mỗi task ≥ 2 lần; với mỗi phiên ghi: trạng thái, `task_assessment.status`, số lần gọi
   model, thời gian, và **đối chiếu bằng mắt người** (frame/evidence trên dashboard) xem kết luận agent đúng không.
   Ghi tỉ lệ "agent đúng / tổng" theo từng task.
6. Đo tài nguyên worker trong lúc chạy (đỉnh `pids.peak`, `memory.peak`, `memory.events`; lệnh trong plan.md
   "Cách chạy") và ghi riêng cho trang thật; kèm lỗi chụp ảnh (Q4/Q5) nếu có.
7. Báo cáo kết luận rõ: (a) engine đủ tốt trên FE này hay không, (b) có cần nâng giới hạn worker không — kèm số đo
   làm bằng chứng; **việc nâng giới hạn là quyết định của user**, không tự áp dụng.
8. Sau khi xong: hỏi user có tắt cờ FE test không (mặc định đề xuất: tắt nếu không còn dùng).

## File liên quan (phạm vi được đụng; ngoài đó cấm)

- Chạy/đọc, không sửa: `scripts/run_task_stability.py`, `docker-compose.agent-loop.yml`,
  `docker-compose.spool-volume.yml`, dashboard Vision (tab Vision + form policy).
- Ghi: project/policy trong DB cục bộ qua API/dashboard (hành động có hiệu ứng, cần user đồng ý), dữ liệu phiên trong
  DB, `.pytest-artifacts/` (gitignore), báo cáo trong `plan/20261125-2140-agent-loop-task-testing/reports/phase-05/`.
- Nếu cần chạy cấu hình compose khác để worker thấy FE của user (mạng, `extra_hosts`): **đó là sửa file cấu hình,
  cần user duyệt riêng**, không nằm trong phạm vi mặc định.
- **Cấm** sửa source; cấm đọc/ghi `.env*`, token; cấm trỏ vào site production hoặc site bên thứ ba.
- Convention: ADR-046 mục 5 (cờ chỉ cho môi trường test; không bao giờ cho production), AGENTS.md "Boundaries
  requiring user direction" (chạm hệ thống bên ngoài cần hỏi trước).

## Không làm

- Không chạy trên production; không bật cờ khi chưa có xác nhận.
- Không bỏ từ `password` khỏi danh sách nhạy cảm, không nới `redact_generation_request` để hợp FE của user
  (xem rủi ro), không sửa `step_deadline`.
- Không đổi giới hạn container worker; không tăng số lượt gọi model (trần 20).
- Không tạo test Playwright từ kết quả (phase 06 là thiết kế).

## Rủi ro / việc cần user duyệt

- **Cần user cung cấp ngay**: URL/origin FE, task, tài khoản test; môi trường FE có truy cập được từ Docker không.
- **Task viết `password=...`** (quyết định chờ user): FE thật nhiều khả năng cần đăng nhập; hiện phải viết tài khoản
  thành câu ("mật khẩu Demo1234"). Nếu user muốn nới rule này cho project FE test thì cần quyết định + phase mới
  (đổi `redact_generation_request`), không làm ở đây.
- **Nhãn tiếng Anh "Password"** (quyết định chờ user): FE thật tiếng Anh có ô "Password" sẽ không agent-typeable
  (bị ẩn khỏi snapshot, `validate_locator_value` từ chối). Nếu gặp, task đăng nhập sẽ `blocked`; báo user quyết định
  chính sách redaction (áp dụng mọi phiên) thay vì tự đổi.
- **Giới hạn container worker** (quyết định chờ user): trang thật nặng có thể vượt 256 pids/1 GiB và gây lỗi chụp
  ảnh; phase này tạo số đo đầu tiên trên trang nặng, nhưng quyết định nâng hay không thuộc user.
- **Dung sai `step_deadline`** (đụng guard runtime): nếu phiên trên Windows host lỗi `invalid_step_deadline`, ghi lại,
  không tự sửa.
- Agent có thể **đổi dữ liệu thật** trên FE của user (tạo/xoá/gửi form). Cần user xác nhận FE là môi trường test với
  dữ liệu bỏ được, và task không có thao tác không hồi phục mà user không muốn.
- Chữ/tên element của FE thật đi tới model provider (dữ liệu của FE thật): user phải đồng ý như tenant đã đồng ý
  chuyển DOM (ADR-046), và không đưa dữ liệu cá nhân thật vào task hoặc môi trường.
- Route policy không ghi audit event (quyết định chờ user): việc bật cờ ở phase này sẽ không có dấu vết audit; ghi
  thời điểm bật vào báo cáo thay thế.
