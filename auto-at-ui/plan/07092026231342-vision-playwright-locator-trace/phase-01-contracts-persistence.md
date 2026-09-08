# Phase 1 — Contract và persistence

Trạng thái: completed. Started: 2026-09-07 23:27 +07:00. Completed: 2026-09-07 23:49 +07:00. Phụ thuộc: scout README; working tree reviewed, initial Alembic head `f8a9b0c1d2e3`.

## Mục tiêu và phạm vi

Định nghĩa ranh giới có version cho việc nhận diện locator, operation thực sự và handoff. Bổ sung schema additive; giữ gallery/state/edge cũ và execution v1.

## Source thêm/sửa

Sửa:
- `packages/contracts/src/auto_at/contracts/vision.py`
- `packages/contracts/src/auto_at/contracts/generation.py`
- `packages/contracts/src/auto_at/contracts/__init__.py`
- `apps/control-plane/domain/entities.py`
- `apps/control-plane/domain/ports.py`
- `apps/control-plane/infrastructure/persistence/models.py`
- `apps/control-plane/infrastructure/persistence/repositories.py`

Thêm:
- `packages/contracts/fixtures/vision-locator-v1/` — JSON synthetic cho accepted/rejected operation và handoff.
- `apps/control-plane/domain/vision.py` — state machine và invariant thuần.
- `apps/control-plane/infrastructure/persistence/vision_unit_of_work.py`
- `migrations/versions/f9a0b1c2d3e4_add_vision_locator_operations.py` — proposed revision; kiểm tra collision/head rồi đặt revision mới nếu cần, không chỉnh migration lịch sử.

## Contract và dữ liệu đề xuất

1. `VisualLocatorDescriptor`: strategy discriminant `role|label|test_id|css`, bounded exact values, scope chuỗi iframe/shadow hỗ trợ, version. Không chứa code biểu thức hay executable JavaScript.
2. `VisualLocatorEvidence`: id, tenant/project/session/state/proposal refs, descriptor, normalized bounding box, matched_count, verified_at, originating_frame_id, status `verified|ambiguous|not_found|stale|unsupported|redacted`, safe reason. Confidence model và kết quả verification là hai trường độc lập.
3. `VisualOperation`: id, session, chronological sequence, attempt, parent operation/checkpoint/edge, purpose `explore|restore|replay|setup`, action kind, locator ref nếu có, expected parent fingerprint, start/end, status `prepared|executing|completed|failed|unknown|rejected`, safe outcome, actual_before/after frame refs, page refs dạng opaque, URL/visual change classification.
4. `VisualOperationFrame`: id, operation id, role `before|after`, checksum/size/type/captured_at, private storage key, deleted_at. Bảng riêng `visual_operation_frames`; không phá unique frame/state của `visual_replay_frames`. Cùng bytes-storage verification qua port mở rộng; key không xuất API.
5. `VisualCheckpoint`: state id, ancestor operation refs, URL và semantic fingerprints, scroll invariants, form-presence invariants; raw runtime state chỉ trong RAM worker. Mô tả trả API chỉ IDs/status. Việc state unavailable sau restart là kết quả hợp lệ.
6. `VisualLocatorHandoff`: id, session/project/tenant, version/hash, bounded branch paths chứa operation/locator IDs và observations đã sanitize, unresolved counts, created_at, generation_request_id nullable. JSON payload immutable; unique (tenant, session, version). Không chứa ảnh, URL provider, cookie hoặc text nhập.
7. Bổ sung `vision_handoff_id` nullable cho generation request và provenance nguồn Vision tùy chọn (session/handoff/hash). Idempotency generation phải gồm handoff identity/hash, không chỉ intent.
8. Bổ sung session version, lease owner/fencing token, lease expiry và next operation sequence để claim có điều kiện. Worker protocol mới `v4` độc lập với v1 execution; Python schema authoritative + TS parser parity bằng fixtures.
9. Mọi reference phải kiểm tra tenant/project/session. Dùng composite unique/FK khi phù hợp, kiểm tra application cho quan hệ liên bảng còn lại. Lifecycle chỉ chuyển tiến, finalized operation không được đổi kết quả, duplicate identical được chấp nhận.

## Cách thực hiện

