# Phase 15b — test cases (QA r1)

Tests: `T` = `tests/test_agent_task_draft_inputs.py` (dev, 30), `Q` = `tests/test_qa_p15b_draft_inputs.py` (QA, 5, new), `P08` = `tests/test_qa_p08_agent_task_trace.py::test_p15b_*`, `FE` = `apps/dashboard` unit tests, `PW` = `workers/playwright/src/vision-dashboard.spec.ts`.

| ID | Tiêu chí | Nhóm | Điều kiện / bước | Mong đợi | Test | Kết quả |
|---|---|---|---|---|---|---|
| C01 | 1 | Happy | trace login (2 type cùng step_index 1) | GET = bước `type` theo thứ tự renderer, độ dài = len giá trị | T `the_steps_are_the_type_steps...` | PASS |
| C02 | 1 | Happy | POST với giá trị dài đúng `text_chars` | không `input_value_mismatch/missing` | T `values_as_long_as_the_answer...` | PASS |
| C03 | 1 | Lỗi | ±1 giá trị so với GET | POST từ chối | T `one_value_more_or_less...` | PASS |
| C04 | 1 | Biên | Unicode/emoji, 500 ký tự, nhiều step_index | độ dài tính theo ký tự, POST chấp nhận đúng các độ dài đó | Q `lengths_count_characters_not_bytes...` | PASS |
| C05 | 1 | Biên | type ở step 1,2,3 | thứ tự = thứ tự thao tác | Q `steps_spread_over_distinct_step_indexes...` | PASS |
| C06 | 1 | Biên | step_index lặp | giữ cả hai mục (không gộp) | T route `answers_the_lengths` (hai mục step_index 1) | PASS |
| C07 | 1 | Happy | locator_name trong GET = name trong mã nguồn render | khớp | T `reads_the_locator_name_that_the_renderer...` | PASS |
| C08 | 2 | Lỗi | quyền viewer / tenant khác / session không có | 404 cùng body | T `route_is_404_the_same...`, `without_submit_generation...`, `missing_session...` | PASS |
| C09 | 3 | Happy | GET thành công | `Cache-Control: private, no-store` | T route x3, Q header | PASS |
| C10 | 4 | Happy | cờ bật, có type | `true, true, [..]` | T route | PASS |
| C11 | 4 | Biên | cờ tắt, có type | `false, true, []` (không lộ độ dài/tên) | T `without_the_flag...`, Q `flag_off_with_type_steps_never_leaks...` | PASS |
| C12 | 4 | Biên | cờ tắt, không type | `false, false, []`; POST `values: []` vẫn tạo draft | T `flag_off_and_no_type_step...`, route | PASS |
| C13 | 4 | Biên | cờ bật, không type; không policy | `true,false,[]`; không policy = cờ tắt | T `without_type_steps...`, `without_a_policy...` | PASS |
| C14 | 5 | Lỗi | running / legacy / no assessment / not achieved / evidence hết hạn / trace refusal | cùng mã 409/422 + detail.code như POST | T parametrize `cannot_back_a_draft`, `gone_evidence...`, route `post_status_and_detail` | PASS |
| C15 | 5 | Biên | consistency không được hỏi | không gọi | T `consistency_is_not_asked` | PASS |
| C16 | 6 | Riêng tư | quét response | chỉ 3 khoá top-level, 3 khoá mỗi mục; không giá trị gõ, operation_id, locator_id, session_id, `version:`, bbox | T `answer_holds_only_lengths...`, P08 `test_p15b_...` | PASS |
| C17 | 7 | Riêng tư | log/audit | không log, không ghi DB | T `logs_nothing_and_writes_nothing`, `it_writes_nothing` | PASS |
| C18 | 7 | Hồi quy | `/trace` shape không đổi; chỉ thêm một route GET | OpenAPI chỉ thêm GET | T `only_route_added_is_a_get`, P08 | PASS |
| C19 | 8 | Happy | cờ bật: form hiện locator + "Needs exactly N characters" | thấy đủ chữ, không placeholder, không điền sẵn | PW ca eligible (18 / 5 ký tự) | PASS |
| C20 | 8 | Biên | cờ tắt, không type | form 0 ô, POST `values: []` | PW ca "no type step", FE model | PASS |
| C21 | 8 | Lỗi | cờ tắt, có type | form không mở, có thông báo, không POST | PW ca refusal, FE model | PASS |
| C22 | 8 | Lỗi | shape sai / thiếu `has_type_steps` / 404 / 409 / 500 | không mở form, không đoán | FE model (14+ dạng), PW | PASS |
| C23 | 8 | Riêng tư | giá trị gõ không vào URL/storage/console/request khác | giữ phase 15 | PW `QA phase 15: typed value stays...` | PASS |
| C24 | 8 | Hồi quy | `typeSteps` cũ đã xoá, form một nguồn | không còn tham chiếu | grep apps/dashboard | PASS |
| C25 | 9 | Hồi quy | nhóm agent_task / route / qa_p08 / qa_p13 / phase14 / consistency / review_guards / renderer / vision_routes / dashboard_route_contracts, trên DB thật | qua, không skip | xem test-report.md | PASS |
| C26 | 9 | Hồi quy | typecheck / lint / npm test dashboard | sạch | xem report | PASS |
| C27 | 9 | Hồi quy | spec Playwright đầy đủ | 88 pass | xem report | PASS |
| C28 | live | Happy | GET route thật trên stack `localhost:7000` | 200 + JSON | curl | CHƯA TEST ĐƯỢC: stack chạy image cũ (OpenAPI không có `test-draft`) |
| C29 | 10 | Hồi quy | `hgraph check` | sạch | xem report | PASS (full); `--changed` còn false positive đã biết |

Stress test: không cần — route chỉ đọc một vết đã có, không vòng lặp trên tập lớn, không query mới, không transaction/lock.
