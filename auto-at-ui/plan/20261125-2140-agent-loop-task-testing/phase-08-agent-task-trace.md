---
phase: 08
title: Gói vết task AgentTaskTrace v1 (dựng tuyến tính từ step log)
status: completed
owner: be-developer
qa: required
dependencies: [phase-07]
---

# Phase 08 — Gói vết task `AgentTaskTrace` v1 (ADR-047, phase B1)

## Mục tiêu

Dựng được từ một phiên agent-loop `completed` một **chuỗi bước tuyến tính, bất biến, có hash** làm đầu vào cho bộ dựng
source (phase 11). Hàm dựng là hàm thuần; **không bảng mới, không migration**: gói vết dựng theo yêu cầu từ
`visual_agent_steps` (ADR-047, "Quyết định" mục 1); bảng chỉ thêm nếu phase 07 kết luận cần. Không dùng lại
`build_vision_handoff`/`VisualLocatorHandoff` (contract bị chặn `type`, `contracts/vision.py:494-496`).

Mỗi bước gồm: thứ tự, `operation_id`, loại action (`navigate|click|type|scroll|wait`), locator đã xác minh (descriptor
`verified`), với `type` chỉ `text_chars`, kết quả controller đo. Kèm `task_assessment` (đã redact), `intent_hash`,
`tenant/project/session`, `trace_hash` (sha256 canonical JSON). Từ chối dựng khi bằng chứng thiếu.

## Tiêu chí xong (kiểm chứng được)

1. Contract mới trong file mới (không sửa `vision.py`/`vision_worker.py`, nên không phải sinh lại TS) với `schema_version`
   `v1`, `extra="forbid"`, `trace_hash` kiểm lại được (mẫu `VisualLocatorHandoff.compute_hash`, `contracts/vision.py:500-518`).
2. Hàm dựng thuần (domain) nhận dữ liệu đã đọc (steps, operations, locators, assessment) và trả `AgentTaskTrace`; thứ tự bước
   = `step_index` rồi thứ tự `operation_ids` trong step (test: nhiều action mỗi step, nhiều step, step có action bị skip).
3. Từ chối có mã lý do (`locator_unavailable`, `operation_failed`, `action_outcome_unknown`, `ephemeral_locator`,
   `evidence_unavailable`, `assessment_unavailable`) cho: operation không `completed`, locator không `verified` hoặc
   `dom_path`, thiếu frame/bằng chứng, phiên không `completed`/không có assessment hoặc `exploration_engine != agent_loop`.
   Theo spike phase 07 (`reports/phase-07/runner-r1.md` mục 6, đo trên 106 phiên agent-loop cục bộ), bộ dựng còn phải:
   (a) **bỏ operation `setup`** (navigate/refresh/wait của controller, nằm ngoài mọi step; mã từ chối không áp dụng);
   (b) **xử lý action bị bỏ qua**: action trong `actions` JSONB của step không có operation id (`wait`/`click` còn lại sau khi
   step dừng sớm `state_changed`/`url_change`, `result` rỗng) thì bỏ qua, không phải lỗi; (c) **xử lý `wait completed`** (có
   operation id, có thật trong chuỗi): quyết định bỏ hay giữ và ghi vào hợp đồng gói vết; (d) **từ chối phiên có step
   `worker_result_mismatch`** (op `explore` không thuộc step nào, chuỗi không đầy đủ; mã `evidence_unavailable` hoặc mã mới do
   phase quyết) và phiên có operation `failed|rejected|unknown` (`operation_failed`/`action_outcome_unknown`). Ghép thứ tự bằng
   `step_index` rồi `operation_ids`, đối chiếu với `visual_operations.sequence` (hai nguồn khớp 106/106 phiên). Phép đo chỉ
   trên fixture `task-ui`/DB cục bộ. Test riêng cho từng ca (a)-(d).
4. Gói vết **không chứa giá trị gõ** (chỉ `text_chars`), không chứa `ref` `version:n`, không chứa toạ độ; test quét JSON
   khẳng định vắng mặt chuỗi mẫu đã gõ.
5. Hash ổn định: dựng hai lần từ cùng dữ liệu cho cùng `trace_hash`; đổi thứ tự hoặc một locator thì đổi hash.
6. Hàm đọc repository (đọc dữ liệu một phiên theo scope tenant/project/session, tái dùng `agent_steps(scope)` tại
   `vision_unit_of_work.py:517` và `snapshot`) có test scope: phiên của tenant/project khác không đọc được.
