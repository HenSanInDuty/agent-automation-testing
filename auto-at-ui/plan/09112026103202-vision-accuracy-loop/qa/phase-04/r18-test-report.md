# Phase 04 — r18 test report (QA r7)

Verdict: PASS (12 case, pass 12 / fail 0). Môi trường: Windows 11, Node 24.12, Playwright 1.50.1, tsx 4.19.2, chromium local.

Output chính:
- `npx playwright test vision-tsx-runtime --workers=1` -> `5 passed (13.3s)` (1 dev + 4 QA).
- Probe tsx dòng cuối: pulse/static/own_name đều `nav completed, prepare prepared, execute completed, text "đã bấm", closed true`; `http {status 422, detail visual_request_rejected}`; `log {error_type unexpected_error, error_name ReferenceError, error_origin page.evaluate, error_digest 30352e3b, leaked false}`; exit 0.
- preflight+sample-guard+visual-buttons+locators+vision.spec+click-evidence: `39 passed (30.5s)`; click-evidence+sample-guard+locators chạy riêng `20 passed`.
- settle + operations `--workers=1`: `140 passed (7.5m)`.
- `npx tsc --noEmit` exit 0; eslint file mới exit 0.
- mongchiton qua tsx, open+close: `OK 282 ms`, `OK 582 ms`.
- `hgraph add playwright-vision-worker` 2 file mới -> tổng 36; `hgraph check` -> "Không có vấn đề".

Graph `--changed`: vẫn exit != 0, 72 file liệt kê `uncovered-changed` với tiền tố `auto-at-ui/` (git root cao một cấp) cùng file Python/dashboard của phase khác; không file test/product nào của r18 nằm trong danh sách; không có drift/stale-file. Đây là sai lệch đường dẫn của công cụ, không phải thiếu graph của r18.

Chưa test được / giới hạn:
- Live container (`playwright-worker` rebuild + open 200) — bị cấm chạm docker; main session làm theo be-developer-r18.
- Red của bug cũ không dựng lại bằng QA (không revert product code); dựa vào bằng chứng dev.
- Stress test: không cần — không đổi vòng lặp/transaction/endpoint nóng.
- Lỗi evaluate trong prepare trả 200 prepare_failed (ghi nhận, ngoài phạm vi r18).
- Tiến trình: các script tự thoát, không còn chrome/tsx.
