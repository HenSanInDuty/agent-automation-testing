STATUS: DONE

CONTEXT_CHECK: ok

```
CONTEXT_CHECK
- conventions: docs/code-standards.md (chỉ mục sang AGENTS.md; AGENTS.md đã đọc). Không có docs/api-conventions.md. Phạm vi là worker TS, không áp dụng luật control-plane Python.
- graphs: playwright-vision-worker
- blast radius: 30 file phụ thuộc (depth 2) / 7 file nó phụ thuộc (hgraph brief vision-dom.ts + vision-checkpoints.ts)
```

Impact: Database không đụng. Contract không đổi (chữ ký observeDom/DomSnapshot, response, env). Không file mới/xoá. Chỉ 4 file trong phạm vi.

## Diff (so với trạng thái phase-01 chưa commit)
- `workers/playwright/src/vision-dom.ts`: +18 / -4
  - `lost` (danh sách ứng viên lần đầu bị chuyển động làm hỏng); `ground()` trả thêm `invalidates` (đặt cùng chỗ đặt `motion.invalidated`).
  - Nhánh skip trong vòng collection: tách `code` (cùng danh sách lý do cũ), `skip(code)`, và nếu `item.value.invalidates && motion.retraversals === 0` thì `lost.push`. Chỉ thu ở lượt đầu nên lượt hai không đếm đôi.
  - Sau vòng `for(;;)`, trước `inspectState`: mỗi `lost` ghép với một element đã bind cùng role+name+button_kind (mỗi element phủ một entry). Không có twin: `skip(reason)` + `unsupported.add("unbound_target")` rồi `coverage_limited` được log như thường.
  - Handle: không thêm handle mới; dispose mọi nhánh giữ nguyên (đường duyệt lại dispose như phase-01, `finally` cũ).
- `workers/playwright/src/vision-dom.spec.ts`: +31 / -4. `observeLoopSwiper` thêm mode `lost` (track dừng ở -1050 giữa hai slide) và `between` (đứng sẵn ở -1050, không chuyển động). Test mới: `T-loop-lost`, "a walk made while no copy is fully in the viewport finds nothing and skips nothing" (đặc tả giới hạn).
- `docs/adr/045-observe-moving-visual-buttons.md`: +29 / -0 (mục A2.5, hai dòng Limits, hai dòng Tests).
- `benchmark/vision/codex/manifest.json`: 2 hash. `vision-dom.ts` 25a85fccb45b29b04318788e44ae6d3ea9e5a2f0de45b24e1d14e660719eff84; `vision-dom.spec.ts` 776887772fde85c0aedc41ed79965b2fe8727eecdfe430369b286289f5d8c2f0.

## Đỏ trước khi sửa (code A2 phase-01, test đã viết)
```
  x  1 src\vision-dom.spec.ts:396:1 › T-loop-lost: a copy that slid out with no equivalent copy fully on show stays a counted skip (1.1s)
  ok 2 src\vision-dom.spec.ts:411:1 › a walk made while no copy is fully in the viewport finds nothing and skips nothing (262ms)
    > 401 |   expect(observation.skipped_count).toBe(1);
    Expected: 1   Received: 0
  1 failed / 1 passed
```
Test đặc tả xanh trên code cũ như kỳ vọng (hành vi hiện có: không ứng viên, không skip).

## Kết quả (cwd workers/playwright)
- `npx tsc --noEmit`: exit 0, không output.
- `vision-dom.spec.ts` toàn file: `48 passed (28.6s)`.
- Chuyển động + T-loop + test đặc tả (`-g "visual button|T-loop|static visual|no copy is fully"`, 10 test x 20): `--workers=1`: `200 passed (3.6m)`; `--workers=4`: `200 passed (59.6s)`. 0 flaky.
- T-loop-out và T-loop-jump vẫn `skipped_count` 0 (nằm trong 200 lượt đó).
- `vision-visual-buttons.spec.ts` + `vision-settle-animation.spec.ts`: `17 passed (12.0s)` (3 + 14).
- `vision-operations.spec.ts`: `99 passed (6.1m)`.
- eslint 2 file: `vision-dom.ts` sạch; `vision-dom.spec.ts` 6 lỗi `no-explicit-any` ở dòng 440-477 (test cũ "failed DOM collection...", có từ trước, không phải code tôi, không sửa).
- Manifest: `1 passed, 9 deselected in 0.19s`, `summary passed 1 failed 0`.
- `hgraph check`: `6 graph, 474 file source / ✔ Không có vấn đề.`

## Khoá danh tính đã tái dùng (phải đọc)
Phase yêu cầu dùng đúng khoá của fingerprint `visual_buttons` (`vision-checkpoints.ts:162-168`, danh sách ở :99-104). Khoá đó nằm trong callback trình duyệt, không export, và ứng viên của walk không mang danh sách attribute. Nên tôi chỉ dùng phần danh tính mà ứng viên và element đã bind cùng có: `role` (từ tag/role), `name` (aria-label, labelled-by, title, text) và `button_kind` (từ tag). Hệ quả: hai link cùng chữ cùng loại nhưng khác `href` bị coi là twin (có thể che một miss). Đã ghi trong ADR Limits. Đóng được khe này cần export khoá từ `vision-checkpoints.ts` (ngoài 4 file của phase này) — để leader quyết.

## Ladder
- Không file/dependency/helper export mới. `lost`: mảng cục bộ, không class. Tái dùng `skip`, danh sách lý do skip sẵn có (chỉ gán `code`), `motion.invalidated`, `motion.retraversals` (chặn đếm đôi), `unsupported`. Twin dùng multiset bằng `indexOf`+`splice` trên mảng khoá chuỗi, không Map/hàm riêng.
- Loại: sửa `skipped = found.skipped` thành cộng dồn mù (đảo ngược A2), và thêm field identity vào walk (chế tiêu chí mới).
- Giới hạn có trần: một lần duyệt lại (comment `ponytail:` phase-01 giữ nguyên).

## GRAPH_UPDATE
- graph đã cập nhật: không cần — không thêm/xoá file, không đổi import
- file mới đã đưa vào graph: không có
- `hgraph check`: `✔ Không có vấn đề.` (`--changed` vẫn báo uncovered-changed vì lệch tiền tố đường dẫn như phase-01; không chạy lại)

## Dọn dẹp
Không mở tiến trình/server/docker. Bản sao so sánh nằm ở scratchpad.