- Tạo bốn bảng `visual_operations`, `visual_operation_frames`, `visual_locator_evidence`, `visual_locator_handoffs`. Unique operation (tenant_id, session_id, sequence) và (tenant_id, session_id, id); frame unique (operation_id, role); locator có FK nguồn proposal/state và frame, handoff unique (tenant_id, session_id, version). Index cho session/sequence và handoff → generation lookup. Nullable linkage hỗ trợ bước setup chưa có logical state.
- Before frame cần tồn tại trước locator evidence tham chiếu frame: insert prepared operation → frame → evidence trong cùng transaction, sau đó mới execute. Không tạo vòng FK bắt buộc insert không được. After/final outcome được finalize một lần có fencing condition.
- Phân biệt state graph (logic) và operation ledger (thời gian) bằng contract riêng.
- UoW cung cấp claim, commit prepared/captured/finalized và read snapshot; application không giữ ORM session qua model/worker await.
- Persist before trước dispatch. Artifact upload và DB commit không atomic: tạo key xác định từ operation/role, verify bytes, commit metadata; retry không overwrite ảnh khác checksum.
- Xóa frame giữ tombstone và operation reference để UI biết unavailable. Chỉ cleanup staging sau acknowledgement; orphan handling chỉ cho key thuộc operation đã xác định.
- Giá trị locator nhạy cảm phải bị loại trước persistence, không sửa thành placeholder rồi gọi verified.

## Tests và validation

Sửa `tests/test_vision_contracts.py`, `tests/test_generation_contracts.py`, `tests/test_persistence_schema.py`.
Thêm `tests/test_vision_operation_repository.py`, `tests/test_vision_handoff_repository.py`.
Kiểm tra vòng reference, tenant mismatch, duplicate sequence/attempt, immutable finalization, invalid scope/value, redaction, handoff hash mismatch, nullable compatibility.

Tại root:
```text
uv run ruff check packages/contracts/src apps/control-plane/domain apps/control-plane/infrastructure/persistence tests/test_vision_contracts.py tests/test_vision_operation_repository.py tests/test_vision_handoff_repository.py
uv run pytest tests/test_vision_contracts.py tests/test_generation_contracts.py tests/test_persistence_schema.py tests/test_vision_operation_repository.py tests/test_vision_handoff_repository.py tests/test_execution_contract_fixtures.py
uv run alembic heads
```

Upgrade migration chỉ trên DB test disposable; xác minh dữ liệu legacy giữ nguyên và chỉ một head.

## Nghiệm thu, rủi ro và non-goals

Contract fixtures được Python validate và sẵn cho worker phase 2. Cross-tenant refs bị từ chối. Schema cũ vẫn đọc được. Không đổi execution envelope, retention hoặc expose checkpoint secrets. Chưa có browser behavior hay API mới ở phase này.


## Phase 1 implementation record - completed 2026-09-07 23:49 +07:00

Implemented versioned, bounded locator/operation/frame/checkpoint/handoff contracts and 19 Python-validated parity fixtures. Evidence requires unique target grounding and actionability; sensitive locator identities are rejected. Added four additive tables, legacy session defaults, generation linkage, immutable checkpoint invariants, conditional leases/fencing, serialized sequences, and commit-per-call UoW. Private frame writes verify size/checksum and durable read-back before metadata commit; tombstones preserve history. Handoffs validate complete branch paths, executed locator identity and immutable hashes; generation keys bind the handoff identity/hash. Runner execution v1 and human approval remain unchanged.

Validation:

- `uv run ruff check .` - passed.
- `uv run pytest tests/test_vision_contracts.py tests/test_generation_contracts.py tests/test_persistence_schema.py tests/test_vision_operation_repository.py tests/test_vision_handoff_repository.py tests/test_execution_contract_fixtures.py -q` - **53 passed**, including real PostgreSQL competing claims/prepares, independent reader visibility, fencing, immutable finalization, scope/FK rejection, frame tombstones, checkpoint/branch rules and migration upgrade.
- `uv run alembic heads` - one head, `f9a0b1c2d3e4`.
- Full Python suite in an isolated `uv run --no-sync python -` process (dotenv disabled, provider-key env removed, outbound sockets restricted to loopback, fresh `.pytest-tmp/locator-phase1-<uuid>` basetemp): **263 passed**. The final three concurrency/checkpoint/DB constraint tests were added afterward and passed in the focused 53-test rerun; the full suite was not repeated unnecessarily.
- Migration test upgraded a new UUID-named PostgreSQL database through `f8a9b0c1d2e3`, seeded legacy session/generation rows, upgraded to head and verified data and nullable/default compatibility. Tests use the disposable `vision-locator-phase1-test` container on localhost:55437; they explicitly skip if that fixture is absent. No application DB migration was performed.

