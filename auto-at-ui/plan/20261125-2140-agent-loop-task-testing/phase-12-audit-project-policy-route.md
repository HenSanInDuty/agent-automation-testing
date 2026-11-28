---
phase: 12
title: Audit event cho route policy của project (PUT .../policy)
status: completed
owner: be-developer-junior
qa: required
dependencies: [phase-06]
---

# Phase 12 — Audit route policy của project (ADR-047, phase B5; Q6)

## Mục tiêu

`PUT /api/v1/test-generations/projects/{project_id}/policy` (`apps/control-plane/api/v1/routes/generation.py:154-177`) hiện
không ghi audit event cho bất kỳ trường nào (allowed origins, `vision_max_hops`, `vision_max_states`,
`vision_owned_test_target`). Bản nháp test từ vết task dựa vào cờ `vision_owned_test_target`; không có audit thì không chứng
minh được ai bật cờ và khi nào (ADR-046, mục Consequences; ADR-047, "Ranh giới duyệt"). Phase này thêm audit cho cả trường
mới lẫn cũ. Phase độc lập, có thể chạy song song với phase 08-11.

Quyết định thiết kế (ADR-047): mỗi lần gọi thành công ghi một `AuditEvent` (`domain/runs.py:101-113`) qua
`SqlAlchemyAuditEventRepository` đã có trong route (`generation.py:23`) và trong cùng transaction với `set_policy`;
`actor` = `subject` của người gọi, `entity_type=project_execution_policy`, `entity_id=project_id`, `correlation_id` mới
(`uuid4()`, vì request không mang). `action`: `project_policy.owned_test_target.enabled` / `.disabled` khi cờ đổi trạng thái
(so giá trị trước đọc bằng `get_policy` ngay trước `set_policy`, không đổi chữ ký repository), và `project_policy.updated`
khi chỉ phần khác đổi hoặc không đổi gì. `audit_events` không có cột payload/hash (`models.py:622-629`,
`repositories.py:759-771`), nên sự kiện không mang giá trị cũ/mới ngoài tên `action`; không đổi schema.

## Tiêu chí xong (kiểm chứng được)

1. Gọi `PUT` với cờ `false→true` ghi đúng một event `project_policy.owned_test_target.enabled`; `true→false` ghi `.disabled`;
   gọi với `vision_owned_test_target` bỏ trống (giữ giá trị cũ) hoặc cờ không đổi ghi `project_policy.updated`.
2. Event có `actor` là `subject` của principal (không phải `system`), `tenant_id` đúng, `entity_id=project_id`,
   `correlation_id` hợp lệ; không có giá trị nhạy cảm nào trong event.
3. Gọi bị từ chối (không có `MANAGE_PROJECT`, origin sai → 404 như hiện tại) không ghi event và không đổi policy; cùng một
   transaction: nếu `set_policy` lỗi thì không có event.
4. Hành vi hiện có giữ nguyên: response (`PolicyRequest`) và quy tắc "bỏ trống giữ giá trị cũ" không đổi; test hiện có qua:
   `tests/test_dashboard_route_contracts.py`, `tests/test_vision_agent_task_assessment.py`, `tests/test_vision_tree_capacity.py`.
5. Test route mới trong file mới (HTTP): đủ ca 1-3.
6. `uv run ruff check .` sạch; `hgraph check --changed` sạch; graph `vision-exploration` cập nhật (route
   `routes/generation.py` thuộc graph này).

## File liên quan (phạm vi được đụng; ngoài đó cấm)

- Sửa: `apps/control-plane/api/v1/routes/generation.py` (chỉ hàm `set_policy`, dòng 154-177; thêm audit trong transaction).
- Mới: `tests/test_generation_policy_audit.py`.
- Sửa (user duyệt 2026-11-27, sau ESCALATE r1): `tests/test_vision_tree_capacity.py`, chỉ thêm giả lập `SqlAlchemyAuditEventRepository` trong `test_project_policy_capacity_http_round_trip_and_enforcement` (route giờ ghi audit trong transaction; không đổi hành vi được kiểm).
- Đọc (không sửa): `apps/control-plane/infrastructure/persistence/repositories.py` (`set_policy:341`, `get_policy:333`,
  `SqlAlchemyAuditEventRepository:755`), `apps/control-plane/domain/runs.py`, `apps/control-plane/domain/authorization.py`,
  `apps/control-plane/infrastructure/persistence/models.py` (`AuditEventModel`).
- Mẫu route/test đã có audit để bắt chước: `apps/control-plane/application/vision_policy.py` (audit khi cập nhật policy tenant),
  `tests/test_vision_policy_routes.py`.
- Convention: `AGENTS.md` — `api/` chỉ HTTP, không gọi DB trực tiếp ngoài repository đã dùng; test route cho mỗi thay đổi
  hành vi; `docs/code-standards.md`. Graph phải đọc: `docs/graphs/vision-exploration.md`; cập nhật: `vision-exploration`.
- Lý do `-junior`: một hàm trong một route, một file test mới, không đổi schema, migration, public contract hay response.

## Không làm

- Không sửa schema/migration, `AuditEvent`, `SqlAlchemyAuditEventRepository`, contract; không thêm payload/hash vào audit.
- Không sửa `routes/vision.py` (policy tenant của Vision) hay chữ ký `set_policy` của repository.
- Không backfill audit cho thay đổi policy trước phase này (ghi nhận trong báo cáo).
- Không đổi quyền: vẫn `MANAGE_PROJECT` (`generation.py:166`).

## Rủi ro / việc cần user duyệt

- Bản ghi policy hiện có không có lịch sử audit trước phase này; ADR-047 chấp nhận (draft vẫn chụp giá trị cờ vào provenance).
- `correlation_id` mới cho mỗi lần gọi (request không mang) nên không nối được với request khác; chấp nhận.
- Việc cần user duyệt: không (Q6 đã chốt).
