---
phase: 13
title: Ranh giới duyệt, guard đường tới model, và sửa ADR-002 (ngoại lệ có phạm vi)
status: completed
owner: be-developer
qa: required
dependencies: [phase-11, phase-12]
---

# Phase 13 — Ranh giới duyệt và ngoại lệ ADR-002 (ADR-047, phase B6; Q1, Q7, Q10)

## Mục tiêu

Trước khi bất kỳ bản nháp có giá trị test nào được tạo (phase 14), đặt đủ rào chắn:

1. **Người duyệt (Q7):** với draft có `provenance.agent_trace_source`, duyệt đòi `Permission.DECIDE_PROPOSAL` (vai `reviewer`,
   `project_admin`, `tenant_admin`; người thật, `domain/authorization.py:44,50,61,110-114`) thay cho `DECIDE_GENERATION`
   (`routes/generation.py:350`), và `decided_by != provenance.requested_by`. Loại draft khác giữ nguyên. Không đổi ma trận vai.
2. **Xác nhận tài khoản dùng một lần (Q1):** trường mới `acknowledge_disposable_credentials` (additive) trong `DecisionRequest`
   (`routes/generation.py:88-90`); draft `contains_test_values` thiếu xác nhận khi duyệt thì từ chối; kiểm lại cờ
   `vision_owned_test_target` của project lúc duyệt.
3. **Guard `credentials_in_source` (Q10):** chặn hai đường nhúng nguyên source vào request sinh rồi tới model: sửa preflight tự do
   (`application/generation.py:289-312`, hiện chỉ chặn với `vision_handoff_id` ở `:290-294`) và
   `POST /runs/{id}/revised-draft` (`routes/runs.py:306-345`, nhúng "Approved source" ở `:340`) cho draft/test case có
   `contains_test_values`.
4. **Excerpt evidence (nơi 10, ADR-047) — BẮT BUỘC:** phase 07 đã xác nhận giá trị gõ nằm trong `playwright-output` khi test
   fail (dòng `fill` trong khung mã; `reports/phase-07/runner-r1.md` mục 3). Loại excerpt `playwright-output` của run
   `contains_test_values` khỏi evidence gửi model (`agents/shared/evidence.py:24,70-90`, `REPORT_TEXTUAL_KINDS`), và xét thêm
   `worker-result` (chưa đo ở phase 07: đo bằng test hoặc loại luôn, ghi quyết định). `redact_value` theo mẫu không bắt được vì
   không biết giá trị literal.
5. **Sửa ADR-002:** thêm đoạn ngoại lệ có phạm vi vào `docs/adr/002-generated-test-authority.md` (xem dưới).

## Tiêu chí xong (kiểm chứng được)

1. Test dùng use case và route trực tiếp: người duyệt trùng người yêu cầu → từ chối; thiếu `DECIDE_PROPOSAL` (contributor) →
   từ chối; `reviewer` khác người → được duyệt; `service` principal → từ chối; sau từ chối `test_cases` và `test_runs`
   không đổi (đếm hàng).
2. Draft `contains_test_values` duyệt thiếu `acknowledge_disposable_credentials=true` → từ chối; có xác nhận nhưng project đã tắt
   cờ → từ chối; draft loại cũ duyệt như trước (test hồi quy `tests/test_generation_provider_routes.py`,
   `tests/test_generation_preflight.py`).
3. Guard 3: với draft/test case `contains_test_values` thì preflight lỗi không tạo `generation_requests` sửa tự do (lỗi
   `credentials_in_source`, theo mẫu `generation.py:290-294`), và `revised-draft` trả 409 `credentials_in_source`; không có chuỗi
   source trong request nào được lưu. Loại draft khác giữ hành vi cũ.
4. Test khẳng định giá trị mẫu **không** vào `generation_requests` qua bất kỳ đường nào của phase này.
5. Test `agents/shared/evidence.py`: evidence gửi model của run `contains_test_values` không còn excerpt `playwright-output` (test dùng
   cấu hình test fail với `fill` gần dòng lỗi, đúng cách phase 07 đo), và quyết định về `worker-result` có test; run không có giá trị test
   giữ hành vi cũ (test hồi quy).
