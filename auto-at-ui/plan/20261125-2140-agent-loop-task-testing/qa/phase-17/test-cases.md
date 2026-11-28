# QA phase 17 — test cases (F5 `derived_from_typed`)

Tự động: `tests/test_qa_p17_typed_flag.py` (21 ca, QA viết) + test của developer (`test_vision_verified_text.py`, `test_agent_task_renderer.py`, `test_agent_task_trace.py`, `test_qa_p16_e2e.py`). E2E: `scripts/run_agent_task_draft_e2e.py --project-suffix p17`, out `.pytest-artifacts/task-draft-e2e-p17/`.

| ID | Tiêu chí | Nhóm | Bước / dữ liệu | Mong đợi | Thực tế | KQ |
|---|---|---|---|---|---|---|
| P17-01 | 1 | Happy | `verify_quotes(..., typed=["Viết báo cáo"])`, ứng viên `hoàn thành: Viết báo cáo` + control `Send` (dev test + loop DB) | ứng viên chứa chữ gõ có `derived_from_typed: true`, `Send` không có khoá | khớp (DB, container) | PASS |
| P17-02 | 1 | Happy | renderer: trace có ứng viên cờ + ứng viên sạch, giá trị requester khác | không assertion cho ứng viên cờ; ứng viên sạch vẫn assert; `stop_conditions` có "1 candidate(s) were left out ..." không chứa chữ nào | `test_flagged_candidates_are_left_out_...` pass | PASS |
| P17-03 | 1 | Biên | mọi ứng viên có cờ | không assertion; ghi "not asserted" | dev test pass | PASS |
| P17-04 | 1 | Biên | không có cờ | không có ghi chú "typed in the session"; vẫn assert | `test_without_any_flag_...` + `test_a_clean_candidate_is_still_asserted...` pass | PASS |
| P17-05 | 1 | Biên | quy tắc overlap: hoa/thường tiếng Việt (`VIẾT BÁO CÁO`), Đ/đ, 1 ký tự bằng cả mục, 1 ký tự trong câu, 2 ký tự mảnh, khoảng trắng nhiều, typed chỉ khoảng trắng/rỗng/danh sách rỗng, candidate rỗng, candidate 160 ký tự, typed dài hơn candidate | theo quy tắc (`_overlaps`: bằng / chứa / nằm trong; mảnh < 2 ký tự chỉ khi bằng cả mục) | 14 ca parametrize pass | PASS |
| P17-06 | 1 | Biên | typed ở dạng NFD, candidate NFC | (ghi nhận) quy tắc không chuẩn hoá Unicode nên KHÔNG đánh cờ | `test_typed_value_in_nfd_form_is_not_matched_known_gap` pass (ghim giới hạn) | PASS (giới hạn, xem report) |
| P17-07 | 1 | Bảo mật | `verify_quotes` với typed `SECRET-VALUE-9` không liên quan | kết quả không chứa giá trị gõ | pass | PASS |
| P17-08 | 2 | Hồi quy | phiên cũ không khoá: `AgentTaskAssessmentCopy` | đọc được, cờ False, dump == payload cũ (hash sha256 trên dump không đổi) | pass; dev test `...before_phase_17...keeps_its_hash` pass (DB container) | PASS |
| P17-09 | 2 | Biên | cờ false vs vắng khoá; cờ true | false: dump không khoá (`exclude_if`); true: có khoá; trace có cờ khác hash trace không cờ | pass | PASS |
| P17-10 | 2 | Đường lỗi | khoá lạ trên item (`typed_value`) | `assessment_unavailable` | dev test pass | PASS |
| P17-11 | 3 | Báo cáo | F4: `test_f4_01`, `test_f4_02` | pass; giới hạn ghim (control name được assert, kết quả tìm không; kết quả chứa từ khoá gõ cũng bị loại) | pass (host + container) | PASS |
| P17-12 | 4 | Hồi quy | nhóm cần DB: `test_vision_verified_text`, `test_agent_task_trace`, `test_vision_agent_loop`, `test_vision_agent_task_assessment` (gồm 2 test loop mới) | pass, DB skip = 0 | 197 passed, 0 skipped (`-rs`) | PASS |
| P17-13 | 4 | Hồi quy | `test_agent_task_*`, `test_qa_p08..p16`, `test_qa_p17` trong container có DB | pass | 789 passed + 49 passed lại sau khi chép `benchmarks/` (3 fail ban đầu là thiếu thư mục trong container, không phải lỗi sản phẩm); skip còn lại = node/tsx/artifact r2 | PASS |
| P17-14 | 4 | Hồi quy | host: renderer + p11 (cần node) + p15c + p16 + p17 + manifest codex | pass | 243 passed, 11 skipped (DB cổng host + harness image), 1 xfailed | PASS |
| P17-15 | 4 | Lint | `ruff check` 9 file đụng | sạch | All checks passed | PASS |
| P17-16 | 5 | E2E | stack thật, phiên marker MỚI `marker-todo` (agent gõ "Viết báo cáo"), task_assessment lưu | `derived_from_typed: true` trên `hoàn thành: Viết báo cáo` và `Xoá Viết báo cáo` | đúng (psql), session `2d92d9b9` | PASS |
| P17-17 | 5 | E2E | `case def` marker `ZQ4471-todo1` (khác giá trị task) | d/e/f đúng mã lỗi; approve 200; run `passed` | run `8a30605a`: `passed` | PASS |
| P17-18 | 5 | E2E | draft marker | không assertion `hoàn thành: ...`; `stop_conditions` ghi "2 candidate(s) were left out ..." | source chỉ còn `getByText("3 việc, 1 đã xong")`; ghi chú có | PASS |
| P17-19 | 5 | E2E | pos-login / pos-todo / pos-search `positive` + 2 rerun mỗi test | `passed` | 3/3 first `passed`; 6/6 rerun `passed` | PASS |
| P17-20 | 5 | E2E | scan marker-todo (DB, log, artifact) | giá trị marker chỉ ở nơi khai báo | `unexpected: []`, `free_text_hits: []`, log 0 | PASS |
| P17-21 | 6 | Graph | `hgraph check` | sạch | 8 graph, 562 file, 0 vấn đề | PASS |
| P17-22 | 1/2 | Fail trên code cũ | chạy test mới trên code trước phase 17 | fail | KHÔNG làm được: các file phase 08–16 chưa commit (`git show HEAD:` không có `verified_text.py`, `agent_task_renderer.py`, `agent_task_trace.py`); dựa vào cấu trúc (`verify_quotes(..., typed)`, contract đóng `extra=forbid`) | KHÔNG KIỂM CHỨNG TRỰC TIẾP |
