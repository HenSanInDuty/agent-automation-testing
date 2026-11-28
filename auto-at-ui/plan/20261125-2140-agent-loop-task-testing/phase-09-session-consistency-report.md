---
phase: 09
title: Báo cáo nhất quán giữa các phiên cùng task (endpoint đọc)
status: completed
owner: be-developer
qa: required
dependencies: [phase-08]
---

# Phase 09 — Báo cáo nhất quán giữa các phiên (ADR-047, phase B2; Q3)

## Mục tiêu

Với một phiên agent-loop `completed`, trả báo cáo đọc-chỉ về các phiên cùng nhóm (cùng `tenant`, `project`, `target_url`,
`intent_hash`; `intent_hash` ở `models.py:127`, tính ở `application/vision.py:93`): số phiên, phân bố trạng thái
`task_assessment`, trạng thái modal, **tỉ lệ đồng thuận** (phiên trùng trạng thái modal / phiên có assessment, cùng cách tính
`benchmark/task_ui/stability.py:138-146`), phiên nguồn có thuộc trạng thái modal không, và cờ đủ điều kiện sinh draft theo
ngưỡng cấu hình (khởi điểm 0,9 theo `stability.py:23`). Bản đầu **chỉ tỉ lệ đồng thuận** (không có chỉ số giống nhau của vết).
Báo cáo không tự chạy thêm phiên và không sinh draft.

## Tiêu chí xong (kiểm chứng được)

1. Endpoint `GET` mới dưới `/api/v1/vision/explorations/{session_id}/consistency` (tên tạm; theo mẫu route `result`,
   `routes/vision.py:805-828`) yêu cầu `Permission.READ` trên project, trả 404 không lộ tồn tại cho tenant/project khác.
2. Chỉ tính phiên `completed` có `task_assessment`; phiên `unavailable`/cũ không có assessment không vào mẫu số (ADR-047,
   "Dùng nhiều phiên nhất quán").
3. Ngưỡng cấu hình qua `config.py` (module duy nhất đọc env; `Settings` truyền vào, không đọc env ở chỗ khác); mặc định 0,9;
   test đổi ngưỡng đổi `eligible`.
4. Quy tắc từ chối trong báo cáo: trạng thái modal khác `achieved`, hoặc phiên nguồn không thuộc trạng thái modal, hoặc đồng
   thuận dưới ngưỡng → `eligible=false` kèm `reason` (`assessment_inconsistent`, `modal_not_achieved`, `source_not_modal`);
   test cho từng ca, kể cả một phiên duy nhất (đồng thuận 100%, 1 phiên: nêu rõ mẫu nhỏ trong báo cáo).
5. Không có "đa số thắng" ngầm: báo cáo luôn trả phân bố trạng thái đầy đủ để người duyệt thấy (test ca 4 `achieved` và 1
   `not_achieved`).
6. Không migration. Truy vấn dùng cột sẵn có (lọc theo `tenant_id`, `project_id`, `intent_hash`); nêu trong báo cáo QA nếu
   cần index (không tự thêm migration, ESCALATE).
7. Test route (HTTP) và test đơn vị cho tính toán; `uv run ruff check .` sạch; test hiện có của vision route
   (`tests/test_vision_routes.py`, `tests/test_vision_results.py`) không hồi quy; `hgraph check --changed` sạch,
   graph `agent-task-draft` và `vision-exploration` cập nhật.

## File liên quan (phạm vi được đụng; ngoài đó cấm)

- Mới: `apps/control-plane/application/agent_task_consistency.py`, `tests/test_agent_task_consistency.py`.
- Sửa: `apps/control-plane/api/v1/routes/vision.py` (thêm một route và response model), `apps/control-plane/config.py`
  (một cờ cấu hình ngưỡng), `apps/control-plane/infrastructure/persistence/repositories.py` (hàm đọc các phiên cùng nhóm,
  nếu `application/` chưa có port phù hợp thì thêm vào `domain/ports.py`).
- Đọc: `benchmark/task_ui/stability.py` (công thức), `apps/control-plane/application/vision_results.py`,
  `apps/control-plane/domain/vision_task_assessment.py`, `apps/control-plane/infrastructure/persistence/models.py`.
- Convention: `AGENTS.md` — `api/` chỉ HTTP, logic ở `application/`; `config.py` là nơi duy nhất đọc env; test route + đơn vị
  (repo chưa có `docs/api-conventions.md`; `docs/api-examples.md` chỉ là ví dụ, không sửa). Graph phải đọc: `docs/graphs/vision-exploration.md`,
  `docs/graphs/agent-task-draft.md` (phase 08); cập nhật: cả hai.
- Tham chiếu: `docs/adr/047-assessment-to-playwright-draft.md` mục "Dùng nhiều phiên nhất quán làm bằng chứng".

## Không làm

- Không import `benchmark/` từ `apps/control-plane` (công thức viết lại ở application, cùng định nghĩa; test đối chiếu số).
- Không chạy thêm phiên, không gọi model, không sinh draft, không đổi `task_assessment`.
- Không thêm chỉ số giống nhau của vết (đã bỏ khỏi bản đầu).

## Rủi ro / việc cần user duyệt

- Đồng thuận trạng thái ≠ đúng: số r4 (98%, phiên bất đồng là phiên sai) và r1 cho thấy đồng thuận chỉ giảm nhiễu ngẫu nhiên;
  báo cáo phải nói rõ điều đó và không dùng từ như "đã xác minh".
- Mẫu nhỏ (1-2 phiên) cho đồng thuận cao giả; hiển thị số phiên cạnh tỉ lệ.
- Ngưỡng 0,9 là điểm xuất phát đo trên fixture, không phải hằng đã chứng minh trên FE thật (phase 05).
