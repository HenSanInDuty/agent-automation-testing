# Phase 5 — API trace, locator và kết quả cuối

Trạng thái: completed. Phụ thuộc: Phases 1, 3, 4.

## Source thêm/sửa

Sửa:
- `apps/control-plane/api/v1/routes/vision.py`
- `apps/control-plane/application/vision_trajectory.py`
- `apps/control-plane/application/vision_replay.py`
- `apps/control-plane/domain/ports.py`
- `apps/control-plane/infrastructure/persistence/repositories.py`
- `apps/control-plane/infrastructure/artifacts/rustfs.py`
- `apps/control-plane/api/v1/routes/generation.py` — source provenance responses.

Thêm `apps/control-plane/application/vision_results.py`.
Tests thêm `tests/test_vision_results.py`, sửa `tests/test_vision_routes.py`, `tests/test_vision_replay.py`, `tests/test_dashboard_route_contracts.py`.

## API đề xuất

Dưới `/api/v1/vision/explorations/{session_id}`:
- `GET /trace?after_sequence=&limit=`: schema_version, committed revision/cursor, operation list, referenced locator/state/frame metadata và has_more. Server cap 100 operations/page, chỉ trả metadata.
- `GET /operation-frames/{frame_id}`: private bytes/no-store, checksum verified, cùng quyền project READ như replay.
- `DELETE /operation-frames/{frame_id}` và `DELETE /operation-frames`: tenant-admin, audit + tombstone, failure semantics giống replay hiện có. “Delete all evidence” UI gọi đúng cả legacy/new store.
- `GET /locators?status=&limit=&after_id=`: bounded safe locator catalog.
- `GET /result`: summary xác định có version/revision, counters, branch dispositions, stop reason, handoff/generation/draft/run/report states + IDs.
- `GET /result/export`: cùng dữ liệu safe dạng JSON attachment; không nhúng ảnh hoặc signed URLs.
Giữ các trajectory/actions/replay-frames routes cũ cho legacy.

## Cách tổng hợp và dữ liệu

1. Application authorize session theo tenant/project trước tất cả lookup; non-service project reader theo boundary đã có. Không để HTTP route tự join repositories.
2. Trace dùng sequence theo thao tác thật; cạnh BFS riêng, một edge có thể có nhiều setup/restore ops. Frame before/after luôn lấy operation refs; deleted/missing có availability + reason.
3. Snapshot operation/frame/locator chỉ trả dữ liệu committed cùng revision, hoặc paginate trên revision watermark để tránh child chưa tồn tại. Không cache response private.
4. `result` có `exploration_state`, `completion_reason`, `evidence_status`, proposed/executed/failed/unknown counters, verified/unresolved locator counts, branch totals và limitations. Unknown không cộng completed; graph node count không thay operation count.
5. Summary không gọi LLM. Chạy được cho running/completed/unavailable/cancelled. Generation link lấy quan hệ handoff → request → draft → linked_run_id; report lookup bằng run ID và quyền tương ứng. Legacy correlation chỉ là compatibility lookup có tenant/project filter và không chọn first ambiguous match.
6. Expose link IDs/relative route metadata, không URL target/raw DOM/cookie/provider diagnostics. Descriptor display đã sanitize ở writer, reader validate lại shape. `input_binding_required` thể hiện bằng safe reason.
7. Report state phân biệt not_started, pending, available, unavailable và legacy_missing từ dữ liệu hiện có. Kết quả khám phá hiện ngay khi hoàn tất; generation lỗi không trả “đợi report” vô hạn.
8. Lịch sử cũ không có operations/locators hiển thị `legacy_evidence_only`; không tự gán verified hay backfill từ screenshot.
9. Xóa frame phải huỷ blob fetch/cache phía client, giữ metadata unavailable; không đổi verdict/draft. API export tôn trọng deletion và quyền đọc ở thời điểm gọi.

## Validation

```text
uv run ruff check apps/control-plane/api/v1/routes/vision.py apps/control-plane/application/vision_results.py
uv run pytest tests/test_vision_results.py tests/test_vision_routes.py tests/test_vision_replay.py tests/test_dashboard_route_contracts.py tests/test_reporting_routes.py
```

Fixtures: same tenant khác project, foreign session refs, service principal, missing/deleted frame, duplicate IDs, failed object deletion, concurrent append pagination, no draft, failed generation, draft pending, linked terminal run/report missing/unavailable. Assert payload không leak sensitive sentinel hoặc storage keys. UI report link phải tương ứng đúng run, không chỉ correlation.

## Nghiệm thu và non-goals

Reader tải được kết quả khám phá ngay cả generation failed, tra được mỗi operation/frame/locator. API đơn thuần đọc không tạo generation/run/report hay gọi provider. Không thêm PDF/DOCX, public share URLs hoặc thay retention.


## Phase 5 completion ? 2026-09-08 22:58 +07:00

Status: **completed**. Added authorized trace pagination, locator catalog, private operation-frame reads/deletions and deterministic result/JSON export endpoints. Reads use repeatable-read snapshots; a changed trace revision rejects continued pagination so clients can restart. Frame metadata includes retained/deleted/missing states and never storage keys. Byte reads verify size/checksum. Deletion is byte-first, retains tombstones, and commits failure audits and prior successful deletions for retry.

Results separate exploration, handoff, generation, draft, run and report states through explicit scoped references. Queued report events remain pending; terminal runs without reports are unavailable. Legacy sessions are labeled evidence-only and use only the exact scoped legacy generation key, never ambiguous correlation lookup. Generation responses expose the optional handoff ID; draft provenance already exposes the validated Phase 4 source.

Validation:
- `uv run pytest tests/test_vision_results.py tests/test_vision_routes.py tests/test_vision_replay.py tests/test_dashboard_route_contracts.py --basetemp <fresh workspace directory> -q --tb=short`: **47 passed**.
- Final result suite after adding queued-report handling: **14 passed**.
- Existing `tests/test_reporting_routes.py` against a UUID disposable PostgreSQL schema with dotenv disabled and process-local DATABASE_URL: **1 passed**. Initial isolated runner omitted the contracts import path and exited before creating a database; corrected invocation passed.
- `uv run ruff check .`: passed.
- Tests cover independent append/revision changes, service/foreign-project/foreign-tenant denial, project-reader deletion denial, corrupted/missing/deleted frame responses, deletion failure audit retention, exports, legacy evidence, exact draft/run/report links and missing/failed/pending reports. No provider calls.

Exact changed paths:
- apps/control-plane/application/vision_results.py (new)
- apps/control-plane/api/v1/routes/vision.py
- apps/control-plane/api/v1/routes/generation.py
- apps/control-plane/infrastructure/persistence/repositories.py
- tests/test_vision_results.py (new)
- tests/test_dashboard_route_contracts.py

Deviations: reused the existing replay authorization boundary and verified operation store without changing their legacy behavior. New reads are application methods with repository adapters; no domain or transport rewrite was needed. The export is JSON metadata only, without screenshot bytes or signed URLs. Real object absence is reported when the selected frame is fetched; metadata reads do not issue storage requests for every retained frame. Phase 6 is unlocked.
