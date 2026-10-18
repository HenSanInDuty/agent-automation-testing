# Phase 02 — Bằng chứng vị trí click

Status: **completed** — started 2026-10-19 04:44, completed 04:52 +07:00.

Implementation paths and command results are in README execution log: 85 Python tests, 43 browser/contract worker tests, typecheck, Ruff and generated parity passed. Worker lint has 10 baseline diagnostics identical to HEAD, deliberately deferred. Unit-of-work already preserves full operation payload; no change was needed there.

Revision from source evidence: Playwright 1.50 uses padding-box offsets, so metadata includes border offset and existing hundredth-pixel rounding. Unsupported transformed/zoomed/clipped/iframe geometry produces no marker rather than an estimated position. Existing dispatch remains unchanged.

## Mục tiêu, phạm vi, prerequisites

Gắn vị trí click worker đã xác nhận với operation và before frame, để UI không suy diễn từ bbox hoặc model proposal. Có thể kiểm độc lập phase 01.

Đọc VisualOperation, worker prepare/execute, schema exporter, repository transition và tests hiện có. Kiểm lại working tree vì contracts/worker/persistence đang được user sửa.

## File cần sửa/thêm

- `packages/contracts/src/auto_at/contracts/vision.py`: model VisualExecutedClick và field optional trên VisualOperation.
- `packages/contracts/export_vision_worker.py`: export model bổ sung nếu cần; regenerate `workers/playwright/src/vision-contract.generated.ts`.
- `workers/playwright/src/vision-contract.ts`: semantic validation tương đương Python.
- `workers/playwright/src/vision-operations.ts`: tạo metadata tại nhánh click được xác nhận, giữ qua finalize/reconcile.
- `apps/control-plane/infrastructure/persistence/repositories.py`: cho phép bổ sung metadata khi finalize operation, kiểm immutability sau terminal.
- `apps/control-plane/infrastructure/persistence/vision_unit_of_work.py`: chỉ sửa nếu đường commit lọc field hoặc cần bảo toàn evidence; không mở rộng transaction qua browser I/O.
- `apps/control-plane/application/vision_results.py`: bảo đảm trace/export công khai đúng safe metadata và liên kết frame.
- `apps/dashboard/app/generation-types.ts`: field optional cho trace reader.
- Tests: `tests/test_vision_contracts.py`, `tests/test_vision_worker_contracts.py`, `tests/test_vision_operation_repository.py`, `tests/test_vision_results.py`, `tests/test_vision_operation_transport.py`, `workers/playwright/src/vision-operations.spec.ts`, `workers/playwright/src/fixtures/vision-target.ts`.

## Contract đề xuất

VisualOperation thêm `executed_click: VisualExecutedClick | None = None`:

| Field | Ý nghĩa |
| --- | --- |
| x, y | Số hữu hạn trong [0,1], điểm viewport đã truyền cho lệnh click được worker xác nhận. |
| viewport_width, viewport_height | Số nguyên dương > 1; viewport CSS pixels tại thời điểm thao tác. |
| before_frame_id | UUID bằng actual_before_frame_id của operation. |
| confirmed_at | Timestamp UTC sau khi locator.click trả thành công. |

Không gọi đây là telemetry chuột native: đây là vị trí lệnh click đã thực thi thành công theo Playwright. Dùng đúng điểm truyền vào locator.click, không dùng tâm bbox. Vị trí pixel là x×(width−1), y×(height−1); UI quy đổi về phần diện tích ảnh bằng cách chia cho width/height. Không nhầm normalized point với tỉ lệ kích thước bbox.

Validator: chỉ action_kind=click; metadata chỉ hiện trên operation finalized completed/failed, có before frame cùng ID, timestamp trong khoảng started_at–ended_at. Failed có thể có metadata nếu click đã hoàn tất nhưng settle/navigation sau đó lỗi. Prepared, executing, rejected, unknown hoặc click ném lỗi thì không phát hành metadata “đã xác nhận”. Thiếu field ở phiên cũ là hợp lệ.

## Hành vi và data flow

