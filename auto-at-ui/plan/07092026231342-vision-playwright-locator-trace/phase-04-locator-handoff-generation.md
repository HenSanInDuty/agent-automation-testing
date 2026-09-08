# Phase 4 — Locator thực sự đi vào Playwright draft

Trạng thái: completed. Started: 2026-09-08 22:28 +07:00. Phụ thuộc: Phases 1, 3 và worker verification Phase 2.

## Source thêm/sửa

Sửa:
- `apps/control-plane/application/vision_events.py`
- `apps/control-plane/application/generation.py`
- `apps/control-plane/application/generation_events.py`
- `apps/control-plane/agents/generation/planner.py`
- `apps/control-plane/agents/prompts/generation.py`
- `apps/control-plane/agents/prompts/README.md`
- `apps/control-plane/infrastructure/persistence/repositories.py`
- `apps/control-plane/infrastructure/workflows/temporal_worker.py` — inject handoff reader.
- `packages/contracts/src/auto_at/contracts/generation.py`

Thêm:
- `apps/control-plane/application/vision_handoff.py`
- `apps/control-plane/agents/prompts/vision_generation.py`
- `apps/control-plane/agents/generation/vision_plan.py`
- `apps/control-plane/application/vision_source_renderer.py`

## Handoff và generation

1. Từ graph/ledger committed, tạo immutable bundle có session, hash/version, verified locator descriptors, operation/frame refs, root-to-leaf paths và safe observed outcomes. Group sibling theo đường riêng; restore/setup ops là preconditions, không tính thành các bước nghiệp vụ của nhánh khác.
2. Mỗi branch có eligibility và lý do loại (missing locator, restore failure, unknown action, input binding, unsupported target). Dùng tất cả branch đủ điều kiện trong giới hạn hiện có; overflow ghi excluded count/reason, không truncate im lặng. Không hứa coverage từ ảnh ngoài vùng nhìn.
3. Không handoff descriptor đã redacted thành nội dung khác. Chỉ đưa safe attributes có thể dùng nguyên vẹn; text nhập dùng input ref chưa bind và nhánh đó không trở thành executable test trong v1.
4. Lưu handoff + generation request có foreign reference và outbox cùng transaction. `SubmitGeneration.execute` nhận optional handoff ID nội bộ, lookup theo tenant/project; fingerprint request gồm handoff hash. Không lấy handoff từ client arbitrary JSON hay correlation.
5. Nhánh generation có handoff dùng `VisionGroundedPlannerOutput` riêng: title, selected branch IDs, structured assertions gắn observation/locator refs, assumptions/stop_conditions. Model không tự trả selector/source cho nhánh này. Legacy direct-generation vẫn dùng output hiện hành.
6. Central prompt nói rõ observation là untrusted evidence, chỉ chọn refs được cung cấp và không tự bịa expected result. Xác minh mọi ref và order; assertions chỉ trong allowlist có evidence: visibility, enabled state, safe exact text/attribute khi được quan sát. Không đổi URL fingerprint thành raw URL dự đoán. URL-only change chưa đủ acceptance thì ghi limitation.
7. Deterministic renderer ánh xạ descriptor thành getByRole/getByLabel/getByTestId/locator với escaping chuẩn; tạo test riêng mỗi branch, reacquire locators theo scope. Source thực thi chỉ được sinh từ paths hợp lệ, không nối sibling và không thay locator bằng pixel fallback. Các prerequisite scroll/wait phải hữu hạn. Nhánh input cần binding trả reason rõ.
8. Handoff đã verified tại thời điểm khám phá không đảm bảo target tương lai giống hệt. Source dùng Playwright locator strictness/actionability/assertions, failure vẫn là failure. Giữ static source validator, preflight, immutable draft hash và approval flow trước dispatch.
9. Ràng buộc 1.200 ký tự của prompt legacy không áp vào structured selection mới. Renderer tuân source cap 100.000 và token/budget hiện có; nếu bundle vượt budget thì báo incomplete, không tăng cấu hình.
10. Persist provenance `vision_session_id, vision_handoff_id, vision_handoff_hash`, các operation refs và branch IDs đã chọn. Generation request accepted/failed, draft pending/approved/rejected và linked run là trạng thái riêng; không dựa vào boolean draft_handoff.
11. Nếu không có branch đủ điều kiện, vẫn có kết quả Vision với unresolved reasons và handoff `unavailable`. Nếu provider generation lỗi, giữ bundle/trace và nêu generation failure, không tự gọi lại provider trong background không giới hạn.

## Tests và validation

