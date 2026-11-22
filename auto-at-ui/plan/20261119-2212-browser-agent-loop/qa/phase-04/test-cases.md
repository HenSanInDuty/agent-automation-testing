# Phase 4 - Test cases (agent loop processor + safety)

Ký hiệu: DEV = `tests/test_vision_agent_loop.py` / `tests/test_vision_agent_safety.py` (developer); QA = `tests/test_vision_agent_loop_qa.py`. Tất cả PASS (xem test-report.md). Fake worker áp công thức budget `1+max_states*(2*max_hops+3)`; fake exchange không gọi model thật; DB là PostgreSQL cô lập `127.0.0.1:55437`.

| ID | AC / rủi ro | Nhóm | Tiền điều kiện / bước | Mong đợi | Test | KQ |
|---|---|---|---|---|---|---|
| P4-01 | AC1 | Happy | 3 bước tới `agent_done` | step log 3 dòng đủ field; action bị chặn có `skipped_reason`, không nằm trong `operation_ids`; prompt chỉ có snapshot mới nhất | DEV `test_three_steps_reach_agent_done...` | PASS |
| P4-02 | AC2 | Biên | ref `abc`, `1:`, `:4`, `1:2:3`, `-1:2`, `3: 4`, rỗng | `invalid_ref`, 0 request worker | DEV `refs_with_the_wrong_shape`, `invalid_and_stale_refs...` | PASS |
| P4-03 | AC2 | Biên | ref version cũ / tương lai / index ngoài map / `03:1` / `3:01` | `stale_ref`, 0 prepare/execute | DEV `old_future_unknown...` | PASS |
| P4-04 | AC2 | Biên | snapshot bị cắt, model click ref đã bị cắt (`1:100`) cùng click ref hiển thị (`1:1`) | ref bị cắt = `stale_ref` 0 request; ref hiển thị chạy | QA `loop_caps_the_snapshot_and_a_trimmed_ref_is_stale...` | PASS |
| P4-05 | AC3 | Lỗi | page checkpoint ngoài allowlist; click/type/scroll/navigate | `origin_blocked`, 0 request; `back`, `close_popup` chạy | DEV `page_outside_the_allowlist...` | PASS |
| P4-06 | AC3 | Lỗi | redirect sang origin khác sau click đầu | origin lấy từ `page_url` checkpoint mới; click kế bị `batch_stopped`, bước sau `origin_blocked` | DEV `origin_comes_from_the_page_after_a_redirect` | PASS |
| P4-07 | AC3 | Lỗi | control `input_type` submit/reset tên vô hại ("Continue", "Clear") | `sensitive_action_blocked`, 0 request | QA `loop_blocks_sensitive_controls...` + DEV safety | PASS |
| P4-08 | AC3 | Biên | tên "Xoa tai khoan", "XÓA", "Xóa" NFD, "THANH TOÁN", "Thanh toan", "Đặt hàng", "Log Out" | cả 9 bị chặn, 0 request worker, `operation_ids=[]`, lý do xuất hiện trong history gửi model | QA `loop_blocks_sensitive_controls_in_both_spellings...` | PASS |
| P4-09 | AC3 | Biên | từng term trong `BLOCKED_ACTION_TERMS` (31) x NFC / NFD / HOA | `check_action` chặn `sensitive_action_blocked` (93 ca) | QA `every_blocked_term_blocks_a_click_in_every_spelling` | PASS |
| P4-10 | AC3 | Biên | "Đăng ký", "ĐĂNG KÝ", "dang ky", "Nạp thẻ", "NẠP THẺ", "nap the" | không bị chặn; ở loop vẫn chạy | QA `benchmark_actions_are_not_blocked`, `loop_runs_the_benchmark_actions...` | PASS |
| P4-11 | AC3 | Biên | 47 label oracle mongchiton | 0 bị chặn | DEV safety | PASS |
| P4-12 | AC3 | Lỗi | `type` text email / >=7 chữ số / khoảng trắng đầu / `password=` / có `\r` `\n` | chặn trước worker; text KHÔNG vào step log | QA `type_of_secret_like_text...`, `loop_blocks_secret_text...`; DEV `line_break` | PASS |
| P4-13 | AC3 | Hồi quy | thành phần term: 31 mục <= 40, không trùng, mỗi dạng có dấu có bản không dấu (trừ `gửi` -> `gui di`) | đúng | QA `blocked_terms_fit_the_contract...` | PASS |
| P4-14 | AC4 | Happy/Biên | dừng batch: `stop_cause` cho completed / url_change / popup / download / fingerprint đổi / failed / rejected / unknown / fingerprint None | đúng nguyên nhân | QA `stop_cause_table` (8) + `tolerates_a_missing_result_fingerprint` | PASS |
| P4-15 | AC4 | Lỗi | 6 điều kiện dừng ở loop (url_change, fingerprint, popup, download, failed, rejected) | action sau 0 call worker (`batch_stopped`); bước kế `observe_dom` đúng 1 lần/bước | DEV `batch_stops_on_page_change...` (6) | PASS |
| P4-16 | AC4 | Lỗi | popup rồi `close_popup` trong cùng batch | `close_popup` bị `batch_stopped` với `stop_cause=popup`, không chạy | QA `popup_blocks_the_rest_of_the_batch...` | PASS |
| P4-17 | AC4 | Happy | `type A -> type B` cùng form | cả hai chạy, không dừng | DEV `two_typed_values...`; QA `type_then_type_then_click...` (cả click sau đó) | PASS |
| P4-18 | AC5 | Biên | 100 element tên 120 ký tự + `skipped_count=200`, cap 300..12000 (unicode 3 byte) | `len(text) <= cap`; ref hiển thị = 1..k; marker `[refs v:k+1-v:100 trimmed]` đúng; dòng "200 control ngoài snapshot" | DEV renderer; QA `renderer_never_exceeds_the_cap...` (5 cap) | PASS |
| P4-19 | AC5 | Biên | cap đúng bằng độ dài đầy đủ / ngắn hơn 1 ký tự; `skipped_count=0` | bằng: không marker; ngắn 1: có marker và <= cap; skipped 0: không có dòng "ngoài snapshot" | QA `renderer_cap_boundary_is_exact`, `renderer_without_skipped...` | PASS |
| P4-20 | AC5 | Biên | snapshot/prompt qua loop với `vision_agent_snapshot_chars=4000`, skipped 150 | snapshot gửi model <= 4000, có marker + "150 control ngoài snapshot" | QA `loop_caps_the_snapshot...` | PASS |
| P4-21 | AC5 | Biên | 3 bước vs 15 bước, memory 2000 + goal 500 ký tự | độ dài memory+history <= `2000+5*600`; history <= 5 mục | DEV `history_and_memory_stay_bounded...` | PASS |
| P4-22 | Rủi ro prompt | Biên | worst case 4000 task + 2000 memory + 5x600 + snapshot 24000 + 20 host x255, ký tự 3 byte | `build_prompt` <= 131072 byte | DEV `worst_prompt_fits...` | PASS |
| P4-23 | AC budget | Biên | `max_steps=20` | đúng 20 lần gọi, lần 21 không; `agent_step_limit`; policy 21 bị contract từ chối | DEV `twenty_calls_of_ten_actions...`; QA `policy_above_twenty...` | PASS |
| P4-24 | AC budget | Lỗi | retry sai schema + `need_screenshot` + ảnh dùng chung trần (max 4: malformed, need_screenshot, ảnh, bước kế) | đúng 4 lần gọi, ảnh ở lần 3, kết thúc `agent_step_limit` | QA `retry_and_screenshot_calls_share_one_ceiling`; DEV `every_bridge_call_counts...` | PASS |
| P4-25 | AC budget | Biên | `need_screenshot` ở lần gọi cuối được phép (max 1) có consent | không gọi stage ảnh, `agent_step_limit` | QA `need_screenshot_on_the_last_allowed_call...` | PASS |
| P4-26 | AC budget | Lỗi | `need_screenshot` có / không consent; 2 lần sai schema liên tiếp; stop ngay bước 1; toàn action bị chặn; rate/phút (fake clock); deadline | gọi ảnh / không gọi + note; `bridge_malformed_output`; `agent_stopped`; `agent_step_limit` không treo; sleep 30s x2; `session_timeout` | DEV 7 test tương ứng | PASS |
| P4-27 | AC budget | Biên | `sequence` 1..n liên tục, `step_index` liên tục, `job_id` khác nhau | đúng | QA `every_agent_step_has_a_distinct_job...` | PASS |
| P4-28 | Budget worker | Biên | `max_states=200,max_hops=1` -> 1001 >= 401; 20 x 10 action không `operation_budget_exhausted` | đúng, 201 prepare | DEV `worker_budget_formula...`, `twenty_calls_of_ten_actions...`, `open_request_carries...` | PASS |
| P4-29 | Lease | Lỗi | mất lease giữa 2 model call | `ValueError` lease, không ghi thêm step | DEV `lease_lost_mid_loop...` | PASS |
| P4-30 | Lease | Lỗi | mất lease khi action đang chạy | `ValueError`, step đó KHÔNG được ghi, 1 model call | QA `lease_lost_while_an_action_runs...` | PASS |
| P4-31 | Lease | Lỗi | mất lease trước observe bước 2 | `ValueError`; chỉ step 1 trong log, không ghi step 2 | QA `lease_lost_before_the_next_observation_never_writes...` | PASS |
| P4-32 | Lease | Hồi quy | event giao lại sau crash | chỉ reconcile (`worker_state_unavailable`), không trùng `step_index`, lần 2 `already_processed` | DEV `redelivery_after_a_crash...` | PASS |
| P4-33 | AC dispatch | Hồi quy | `exploration_engine` planner / agent_loop / thiếu thuộc tính | planner / agent / planner; `handler` ghi đè cả hai | DEV `dispatch_picks_the_processor...` | PASS |
| P4-34 | AC dispatch | Lỗi | session planner đưa vào processor agent | `ValueError`, 0 call worker, 0 model call, 0 step | QA `planner_session_is_refused...` | PASS |
| P4-35 | AC dispatch | Hồi quy | cột `exploration_engine` default `planner`, NOT NULL | đúng | QA `session_with_no_engine_column_value_defaults_to_the_planner` | PASS |
| P4-36 | AC6/7 | Hồi quy | không op `restore`/`replay`; click/type có binding + purpose `explore`; `export_operation` chấp nhận mọi op | đúng | DEV (3 test) | PASS |
| P4-37 | AC7 | Hồi quy | trace: agent có `agent_step`, planner không | đúng | DEV `trace_adds_agent_step_for_agent_sessions_only` | PASS |
| P4-38 | AC1 | Lỗi | secret trong evaluation/memory/next_goal | `[REDACTED]` trong step log | DEV `secrets_in_model_text...` | PASS |
| P4-39 | AC4 | Lỗi | op `unknown` giữa batch | session kết thúc `action_outcome_unknown`, phần đã chạy vẫn nằm trong log | DEV `lost_action_outcome...` | PASS |
| P4-40 | AC7 | Hồi quy | 12 file test v4 trong "Tiêu chí xong" | xanh | xem test-report.md | PASS |
| P4-41 | AC7 | Hồi quy | sha256 identity v4 (`tests/fixtures/v4_identity.json`) | khớp | `test_agent_loop_contracts.py -k "sha256 or baseline or identity"` | PASS |

Chưa kiểm được (không thuộc phạm vi hành vi offline): `agent_step` qua `/trace` route thật (xem test-report.md mục "Vấn đề").
