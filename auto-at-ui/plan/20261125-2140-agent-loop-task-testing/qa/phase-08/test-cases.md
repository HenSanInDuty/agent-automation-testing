# Phase 08 — test cases (QA)

Automation: `tests/test_qa_p08_agent_task_trace.py` (48 case, tên `test_p08_*`), dùng builder `Rows` của developer (chỉ đọc). Kết quả lần chạy cuối: 46 pass, 2 xfail (strict, là finding).

| AC | ID | Loại | Bước / dữ liệu | Mong đợi | Kết quả |
| --- | --- | --- | --- | --- | --- |
| 1 | T1-1 | happy | dựng login 2 step, validate lại JSON | round-trip bằng nhau, hash kiểm lại | PASS (test dev + `extra_forbid` QA) |
| 1 | T1-2 | âm | `zz_extra` ở 7 mô hình lồng (trace, assessment, facts, check, step, outcome, locator) | ValidationError | PASS `test_p08_extra_forbid_on_every_nested_model` |
| 1 | T1-3 | âm | sửa từng trường (tenant, url, outcome, kind, bỏ step, đảo, status) giữ hash cũ | ValidationError; seal lại cho hash khác | PASS `test_p08_hash_changes_on_each_single_field...` |
| 1 | T1-4 | âm | gán `trace.target_url=`/`steps[0].kind=` | ValidationError (frozen) | PASS `test_p08_trace_is_frozen` |
| 2 | T2-1 | happy | step 2 có action skip đầu/giữa/NoResult, step 1 có skip giữa, step 3 rỗng, step đưa vào đảo | thứ tự step_index rồi operation_ids | PASS `..._order_skipped_action...` |
| 2 | T2-2 | biên | `operation_ids` ngược `sequence` | theo log, không theo sequence | PASS |
| 2 | T2-3 | âm | cùng operation ở 2 step | `evidence_unavailable` | PASS |
| 2 | T2-4 | âm | purpose `replay` (không explore/setup) | `evidence_unavailable` | PASS |
| 3 | T3-1 | âm | `unknown` ở step 4 | `action_outcome_unknown`, step_index=4, operation_id | PASS |
| 3 | T3-2 | âm | click+type x {locator absent, ambiguous, dom_path, after deleted, failed, rejected, unknown} (14 case) | mã đúng từng ca | PASS `test_p08_codes_for_both_targeted_kinds` |
| 3 | T3-3 | âm | scroll/wait/navigate không locator: build OK; after frame đã xoá | OK / `evidence_unavailable` | PASS |
| 3 | T3-4 | âm | frame trước bị tombstone | `evidence_unavailable` | PASS |
| 3 | T3-5 | âm | `back`, `close_popup` | `action_unsupported` | PASS |
| 3 | T3-6 | âm | state failed, engine script, assessment là str/list/{}/vượt giới hạn checks/status lạ | `assessment_unavailable` | PASS |
| 3(a) | T3a | biên | setup giữa step, sau step cuối (unknown, không thuộc step nào) | không thành step, không từ chối | PASS |
| 3(b) | T3b-1 | biên | skip có `stop_reason=url_change`, 2 skip | chỉ phần đã chạy | PASS |
| 3(b) | T3b-2 | âm | entry `result: None` không có operation id | `evidence_unavailable` (log không khớp) | PASS |
| 3(c) | T3c-1 | happy | wait completed | giữ, `duration_ms=500`, locator/text/delta null trong JSON | PASS |
| 3(c) | T3c-2 | biên | chỉ có một wait | trace hợp lệ | PASS |
| 3(d) | T3d-1 | âm | step 2 `worker_result_mismatch`, mọi op khác hợp lệ | `evidence_unavailable`, step_index=2 | PASS |
| 3(d) | T3d-2 | âm | op explore mồ côi sau chuỗi hợp lệ | `evidence_unavailable`, operation_id = mồ côi | PASS |
| 3 | T3-7 | biên | `delta_y`/`duration_ms`/`text_chars` = -1, 0, 1e7 | từ chối `evidence_unavailable` hoặc trace hợp lệ, không crash | PASS |
| 3 | T3-8 | âm | `operation_ids[0]="not-a-uuid"` | `AgentTaskTraceRefused` | **FAIL nhẹ (xfail)**: `ValueError: badly formed hexadecimal UUID string` thô, `domain/agent_task_trace.py:130` |
| 3 | T3-9 | biên | `target_url` 2100 ký tự | từ chối có mã hoặc ValidationError | PASS (ValidationError, không phải refusal có mã; ghi chú) |
| biên | TB-1 | unicode | locator tiếng Việt + emoji + 200 ký tự | giữ nguyên, round-trip JSON | PASS |
| 4 | T4-1 | âm | nhét `text/value/typed/ref/x/y/executed_click` vào action và result của mọi step | không xuất hiện sentinel, `7:9`, toạ độ, `version:`, key cấm | PASS |
| 4 | T4-2 | âm | locator row có bounding_box, sentinel ở `text` của operation | không có trong JSON | PASS |
| 4 | T4-3 | âm | giá trị gõ nằm trong `summary` và `checks[].evidence` | KHÔNG lọt | **ghi nhận: lọt** (`test_p08_FINDING_...` khẳng định đếm 2 lần) |
| 4 | T4-4 | âm | ref agent `1:7` trong `summary`/`evidence` | không có trong gói vết | **FAIL (xfail strict)**: lọt; xảy ra thật ở phiên cục bộ e660f6a3 |
| 5 | T5-1 | happy | dựng hai lần | cùng hash | PASS |
| 5 | T5-2 | âm | đổi 1 locator, hoán locator hai step, đổi thứ tự, text_chars, assessment, intent | hash đổi | PASS (dev + QA) |
| 5 | T5-3 | biên | delta_y, duration_ms có trong hash | field-level | PASS |
| 6 | T6-1 | happy | DB thật (55437): vòng agent giả, đọc gói vết, không giá trị gõ, hash kiểm lại | OK | PASS `test_p08_real_db_scope_and_invariants` |
| 6 | T6-2 | âm | tenant khác, tenant rỗng, project khác, session khác, cả ba khác | `AgentTaskTraceNotFound` | PASS (5 scope) |
| 6 | T6-3 | hồi quy | phiên chưa xong (state=unavailable) | `assessment_unavailable` | PASS (test dev) |
| 7 | T7-1 | graph | `hgraph check` / `check --changed` | sạch cho file phase 08 | PASS (xem report; `--changed` còn dương tính giả cũ) |
| 8 | T8-1 | hồi quy | handoff, assessment, results + trace | không hồi quy | PASS 148 pass / 2 xfail / 0 skip |
| 8 | T8-2 | lint | `ruff check .` | sạch | PASS |
| local | TL-1 | đọc DB cục bộ | 217 phiên agent_loop, `READ ONLY` | bất biến | 1 vi phạm (T4-4), còn lại OK |

## Vòng 2 (thêm)
| ID | Nhóm | Bước | Mong đợi | Kết quả |
|---|---|---|---|---|
| P08-R2-01..42 | Biên/AC4 | 14 dạng ref x summary/expectation/evidence | không còn `\d+:\d+` trong JSON gói vết, trường vẫn có nội dung | PASS |
| P08-R2-43 | Xác định | dựng 2 lần cùng dữ liệu, seal lại | cùng trace_hash, kiểm lại được | PASS |
| P08-R2-44 | Biên | text 1000 ký tự đầy ref | dựng được, sạch ref | PASS |
| P08-R2-45 | Lỗi | target_url > 2000 | Refused evidence_unavailable | PASS |
| P08-R2-46 | Hồi quy | 2 test xfail vòng 1 (summary ref, operation_id không UUID) | pass sau gỡ xfail | PASS |
| P08-R2-47 | Replay | 217 phiên DB cục bộ chỉ đọc | 169/3/45, 0 ref | PASS |
