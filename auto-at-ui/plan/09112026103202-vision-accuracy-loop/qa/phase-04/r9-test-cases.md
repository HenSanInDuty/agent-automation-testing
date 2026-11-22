# Phase 04 r9 - test cases (receipt clock skew, ADR 041)

Automation: `tests/test_qa_r9_bridge_receipt.py` (+ 4 test dev trong `tests/test_codex_bridge_spool.py`). `now` = đồng hồ bridge truyền vào `stop_reason`.

| ID | Nhóm | Điều kiện / bước | Mong đợi | Kết quả |
|---|---|---|---|---|
| T01 | Happy | `RECEIPT_CLOCK_SKEW` | = 1 s | PASS |
| T02 | Biên | recorded_at = now+1s đúng biên, ttl 5 s | None (chấp nhận) | PASS |
| T03 | Biên | recorded_at = now+1s+1us | bridge_policy_revoked | PASS |
| T04 | Biên | recorded_at = now+5s / +10min / +1day | revoked | PASS (3) |
| T05 | Happy | recorded_at = now-1s, expiry now+5s | None | PASS |
| T06 | Lỗi | receipt hết hạn (expiry < now; expiry == now) dù trong skew | revoked | PASS |
| T07 | Lỗi | thiếu authorization.json | revoked | PASS |
| T08 | Biên | file rỗng / `{not json` / `[]` / `null` | không bao giờ trả None (raise hoặc revoked) | PASS (4) |
| T09 | Lỗi | now >= deadline (== và +1s) kèm receipt hợp lệ | bridge_deadline_exceeded | PASS |
| T10 | Lỗi | expiry receipt > deadline | revoked | PASS |
| T11 | Lỗi | ttl 11 s / 60 s / 3600 s | revoked | PASS (3) |
| T12 | Biên | ttl = 0 (expiry == recorded_at) | revoked | PASS |
| T13 | Lỗi | status "claimed" thay "queued" | revoked | PASS |
| T14 | Lỗi | now < request.created_at | revoked | PASS |
| T15 | Revoke thật | stream: 5 poll xanh, xoá authorization.json; rồi lease 300 ms không re-sign, đợi 0.4 s | revoked ở poll kế; skew không kéo dài lease | PASS |
| T16 | Revoke thật | cancel.json trong lúc stream | bridge_cancelled | PASS |
| T17 | Đồng thời | thread re-sign liên tục (~12 ms/lần trên Windows, nhanh hơn 2 s của control-plane) + 1500 poll với now lấy trước khi đọc | 0 revoked sai | PASS (1414 poll, 0 revoked) |
| T18 | Đồng thời | như T17, nhịp 2 ms | 0 revoked sai | PASS |
| T19 | Đồng thời | poll chậm (now lấy rồi trễ 30 ms mới đọc) + re-sign liên tục, skew thật | 0 revoked sai | PASS |
| T20 | Hồi quy bug | T19 nhưng monkeypatch skew=0 (hành vi cũ) | revoked sai xuất hiện | PASS: 76/76 và 78/78 poll bị revoked sai (đỏ trên code cũ) |
| T21 | Tham khảo | T17 với skew=0 | không assert đỏ (cửa sổ race ~us, xác suất thấp) | 0/1406 revoked: race nguyên bản khó tái hiện trên máy này |
| T22 | Hồi quy | `ruff check .` | sạch | PASS |
| T23 | Hồi quy | bridge/claude/agent-loop bridge suites | không đỏ do r9 | 253 passed, 46 skipped, 1 failed (benchmark manifest cũ, xem report) |
