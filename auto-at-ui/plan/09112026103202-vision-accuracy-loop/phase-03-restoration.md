# Phase 03 — Tái hiện race và sửa restoration có kiểm chứng

## Mục tiêu và prerequisites

Có oracle và harness từ phase 01–02. Giải quyết nguyên nhân chặn lớn nhất:
restore wait bị state_mismatch giữa prepare và dispatch. Không mặc định mọi
mismatch là carousel, cũng không coi ảnh giống nhau là checkpoint đúng.

## File dự kiến

- `workers/playwright/src/fixtures/vision-target.ts`: fixture điều khiển thời điểm drift.
- `workers/playwright/src/vision-operations.spec.ts`: race prepare/execute, evidence.
- `tests/test_vision_page_batch.py`: application + DB + Chromium flow.
- `apps/control-plane/application/vision_trace_events.py`: restore và luồng refresh.
- `apps/control-plane/application/vision_operations.py`: chỉ sửa nếu cần phân biệt
  proven pre-dispatch rejection với unknown; giữ reconcile/ack/evidence ordering.
- `workers/playwright/src/vision-revalidation.ts`, `vision-checkpoints.ts`,
  `vision-operations.ts`: chỉ đổi phần được fixture chứng minh cần thiết.
- `tests/test_codex_revalidation.py`, `tests/test_vision_live_persistence.py`,
  `tests/test_vision_viewport_scan.py`: guard và budget regression liên quan.
- Thêm `docs/adr/023-bounded-restore-recovery.md`; cập nhật
  `benchmark/vision/codex/manifest.json` với source hashes/cases mới.

## Thiết kế và thứ tự xử lý

1. Fixture server barrier đổi control sau prepare thành công, trước execute,
   đúng với diagnostic lượt cuối. Tách biến thể drift tạm thời trở lại checkpoint
   và drift vĩnh viễn/context đổi. Dùng barrier, không dựa timing sleep may rủi.
2. Regression hiện tại phải tái hiện lý do stop; lưu trace của red run.
3. Cách sửa ưu tiên: chỉ với **read-only restore wait đã được chứng minh rejected
   trước dispatch**, cho phép tối đa hai chu kỳ quan sát mới + so checkpoint gốc.
   Mỗi operation có ID/evidence mới; giữ bản ghi rejection cũ. Không đổi nó thành
   completed. Refresh phải cùng Page và nằm trong state/hop/step/operation budget.
4. Chỉ phát lệnh verification mới khi toàn bộ checkpoint gốc được worker xác minh.
   Chu kỳ không kéo dài step deadline; policy giảm hoặc hết budget dừng partial.
   Không retry click/type/Back/scroll đã thực hiện hoặc có outcome unknown.
5. Nếu trang không bao giờ trở về checkpoint: giữ fail-closed. Khi evidence cho
   thấy chặn do thay đổi không liên quan mục tiêu, đánh giá riêng việc mở **nhánh
   quan sát mới** và lấy proposal mới cho mục tiêu độc lập chưa thử, bằng context/
   target revalidation của ADR-019/020. Không nhận nhánh mới là “đã restore”,
   không tái dùng proposal/checkpoint cũ, không lấy no-op làm bằng chứng đúng.
6. Trước khi triển khai nhánh mới: chứng minh Page/document/URL/form/landmark/
   target identity/actionability/dependency tương đương cần thiết; target có
   phụ thuộc state chưa chứng minh phải giữ blocked. Ghi ADR riêng hoặc mở rộng
   ADR-023 và contract capability nếu cần. Đây là nhánh thiết kế có điều kiện,
   không là lý do bỏ guard toàn cục.
7. Chạy negative tests cùng positive; source checkpoint bất biến, privateForms
   chỉ RAM, full replay preflight giữ nguyên. Giữ nguyên runtime conclusion dù
   benchmark một lượt có thể vượt >95%.

## Contract và rollout

Ưu tiên controller-only recovery dùng các operation hiện có. Không thay execution
v1/API/DB. Nếu worker cần chứng cứ machine-readable cho pre-dispatch, theo private
contract workflow phase 02; controller không đoán từ chuỗi log tự do.
Rebuild đúng services thay đổi, drain rồi deploy worker/controller tương thích;
verify hashes. Rollback image, không rewrite session.

## Tests/commands

Tại worker: `npm.cmd run typecheck`;
`npm.cmd test -- src/vision-operations.spec.ts src/vision-visual-buttons.spec.ts src/vision-readiness.spec.ts --workers=1`.
Tại repo:
`uv run ruff check .`;
`uv run python benchmark/vision/codex/run_offline.py -q --tb=short tests/test_vision_page_batch.py tests/test_codex_revalidation.py tests/test_vision_live_persistence.py tests/test_vision_viewport_scan.py tests/test_vision_handoff.py tests/test_codex_bridge_benchmark.py`.

Matrix bắt buộc: temporary/permanent carousel drift; replaced node; changed href/
label; disabled/covered target; modal/heading/URL/private form drift; popup nhiều
tầng; Back hydrate; empty viewport; state policy giảm; revocation; lost ack/unknown.
Kiểm tra exactly-once side effects, bounded observations, no replay prefix,
đủ frame, không click sibling khi source chưa xác minh.
Chạy race fixture 20 lần theo các barrier schedule xác định; negative cases
phải chặn 100%, không được bỏ failed trial vì coi là flaky.

## Acceptance và non-goals

Red→green cho nguyên nhân đã chọn, negative suite xanh, không relax checkpoint
hoặc live-node gate. Fix không đủ đưa live >95% thì tiếp phase 04; không tuyên bố
đã đạt chỉ vì test local qua. Không tắt carousel website hoặc tăng ngân sách.

## Kết quả thực thi

Completed 2026-11-09 12:05 +07. Red reproduction: rejected restore wait trước
dispatch; green: 6 variants, 20 worker race schedules và 82 worker regressions.
Broad isolated suite: 177 passed, zero skip/error. Bổ sung hop cap sau khi broad
suite build, được kiểm riêng bằng 6 variants trên final source. Ruff, typecheck,
contract generator check và diff check passed. Xem README chuẩn và
`benchmark/vision/accuracy/phase03-validation-20261109.json` cho provenance.
Private nullable dispatch proof là deviation cần thiết; compatible rollout
controller + worker, execution v1 không đổi. Phase 04 tiếp tục đo live.

