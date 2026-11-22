# Phase 4 - Test report (QA r1)

QA VERDICT: PASS

Môi trường: Windows 11, `uv run pytest`, `CODEX_BRIDGE_ENABLED=false`, PostgreSQL cô lập `127.0.0.1:55437` (fixture `disposable_database`), `--basetemp` trong scratchpad (thư mục `%TEMP%\pytest-of-hen` bị từ chối quyền: chạy không `--basetemp` cho 5 ERROR môi trường ở `test_agent_loop_bridge_qa.py`, không phải lỗi sản phẩm). Không gọi model thật, không migration lên DB thật, không docker. Log: `reports/phase-04/qa-*.log`.

## Automation mới
`tests/test_vision_agent_loop_qa.py`: 133 test (riêng file: `133 passed in 29.01s`). Tái dùng fake của developer (`FakeWorker`, `FakeExchange`, `run_agent`); không sửa source app.
Bổ sung so với DEV: bảng `stop_cause`; renderer ở 5 cap + biên đúng/ngắn 1 ký tự + skipped=0; 31 term x NFC/NFD/HOA (93 ca); loop chặn tên không dấu/NFD/HOA + submit/reset tên vô hại; ref bị cắt => `stale_ref`; secret text không vào log; trần dùng chung retry + need_screenshot + ảnh; need_screenshot ở lần gọi cuối; lease mất khi action đang chạy và trước observe; popup chặn `close_popup`; processor từ chối session planner; default `exploration_engine`.

## Kết quả chạy (output thật)
| Nhóm | Lệnh (rút gọn) | Kết quả |
|---|---|---|
| QA riêng | `pytest tests/test_vision_agent_loop_qa.py` | `133 passed, 1 warning in 29.01s` |
| Test mới phase 4 + liên quan | `qa + test_vision_agent_loop + test_vision_agent_safety + test_vision_agent_engine_selection + test_agent_loop_contracts + test_agent_loop_bridge_qa` | `385 passed, 3 skipped, 6 warnings in 159.12s` (3 skip: "bridge process runs in the Linux container") |
| Hồi quy 1 | event_processor, results, conclusion, progress, operation_failure_stage, live_persistence, target_preflight | `141 passed, 6 warnings in 198.26s` |
| Hồi quy 2 | provider_integration, viewport_scan, locator_pipeline, accuracy_loop | `50 passed, 9 warnings in 268.40s` |
| Hồi quy page_batch (81 test, chia node id) | 27 + 27 + (13 + 7 + 7) | `27 passed 261.73s`; `27 passed 334.66s`; chunk 3 nguyên khối (27) quá 535s nên chia: `13 passed 502.45s`, `7 passed 100.12s`, `7 passed 112.83s` = 81/81 pass |
| Identity v4 | `test_agent_loop_contracts.py -k "sha256 or baseline or identity"` | `2 passed` (cả file contracts nằm trong nhóm 385 pass) |
| Ruff | `uv run ruff check .` | `All checks passed!` |
| Benchmark | `git status --short -- benchmark` | page_batch ghi đè `benchmark/vision/visual-buttons/flow-result.json` (như phase trước); đã `git checkout -- benchmark/vision/visual-buttons/flow-result.json`; kiểm lại: rỗng |

Tổng: 133 QA + toàn bộ regression: pass, 0 fail. Không có test flaky quan sát được (page_batch chậm nhưng ổn định, thời gian dao động 100-500s theo tải máy).

## Graph
`hgraph add vision-agent-loop tests/test_vision_agent_loop_qa.py` (QA đã chạy). `hgraph check`: `5 graph, 454 file source / Không có vấn đề`. `hgraph check --changed` vẫn exit 1 vì lỗi tiền tố `auto-at-ui/` (git gốc ở thư mục cha, cùng tình trạng phase 1-4 đã báo, user chấp nhận ở phase 3); không còn file phase 4 nào bị báo thiếu graph (`grep qa.py` = 0).

## Quan sát (không FAIL)
1. `agent_step` trong `/trace` production chưa hoạt động (developer mục 1): `SqlAlchemyVisualTraceRepository` thiếu `agent_steps`; test gán thủ công. Cần xử lý trước phase 5 (leader xếp).
2. Từ khoá `gửi` chỉ có dạng `gui di` không dấu: control tên chỉ "Gui" (không dấu) không bị chặn ở cả lớp Python lẫn worker. Có chủ đích tránh false positive ("guide"); rủi ro thấp, ghi để phase 6 cân nhắc.
3. Khi `lease_owner` bị thay mà `fencing_token` giữ nguyên, `check_policy` không phát hiện nên vẫn thêm 1 lần gọi model trước khi ghi step bị fence từ chối. An toàn (không ghi trùng) nhưng tốn 1 call; chỉ ghi nhận.
4. `finish("agent_done")` đặt `state=unavailable` (developer mục 2): dashboard phase 5 phải map reason.

## Chưa test được
- Worker Playwright thật, model/bridge thật, Docker, `/trace` qua route HTTP thật: ngoài phạm vi phase này (dồn phase 6; xem quan sát 1).
- Stress test: không cần - vòng lặp bị trần cứng 20 lần gọi x 10 action, snapshot bị cắt cố định, không query/transaction mới.
- Mutation kiểm vô hiệu của test QA: không làm (không được sửa source); developer đã tự làm 1 mutation (url_change) ở báo cáo r1.

Tài liệu: `qa/phase-04/test-cases.md`, `qa/phase-04/test-report.md`; automation `tests/test_vision_agent_loop_qa.py`.
