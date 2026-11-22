---
phase: 4
title: "Agent loop processor + safety"
status: completed
priority: P1
owner: be-developer
qa: required
dependencies: [1, 2, 3]
---
## Mục tiêu
Processor vòng lặp khép kín cho session `agent_loop`: observe → render snapshot có ref `version:n` (cắt + marker) → gọi model với
memory + K bước → kiểm an toàn bằng code → chạy action qua `ExecuteVisualOperation` → dừng batch khi trang đổi → ghi step log → lặp
tới done/stop/hết budget. Dispatch theo `exploration_engine`.

## Database Impact
Ghi `visual_agent_steps` (bảng từ phase 1) và các bảng v4 sẵn có (`visual_exploration_states`, `visual_action_proposals`,
`visual_trajectory_edges`, `visual_operations`, `visual_operation_frames`, `visual_locator_evidence`). Không đổi schema.

## File liên quan
Tạo:
- `apps/control-plane/application/vision_agent_loop.py` (`VisionAgentLoopProcessor` + hàm render snapshot + hàm `run_operation`)
- `apps/control-plane/domain/vision_agent_safety.py` (`check_action(action, element, page_origin, allowed_origins) -> Decision`)
- `tests/test_vision_agent_loop.py`, `tests/test_vision_agent_safety.py`
Sửa:
- `apps/control-plane/infrastructure/workflows/vision_publisher.py` (~:20-47: chọn processor theo `record.exploration_engine`; giữ `handler`)
- `apps/control-plane/application/vision_results.py` (trace payload: mỗi operation có thêm `agent_step` tuỳ chọn = {step_index,
  evaluation_previous_goal, memory, next_goal} của bước chứa nó, và danh sách action bị chặn/bỏ qua của bước; đọc qua
  `agent_steps(session_id)` của unit of work (phase 1); session planner không có field này)
- (user duyệt sau leader-r1) `apps/control-plane/infrastructure/persistence/repositories.py` (thêm `agent_steps(scope)` vào
  `SqlAlchemyVisualTraceRepository`) và `apps/control-plane/infrastructure/persistence/vision_unit_of_work.py` (gọi lại repo, bỏ query trùng);
  test với repo SQL thật đặt trong `tests/test_vision_agent_loop.py`.
- `apps/control-plane/api/v1/routes/vision.py` KHÔNG sửa ở phase này (phase 1 sở hữu); nếu schema response trace là model Pydantic
  ở route thì field `agent_step` optional được thêm trong phase 1 — kiểm khi bắt đầu, báo leader nếu thiếu.

## Luồng dữ liệu của phase này
1. Lease (`uow` như v4) → dựng `VisualWorkerOpen` ngay trong `vision_agent_loop.py` (không đụng `vision_trace_events.py:218`):
   `agent_mode=True`, `blocked_action_terms` = danh sách của `domain/vision_agent_safety.py`, `allowed_origins` của project,
   `max_states`/`max_hops` chọn sao cho budget operation của worker `1 + max_states*(2*max_hops+3)` ≥ 401
   (= 1 + 20 lần gọi × 10 action × 2) — công thức kiểm lại ở `infrastructure/vision_worker.py:118-135` không đổi
   → op `navigate` purpose `setup` + checkpoint.
2. Vòng: `worker.observe_dom(snapshot_id=uuid4(), expected_state_fingerprint)` → `version += 1`, map `{(version,n): (snapshot_id, element_id)}`
   → render ≤ `settings.vision_agent_snapshot_chars` + `[refs a-b trimmed]` khi cắt + dòng "N control ngoài snapshot" từ `skipped_count`.
   Origin trang hiện tại lấy từ `page_url` của checkpoint/state sau op gần nhất.
3. Trần gọi = `min(policy.max_steps, 20)`; `CodexCallBudget.reserve()` cho MỌI lần gọi (kể cả retry sai schema và stage image)
   → `CodexModelBatch(agent-loop-v1, agent_context)` → `AgentLoopOutput`. `need_screenshot` → một lần gọi stage image nếu consent
   cho phép, không có consent ⇒ báo model "screenshot không khả dụng" ở bước sau; `stop`/done → finish.
