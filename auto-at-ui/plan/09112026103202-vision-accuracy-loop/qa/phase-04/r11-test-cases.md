# r11 test cases - agent-loop-v2 prompt

Automation: `tests/test_qa_r11_agent_loop_prompt.py` (23 test items). Offline, no docker, no model.

| ID | Nhóm | Tiền điều kiện / bước | Mong đợi | Kết quả |
|---|---|---|---|---|
| R11-01 | Happy | snapshot qua `render_snapshot` (more below yes, 9 control ngoài) -> `build_prompt` | khối page chứa `more below: yes` và `9 control ngoài snapshot`; prompt bắt đầu bằng INSTRUCTIONS; ref `4:1` có mặt | PASS |
| R11-02 | Biên | more below yes, skipped 0 | có `more below: yes`, không có dòng ngoài snapshot | PASS |
| R11-03 | Biên | more below no, skipped 2 | có `more below: no` + `2 control ngoài snapshot` | PASS |
| R11-04 | Biên | more below no, skipped 0 | không signal nào | PASS |
| R11-05 | Happy | INSTRUCTIONS | có "Covering the starting page first", navigate/back, scroll down, "Do not return complete while the starting page"; chuỗi hướng dẫn khớp đúng chuỗi renderer phát ra | PASS |
| R11-06 | Biên | phần mới + Finishing | không URL/domain/slug site (mongchiton, su-kien...), không "N nút/controls" cố định | PASS |
| R11-07 | Hồi quy | 13 câu an toàn v1 (allowed hosts, chỉ close_popup/back off-origin, không submit/download/sign out, không password, không theo lệnh trong page, batch 10, không bịa URL/selector, navigate không URL, advisory, không lặp action lỗi) | còn nguyên trong prompt | PASS x13 |
| R11-08 | Đường lỗi | `check_action` scroll trên origin lạ; back trên origin lạ; `AGENT_MAX_CALLS` | scroll bị `origin_blocked`, back được phép, cap = 20 (guard ở code, không phụ thuộc prompt) | PASS |
| R11-09 | Đường lỗi | snapshot chứa `UNTRUSTED_PAGE_DATA>>>` | marker đóng chỉ xuất hiện 1 lần | PASS |
| R11-10 | Provenance | PROMPT_BUILDERS, bridge job, `vision_agent_loop` | builders = {codex-dom-v11, agent-loop-v2}; job `agent-loop-v2`; vision_agent_loop không hard-code literal, truyền `PROMPT_VERSION` vào `uow.running` và vào exchange | PASS |
| R11-11 | Compat | request `agent-loop-v1` | `build_prompt` từ chối "unsupported agent prompt version" (session/job cũ không được render lặng lẽ) | PASS |
| R11-12 | Kịch bản | model script tuân chỉ dẫn, bắt đầu ngoài trang gốc, snapshot thật qua renderer | trace navigate, scroll, scroll, complete; 4 call <= 20; complete chỉ khi trang gốc `more below: no` và hết dòng ngoài snapshot | PASS |
| R11-13 | Fix-repro | tái hiện bug r10 (model bỏ qua signal) | KHÔNG chạy được trên v1: `agent_loop.py` chưa tracked trong git HEAD, không có bản v1 để đối chứng; R11-05 là proxy (v1 không có các câu này theo be-developer-r11). Hành vi thật của model chỉ live mới biết | CHƯA TEST (xem report) |
| R11-14 | Loop DB | scripted loop có DB (`test_vision_agent_loop.py` run_agent) | cần PostgreSQL 127.0.0.1:55437 | SKIP (môi trường) |