6. Phần sửa ADR-002 xong: **chữ cụ thể do user duyệt trong phase này** (PM soạn bản nháp, phiên chính đưa user duyệt, chỉ khi user
   duyệt mới ghi vào file; không tự commit/sửa khi chưa duyệt). Nội dung phải: (a) nêu phạm vi: chỉ project có
   `vision_owned_test_target`, chỉ draft dựng từ vết task của phiên agent (`provenance.agent_trace_source`); (b) liệt kê đủ nơi
   giá trị tài khoản dùng một lần có thể nằm literal theo bảng "Giá trị test (Q1)" của ADR-047: `generated_test_drafts`,
   `test_cases.specification`, `test_runs.request`, `outbox_events.payload`, input/history workflow Temporal, phản hồi API/dashboard,
   workspace tạm của worker, **artifact của run (trace, snapshot DOM kể cả ô mật khẩu, screenshot, video; Q11: user đã chấp nhận,
   spike phase 07 xác nhận có giá trị kể cả khi test pass, giữ `retain_days`=30)**; ghi chú: thời gian lưu thực tế của artifact
   không được bảo đảm 30 ngày vì job xoá artifact hết hạn đang lỗi cả lô trên stack cục bộ (ngoài phạm vi plan, ghi nợ, user xử lý
   bằng `/h-fix`; xem ADR-047 mục "Rủi ro"); (c) giữ cấm: raw request (`generation_requests`), audit, log, `provenance`; (d) nêu
   đường tới model bị chặn (sửa preflight, `revised-draft`, excerpt `playwright-output` và `worker-result` theo mục 4); (e) giữ nguyên các câu còn lại của ADR-002
   (planner không có quyền, allowlist origin, import chỉ `@playwright/test`, duyệt bất biến, workspace tạm). Hai câu bị sửa:
   `docs/adr/002-generated-test-authority.md:16-20` ("Raw requests and credentials are not persisted or sent to a model. Login and
   supplied credentials are outside v1 scope.").
7. `uv run ruff check .` sạch; test mới + test hiện có của generation/proposal/run qua (`tests/test_proposal_use_cases.py`,
   `tests/test_run_routes.py`, `tests/test_reporting_executor.py`, `tests/test_agent_boundaries.py`); `hgraph check --changed` sạch;
   graph `agent-task-draft`, `vision-exploration` cập nhật.

## File liên quan (phạm vi được đụng; ngoài đó cấm)

- Sửa: `apps/control-plane/application/generation.py` (`DecideGeneratedDraft`: quy tắc người duyệt, xác nhận, guard preflight),
  `apps/control-plane/api/v1/routes/generation.py` (`DecisionRequest`, nhánh quyền ở `decide`),
  `apps/control-plane/api/v1/routes/runs.py` (guard `revised-draft`), `apps/control-plane/agents/shared/evidence.py` (chỉ nếu
  mục 4 cần), `docs/adr/002-generated-test-authority.md` (chỉ đoạn ngoại lệ, sau khi user duyệt chữ).
- Mới: `tests/test_agent_task_review_guards.py`.
- Sửa (user duyệt 2026-11-27, sau ESCALATE r1 — đường rò `review_context`): `apps/control-plane/application/reporting_events.py`, `apps/control-plane/infrastructure/workflows/temporal_worker.py`, `tests/test_reporting_event_processor.py` — chỉ để truyền cờ `contains_test_values` của test case vào evidence. Chữ ADR-002 đã duyệt: `reports/phase-13/user-answers-r1.md`.
- Đọc: `apps/control-plane/domain/authorization.py`, `apps/control-plane/infrastructure/persistence/models.py`,
  `docs/adr/004-proposed-identity-rbac.md`, `docs/adr/047-assessment-to-playwright-draft.md`, `reports/phase-07/` (kết quả spike).
- Có thể thêm khoá vào `test_cases.specification` khi duyệt (`application/generation.py:320-324`, ví dụ `contains_test_values`) để
  guard `revised-draft` và evidence nhận biết; không đổi schema bảng.
- Convention: `AGENTS.md` — "agents return structured proposals, never change suites or verdicts without an explicit approval
  flow", `domain/` thuần, `api/` chỉ HTTP; ADR-002 (authority), ADR-004 (RBAC). Graph phải đọc: `docs/graphs/agent-task-draft.md`,
  `docs/graphs/vision-exploration.md`; cập nhật: cả hai.

## Không làm

- Không đổi ma trận vai hay thêm `Permission` mới; không đổi cách duyệt của các loại draft khác.
- Không che source ở payload outbox/`test_runs.request`/workflow (Q10 = A); không thêm bộ dữ liệu test hay kênh tiêm giá trị.
- Không đổi cấu hình trace/video/screenshot của runner, không thêm kiểm quyền xem artifact riêng (Q11 = A); không sửa job
  xoá artifact (`application/artifact_retention.py`, việc riêng của user, `/h-fix`).
- Không sửa ADR khác ngoài ADR-002 (đoạn ngoại lệ); không sửa ADR-047/ADR-004; không tạo đường nào khác tới test case/run.
- Không tạo draft (phase 14).

## Rủi ro / việc cần user duyệt

- **Cần user duyệt chữ sửa ADR-002 trong phase này** (tiêu chí 6); phase không đóng được khi user chưa duyệt. Phạm vi chấp thuận
  đã gồm artifact của run (Q11) nên chữ về nơi 9 không phải câu hỏi mới, chỉ cần duyệt câu chữ.
- Người duyệt khác người yêu cầu: tenant chỉ có một actor không hoàn tất được vòng (đã được user chấp nhận); local dùng hai header
  `X-Actor-Id`.
- Guard làm draft loại này không có đường "sửa tự do bằng model": muốn sửa thì sinh draft mới từ phiên (đã nêu ở ADR-047).
- Đường duy nhất tới test case/run phải vẫn là `DecideGeneratedDraft` với `approved=true` (ADR-002); test tiêu chí 1 ghim điều này.
