# Phase 3 — Điều phối và lưu trace đang chạy

Trạng thái: completed. Started: 2026-09-08 21:34 +07:00. Completed: 2026-09-08 22:28 +07:00. Phụ thuộc: Phases 1–2.

Confirmed revision 2026-09-08: user declined cost reservations (“no, we dont need it”). Pricing/accounting additions and missing-price gating are out of scope. Preserve compatible cost metadata, enforce cumulative model steps and existing rate/byte/deadline/traversal limits, and resume the remaining Phase 3 integration. The historical pricing blocker below is resolved.

## Mục tiêu

Mỗi thao tác được commit độc lập, nhìn thấy qua reader khác trong lúc session còn chạy; queue, retry, deadline và failure không làm mất evidence đã lưu.

## Source thêm/sửa

Sửa:
- `apps/control-plane/application/vision_events.py`
- `apps/control-plane/application/runs.py` — PublishOutbox integration giới hạn cho Vision.
- `apps/control-plane/domain/activity.py`
- `apps/control-plane/domain/ports.py`
- `apps/control-plane/infrastructure/workflows/temporal_worker.py`
- `apps/control-plane/infrastructure/persistence/vision_unit_of_work.py`
- `apps/control-plane/infrastructure/persistence/repositories.py`
- `apps/control-plane/infrastructure/artifacts/rustfs.py`

Thêm `apps/control-plane/infrastructure/vision_worker.py` (typed transport),
`apps/control-plane/application/vision_operations.py` (operation state machine orchestration).
Sửa `agents/vision/executor.py`, `agents/prompts/vision.py`, `agents/prompts/README.md` khi bổ sung sanitized state/history context và bỏ chỉ dẫn JSON single-action/batch mâu thuẫn; bump prompt version.

## Luồng và transaction

1. Thay việc truyền một SQLAlchemy session sống suốt publish_forever bằng Vision handler có UoW factory riêng. Outbox đọc/claim ngắn rồi gọi handler ngoài transaction chứa IO; giữ hành vi các handler khác và regression tests.
2. Claim session bằng lease + fencing token trong transaction ngắn. Persist session running trước browser/model IO. Process khác không đồng thời thực hiện cùng session.
3. Mỗi proposal có ID và edge lưu trước enqueue; dùng graph BFS hiện có. Parent state và ancestor operation/locator refs quyết định target checkpoint. Giá trị nhập vẫn memory-only; restart không dựng lại secret từ logs.
4. Gọi worker prepare → kiểm chứng metadata, checksum/bytes/type/IDs → upload before và commit prepared operation + frame + activity.
5. Commit `executing` trước execute. Worker execute → persist after/capture failure + locator evidence + state/edge finalize + activity trong transaction ngắn → ACK cleanup. API reader có thể đọc mỗi commit.
6. Không chỉ upload bytes rồi chờ kết thúc phiên mới commit DB. Dữ liệu cũ đã commit không rollback khi generation hoặc model sau đó lỗi.
7. Worker transport phản hồi thất lạc: query cùng operation ID; identical stored result có thể reconcile. Không có result mà có thể đã click thì finalize unknown và dừng nhánh phụ thuộc. Không tự replay side effect unknown.
8. Mỗi back/restore/replay chuẩn bị và commit qua cùng luồng; ghi purpose cho UI. So checkpoint trước proposal tiếp theo. Limit/error dừng các edge đang queued với outcome, không bỏ dangling proposed.
9. Phân biệt URL change và visual/semantic change. Chỉ no-change khi đủ observation xác nhận; ảnh hash mismatch cho biết bytes khác chứ không kết luận chức năng pass.
10. Giữ max_states cho logical nodes và max_hops cho depth. Giới hạn số primitive operation (đề xuất `max_states * (max_hops + 3)`) tính cả restoration; byte cap từng frame giữ nguyên. Tổng staging hữu hạn nhờ ACK; không cho provider/rate sleep vượt absolute session deadline. Tính budget model cộng dồn theo guard hiện có, không reset guard mỗi node.
11. Re-read policy/consent trước mỗi model call và browser action; lease expiry, cancellation/policy disable, capture/provider failure đều giữ partial trace và finalize reason.
12. Thêm progress stages allowlist: locator.verified/unresolved, operation.prepared/completed/failed/unknown, state.restore_started/restored/failed, handoff status. Activity chỉ chứa IDs/counts/safe enums, không descriptors/text/URLs.
13. Startup reconciliation: lease hết và worker còn result thì recover evidence; worker state mất thì kết thúc unavailable với trace trước đó. Không mô tả at-least-once là exactly-once browser execution.

## Tests và validation

