---
phase: 15b
title: Bước `type` của draft — API trả độ dài mong đợi, form hiện độ dài
status: completed
owner: both
qa: required
dependencies: [phase-15]
---

# Phase 15b — Độ dài mong đợi của bước `type` (ADR-047 Q1, nợ của phase 15)

## Mục tiêu

Phase 15 mục tiêu và ADR-047 (`:153-154`) đòi form liệt kê "tên locator và độ dài mong đợi" của từng bước `type`, nhưng không có
API nào trả `text_chars`: `GET /explorations/{id}/trace` là replay chung (không có trường này), `text_chars` chỉ nằm trong gói vết
nội bộ (`domain/agent_task_trace.py:131`, `contracts/agent_task_trace.py:139`). Hậu quả hiện tại: người nhập chỉ biết sai sau
`input_value_mismatch`. Phase này thêm đúng một route GET additive và để form hiện độ dài. Đề xuất gốc: `reports/phase-15/pm-r1.md`
(mục b, c); user duyệt 2026-11-27.

Route mới (tên cuối do be chốt trong phạm vi này, mặc định): `GET /api/v1/vision/explorations/{session_id}/test-draft/inputs`,
cạnh `POST .../test-draft` (`api/v1/routes/vision.py:930`). Response (model đóng `extra="forbid"`, đặt trong `vision.py` như
`AgentTaskDraftResponse` ở `:905`; `packages/contracts/.../generation.py` hiện không chứa kiểu draft agent-task nên không đổi):
`{ owned_test_target: bool, has_type_steps: bool, type_steps: [{ step_index, locator_name, text_chars }] }` (`has_type_steps` thêm
theo PM r2 2026-11-27), `type_steps` theo đúng thứ tự `type` mà
`render_agent_task_source` ghép giá trị (`application/agent_task_renderer.py:112-125`).

## Tiêu chí xong (kiểm chứng được)

1. **Một nguồn dữ liệu.** `type_steps` lấy từ cùng `AgentTaskTrace` mà `CreateAgentTaskDraft` dùng (`read_agent_task_trace`,
   `application/agent_task_draft.py:224-234`), lọc `step.kind == "type"` y như `_check_values` (`agent_task_renderer.py:113`). Test:
   với cùng một trace, số bước và thứ tự của GET bằng số giá trị mà POST yêu cầu; một mảng giá trị dài đúng `text_chars` từ GET
   thì POST không trả `input_value_mismatch`/`input_value_missing`.
2. **Quyền và tenant.** Cùng kiểm với POST: `actor_for_tenant` + `require(actor, Permission.SUBMIT_GENERATION)`
   (`agent_task_draft.py:125-128`); thiếu quyền, khác tenant, không có phiên đều trả 404 như nhau (không phân biệt). Test ba ca.
3. **Header.** Response có `Cache-Control: private, no-store` (như `vision.py:793`).
4. **Chỉ khi cờ bật.** Project chưa bật `vision_owned_test_target` (`agent_task_draft.py:141`) và trace có bước `type` → trả
   `owned_test_target: false`, `has_type_steps: true`, `type_steps: []` (không lộ độ dài), khớp hành vi POST
   `input_value_not_allowed`. Cờ tắt và không có bước `type` → `owned_test_target: false`, `has_type_steps: false`, `type_steps: []`
   (POST vẫn cho tạo draft `values: []`). Cờ bật → `has_type_steps` = có ít nhất một bước `type`. `has_type_steps` tính bằng
   `has_test_values(trace)` (cùng hàm POST dùng ở `agent_task_draft.py:173`), không lộ gì ngoài sự có/không của bước `type`
   (đã thấy được trong replay `/trace` và qua mã lỗi POST). Test cả ba ca. (PM r2 2026-11-27)
5. **Điều kiện như POST.** Phiên chưa completed / không `achieved` / bằng chứng hết hạn: trả cùng mã lỗi (422/409 với `detail.code`) mà
   POST dùng, qua cùng `_check_assessment` và `_read_trace`; không tạo bản sao luật. Không đòi consistency (đó là việc của POST và của
   `/consistency`).
6. **Không lộ gì ngoài độ dài.** Response không chứa giá trị gõ, ref `version:n`, toạ độ, `operation_id`, hay `locator_id`;
   `locator_name` là tên đã redact theo đường mà renderer dùng cho locator. Test quét (nối vào mẫu quét của phase 08,
   `tests/test_qa_p08_agent_task_trace.py`) fail nếu xuất hiện trường khác.
7. **Log/audit.** Route không log body, không ghi giá trị hay độ dài vào log và `audit_events`; không thêm gì vào `/trace`. Test
   khẳng định `/trace` không đổi shape.
8. **FE.** `generation-types.ts`/`generation-api.ts` có kiểu và hàm gọi mới; `openForm` lấy bước từ route mới thay cho `typeSteps()` dựng từ
   `/trace` (một nguồn, bỏ suy diễn ở client; xoá hàm/ test `typeSteps` nếu không còn dùng). Mỗi ô nhập hiện "Needs exactly N characters"
   (không placeholder giả, không điền sẵn); form chỉ bị chặn (thông báo, không mở) khi `owned_test_target` false VÀ `has_type_steps` true; cờ tắt mà `has_type_steps` false
   thì form mở với 0 ô nhập và gửi `values: []` như phase 15 (PM r2 2026-11-27); test model + ca trong
   `generation-api.test.ts`. Giá trị gõ vẫn không vào URL/storage/console (tiêu chí 2 của phase 15 vẫn đúng).