Implementation details/deviations: non-indexed operation/evidence/handoff contract fields are retained in validated JSON payloads; query/reference fields have explicit columns and scoped FKs. Checkpoint metadata is a nullable JSON column on existing states, with raw browser state still memory-only. Migration downgrade refuses destructive evidence deletion, following the plan's rollback-writer policy. The private storage port is defined and tested using an immutable in-memory fixture store; the RustFS adapter and worker transport integration remain Phase 3/2 responsibilities. The existing unrestricted full-suite invocation made one unintended Hugging Face call through an unrelated triage test; its failure and the successful isolated rerun are documented above. No local provider settings or unrelated tests were changed.

Exact implementation paths (relative to `auto-at-ui/`):

- `packages/contracts/src/auto_at/contracts/vision.py`
- `packages/contracts/src/auto_at/contracts/generation.py`
- `packages/contracts/src/auto_at/contracts/__init__.py`
- `apps/control-plane/domain/entities.py`
- `apps/control-plane/domain/ports.py`
- `apps/control-plane/domain/vision.py`
- `apps/control-plane/infrastructure/persistence/models.py`
- `apps/control-plane/infrastructure/persistence/repositories.py`
- `apps/control-plane/infrastructure/persistence/vision_unit_of_work.py`
- `migrations/versions/f9a0b1c2d3e4_add_vision_locator_operations.py`
- `tests/test_vision_contracts.py`
- `tests/test_generation_contracts.py`
- `tests/test_persistence_schema.py`
- `tests/test_vision_operation_repository.py`
- `tests/test_vision_handoff_repository.py`
- `tests/vision_trace_fixtures.py`
- `packages/contracts/fixtures/vision-locator-v1/descriptor.accepted.json`
- `packages/contracts/fixtures/vision-locator-v1/descriptor.rejected-scope.json`
- `packages/contracts/fixtures/vision-locator-v1/descriptor.rejected-sensitive.json`
- `packages/contracts/fixtures/vision-locator-v1/handoff.accepted-branch.json`
- `packages/contracts/fixtures/vision-locator-v1/handoff.accepted-empty.json`
- `packages/contracts/fixtures/vision-locator-v1/handoff.rejected-hash.json`
- `packages/contracts/fixtures/vision-locator-v1/handoff.rejected-unbound-input.json`
- `packages/contracts/fixtures/vision-locator-v1/locator.accepted-redacted.json`
- `packages/contracts/fixtures/vision-locator-v1/locator.accepted-verified.json`
- `packages/contracts/fixtures/vision-locator-v1/locator.rejected-ambiguous-verified.json`
- `packages/contracts/fixtures/vision-locator-v1/locator.rejected-not-actionable.json`
- `packages/contracts/fixtures/vision-locator-v1/locator.rejected-wrong-target.json`
- `packages/contracts/fixtures/vision-locator-v1/operation.accepted-prepared.json`
- `packages/contracts/fixtures/vision-locator-v1/operation.accepted-unknown.json`
- `packages/contracts/fixtures/vision-locator-v1/operation.rejected-executing-no-before.json`
- `packages/contracts/fixtures/vision-locator-v1/operation.rejected-missing-reason.json`
- `packages/contracts/fixtures/vision-locator-v1/operation.rejected-stop.json`
- `packages/contracts/fixtures/vision-locator-v1/worker.accepted-v4.json`
- `packages/contracts/fixtures/vision-locator-v1/worker.rejected-missing-scope.json`

Canonical documentation updated: this README and `phase-01-contracts-persistence.md`. Next: Phase 2 browser locator grounding, per-operation capture, and checkpoint restoration. No new writer or browser feature is enabled by Phase 1 alone.

Validation cleanup: the owned disposable PostgreSQL container was stopped and automatically removed after the checks. `git diff --check` passed for modified tracked Phase 1 source/test files.
