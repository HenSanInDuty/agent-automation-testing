# Phase 03 — Wiring legacy/v4, snapshot và failure trace

## Execution status

Completed: 2026-10-17 18:28 +07:00 (started 18:07 +07:00).
Shared legacy/v4 dispatch, fresh policy checks, confirmation/idempotency,
centralized prompt provenance and safe completion traces are implemented.
Final combined validation: **178 passed, no skips**; provider/Drive/diagnostic
and policy persistence regressions: **68 passed, no skips**. Repository-wide
Ruff and diff checks passed. See the canonical README for exact changed paths,
commands, resolved failures, environment cleanup and the phase 04 handoff.

Real local browsers exercised both backends through mocked Gemini HTTP, including
a non-button link click and policy/provider failure stops with retained evidence.
PostgreSQL was isolated on port 55437; the owned fixture was removed afterward.
No provider calls, tenant enablement, prompt change or worker/execution contract
change occurred. Dashboard work and final rollout evaluation remain in phases 04–05.

Implementation additions within this phase's scope:
- `apps/control-plane/domain/vision.py` and `domain/activity.py` provide a closed
  model-failure allowlist and safe completion-progress metadata.
- `SqlAlchemyVisionPolicyReader` in the planned unit-of-work module supplies fresh,
  detached policy reads to legacy composition without changing its write transaction.
- `tests/test_vision_provider_integration.py` exercises both legacy and v4 with a
  real local browser, isolated PostgreSQL and Gemini HTTP `MockTransport`.
  Existing live-persistence, results, pipeline and contract tests are reused unchanged.
- Explicit correlation IDs are part of retry identity. Clients omitting that
  optional field retain the original server-generated ID; the HTTP schema is unchanged.
- Submission now invokes the existing CSRF dependency, as policy writes already do.

## Mục tiêu / prerequisites

Sau phases 01–02, cho provider mới đi qua luồng thực thi thật mà giữ durable evidence, tenant isolation và deterministic worker. Failure phải giải thích được; switch/revoke policy không làm gửi ảnh sai nơi.

## Files

Sửa:
- `apps/control-plane/infrastructure/workflows/vision_publisher.py`.
- `apps/control-plane/infrastructure/workflows/temporal_worker.py`.
- `apps/control-plane/application/vision_events.py`.
- `apps/control-plane/application/vision_trace_events.py`.
- `apps/control-plane/application/vision.py`.
- `apps/control-plane/infrastructure/persistence/vision_unit_of_work.py`.
- `apps/control-plane/api/v1/routes/vision.py` — submit schema/HTTP mapping.
- `tests/test_vision_event_processor.py`, `tests/test_vision_live_persistence.py`, `tests/test_vision_results.py`, `tests/test_vision_policy_routes.py`.

Thêm `tests/test_vision_provider_submission.py` cho snapshot/stale confirmation/idempotency. Tái sử dụng protocol/dispatch phase 02 và fixtures `tests/vision_trace_fixtures.py`.

## Implementation steps