7. `docs/graphs/agent-task-draft.md` được lập bằng `hgraph add agent-task-draft ...` (xem mục graph); `hgraph check --changed`
   sạch; graph `vision-exploration` cập nhật nếu chạm file thuộc nó.
8. `uv run ruff check .` sạch; test mới và các test liên quan qua: `tests/test_vision_handoff.py`,
   `tests/test_vision_agent_task_assessment.py`, `tests/test_vision_results.py` (không hồi quy).

## File liên quan (phạm vi được đụng; ngoài đó cấm)

- Mới: `packages/contracts/src/auto_at/contracts/agent_task_trace.py` (tên tạm), `apps/control-plane/domain/agent_task_trace.py`
  (hàm dựng thuần), `apps/control-plane/application/agent_task_trace.py` (đọc dữ liệu + gọi hàm dựng),
  `tests/test_agent_task_trace.py`, `docs/graphs/agent-task-draft.md` (qua `hgraph add`).
- Đọc (tồn tại, không sửa): `apps/control-plane/application/vision_handoff.py`, `apps/control-plane/domain/vision_task_assessment.py`,
  `apps/control-plane/infrastructure/persistence/vision_unit_of_work.py`, `apps/control-plane/infrastructure/persistence/models.py`
  (`VisualAgentStepModel`, `VisualOperationModel`, `VisualLocatorEvidenceModel`), `packages/contracts/src/auto_at/contracts/vision.py`,
  `apps/control-plane/application/vision_results.py`.
- Có thể sửa tối thiểu: `apps/control-plane/infrastructure/persistence/repositories.py` (chỉ nếu cần thêm hàm đọc
  `agent_steps` cho repository của `application/`; kiểm `agent_steps` có trên `SqlAlchemyVisualTraceRepository` như graph
  `vision-agent-loop` ghi chú).
- Convention: `AGENTS.md` — `domain/` thuần (không import FastAPI/persistence), `application/` dùng port, contract chung ở
  `packages/contracts/`, test tập trung cho mỗi thay đổi hành vi; `docs/code-standards.md`.
- Graph phải đọc trước: `docs/graphs/vision-agent-loop.md`, `docs/graphs/vision-exploration.md`; chạy `hgraph brief`
  cho các file đọc/sửa. **Graph lập mới: `agent-task-draft`** — gồm file mới của phase này và các file hiện chưa thuộc graph
  nào mà thiết kế chạm: `application/generation.py`, `application/vision_handoff.py`, `application/vision_source_renderer.py`,
  `domain/proposals.py`, `application/proposals.py`, `runners/ports.py` (kết quả `hgraph brief` 2026-11-26). Phase 09-14
  thêm file của chúng vào graph này bằng `hgraph add`/`sync`.
- Tham chiếu thiết kế: `docs/adr/047-assessment-to-playwright-draft.md` (mục "Quyết định", "Cái gì đã có, cái gì thiếu").

## Không làm

- Không sửa `build_vision_handoff`, `VisualLocatorHandoff`, contract worker; không sinh lại `vision-contract.generated.ts`.
- Không thêm bảng, cột hay migration (đã kiểm chứng ở phase 07: không cần; bảng nguồn không có TTL và không có mã xoá,
  `reports/phase-07/runner-r1.md` mục 5. Chỉ mở lại nếu sau này thêm TTL cho `visual_agent_steps`/`visual_operations`/
  `visual_locator_evidence` hoặc muốn gói vết sống quá 60 ngày của `intent_retention_until`; khi đó quay lại PM).
- Không đọc/ghi giá trị đã gõ; không gọi model; không tạo draft (phase 14).
- Không đổi `domain/vision_task_assessment.py`.

## Rủi ro / việc cần user duyệt

- Phase 07 đã xong: locator `verified`/`role` có cho mọi `type`/`click` của 3 task fixture (không đổi hình dạng gói vết);
  đọc `reports/phase-07/runner-r1.md` mục 1, 2, 6 trước khi bắt đầu.
- Contract mới là contract chung (`packages/contracts`); đặt tên/`schema_version` đúng convention và không nhân đôi ở control plane.
- Việc cần user duyệt: không có (đã duyệt qua ADR-047); gặp quyết định nghiệp vụ mới thì ESCALATE.
