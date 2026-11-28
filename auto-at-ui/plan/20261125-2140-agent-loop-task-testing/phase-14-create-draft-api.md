---
phase: 14
title: API tạo bản nháp Playwright từ phiên agent-loop
status: completed
owner: be-developer
qa: required
dependencies: [phase-09, phase-11, phase-13]
---

# Phase 14 — API tạo draft (ADR-047, phase B7; Q1, Q3, Q9)

## Mục tiêu

Nối các phần đã có thành một use case và một route: người có `SUBMIT_GENERATION` yêu cầu draft từ một phiên agent-loop
`completed`. Trong **một transaction**: kiểm điều kiện, dựng gói vết (phase 08), ứng viên (phase 10), kiểm báo cáo nhất quán
(phase 09), nhận giá trị test, render source (phase 11), tạo `generation_requests` `completed` + `generated_test_drafts`
`pending_review` + audit. Không qua outbox/processor (ADR-047, "Quyết định" mục 2). Duyệt, preflight, tạo test case + run,
verdict giữ nguyên đường `DecideGeneratedDraft` (phase 13 đã siết).

Route (tên tạm): `POST /api/v1/vision/explorations/{session_id}/test-draft`, CSRF + `Idempotency-Key`, mẫu
`POST /runs/{id}/revised-draft` (`routes/runs.py:294-330`). Body: `values` cho từng bước `type` theo thứ tự (khi chuỗi có
bước `type`).

## Tiêu chí xong (kiểm chứng được)

1. Điều kiện đủ để tạo (mọi điều kiện sai trả lỗi có mã, không tạo hàng nào): phiên `agent_loop` `completed` có assessment
   `achieved` (Q9: `not_achieved`/`blocked`/`inconclusive` → `assessment_not_achieved`; phiên cũ không có assessment →
   `assessment_unavailable`); báo cáo nhất quán `eligible` (`assessment_inconsistent`); origin trong allowlist
   (`generation.py:71-75`); `SUBMIT_GENERATION` (service principal không có); chuỗi có `type` thì project bật
   `vision_owned_test_target` (`input_value_not_allowed`); đủ giá trị, độ dài khớp `text_chars` (`input_value_missing`,
   `input_value_mismatch`); bằng chứng còn (`evidence_expired`).
2. Một transaction: lỗi giữa chừng không để lại request mồ côi; audit `generation.requested` và `generation.completed` ghi `actor` là
   người yêu cầu (không `system`, khác `generation.py:115`); `provenance` có `agent_trace_source{session_id, trace_hash}`,
   `contains_test_values`, `owned_test_target` (giá trị cờ lúc tạo), `requested_by`, `consistency` (số phiên, đồng thuận).
3. Idempotency theo (`session_id`, `trace_hash`): gọi lại trả draft cũ, không băm/so giá trị; cùng key khác body → 409 theo mẫu
   `generation.py:87-95`. `generation_requests.redacted_request` là câu cố định trung tính, không chữ task, không giá trị.
4. **Giá trị chỉ ở nơi cho phép** (ADR-047 AC3): test với một giá trị mẫu duy nhất quét: DB phiên, `visual_agent_steps`,
   `audit_events`, `generation_requests`, `provenance`, idempotency key, response của route tạo, log captured
   (`caplog`/log của framework, kể cả log request body) và response lỗi → vắng; xuất hiện đúng ở source draft (và các nơi khai báo
   sau duyệt: test case, `test_runs.request`, `outbox_events.payload`, phản hồi `GET` draft/run). Thêm một nơi lưu mới khiến test fail
   (danh sách nơi cho phép khai báo trong test).
5. Draft tạo xong ở `pending_review`, chưa có test case/run; test khẳng định bảng `test_cases` và `test_runs` không đổi.
6. Không migration, không bảng/cột mới. Contract response không chứa giá trị test.
7. Test route (HTTP) và test use case, bao gồm: không đủ quyền (404 không lộ), tenant/project khác, CSRF thiếu, phiên chưa xong,
   không nhất quán, thiếu giá trị, project không bật cờ.
8. Các test hiện có qua: `tests/test_generation_provider_routes.py`, `tests/test_generation_event_processor.py`,
   `tests/test_vision_routes.py`, `tests/test_run_routes.py`; `uv run ruff check .` sạch; `hgraph check --changed` sạch; graph
   `agent-task-draft`, `vision-exploration` cập nhật.

## File liên quan (phạm vi được đụng; ngoài đó cấm)

- Mới: `apps/control-plane/application/agent_task_draft.py` (use case), `tests/test_agent_task_draft.py`,
  `tests/test_agent_task_draft_routes.py`.
- Sửa: `apps/control-plane/api/v1/routes/vision.py` (route + request/response model), có thể
  `apps/control-plane/api/v1/dependencies/vision.py` (dựng use case), `apps/control-plane/infrastructure/persistence/repositories.py`
  (chỉ hàm đọc/ghi sẵn có của `SqlAlchemyGenerationRepository`; thêm hàm nhỏ nếu thật cần).
- Đọc/dùng lại (không sửa): `apps/control-plane/application/generation.py` (`SubmitGeneration`, mẫu ghi request/draft),
  `application/agent_task_trace.py`, `application/agent_task_consistency.py`, `application/agent_task_renderer.py` (phase 08-11),
  `apps/control-plane/domain/authorization.py`, `apps/control-plane/api/v1/routes/runs.py` (mẫu CSRF/idempotency),
  `packages/contracts/src/auto_at/contracts/generation.py`.
- Convention: `AGENTS.md` — `api/` chỉ HTTP, logic ở `application/`; không gọi runner/DB trực tiếp từ route; "agents return
  structured proposals"; test route + đơn vị. Graph phải đọc: `docs/graphs/agent-task-draft.md`, `docs/graphs/vision-exploration.md`,
  `docs/graphs/vision-agent-loop.md`; cập nhật: `agent-task-draft`, `vision-exploration`.
- Tham chiếu: `docs/adr/047-assessment-to-playwright-draft.md` ("Business flow", "Data flow", AC1-AC7).

## Không làm

- Không tạo test case/run, không gọi worker, không gọi model; không outbox cho việc tạo draft.
- Không lưu giá trị ngoài source của draft; không đưa giá trị vào log, audit, provenance, response ngoài source.
- Không sinh draft từ phiên `not_achieved` (Q9); không hợp nhất nhiều phiên (Q3); không trích giá trị từ chữ task (Q5).
- Không sửa `DecideGeneratedDraft` (phase 13), renderer (phase 11), dashboard (phase 15).

## Rủi ro / việc cần user duyệt

- Body có giá trị: framework/middleware hoặc exception handler có thể log request body; tiêu chí 4 buộc kiểm; phát hiện thì sửa ở
  route/handler thuộc phase này, không tắt log toàn hệ thống.
- Mỗi lần yêu cầu cần người nhập giá trị (đã được user chấp nhận); không có đường tự động hoá.
- Việc cần user duyệt: không.

## Kết quả (2026-11-27)

leader + QA PASS vòng 1. Tiêu chí 3 thực hiện theo ADR-047: cùng key khác body trả 200 + draft cũ (không so giá trị); user chấp nhận. Nợ (b), (c), (d): xem `plan.md`, mục "Quyết định đã chốt". Báo cáo: `reports/phase-14/`, QA: `qa/phase-14/`.
