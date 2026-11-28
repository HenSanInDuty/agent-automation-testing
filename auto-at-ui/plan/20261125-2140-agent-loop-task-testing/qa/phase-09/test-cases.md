# Phase 09 test cases (QA)

File: `tests/test_qa_p09_agent_task_consistency.py` (94 items: 93 pass, 1 xfail strict). All DB/HTTP cases run on Postgres 127.0.0.1:55437 (0 skip).

| AC | ID | Nhóm | Bước / dữ liệu | Mong đợi | Kết quả |
|---|---|---|---|---|---|
| 1 | test_ac1_all_denials_are_byte_identical_to_not_found | đường lỗi | GET phiên có thật với principal: không grant, project khác, tenant khác, service (tenant admin), service (project) vs GET uuid không tồn tại | status 404, body và header (trừ date/correlation/traceparent) giống hệt | PASS |
| 1 | test_ac1_session_of_another_tenant_is_not_found_and_identical | đường lỗi | phiên của tenant-b gọi bằng tenant-a | giống hệt 404 "không tồn tại" | PASS |
| 1 | test_ac1_success_has_no_store_and_each_role_with_read_gets_200 | happy | viewer/contributor/reviewer/project_admin | 200 + `Cache-Control: private, no-store` | PASS |
| 1 | test_ac1_a_bad_uuid_is_422_not_a_500 | biên | id không phải uuid | 422 | PASS |
| 1 | test_ac1_response_carries_no_task_text_or_urls | rò rỉ | quét body | không URL/hash/ciphertext | PASS |
| 1,2 | test_group_excludes_other_tenant_project_url_intent_and_engine | cách ly | thêm phiên khác tenant / project / url / url hoa / intent / engine planner cùng nhóm 3 phiên | chỉ 3 phiên vào nhóm | PASS |
| 2 | test_denominator_ignores_unassessed_or_unfinished_sessions x12 | mẫu số | thêm 1 phiên: unavailable (có/không assessment), running, cancelled, failed, completed không assessment, status lạ, status HOA, assessment là chuỗi, `{}`, status null, status là list | assessed vẫn 3, group 4 (11 ca); ca status là list không 500 | 11 PASS, 1 XFAIL strict (xem ghi chú L1) |
| 2,4 | test_source_without_assessment_is_refused_not_crashing | biên | nguồn unavailable / completed không assessment | `source_not_modal`, source_status null | PASS |
| 2,4 | test_planner_session_as_source_is_refused | biên | nguồn engine planner | refused source_not_modal | PASS |
| 2 | test_group_without_any_assessed_session | biên | nhóm 0 phiên có assessment | rate null, eligible false, small_sample | PASS |
| 4 | test_reason_assessment_inconsistent_only | reason | 4 achieved + 1 blocked | `[assessment_inconsistent]` | PASS |
| 4 | test_reason_modal_not_achieved_only | reason | 10 not_achieved | `[modal_not_achieved]` | PASS |
| 4 | test_reason_source_not_modal_only | reason | 9 achieved + 1 not_achieved, nguồn = not_achieved | `[source_not_modal]` | PASS |
| 4 | test_reasons_combine_all_three_in_fixed_order | reason | blocked,blocked,achieved, nguồn achieved | 3 reason, thứ tự cố định | PASS |
| 3,4 | test_threshold_boundary_nine_of_ten_is_eligible_at_0_9_like_stability | biên | 9/10, ngưỡng 0,9 | eligible (>= như stability.py:187) | PASS |
| 3 | test_threshold_boundary_just_above_and_below | biên | 9/10 với 0,91 / 0,9 / 1 | false / true / false | PASS |
| 3 | test_threshold_one_requires_unanimity | biên | 4/4 với 1,0 | eligible | PASS |
| 3 | test_threshold_comes_from_env_through_settings | cấu hình | env AGENT_TASK_CONSISTENCY_THRESHOLD=0.75; bỏ env | 0.75; mặc định 0.9 | PASS |
| 3 | test_invalid_threshold_is_rejected_when_building_settings x10 | đường lỗi | 0, 0.0, -0.1, -1, 1.0001, 2, 90, "abc", "nan", "inf" | ValidationError | PASS |
| 3 | test_invalid_threshold_in_env_is_rejected x4 | đường lỗi | env "0","-0.5","1.5","x" | ValidationError | PASS |
| 3 | http threshold cases (dev + QA use_threshold) | happy | đổi Settings qua dependency | `threshold` và `eligible` đổi theo | PASS |
| 5 | test_four_achieved_one_not_achieved_shows_everything_and_is_not_eligible | happy | 4 achieved + 1 not_achieved | đủ 4 khoá status_counts, rate 0,8, eligible false, modal vẫn báo | PASS |
| 5 | test_modal_tie_is_deterministic_and_repeatable | biên | 2-2, gọi 5 lần | cùng một JSON; modal = achieved (chữ cái) | PASS |
| 5 | test_tie_result_does_not_depend_on_insertion_order | biên | đảo thứ tự | báo cáo giống hệt | PASS |
| 4,5 | test_single_session_is_100_percent_with_small_sample_flag | biên | 1 phiên | 100%, small_sample true | PASS |
| 4 | test_two_sessions_are_still_small_three_are_not | biên | 2 vs 3 phiên | small true / false | PASS |
| 5 | test_large_group | biên | 150 phiên | assessed 150, rate 0,8 | PASS |
| 4,7 | test_random_distributions_match_benchmark_stability x40 | đối chiếu | 40 seed phân bố ngẫu nhiên 1..25 phiên so `stability._task_stats` | rate, modal, modal_count, assessed, status_counts, "stable" khớp | PASS |
| 7 | test_control_plane_does_not_import_benchmark_task_ui | cấu trúc | grep import | không import stability / benchmark.task_ui | PASS |
| 3 | test_only_config_reads_environment_for_the_threshold | cấu trúc | grep environ/getenv | chỉ config.py | PASS |
| rủi ro | test_response_never_claims_verification | lời văn | quét body | không "verified/xác minh/đã kiểm chứng/validated/proven"; có "not proof" và advisory | PASS |
| 6 | test_get_writes_nothing | chỉ đọc | đếm hàng, id/updated_at/state/task_assessment trước-sau, gọi cả id lạ | không đổi | PASS |
| 6 | test_route_is_get_only | chỉ đọc | POST/PUT/PATCH/DELETE | 404/405/403/422, dữ liệu không đổi | PASS |
| 7 | Hồi quy: test_agent_task_consistency, test_vision_routes, test_vision_results, test_agent_task_trace, test_qa_p08_agent_task_trace | hồi quy | chạy cả bộ | không hồi quy | PASS (xem report) |
