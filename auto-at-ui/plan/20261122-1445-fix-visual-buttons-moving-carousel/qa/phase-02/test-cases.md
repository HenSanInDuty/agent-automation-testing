# Phase 02 — test cases (QA r1)

Cwd `workers/playwright` trừ khi ghi khác. Spec: `src/vision-dom.spec.ts` (automation nằm sẵn trong repo, QA không thêm file mã).

| ID | Tiêu chí | Cách kiểm | Mong đợi | Kết quả |
|---|---|---|---|---|
| P2-01 | T-loop-lost: ứng viên lần đầu trượt ra, không có bản sao tương đương trọn viewport | spec `T-loop-lost` x20 (workers=4) | `skipped_count` 1, `motion_retraversals` 1 | PASS 20/20 |
| P2-02 | T-loop-out giữ 0 skip (hàng rào chống đảo ngược A2) | spec `T-loop-out` x20 | `skipped_count` 0, retraversals 1 | PASS 20/20 |
| P2-03 | T-loop-jump giữ 0 skip | spec `T-loop-jump` x20 | bind được, skip 0 | PASS 20/20 |
| P2-04 | Test đặc tả duyệt giữa lúc trượt | spec "a walk made while no copy is fully..." x20 | không ứng viên, không skip (giới hạn đã biết) | PASS 20/20 |
| P2-05 | Giới hạn: tối đa một lần duyệt lại, chờ có trần | spec "never stops within the wait" + code `vision-dom.ts` `motion.retraversals > 0` break | bounded delay, không lặp vô hạn | PASS (x20) |
| P2-06 | Dispose handle ở mọi nhánh | spec "failed DOM collection releases grounded targets..." + đọc code (dispose trước khi duyệt lại, `finally`) | không rò | PASS (48/48 spec đầy đủ) |
| P2-07 | Khoá "tương đương" = role+name+button_kind (user chấp nhận khe hở href, ghi ADR) | đọc code vision-dom.ts khối `twins` | multiset, mỗi element phủ một miss | PASS (chấp nhận theo user) |
| P2-08 | Contract không đổi, chỉ 4 file phạm vi | git status | chỉ 4 file + preflight/log đã có | PASS |
| R-01 | 6 test chuyển động cũ (TC-01..06) | spec x20 workers=4 | xanh | PASS |
| R-02 | Toàn `vision-dom.spec.ts` | 1 lượt | 48/48 | PASS |
| R-03 | `tsc --noEmit` | | exit 0 | PASS |
| R-04 | `vision-visual-buttons.spec.ts` | | 3 pass | PASS |
| R-05 | `vision-settle-animation.spec.ts` | | 14 pass | PASS |
| R-06 | `vision-operations.spec.ts` | workers=4 | 99 pass | PASS |
| R-07 | Manifest hash | `run_offline.py -k manifest` | 1 passed | PASS |
| R-08 | Graph | `hgraph check` | sạch | PASS (`--changed` báo uncovered-changed do lệch tiền tố, đã biết) |
| L-01..L-03 | Harness live trên bản sao có chẩn đoán, 3 lần x 40 quét (30 scan@1152 + 10 click) | `ab.mts fixed 10 30` | 0 skip | PASS: withSkip 0/120, errors 0 |
| L-04 | Dòng visible-but-unbound có `skipped>0` hoặc giải thích bằng duyệt-giữa-lúc-trượt | log `s4-ab-p2-qa-3.log` dòng 127 | giải thích được | PASS, kết luận (a), xem report |
| L-05 | Luật mới hoạt động live: ứng viên lost có twin → không skip | DIAG end `lost:1, skipped:0` | 6 lần/120, đều skip 0 | PASS |
| N-01 | Tái hiện bug phase-02 trên code phase-01 (đỏ trước sửa) | dựa bằng chứng dev (T-loop-lost 1 failed Expected 1 Received 0) | đỏ trên A2 phase-01 | Không tự chạy lại (không có bản code cũ tách riêng); dựa dev |
| N-02 | Stress | không cần: thay đổi không đụng vòng lặp lớn/transaction; duyệt lại có trần 1 | n/a | n/a |
