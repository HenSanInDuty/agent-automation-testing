STATUS: PASS

QA VERDICT: PASS
(Offline. Hành vi thật của model chưa kiểm chứng; cần live r12.)

GRAPH: `hgraph check` -> "✔ Không có vấn đề." (sau `hgraph add vision-agent-loop tests/test_qa_r11_agent_loop_prompt.py` và `hgraph sync codex-bridge --apply` vì drift). `hgraph check --changed` còn liệt kê file uncovered từ các round trước (codex_service.py, routes/vision.py, config.py ...), không thuộc r11.

Đã test: 23 test item mới (14 case, xem qa/phase-04/r11-test-cases.md) - pass 23 / fail 0.
Hồi quy: ruff sạch; pytest nhóm yêu cầu + test mới: 404 passed, 64 skipped (toàn bộ skip = PostgreSQL 127.0.0.1:55437 không có).

Chưa test được:
- Model thật tuân chỉ dẫn hay không (chỉ live).
- Không có bản v1 trong git để chứng minh test fail trên code cũ.
- Loop DB-backed skip (không có PostgreSQL); thay bằng loop script offline.
- manifest-hash test `test_codex_bridge_benchmark.py` không chạy lại; theo be-developer vẫn fail như cũ (đã biết).

Tài liệu: qa/phase-04/r11-test-cases.md, qa/phase-04/r11-test-report.md, tests/test_qa_r11_agent_loop_prompt.py