1. Giữ nguyên prepare/groundLocator, origin policy, fence, timeout và dispatch exactly-once hiện có.
2. Tại nhánh click, đọc viewport và tính tọa độ từ cùng các giá trị dùng cho call hiện hành. Không thay click sang mouse.click chỉ để vẽ marker, không thêm click/retry/delay vào target.
3. Chỉ tạo metadata sau locator.click resolve. Gắn before frame đã được persist trước dispatch. Nếu geometry/viewport không thể gắn với before frame một cách chắc chắn, bỏ metadata; không đánh dấu một vị trí đoán.
4. Kiểm chứng với fixture có browser click listener rằng tọa độ command và clientX/clientY thực tế trùng trong dung sai, bao gồm target có border, scroll và popup. Listener chỉ ở fixture kiểm thử. Nếu phát hiện Playwright offset khác do border/padding/auto-scroll thì chuyển đổi geometry cho metadata theo điểm thực tế mà click call hiện hữu sử dụng, không sửa hành vi click để ép test pass.
5. Sau navigation/popup, metadata vẫn trỏ before frame của trang nguồn. Không chuyển nó sang after_page_id hoặc screenshot mới.
6. Giữ metadata khi click resolve rồi settle thất bại; UI sau này vẫn báo bước thất bại. Nếu execute có kết quả unknown, không suy luận click đã thành công hoặc replay click để lấy metadata.
7. Persist trong payload JSON theo flow operation hiện tại. Cho phép transition null → confirmed khi finalize; terminal replay/reconcile phải trả cùng metadata, không cho sửa vị trí đã lưu.
8. read_trace và export giữ safe metadata, revision gồm thay đổi metadata. Không lộ proposal text, typed text, storage key, cookie hoặc URL. Các read routes vẫn chỉ đọc, không gọi worker.
9. Dữ liệu cũ/legacy không backfill. Thiếu điểm click hiển thị “Click position unavailable” khi xem lại; vẫn xem được ảnh.

## Compatibility, rollout, vận hành

- Không đổi TestExecutionRequest/TestExecutionResult v1, endpoints /screen hoặc bytes ảnh. Không đổi model/provider/prompt, quyền, consent, secrets, retention hay cost/rate guards.
- Không cần migration cột theo schema hiện tại. Kiểm round-trip repository trước khi kết luận triển khai.
- Python và TS reader mới phải chấp nhận missing field. Reader cũ extra=forbid không chấp nhận JSON có field mới: cập nhật reader/API trước worker writer, đồng bộ exporter.
- Backend downgrade cần giữ patch reader hiểu metadata; không tuyên bố có thể rollback binary cũ ngay, không xóa field lịch sử như một thao tác rollback tự động.

## Tests và validation

- Contract Python/TS: old payload, null, hợp lệ, NaN/Inf/out of range, frame mismatch, trạng thái không hợp lệ, timestamp sai.
- Worker fixture: click thành công, rejected locator, click throw/unknown, settle fail sau click, scroll/border/popup, repeated execute cùng ID không click hai lần và giữ metadata.
- Persistence/transport: round trip, immutability, mismatched scope/frame bị chặn, reconcile không mất metadata.
- API: field qua trace/export, metadata không mở quyền ảnh; xóa ảnh vẫn giữ lịch sử operation nhưng availability=deleted; legacy không có điểm click.

```powershell
uv run python packages/contracts/export_vision_worker.py
uv run ruff check .
uv run pytest tests/test_vision_contracts.py tests/test_vision_worker_contracts.py tests/test_vision_operation_repository.py tests/test_vision_results.py tests/test_vision_operation_transport.py tests/test_execution_contract_fixtures.py
pnpm --filter @auto-at/playwright-worker typecheck
pnpm --filter @auto-at/playwright-worker lint
pnpm --filter @auto-at/playwright-worker test src/vision-operations.spec.ts
```

Xác minh generated output chỉ thay phần dự kiến. Fixtures dùng browser local và mock transport, không provider call.

## Acceptance, rủi ro, non-goals

- Một click confirmed có metadata bền vững, đọc lại đúng frame/point; old sessions vẫn đọc được.
- Metadata không thay đổi lifecycle/verdict, không phát thêm hành động.
- Rủi ro: Playwright position tính theo padding box, auto-scroll hoặc DOM layout thay đổi. Test tọa độ là điều kiện bắt buộc; nếu không xác minh được thì bỏ marker, ghi limitation an toàn.
- Không triển khai live frame metadata protocol, cursor stream, telemetry chuột liên tục hoặc schema mới cho deterministic run.
