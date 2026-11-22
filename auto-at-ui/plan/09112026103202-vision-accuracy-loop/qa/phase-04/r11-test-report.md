# r11 test report (QA r4 phase 04)

Verdict: PASS (offline). Hành vi thật của model chưa kiểm chứng.

Môi trường: Windows, uv, không docker, không PostgreSQL test (127.0.0.1:55437 không có), không bridge/model.

## Kết quả lệnh thật
- `uv run ruff check .` -> `All checks passed!`
- `pytest tests/test_qa_r11_agent_loop_prompt.py` -> `23 passed in 1.24s`
- Hồi quy gộp `tests/test_agent_loop_*.py tests/test_vision_agent_loop*.py tests/test_codex_bridge_contracts.py tests/test_claude_bridge.py tests/test_qa_r11_agent_loop_prompt.py` -> `404 passed, 64 skipped, 1 warning in 109.64s`
- Skip: các test scripted loop trong `test_vision_agent_loop.py` / `_qa.py` đều `isolated PostgreSQL fixture unavailable on 127.0.0.1:55437` (môi trường, không phải lỗi). Nghĩa là loop DB-backed (ba bước tới agent_done, 20 call cap) không chạy được ở lần này; phần được phủ thay bằng R11-12 (loop script dùng code thật `render_snapshot`/`build_prompt`/`check_action`, không dùng DB).
- Test manifest-hash `test_codex_bridge_benchmark.py` không nằm trong nhóm lệnh QA yêu cầu; theo be-developer-r11 vẫn fail như cũ (drift hash, ngoài phạm vi r11); không chạy lại ở đây.

## Graph
- `hgraph add vision-agent-loop tests/test_qa_r11_agent_loop_prompt.py` -> đã thêm (27 file).
- Sau đó `hgraph check` báo drift codex-bridge (test mới import `test_agent_loop_bridge`) -> chạy `hgraph sync codex-bridge --apply` (chỉ docs/graphs/codex-bridge.md thêm test mới). `hgraph check` -> `✔ Không có vấn đề.`
- `hgraph check --changed` vẫn liệt kê 63 file đổi, trong đó nhiều file uncovered (`codex_service.py`, `routes/vision.py`, `codex_bridge.py`, `config.py`...) đến từ working tree nhiều round trước, không thuộc r11 (r11 chỉ chạm `agent_loop.py`, README prompts, 4 test, graph doc); `hgraph check` đầy đủ sạch. Ghi nhận để leader quyết định, không coi là FAIL r11.

## Chưa test được
- Model thật có tuân chỉ dẫn (quay lại trang gốc, scroll, không complete sớm) hay không: chỉ live mới biết; R11-12 dùng script tuân thủ nên chỉ chứng minh pipeline chấp nhận, không chứng minh model nghe lời.
- Fail-trên-code-cũ: không có bản v1 trong git (agent_loop.py chưa tracked).
- Loop có DB (PostgreSQL không có) -> skip.
- Rủi ro đã nêu bởi be-developer: cap 20 call có thể chặn trước khi phủ hết; model vẫn có thể bỏ qua (không có guard code).
- Stress test: không cần - chỉ đổi text prompt, không vòng lặp lớn/query/transaction.