4. Với từng action: ref sai regex ⇒ `invalid_ref`; version ≠ hiện tại hoặc không có trong map ⇒ `stale_ref` (không gọi worker);
   `check_action` ⇒ `origin_blocked`/`sensitive_action_blocked` (không gọi worker); hợp lệ ⇒ state/proposal/edge qua `uow.proposals`
   → hàm `run_operation` dựng `VisualWorkerPrepare` (binding `dom_snapshot_id`/`dom_element_id`, purpose `explore`) →
   `ExecuteVisualOperation.execute`. (Renderer/run_operation là hàm trong cùng file; chỉ tách lớp nếu file > ~400 dòng.)
5. Dừng batch khi `url_change`, `state_fingerprint` đổi (ngoài re-baseline form), popup, download hoặc op không `completed`.
6. `uow.record_agent_step(...)` (fenced, redact) + activity `agent.step`. Lịch sử cho bước sau = memory mới + 5 bước gần nhất
   (mỗi bước: evaluation, next_goal, tóm tắt action + kết quả/mã lỗi).
7. Kết thúc: `uow.finish(lease, reason)` với `agent_done`, `agent_stopped`, `agent_step_limit` (hết 20 lần gọi), `session_timeout`,
   hoặc mã lỗi worker. Không bao giờ phát `restore`/`replay`.

## Convention áp dụng
`AGENTS.md`: `domain/` thuần (không import FastAPI/persistence/LangChain); `application/` điều phối qua port; agent không đổi verdict.
Lặp ~60 dòng của `primitive()` v4 là nợ kỹ thuật có chủ đích (không sửa `vision_trace_events.py` — AC7); ghi vào ADR-038 ở phase 6.

## Graph liên quan
Thêm `vision_agent_loop.py`, `vision_agent_safety.py`, `vision_publisher.py` vào graph `vision-agent-loop` (`hgraph check --changed`).

## Các bước thực hiện
1. `vision_agent_safety.py` + test thuần (allowlist qua `ProjectExecutionPolicy.allows`/`origin_for_url`; submit/reset từ `CodexDomElement.input_type`;
   từ khoá trên `name` — cùng danh sách với worker phase 2, KHÔNG gồm "đăng ký", "nạp thẻ"; kind ngoài 7 kind ⇒ chặn).
2. Hàm render snapshot (ref ngắn, cắt, marker, `skipped_count`) + test.
3. Hàm `run_operation` dựng prepare/operation như `vision_trace_events.py:165-176, 288-292, 344-350`.
4. `VisionAgentLoopProcessor` vòng lặp + dừng batch + step log + finish.
5. Dispatch ở `vision_publisher.py`.
6. Test với fake worker + fake exchange (mẫu `test_vision_event_processor.py`, fixtures `tests/vision_trace_fixtures.py`).

## Unit test phải viết
`test_vision_agent_loop.py` (fake worker + fake exchange; phần ghi DB/fence dùng DB-gated như phase 1):
- happy path 3 bước tới `agent_done`; step log 3 dòng đủ field, action bị chặn có `skipped_reason` và không có trong `operation_ids` (AC1);
  prompt mỗi bước chỉ chứa snapshot mới nhất.
- ref sai regex ⇒ `invalid_ref`; ref version cũ, version tương lai, index không có trong map ⇒ `stale_ref`; số call prepare/execute = 0 (AC2).
- action trên page observe-only (origin từ checkpoint `page_url`, gồm trang sau redirect), submit/reset, từ khoá ⇒ chặn, không gọi worker,
  lý do trong step log; `close_popup`/`back` trên page observe-only được chạy (AC3).
- tham số hoá 5 điều kiện dừng batch {url_change, fingerprint đổi, popup mới, download, status ≠ completed}: action sau có 0 call worker,
  bước kế gọi `observe_dom` đúng 1 lần; batch `type A`, `type B` chạy cả hai (AC4).