9. Python: `uv run ruff check .` và các test `tests/test_agent_task_draft*.py`, `test_qa_phase14_agent_task_draft.py`,
   `test_qa_p08_agent_task_trace.py` qua. Dashboard: `npm run typecheck`, `npm run lint`, `npm test` sạch; spec
   `workers/playwright/src/vision-dashboard.spec.ts` (mock route mới ở `agentDraftApi`, ca "form hiện độ dài") qua;
   `uv run pytest tests/test_dashboard_route_contracts.py` qua.
10. `hgraph check --changed` sạch; graph `agent-task-draft`, `vision-exploration` (route mới), `vision-dashboard` cập nhật.

## Owner và cách chia (tuần tự trong cùng phase)

`owner: both`, **be làm xong và nộp trước, fe làm sau** (fe phụ thuộc hợp đồng route). Lý do không để be làm cả: phần FE đụng TypeScript,
test dashboard và spec Playwright, ngoài toolchain Python của be; nhưng phần FE ngắn nên không tách thành phase riêng.
Không file nào hai bên cùng sửa.

- **be-developer** (làm trước): 
  - sửa `apps/control-plane/api/v1/routes/vision.py` (route + model response; không đụng route khác),
  - sửa `apps/control-plane/application/agent_task_draft.py` (thêm một use case đọc, ví dụ `ReadAgentTaskDraftInputs`, dùng lại
    `_check_assessment`, `_read_trace`; không đổi `CreateAgentTaskDraft.execute`),
  - sửa `apps/control-plane/application/agent_task_renderer.py` chỉ để xuất hàm thuần liệt kê bước `type` dùng chung với
    `_check_values` (không đổi hành vi),
  - test: mới `tests/test_agent_task_draft_inputs.py`; sửa `tests/test_agent_task_draft_routes.py` (ca route nếu cần),
    `tests/test_qa_p08_agent_task_trace.py` (chỉ thêm ca quét `/trace` không đổi),
  - graph `docs/graphs/agent-task-draft.md`, `docs/graphs/vision-exploration.md`.
  - Bàn giao cho fe: tên route, tên trường, ví dụ JSON thật trong báo cáo be.
- **fe-developer** (làm sau khi be PASS): 
  - sửa `apps/dashboard/app/generation-types.ts`, `apps/dashboard/app/generation-api.ts`,
  - sửa `apps/dashboard/app/components/agent-task-draft-model.ts` (kiểu `TypeStep` thêm `textChars`; hàm map response; bỏ `typeSteps` nếu
    không dùng) và `agent-task-draft-model.test.ts`,
  - sửa `apps/dashboard/app/components/agent-task-draft-panel.tsx` (`openForm` + nhãn độ dài),
  - test: `apps/dashboard/app/generation-api.test.ts`; `workers/playwright/src/vision-dashboard.spec.ts` (chỉ `agentDraftApi` và ca mới),
  - graph `docs/graphs/vision-dashboard.md`.

Ngoài các file trên: cấm. Đặc biệt không đụng `packages/contracts/**`, `vision_agent_loop.py`, `domain/agent_task_trace.py`, worker.

## Convention và graph

- Convention: `AGENTS.md` (routes chỉ HTTP, use case ở `application/`, thay đổi hành vi kèm test, dashboard là client mỏng không giữ
  luật), `docs/code-standards.md`, `docs/api-conventions.md` (mục đặt tên route/lỗi, nếu có; be đọc trước khi đặt tên cuối).
- Graph đọc trước: `docs/graphs/agent-task-draft.md`, `docs/graphs/vision-exploration.md` (be); `docs/graphs/vision-dashboard.md` (fe).
  Cập nhật sau: `agent-task-draft`, `vision-exploration`, `vision-dashboard` (`hgraph add`/`sync`). Không lập graph mới.
- Tham chiếu: `docs/adr/047-assessment-to-playwright-draft.md` (Q1, dòng 153-154, 298, 356), `reports/phase-15/pm-r1.md`.

## Không làm

- Không trả giá trị gõ hay thêm trường vào `/trace`; không đổi `PlanningProvenance`/contract chung; không đổi quy tắc của POST (kể cả
  mã lỗi); không thêm đường chạy test; không để FE suy ra độ dài từ chữ task hay đoán.
- Không sửa chính sách redaction (Q4, Q5), không sửa luật consistency.
- Không đụng việc của phase 16 (e2e); phase 16 dùng route này nhưng không sửa nó.

## Rủi ro / việc cần user duyệt

- Độ dài của mật khẩu thật mà agent đã gõ có thể lộ cho người xem phiên: giảm bằng cờ `vision_owned_test_target` (tiêu chí 4), quyền
  `SUBMIT_GENERATION` + tenant, `no-store`, và ADR Q1 chấp nhận tài khoản dùng một lần. Độ dài đã lộ gián tiếp qua oracle
  `input_value_mismatch`, nên rủi ro thêm là thấp.
- Hai nơi dựng danh sách bước `type` sẽ lệch nhau nếu be không dùng chung hàm với `_check_values`: tiêu chí 1 chặn việc này.
- Đổi nguồn dữ liệu của form (từ `/trace` sang route mới) làm spec Playwright và mock của phase 15 phải cập nhật; fe chịu.
- Việc cần user duyệt: không. Tên route mặc định có thể đổi nếu `docs/api-conventions.md` đòi khác; be ghi tên cuối vào báo cáo.
