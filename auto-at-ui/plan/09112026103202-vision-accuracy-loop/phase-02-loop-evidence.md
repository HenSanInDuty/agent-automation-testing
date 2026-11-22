# Phase 02 — Vòng chạy có thể tiếp tục và bằng chứng chẩn đoán

Status: completed, 2026-11-09 11:44 +07. 35 tests passed, scoped Ruff passed.
Historical API import verified the exact before_dispatch failure without a POST.
Canonical README lists exact changed paths, commands, Windows Temp remediation
and deferred bridge usage metadata (not exposed by result API). No production
endpoint, worker contract, policy, prompt or execution verdict changed here.

## Mục tiêu và điều kiện trước

Phase 01 hoàn thành. Dùng API hiện có để tạo/đối soát phiên, thu evidence và chấm;
lệnh script điều khiển vòng chạy, Codex phân tích/sửa code theo plan, không để
một process tự sửa source hoặc tự phê duyệt generated tests.

## File thêm/sửa dự kiến

- Thêm `benchmark/vision/accuracy/run.py`: CLI start/resume/collect/evaluate
  (tên subcommand là thiết kế mới, chưa có hiện tại).
- Thêm `benchmark/vision/accuracy/evidence.py`: lọc safe metadata và join IDs.
- Thêm `tests/test_vision_accuracy_loop.py`: HTTP fake và artifact lifecycle.
- Thêm `benchmark/vision/accuracy/runs/<iteration-id>/` khi chạy: manifest,
  diagnosis, score, validation và evidence references; không lưu secrets.
- Nếu diagnostics hiện có thiếu, sửa `workers/playwright/src/vision-observability.ts`,
  `workers/playwright/src/vision-checkpoints.ts`, `workers/playwright/src/vision-operations.ts`
  và tests tương ứng `vision-observability.spec.ts`, `vision-operations.spec.ts`.
- Tận dụng `apps/control-plane/application/vision_reload.py`,
  `apps/control-plane/api/v1/routes/vision.py`, `application/vision_results.py`;
  không đổi chúng trừ khi regression chứng minh endpoint thiếu contract cần thiết.

## Luồng dữ liệu chi tiết

1. Persist iteration ID + source/config/oracle hash + idempotency key **trước**
   POST reload. Đọc context tenant/actor/consent từ cấu hình được phép; secret
   source vẫn hiện hữu, không embed token trong report hoặc shell history.
2. Đảm bảo không có vòng đang active; POST reload trên retained request.
   Retry transport dùng cùng key; crash trước nhận session ID vẫn recover cùng key.
3. Poll có deadline ở client, nhưng timeout theo dõi không đồng nghĩa phiên lỗi.
   Khi resume luôn đối soát phiên cũ; không bỏ chạy rồi tạo mới.
4. Thu result/trace/frame bằng endpoint có quyền. Lưu operation status và safe
   failure_stage, code, page/URL/scroll/context/form-change flags, source checkpoint
   references, timings, model jobs, calls và inventory.
5. Phân loại: capture/hydration, prepare_start drift, before_dispatch drift,
   target/context/private-form drift, popup/history/scroll restore, locator,
   coverage discovery, state/snapshot budget, model/provider/quota, missing evidence.
6. Diagnostics phải chứng minh thời điểm có/không dispatch; nếu chưa biết thì unknown.
   Chỉ log hashed identity/change categories; không log giá trị form/DOM thô.
   Attribution đến node chỉ dùng dữ liệu an toàn và không thay guard.
7. Xuất score và missing/wrong/unverified targets; mọi lượt đều được giữ,
   gồm run failed hoặc quota-limited. Không lấy best-of rồi bỏ lượt xấu.
8. Review budget tích lũy trước lượt kế. Quota/billing không biết → ghi unknown,
   không tuyên bố không mất phí. Khi cần material cost mới phải có user direction.

## Contract/API/schema

Reuse API reload/result/trace/frame hiện có. Mỗi artifact có schema version và
run provenance; credentials/intent không là artifact. Không migration.
Nếu cần thêm worker result field, định nghĩa ở
`packages/contracts/src/auto_at/contracts/vision_worker.py`, regenerate TS bằng
`uv run python packages/contracts/export_vision_worker.py`; kiểm đồng bộ bằng
`uv run python packages/contracts/export_vision_worker.py --check`.
Không tự sửa generated output đơn lẻ. Thêm compatibility test/capability
nếu semantic wire thay đổi; giữ execution v1.

## Validation và acceptance

`uv run pytest tests/test_vision_accuracy_loop.py tests/test_vision_accuracy_metrics.py -q`.
Worker checks cho file thực sự đổi: `npm.cmd run typecheck` và các spec trên.

Mock HTTP: timeout sau submit, crash/resume, key trùng, policy đổi, 401/403,
phiên chưa terminal, quota, missing frame, duplicate collection, schema mismatch,
đường dẫn output trùng. Kiểm tra không tạo duplicate live session, không tự
cancel hay retry side effect, không ghi secret vào artifact.
Replay lại metadata của c8fbd0ea phải phân loại rejected restore đúng stage
và giữ partial; không gọi provider để kiểm thử harness.

Không làm autonomous healing service, dashboard mới hoặc scheduler production.

## Kết quả thực thi

Completed 2026-11-09 11:44 +07. Harness API lưu idempotency trước submission,
thu safe evidence bất biến và kiểm checksum cùng outcome review khi chấm.
35 Python tests và Ruff passed. Historical import giữ 81 operations của c8fbd0ea,
xác định before_dispatch/state_mismatch, không POST và không đủ điều kiện qualification.
Deviation: actual model jobs/cost cần safe bridge metadata riêng ở phase 04;
không suy ra call count từ số batch. Exact paths/commands trong README chuẩn.