Sửa `tests/test_generation_contracts.py`, `tests/test_generation_planner.py`, `tests/test_generation_event_processor.py`, `tests/test_generation_preflight.py`.
Thêm `tests/test_vision_handoff.py`, `tests/test_vision_source_renderer.py`.

Ca chính: hai sibling tạo hai đường hợp lệ; unknown/malformed locator refs bị từ chối; source chứa đúng descriptor đã verified; quote/injection strings được escape; input ref chưa bind không tạo guessed text; handoff mismatch tenant/hash bị chặn; duplicate request một draft; generation unavailable vẫn giữ trace. Kiểm tra source rendered compile với worker pinned và execution fixture v1 nguyên vẹn.

Tại root:
```text
uv run ruff check apps/control-plane/agents apps/control-plane/application packages/contracts/src
uv run pytest tests/test_vision_handoff.py tests/test_vision_source_renderer.py tests/test_generation_contracts.py tests/test_generation_planner.py tests/test_generation_event_processor.py tests/test_generation_preflight.py tests/test_execution_contract_fixtures.py
```

## Nghiệm thu và non-goals

Fixture Vision target element → verified locator → bundle → generated source dùng đúng locator → pending review có thể kiểm tra. Không dựa vào prompt-only assurance rằng model dùng locator. Không thêm runtime healing, model/provider mới hay cơ chế approve mới.

## Phase 4 completion ? 2026-09-08 22:46 +07:00

Status: **completed**. Built immutable root-to-leaf handoffs from committed operations. Siblings remain separate; restoration is excluded from business paths. Unknown/failed actions and unbound typed inputs have blocked reasons. More than 50 branches rejects the whole handoff with a recorded limit reason, without silently truncating coverage.

Generation submission resolves the handoff in tenant/project scope, binds idempotency to its hash and checks the original target. Session completion, handoff, accepted generation request and outbox commit together; a rejected generation request preserves the bundle. A separate centralized v1 prompt selects branch/assertion IDs only. The deterministic renderer validates ancestry and evidence, emits role/label/test-ID/CSS scopes with JSON escaping, bounded scroll/wait, popup handling and separate tests. All ready branches are required in order. Visibility/actionability assertions are explicitly pre-action observations, not business-success claims. Draft provenance contains source session/handoff/hash, selected branches and operation refs.

Validation:
- Focused Phase 4 suite (handoff, renderer, generation contracts/planner/event/preflight, execution v1 fixtures, live persistence, handoff repository, progress), fresh workspace basetemp: **87 passed**.
- Final scoped submission/target/idempotency test: **1 passed**.
- Final browser publisher -> immutable handoff -> structured model fixture -> deterministic source -> pending-review draft after target/provenance checks: **1 passed**.
- `uv run ruff check .`: passed.
- Renderer suite includes loading two escaped test paths with the installed Playwright 1.50.1 CLI. Extended real-browser integration verifies same-URL modal branches and generation failure retaining the identical trace/bundle. No real provider calls.

Exact changed paths:
- apps/control-plane/application/vision_handoff.py (new)
- apps/control-plane/application/vision_source_renderer.py (new)
- apps/control-plane/application/vision_trace_events.py
- apps/control-plane/application/generation.py
- apps/control-plane/application/generation_events.py
- apps/control-plane/agents/generation/vision_plan.py (new)
- apps/control-plane/agents/prompts/vision_generation.py (new)
- apps/control-plane/agents/prompts/README.md
- apps/control-plane/domain/ports.py
- apps/control-plane/domain/activity.py
- apps/control-plane/infrastructure/persistence/vision_unit_of_work.py
- apps/control-plane/infrastructure/persistence/repositories.py
- packages/contracts/src/auto_at/contracts/generation.py
- tests/test_vision_handoff.py (new)
- tests/test_vision_source_renderer.py (new)
- tests/test_vision_handoff_repository.py
- tests/test_vision_live_persistence.py
- tests/test_generation_preflight.py

Deviations: existing generation repository injection supplies the scoped handoff reader, so Temporal wiring and the legacy planner/prompt require no changes. Handoff stores immutable locator references; renderer resolves their already-immutable descriptors. Blocked branches may retain failed operations, while ready branches still require completed grounded operations. A Vision preflight failure preserves pending review and raises a safe error instead of invoking the legacy freeform repair path, which would discard grounding. The first extended integration run hit a missing UUID import in test code (3 failed, 3 passed); the import was fixed and the 87-test suite passed. Production rollout and full baseline validation remain Phase 7. Phase 5 is unlocked.