Sửa `tests/test_vision_event_processor.py`, `tests/test_vision_progress.py`, `tests/test_outbox_publishing.py`, `tests/test_transaction_boundary.py`.
Thêm `tests/test_vision_live_persistence.py`: hai DB connections, chặn fake model ở node tiếp theo rồi assert reader thấy before/after; inject crash/upload failure/timeout/redelivery và assert previous commits giữ nguyên.
Test cả capture-before thất bại không click, capture-after thất bại không xóa record, failed restoration chặn sibling, policy disable giữa phiên, guards session tổng cộng.

Tại root:
```text
uv run ruff check apps/control-plane tests/test_vision_event_processor.py tests/test_vision_live_persistence.py
uv run pytest tests/test_vision_event_processor.py tests/test_vision_progress.py tests/test_outbox_publishing.py tests/test_transaction_boundary.py tests/test_vision_live_persistence.py tests/test_vision_replay.py
```
Independent-reader test dùng PostgreSQL test disposable, không chỉ mocks hoặc SQLite một connection.

## Nghiệm thu, rủi ro và non-goals

Reader thấy partial progress khi worker/model còn đang chờ; redelivery không thêm click đã hoàn tất. Không đổi infrastructure provider hoặc refactor workflow của tất cả agents. Nếu concurrency wiring thay đổi, chứng minh publisher vẫn xử lý run/cancel/report events theo regression suite.

## Phase 3 implementation checkpoint — 2026-09-08 21:47 +07:00

Status: **in progress, awaiting a material runtime-policy decision**. Phase 3 is not complete; phases 4–7 have not started.

Implemented and independently validated the operation foundation:
- Typed bounded HTTP transport for v4 open/prepare/execute/read/frame/checkpoint/ACK/close, private identity headers, response identity checks, frame signatures/checksums/byte caps, and safe transport failures.
- Persist operation intent before prepare, persist verified before bytes before execute, commit executing before dispatch, persist final evidence before ACK, and read the same operation after a lost execute response. Unknown operations block subsequent work. Duplicate final delivery retries ACK only. Per-call deadline handling renews the lease during pending async work.
- Conditional S3 create-only operation-frame writes using IfNoneMatch, bounded checksum/type-verified read-back, closed response bodies, and operation-frame deletion.
- Permit a worker rejection after persisted dispatch intent (executing does not prove an action occurred). Retain unresolved locator evidence on prepared/rejected operations while still requiring verified grounding for executing/completed target actions.

Exact implementation paths changed in this session (relative to auto-at-ui/):
- apps/control-plane/application/vision_operations.py (new)
- apps/control-plane/infrastructure/vision_worker.py (new)
- apps/control-plane/infrastructure/artifacts/rustfs.py
- apps/control-plane/domain/ports.py
- apps/control-plane/domain/vision.py
- apps/control-plane/infrastructure/persistence/repositories.py
- tests/test_vision_live_persistence.py (new)
- tests/test_vision_operation_transport.py (new; focused adapter tests split from the planned integration file)

Validation:
- `uv run ruff check .` — passed after final changes.
- `uv run pytest tests/test_vision_live_persistence.py tests/test_vision_operation_transport.py -q` — **19 passed**, including 10 actual disposable-PostgreSQL tests and 9 synthetic HTTP/S3 checks. An independent DB connection sees executing + before before dispatch and completed + both frames while the next fixture model coroutine waits. Covers lost response, browser loss, redelivery, upload/capture failures, policy disable, deadlines, operation caps, mismatched identity and failed ACK.
- `uv run pytest tests/test_vision_live_persistence.py tests/test_vision_operation_transport.py tests/test_vision_operation_repository.py tests/test_vision_handoff_repository.py tests/test_vision_event_processor.py tests/test_vision_progress.py tests/test_outbox_publishing.py tests/test_transaction_boundary.py tests/test_vision_replay.py tests/test_rustfs_artifacts.py tests/test_execution_contract_fixtures.py -q` — **69 passed, 1 setup error** at the existing Windows default pytest temp directory. Reran `uv run pytest tests/test_vision_event_processor.py --basetemp <fresh .pytest-tmp/locator-phase3-UUID> -q` — **3 passed**. The two final unknown-dependency/ACK tests were added afterward and are included in the 19-test rerun above.
- `uv run python packages/contracts/export_vision_worker.py --check` — passed.
- `uv run alembic heads` — one head, f9a0b1c2d3e4. The existing migration regression ran against a disposable database in the focused selection.
- Scoped `git diff --check` — passed.
- Full Python, browser and dashboard suites were not rerun for this partial checkpoint; the full plan's final validation remains outstanding. No provider/model/Drive calls were made by the fixture tests.

Environment: started the existing local Docker Desktop daemon after confirming it was stopped. Docker's existing restart policies also restarted pre-existing local containers. Created only the owned postgres:17-alpine container vision-locator-phase3-test on 127.0.0.1:55437, with UUID-named disposable databases; no application database migration or deployment was performed. The owned test container was stopped and auto-removed after validation; the pre-existing local services were left running.

