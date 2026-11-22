# Phase 04 — r18 test cases (QA r7)

Automation mới: `workers/playwright/src/vision-tsx-runtime.qa.spec.ts` + `src/fixtures/vision-tsx-runtime-flow-probe.ts` (chạy dưới tsx thật, cùng transform `npm run start`).

| ID | Nhóm | Tiền điều kiện / bước | Mong đợi | Thực tế | KQ |
|---|---|---|---|---|---|
| T1 | Happy | tsx: open -> navigate -> observeDom -> prepare click -> execute -> close, trang có pulse (ADR-042) | nav completed, prepare prepared, execute completed, #out = "đã bấm", page closed | đúng (outcome `observed`) | PASS |
| T2 | Happy | như T1, trang tĩnh | như T1 | đúng | PASS |
| T3 | Lỗi | tsx, mọi `page.evaluate` ném ReferenceError (message chứa URL/token/text) tại open qua HTTP handler | 422 `visual_request_rejected`; log `error_type=unexpected_error`, `error_name=ReferenceError`, `error_origin=page.evaluate`, `error_digest` 8 hex, không lộ message | đúng, leaked=false | PASS |
| T4 | Biên | trang tự định nghĩa `globalThis.__name = function pageOwnName` | shim không ghi đè; flow vẫn completed | `__name.name === "pageOwnName"`, execute completed. Hành vi: shim chạy trước script trang, nên định nghĩa của trang thắng (không phải do `||`) | PASS |
| T5 | Biên | trang không định nghĩa `__name` | `typeof __name === "function"` (shim) | function | PASS |
| T6 | Biên | tiếng Việt có dấu ("Bấm thử", "đã bấm") | khớp NFC | đúng | PASS |
| T7 | Hồi quy | `vision-tsx-runtime.spec.ts` (dev) | pass | pass | PASS |
| T8 | Hồi quy | preflight, sample-guard, visual-buttons, locators, vision.spec, click-evidence `--workers=1` | pass | 39 + 20 pass | PASS |
| T9 | Hồi quy | settle + operations `--workers=1` | pass | 140 pass (7.5m) | PASS |
| T10 | Hồi quy | `npx tsc --noEmit`, eslint file mới | exit 0 | exit 0 | PASS |
| T11 | Thật | open+close tới mongchiton.vn dưới tsx (`r17-open-probe.mts`, không click), 2 lần | OK | OK 282 ms, OK 582 ms | PASS |
| T12 | Fix | tái hiện bug cũ (`__name is not defined` dưới tsx) | fail trước fix, pass sau | red của dev ghi trong be-developer-r18 (spec cũ fail trước fix); QA không revert product code nên không tự dựng lại red. Sau fix T1-T3 pass | PASS (dựa trên bằng chứng dev) |

Ghi nhận: lỗi evaluate xảy ra trong `prepare` (sau open) không thành 422 `unexpected_error` mà worker bắt và trả 200 `status=rejected, outcome_code=prepare_failed`; chỉ lỗi ở open/observe/screen... lên tới handler. Không phải lỗi của r18, chỉ ghi nhận.
