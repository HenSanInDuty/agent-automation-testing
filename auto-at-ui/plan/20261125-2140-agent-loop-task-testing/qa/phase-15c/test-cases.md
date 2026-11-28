# Phase 15c - test cases (QA r1)

Automation: `tests/test_qa_p15c_fixes.py` (41 ca sinh ra từ 29 hàm test; F1 chạy trên host qua `tsx` thật của worker, F2 cần DB nên chạy trong container `qa15c-pytest`).
Kết quả: host `33 passed, 8 skipped` (8 ca F2 DB skip); container `18 passed, 23 skipped` (F1 skip vì không có node). Hợp: mọi ca chạy ít nhất một nơi, không ca nào fail.

## F1 - traceparent trong runner_config (worker `contract.ts`)

| ID | Nhóm | Bước / dữ liệu | Mong đợi | Kết quả |
|---|---|---|---|---|
| F1-01 | Happy, nối đầu-cuối | `POST /api/v1/runs` (route thật, DB giả) với runner_config chế độ source; lấy `runner_config` route dựng; đưa vào `validatePlaywrightTestSourceMode` thật | 5 khoá (4 + traceparent), traceparent khớp regex worker, worker chấp nhận | PASS |
| F1-02 | Happy | như F1-01 kèm header `traceparent` đến | traceparent mang trace id đến (`c*32`), worker chấp nhận | PASS |
| F1-03 | Biên | `trace_context(...)` với None / hợp lệ / "garbage" / "00-short-bad-01" | luôn ra chuỗi khớp regex worker | PASS |
| F1-04 | Hồi quy | config 4 khoá, không traceparent | chấp nhận | PASS |
| F1-05 | Đường lỗi | traceparent: sai chữ, "", 7, null, list, dict, version 01, id ngắn/dài, cờ 1 ký tự, không hex, xuống dòng cuối, khoảng trắng đầu (13 ca) | từ chối "invalid playwright_test_source runner configuration" | PASS 13/13 |
| F1-06 | Đường lỗi | khoá lạ (`shell`, `headers`, `traceparent2`, `Traceparent`, `tracestate`), có và không có traceparent hợp lệ (5 ca) | từ chối | PASS 5/5 |
| F1-07 | Đường lỗi | traceparent hợp lệ nhưng thiếu `allowed_origins` / hash sai / mode `shell` / thay cho `source_hash` | từ chối (traceparent không "bù" khoá thiếu) | PASS |
| F1-08 | Biên | config hợp lệ + traceparent | chấp nhận (hình dạng trả về do spec developer kiểm) | PASS |
| F1-bug | Tái hiện bug cũ | chạy F1-01, F1-02, F1-08 với `contract.ts` của HEAD (qua `QA_CONTRACT_TS`) | FAIL trên code cũ | `3 failed, 21 passed` trên code cũ; pass trên code mới |

## F2 - `ObservedText` chỉ theo quan sát cuối (`vision_agent_loop.py`)

| ID | Nhóm | Dữ liệu | Mong đợi | Kết quả |
|---|---|---|---|---|
| F2-01 | Unit | verify_quotes với ObservedText chỉ chứa quan sát sau vs cộng dồn cả hai | chỉ "3 viec..." ; dropped 1; cộng dồn cho 2 (mô tả hành vi cũ) | PASS |
| F2-02 | Bug cũ | 2 quan sát: "2 viec, 1 da xong" rồi "3 viec, 1 da xong"; check trích cả hai | chỉ "3 viec" là ứng viên; dropped 1 | PASS (fail khi bỏ dòng reset) |
| F2-03 | Biên | quan sát cuối không có chữ trang | không ứng viên chữ; dropped 1 | PASS (fail khi bỏ reset) |
| F2-04 | Biên | 3 quan sát, "middle only" chỉ ở giữa | chỉ "final"; dropped 2 | PASS (fail khi bỏ reset) |
| F2-05 | Biên | chữ ở cả quan sát đầu và cuối | vẫn là ứng viên | PASS |
| F2-06 | Biên | phiên 1 lượt (không thao tác) | ứng viên từ quan sát duy nhất | PASS |
| F2-07 | Hồi quy login-success | "Đăng nhập" trước, "Xin chào, demo" sau (unicode) | "Xin chào, demo" là ứng viên; "Đăng nhập" bị loại | PASS (fail khi bỏ reset) |
| F2-08 | Hồi quy search-results | kết quả "Balo laptop" sau tìm; "Áo thun cotton" không từng thấy | "Balo laptop" ứng viên; dropped 1 | PASS |
| F2-09 | Hồi quy | check `not_met` | không ứng viên | PASS |
| F2-mut | Tái hiện | xoá dòng `seen = ObservedText()` ở vòng quan sát (bản copy trong container, đã khôi phục, `diff` sạch) | F2-02/03/04/07 fail | `4 failed, 5 passed` |

## F3 / ca (i) - ADR-047, danh sách ghim, quyết định user

| ID | Nhóm | Kiểm | Kết quả |
|---|---|---|---|
| F3-01 | Khớp | dòng nơi 9 của ADR nêu `0-trace.network`, `postData`, `.dat`, `0-trace.stacks`, "không thêm loại artifact mới"; `ARTIFACT_PLACES_EXPECTED` không chứa stacks; `0-trace.stacks` vẫn là unexpected | PASS |
| F3-02 | Khớp | ADR Q11 + Rủi ro: "Cập nhật phase 15c", điều kiện sử dụng, "không có code che", "Giá trị nằm trong câu task", 4 cột chữ tự do | PASS |
| F3-03 | Khớp | `FREE_TEXT_PLACES` đúng 4 cột ADR liệt kê; không thuộc danh sách khai báo; bảng của chúng vẫn nằm trong `MUST_BE_CLEAN_TABLES` | PASS |
| F3-04 | Biên | `VALUE_IN_TASK_TEXT` đúng những phiên mà câu task (tasks.v1.json) chứa giá trị; marker không có trong câu task và không được chấp nhận ở chữ tự do; audit_events/generation_requests vẫn bị coi là hit sạch | PASS |
| F3-05 | Biên | nơi đã khai báo không bao giờ bị báo free-text hay clean-hit | PASS |
| F3-06 | Ca (i) | `case_i` kỳ vọng 409 `assessment_not_achieved`; phase-16 3(i) nói cùng; ca DB `locator_unavailable` vẫn nguyên | PASS |
| F3-07 | Khớp | phase-16 tiêu chí 4 không còn nói `0-trace.network` "không có" | PASS |
| F3-08 | Quyết định user | `user-answers-r1.md` khớp: chấp nhận `assessment_not_achieved`, F3 danh sách, F4 chưa quyết | PASS |

## Hồi quy (blast radius: `routes/runs.py`, `contract.ts`, `vision_agent_loop.py`, renderer, script/test phase 16)

| Nhóm | Lệnh | Kết quả |
|---|---|---|
| Container (DB thật): verified_text, agent_task_draft_e2e/_routes, renderer*, vision_agent_loop*, assessment | pytest | 368 passed, 1 skipped |
| Host: test_run_routes, codex_bridge_benchmark, vision_verified_text, agent_task_draft_e2e | pytest | 37 passed, 25 skipped (DB) |
| Worker | `npm.cmd run typecheck`; `playwright test contract.spec.ts observability.spec.ts` | sạch; 20 passed, 1 skipped |
| Lint | `uv run ruff check .` | All checks passed |