Decision needed: the current VisionPolicy and session record expose max_cost_usd, but neither Vision executor nor shared AgentStepGuard implements dollar accounting. Add an explicit administrator-configured conservative per-request reservation and fail closed when absent, or leave live calls disabled pending a pricing source? This changes runtime-policy shape and cannot be silently inferred from a stored dollar limit. No cost/model/provider policy has been changed.

Remaining Phase 3 work: publisher separation and session running/final commits; graph/proposal/checkpoint persistence and BFS restoration integration; atomic operation/frame/state/edge/activity commits; closed progress stages; cumulative model guards and approved cost reservation; centralized batch prompt correction/versioning; full startup takeover reconciliation including evidence under an older fence; cancellation/failure finalization of queued edges; processor/independent-reader tests through the actual publisher wiring. The tested operation service is not yet wired into VisionEventProcessor or temporal_worker. No new v4 writer is enabled. Current reconciliation covers same-owner lost responses and fails closed on worker loss; it does not yet implement recovery of an expired owner's completed evidence.

Canonical documentation: this checkpoint is recorded in both README.md and phase-03-orchestration-live-trace.md. Overall progress remains **2/7 completed**; no later dependency is unlocked.

## Phase 3 completion ? 2026-09-08 22:28 +07:00

Status: **completed**. This record supersedes the historical partial checkpoint and its resolved pricing question.

Implemented the v4 publisher outside the outbox transaction, fenced session lifecycle, durable operation/frame/locator/checkpoint/state/edge/activity commits, independent BFS branches and traced checkpoint restoration/replay. Recovery reads an expired owner's final evidence without dispatching another action; lost browser state ends unavailable with preserved evidence. Cancellation, provider failure and failed restoration finalize pending proposals. Cumulative model steps, live consent/policy checks, rate/byte/traversal caps and the absolute deadline remain enforced. The centralized batch prompt is version v3. Cost accounting was omitted as the user requested.

Validation:
- Focused Python regression command selecting test_vision_event_processor, test_vision_progress, test_vision_executor, test_outbox_publishing, test_transaction_boundary, test_vision_live_persistence, test_vision_replay, test_vision_operation_repository, test_vision_handoff_repository and test_vision_operation_transport with a fresh workspace basetemp: **99 passed**.
- After adding the restore-failure activity emission: `uv run pytest tests/test_vision_live_persistence.py -k 'publisher_browser and restore_failed' -q --tb=short`: **1 passed**.
- `uv run ruff check .`: passed.
- Worker `npm.cmd run typecheck`: passed; `npm.cmd test -- src/vision.spec.ts src/vision-locators.spec.ts src/vision-operations.spec.ts --workers=1`: **31 passed**.
- Five real Chromium/PostgreSQL publisher cases cover A/B branching, same-URL modal/replay, failed restoration, cancellation and model failure. A separate DB reader sees committed frames while the next fixture model waits. Two takeover cases cover retained/lost worker evidence. No model/provider/Drive calls were made.

Exact Phase 3 paths (relative to auto-at-ui):
- apps/control-plane/application/vision_operations.py
- apps/control-plane/application/vision_trace_events.py
- apps/control-plane/application/vision_events.py
- apps/control-plane/application/runs.py
- apps/control-plane/domain/ports.py
- apps/control-plane/domain/vision.py
- apps/control-plane/domain/activity.py
- apps/control-plane/infrastructure/vision_worker.py
- apps/control-plane/infrastructure/artifacts/rustfs.py
- apps/control-plane/infrastructure/persistence/vision_unit_of_work.py
- apps/control-plane/infrastructure/persistence/repositories.py
- apps/control-plane/infrastructure/workflows/vision_publisher.py
- apps/control-plane/infrastructure/workflows/temporal_worker.py
- apps/control-plane/agents/vision/executor.py
- apps/control-plane/agents/prompts/vision.py
- apps/control-plane/agents/prompts/README.md
- workers/playwright/src/vision-checkpoints.ts
- workers/playwright/src/vision-locators.ts
- workers/playwright/src/vision-operations.ts
- workers/playwright/src/fixtures/vision-integration-server.ts
- tests/test_vision_live_persistence.py
- tests/test_vision_operation_transport.py
- tests/test_vision_executor.py
- tests/test_vision_progress.py
- tests/test_outbox_publishing.py

Deviations: separate v4 processor/publisher modules preserve legacy behavior and transaction ownership. The operation cap matches Phase 2's bounded restoration budget, 1 + max_states * (2 * max_hops + 3). Real HTTP testing exposed tsx-injected function-name helpers inside page.evaluate; object methods fix the serialization issue. Replay checkpoint references are scoped to the destination checkpoint, which may differ from the original proposal's source state. Navigation starts a new branch ancestry. No v4 submission writer is enabled yet; rollout remains Phase 7.

The owned disposable PostgreSQL container is running for subsequent plan validation. UUID databases are removed by fixtures; application databases were not migrated. Full Python/dashboard/Compose validation remains Phase 7. Phase 4 is unlocked.