1. Inject shared model batch qua composition roots. V4 publisher dùng cùng implementation; legacy processor bỏ tự tạo Drive/model factory trong application. Constructor tests được cập nhật đồng bộ; không thêm infrastructure dependency mới vào application/domain.
2. Persist provider/model và centralized VISION_PROMPT_VERSION cho session mới từ submit. Không sửa provider/model/prompt metadata của lịch sử. Session trước đây thiếu metadata mới vẫn đọc/hiển thị được.
3. POST `/api/v1/vision/explorations` thêm optional `expected_provider`, `expected_model` với rule cả hai hoặc không. Bắt buộc cho Gemini submission mới; HF client cũ không có vẫn tương thích. So sánh với effective saved policy ở transaction tạo session. Nếu lệch, 409 `vision_policy_changed`, không outbox/session/request provider. Không nhận expected fields như quyền override policy.
4. Giữ idempotency: retry đúng tenant/project/correlation/task/target trả session đã tạo, kể cả policy vừa đổi; không tạo session/call mới. Xác minh ownership và identity trước return; khác payload vẫn conflict. Expected provider/model phải đối chiếu snapshot cũ nếu client có gửi, không buộc retry đúng session theo policy mới. Idempotent lookup có thể chuyển trước current-policy readiness, nhưng luôn sau auth và validate identity.
5. V4 giữ live-policy check trước/giữa external operations; thêm consent binding vào điều kiện. Legacy phải đọc lại effective policy/project origin ở external boundary bằng repository, bảo đảm fresh read chứ không cache settings. Snapshot mismatch/disabled/revoked → `policy_disabled`; không gọi provider mới.
6. Preserve cumulative step/token/evidence, rate, session deadline, max_hops/states và replay guards. Shared callback kiểm tra sau model response; không thực thi proposal sau revocation phát hiện. Không giữ transaction v4 mở trong HTTP/provider/worker calls.
7. Carry safe failure reason phase 02 đến terminal record/progress/result API; `model_unavailable` vẫn đọc cho dữ liệu cũ. Thất bại sau navigate giữ screenshot và partial trace, không tạo candidate giả hoặc trả complete coverage. HF image_delivery_auth_required không bị đổi thành lỗi Gemini.
8. Giữ lease fencing và commit ordering. Unknown browser result → stop; outbox replay/duplicate không lặp click/type có kết quả chưa biết. Không tăng hoặc reset sequence khi đổi adapter.
9. Draft generation dùng general runtime như cũ. Nếu Vision hoàn thành nhưng draft lỗi, lưu đúng ranh giới outcome; không đánh dấu Vision fail chỉ vì text provider, cũng không mark draft thành công. Approval của generated suite/verdict không thay đổi.

## API/contracts/schema

Chỉ additive submit fields và safe reason strings, không SQL migration hoặc thay payload worker. `policy_version` hiện là config key; không mô tả nó như revision CAS. Snapshot + expected provider/model bảo vệ nơi nhận ảnh; limits vẫn lấy policy server và check khi chạy. Đồng thời đổi policy qua API được serialize bởi transaction hiện có; không hứa thu hồi request đã gửi.

## Tests / validation

- Hai backend flags legacy/v4 với Gemini fake: navigate → valid candidate → click non-button → durable before/after. HF vẫn qua nhánh cũ.
- Provider/model change, disable/revoke, allowed-origin change trước call và sau response: stop không thêm action hoặc gửi ảnh provider mới.
- HTTP stale expected pair và missing pair Gemini; old HF request; idempotent same session sau policy switch; cross-tenant/correlation mismatch bị chặn.
- 401/402/429/timeout/invalid response safe reason giữ từ executor đến result; trace trước lỗi vẫn đọc được; không enqueue draft nếu Vision unavailable.
- Crash/replay/fencing và unknown-outcome tests cũ pass, action/execution schema không đổi.

```powershell
uv run pytest tests/test_vision_provider_submission.py tests/test_vision_policy_routes.py tests/test_vision_event_processor.py tests/test_vision_live_persistence.py tests/test_vision_results.py tests/test_vision_locator_pipeline.py tests/test_vision_migration_compatibility.py tests/test_vision_worker_contracts.py tests/test_execution_contract_fixtures.py tests/test_agent_boundaries.py
uv run ruff check apps/control-plane/application apps/control-plane/infrastructure/workflows apps/control-plane/infrastructure/vision apps/control-plane/infrastructure/persistence/vision_unit_of_work.py apps/control-plane/api/v1/routes/vision.py
```

Live persistence tests yêu cầu PostgreSQL fixture riêng 127.0.0.1:55437 theo runbook; không trỏ tests vào app DB 5432. Nếu thiếu fixture, ghi blocked validation và dựng fixture theo hướng dẫn trước exit; skip không đủ để nghiệm thu phase.

## Exit criteria / non-goals

Cả legacy/v4 có integration evidence, session snapshots và idempotency đúng; không giữ SQL transaction v4 trong external call. Không migration lịch sử, bật v4 mặc định, redesign legacy toàn bộ transaction, thêm live stream hoặc mở rộng text providers.
