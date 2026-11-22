# Phase 04 QA r1 — test cases (refresh đọc-chỉ off-origin)

Worker spec: W = `workers/playwright/src/vision-agent-mode.spec.ts`, Q = `vision-agent-mode.qa.spec.ts` (QA-W20/W21 do QA thêm). Control-plane: `tests/test_vision_agent_loop.py` (L), `tests/test_vision_agent_loop_qa.py`.

| ID | Nhóm | Mô tả / dữ liệu | Mong đợi | Test | Kết quả |
|---|---|---|---|---|---|
| A1 | (a) happy | popup ngoài allowlist, DOM đổi -> observeDom state_mismatch; refresh setup+wait+refresh_observation | completed, executed_click null, observe lại thấy tên mới, không POST ngoài, `dataset.clicked` undefined | W "only the read-only observation refresh..." | PASS |
| A2 | (a) | QA-W20 cuối: refresh hợp lệ sau chuỗi bị từ chối | completed, executed_click null, posts rỗng | Q QA-W20 | PASS |
| B1 | (b) | click off-origin (ref) | rejected origin_blocked | W "a popup outside the allowlist..." | PASS |
| B2 | (b) | type off-origin | origin_blocked | W popup test | PASS |
| B3 | (b) | scroll / navigate off-origin | origin_blocked | W popup test | PASS |
| B4 | (b) | wait explore thường | origin_blocked | W refresh test | PASS |
| B5 | (b) | wait setup không cờ refresh | origin_blocked | W refresh test | PASS |
| B6 | (b) | refresh với purpose=explore | origin_blocked | W refresh test | PASS |
| B7 | (b) | click/type gắn cờ refresh (+ref, state_id, proposal_id) | origin_blocked, executed_click null | Q QA-W20 | PASS |
| B8 | (b) | scroll/navigate gắn cờ refresh | origin_blocked | W + Q QA-W20 | PASS |
| B9 | (b) | refresh wait kèm proposal_id / dom_snapshot / expected_locator / restore / replay / thiếu checkpoint | rejected invalid_observation_refresh hoặc origin_blocked (hoặc invalid_contract do validator), không thực thi | Q QA-W20 | PASS |
| B10 | (b) | refresh với fingerprint sai off-origin | rejected state_mismatch | Q QA-W20 | PASS |
| B11 | (b) | sau refresh, click vẫn origin_blocked; close_popup vẫn chạy | origin_blocked / completed | W | PASS |
| C1 | (c) trong-origin | refresh kèm proposal_id | invalid_observation_refresh | Q QA-W21 | PASS |
| C2 | (c) | refresh hợp lệ, rồi click thường "Đổi nội dung" | completed; DOM đổi | Q QA-W21 | PASS |
| C3 | (c) | toàn bộ 143 spec worker cũ (agent + v4) | không đổi | 3 file spec | PASS |
| D1 | (d) chuỗi r5 | click rời origin -> state_mismatch -> 1 refresh -> agent_done | safe_failure_reason agent_done, 1 refresh, không origin_blocked | L test_a_stale_read_off_origin_is_refreshed... | PASS |
| D2 | (d) | off-origin chỉ gửi refresh wait, click/type/wait thường skip origin_blocked | prepares sau click = [wait+refresh] | L test_only_the_refresh_wait_is_sent... | PASS |
| D3 | (d) | trong origin vẫn refresh bằng wait | agent_done, 1 refresh | L test_a_stale_read_inside... | PASS |
| E1 | (e) | không bao giờ settle (3 state_mismatch) | terminal state_mismatch; observe_dom = 1+REFRESH_ATTEMPTS; refresh = REFRESH_ATTEMPTS-1 | L test_an_off_origin_read_that_never_settles... | PASS |
| F1 | (f) hồi quy | toàn bộ test agent loop + QA + live persistence (219 case, Postgres cô lập) | xanh | pytest | PASS |
| F2 | (f) | ruff, tsc | sạch | lệnh | PASS |

Lưu ý trung thực: test L (d/e) xanh cả trên control-plane gốc vì FakeWorker áp luật worker mới (dev đã nêu); bằng chứng đỏ->xanh thật nằm ở worker spec A1 (đỏ trên luật cũ theo dev r4). QA không chạy lại bản đỏ (không sửa source ứng dụng).
