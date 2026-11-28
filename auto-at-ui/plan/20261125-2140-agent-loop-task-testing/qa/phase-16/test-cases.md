# QA phase 16 (cuối plan) — test cases, vòng r1

Kết quả thực tế lấy từ lượt chạy của QA ngày 2026-11-28 (output ở `test-report.md`). "DB" = `SELECT` chỉ đọc qua `docker exec auto-at-ui-postgres-1 psql`.

## A. Ma trận truy vết ADR-047 AC1–AC7

| ID | AC | Bằng chứng tự động | Bằng chứng thật (r2) | Kết quả |
|---|---|---|---|---|
| TC-AC1 | Phiên `achieved` -> draft -> duyệt -> `passed`; fixture phá `/broken` -> `failed` | `tests/test_agent_task_draft_e2e.py` (29 ca, DB thật) | 3 run đầu `passed` (login `5ce3296e`, todo `c49196e5`, search `af88aea7`); ca (b) `b4de3ea8` `failed` sau `POST /__mode?broken=1`. Đối chiếu DB: 22/22 run trong `state.json` khớp `test_runs.status` | ĐẠT (search: xem F4, chỉ assert điều khiển) |
| TC-AC2 | Thứ tự bước `type`/`step_index` | `test_agent_task_trace.py` (31), `test_agent_task_renderer.py` (28), `test_qa_p08`, `test_qa_p11` | source của draft login có 2 bước `type` đúng thứ tự (ghi nhận trong r2) | ĐẠT |
| TC-AC3 | Giá trị chỉ ở tập nơi khai báo | `test_agent_task_draft_e2e.py` (quét từng bảng + danh sách ghim), `test_qa_p15c_fixes.py::test_f3_*` | QA quét độc lập 30 bảng (mục B) + log 4 container + artifact do dev (không quét lại artifact) | ĐẠT (artifact: dựa r2) |
| TC-AC4 | Không đường nào tạo test/run thiếu duyệt; reviewer khác requester, vai, xác nhận | `test_agent_task_review_guards.py` (22), `test_qa_p13_review_guards.py`, e2e ca d/e/f | DB: 6 draft đã duyệt đều `requested_by=task-e2e-requester` <> `decided_by=task-e2e-reviewer`, `approved=t` | ĐẠT |
| TC-AC5 | Nhóm không nhất quán bị từ chối `assessment_inconsistent` | `test_agent_task_consistency.py` (17), `test_qa_p09` | ca (c): 4 achieved + 1 not_achieved, 0,8 < 0,9, 409 (ghi nhận r2) | ĐẠT |
| TC-AC6 | Audit đủ sự kiện, actor thật, `correlation_id` | `test_generation_policy_audit.py` (10), `test_qa_p12_policy_audit.py`, `test_agent_task_draft_routes.py` | không quét lại `audit_events` ngoài kiểm vắng giá trị | ĐẠT (tự động) |
| TC-AC7 | ruff, test mới + cũ, graph | xem mục C | `hgraph check` sạch; `ruff check .` 1 lỗi ngoài phạm vi | ĐẠT CÓ GHI CHÚ |

## B. Ma trận tiêu chí phase 16

| ID | Tiêu chí | Bằng chứng | Kết quả |
|---|---|---|---|
| TC-16-1 | 3 task: draft -> duyệt -> run `passed` | DB: 6 draft `approved`, `linked_run_id` khớp state; 3 run đầu `passed` | ĐẠT (F4 cho search) |
| TC-16-2 | chạy lại >= 5, >= 90% | DB: 15 rerun `passed` (5+5+5), cùng `test_case_id` với draft tương ứng; test QA mới `test_qa_p16_e2e.py::test_r2_01/02` (8 passed) | ĐẠT 15/15 |
| TC-16-3a..j | Ca âm | e2e ca DB + r2 events; QA không chạy lại (tốn phiên model) | ĐẠT theo r2 + test tự động; không tái chạy độc lập |
| TC-16-4 | Quét nơi lưu | QA quét lại DB: `Demo1234`, `Viết báo cáo`, `balo`, `ZQ4471-todo1` | ĐẠT (kết quả mục B của report); artifact: không quét lại |
| TC-16-4b | form hiện độ dài | `test_agent_task_draft_inputs.py`, `test_qa_p15b_draft_inputs.py`; r2 `inputs` | ĐẠT (không chạy lại thật; dashboard image cũ) |
| TC-16-5 | hai actor thật | DB: `task-e2e-requester` / `task-e2e-reviewer` | ĐẠT |
| TC-16-6 | báo cáo chạy | `be-developer-r2.md` mục "Số liệu"; `summary.json` | ĐẠT (số liệu khớp summary: 6/6 achieved có ứng viên, 15/15) |
| TC-16-7 | suite tự động | mục C | ĐẠT |
| TC-16-8 | graph | `hgraph check` sạch; `--changed` false positive | ĐẠT CÓ GHI CHÚ (`tests/test_qa_p15c_fixes.py` chưa thuộc graph nào) |

## C. Automation đã chạy

| ID | Nhóm | Kết quả |
|---|---|---|
| TC-C1 | e2e + task_stability (container, DB thật) | 72 passed |
| TC-C2 | agent_task_* + qa_p08..p15c + phase14 + policy_audit + reporting_event_processor + task_stability + verified_text (container) | 845 passed, 26 skipped, 2 xfailed |
| TC-C3 | generation* + qa_p2/p3 + phase01 + assessment (container) | 204 passed, 8 skipped, 4 failed do container thiếu `git` (không phải lỗi sản phẩm); chạy lại `test_qa_p3` trên host: pass |
| TC-C4 | host: qa_p3, p15c, p11 renderer, renderer, e2e, task_stability (có node, DB skip) | 281 passed, 30 skipped, 1 xfailed |
| TC-C5 | `apps/dashboard` typecheck + test | không lỗi; 80/80 |
| TC-C6 | `workers/playwright` typecheck | không lỗi |
| TC-C7 | `tests/test_qa_p16_e2e.py` (mới, QA) | 8 passed |

## D. Ca mới của QA (`tests/test_qa_p16_e2e.py`)

| ID | Nhóm | Kỳ vọng | Kết quả |
|---|---|---|---|
| TC-F5-01 | Biên / đặc trưng F5 | requester nhập giá trị khác: `fill` dùng giá trị mới, assertion vẫn chứa chữ cũ của phiên | PASS (xác nhận F5 tồn tại) |
| TC-F5-02 | Đối chứng | cùng giá trị -> assertion hợp lệ | PASS |
| TC-F5-03 | Xác định | render hai lần cho cùng source | PASS |
| TC-F4-01 | Đặc trưng F4 | chỉ ứng viên `control_name` -> chỉ assert điều khiển, không có chữ kết quả | PASS (xác nhận F4) |
| TC-R2-01 | Hồi quy dữ liệu | rerun >= 5, >= 90%, toàn `passed` | PASS |
| TC-R2-02 | Hồi quy dữ liệu | state khớp summary; mọi rerun qua `POST /api/v1/runs`; không `errored`/`queued` | PASS |
| TC-R2-03 | Bảo mật | `events.jsonl` không chứa giá trị mẫu | PASS |
| TC-P16-01 | Ràng buộc | ngưỡng 0,9 vẫn có trong harness | PASS |