- renderer: 100 element tên 120 ký tự + `skipped_count=200` ⇒ phần snapshot ≤ `vision_agent_snapshot_chars`, marker `[refs a-b trimmed]`
  đúng ref bị cắt, có dòng "200 control ngoài snapshot"; sau 3 bước và sau 15 bước độ dài phần lịch sử ≤ cùng một hằng số (AC5).
- ngân sách: `policy.max_steps=20` ⇒ lần gọi 20 chạy, lần 21 không, kết thúc `agent_step_limit`; retry sai schema và `need_screenshot`
  đều tính vào trần; `max_requests_per_minute` được tôn trọng (fake clock); `need_screenshot` không consent ⇒ không gọi stage image;
  `stop` ngay bước 1 ⇒ `agent_stopped`; model trả toàn action bị chặn liên tục ⇒ kết thúc `agent_step_limit`, không treo; deadline ⇒ `session_timeout`.
- worker open: `max_states`/`max_hops` cho budget ≥ 401; 20 bước × 10 action không gặp `operation_budget_exhausted` với fake worker áp công thức.
- lease mất giữa vòng ⇒ dừng an toàn, không ghi step; xử lý lại event sau resume không ghi trùng `step_index`.
- step log: task/memory chứa chuỗi secret ⇒ được redact.
- không operation nào có purpose `restore`/`replay`; mọi click có binding + purpose `explore`; `benchmark/vision/accuracy/evidence.py`
  `export_operation` chấp nhận mọi op (AC6 phần offline).
- trace: session agent loop có `agent_step`; session planner không có (AC7).
- engine `planner` vẫn đi `VisionTraceEventProcessor` (AC7).
`test_vision_agent_safety.py`: bảng quyết định cho từng rule; từ khoá hoa/thường, có dấu/không dấu, NFD; "ĐĂNG KÝ"/"NẠP THẺ" KHÔNG bị chặn;
chạy `check_action` trên toàn bộ `label` của `benchmark/vision/accuracy/oracle-mongchiton-1280-v1.json` (positive) ⇒ 0 bị chặn.

## Tiêu chí xong (checklist)
- [ ] Test mới xanh.
- [ ] Hồi quy xanh: `test_vision_event_processor.py`, `test_vision_live_persistence.py`, `test_vision_locator_pipeline.py`,
      `test_vision_operation_failure_stage.py`, `test_vision_page_batch.py`, `test_vision_provider_integration.py`, `test_vision_target_preflight.py`,
      `test_vision_viewport_scan.py`, `test_vision_progress.py`, `test_vision_results.py`, `test_vision_conclusion.py`, `test_vision_accuracy_loop.py`.
- [ ] `uv run ruff check .` sạch.

## Ghi chú từ phase 2 (leader-r1, QA-r1)
- Worker khớp `blocked_action_terms` kiểu "chứa" sau NFC + chữ thường, **không bỏ dấu**: danh sách từ khoá ở domain Python phải có cả
  dạng có dấu và không dấu (VD "nạp thẻ" và "nap the"), và có test cho cả hai dạng.
- Worker agent mode chặn `type` có `\r`/`\n` (`sensitive_action_blocked`): control-plane không sinh/gửi text có xuống dòng.
- Worker chỉ cho phép đúng ngân sách operation theo công thức `1 + max_states*(2*max_hops+3)`: phase 4 chọn `max_states`/`max_hops` để budget ≥ 401 như plan.
  Nguồn: `reports/phase-02/leader-r1.md`, `reports/phase-02/qa-r1.md`.

## Rủi ro & tín hiệu nhận biết hỏng
- FK proposal/state sai ⇒ `repositories.py:1008-1016` từ chối operation (lỗi integrity trong test).
- Không truyền binding ⇒ locator không `verified` ⇒ benchmark không chấm được (test evidence đỏ).
- Batch không dừng khi popup ⇒ op kế `stale_dom_snapshot` hàng loạt.
- Lease mất giữa vòng ⇒ phải dừng an toàn như v4 (test fence).
