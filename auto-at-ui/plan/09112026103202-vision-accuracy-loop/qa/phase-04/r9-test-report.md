STATUS: PASS (có lưu ý, xem Phán quyết)

# Phase 04 r9 - test report

## Môi trường
Windows 11, uv venv, pytest `--basetemp=.pytest-artifacts/qa-r3tmp`. Không đụng docker/bridge/model.

## Kết quả
- `uv run pytest tests/test_qa_r9_bridge_receipt.py -q -s`: `28 passed in 22.83s` (chạy 3 lần, ổn định).
  - `polls=1414 ... revoked=0` (skew 1 s, race re-sign).
  - `ZERO-SKEW polls=76 false_revoked=76` và `polls=78 false_revoked=78` (hành vi cũ, poll trễ 30 ms): bug tái hiện, fail trên code cũ / pass trên code mới.
  - `OLD-BEHAVIOUR polls=1406 false_revoked=0`: race gốc (cửa sổ micro-giây) không tự đỏ trên máy này; chỉ đỏ khi poll chậm. Lý do: control-plane tạo `recorded_at` trước khi fsync (~10 ms), nên receipt đang nằm trên đĩa thường cũ hơn `now`. Race thật cần bridge trễ giữa lấy `now` và đọc (CPU nghẽn, log, GC) - đúng cơ chế T19/T20.
- `uv run ruff check .`: `All checks passed!`
- Hồi quy: 12 file (`test_codex_bridge_*` trừ end_to_end, `test_claude_bridge`, `test_agent_loop_bridge*`, file mới): `1 failed, 253 passed, 46 skipped`.
  - FAILED `tests/test_codex_bridge_benchmark.py::test_offline_manifest_provenance_and_explicit_live_boundary`: hash nguồn trong `benchmark/vision/codex/manifest.json` lệch với 17 file (gồm file không liên quan r9 như `docker-compose.codex.yml`, `workers/playwright/src/*`, `process.py`). Manifest cũ từ trước r9 (không có diff trong `benchmark/vision/codex`), không do thay đổi spool.py. spool.py và test_codex_bridge_spool.py cũng nằm trong danh sách lệch; cần regenerate manifest ở round khác. Đây là lỗi tồn đọng của suite, không thuộc phạm vi r9, nhưng nên giao dev xử lý.
  - Không collect: `tests/test_codex_bridge_end_to_end.py` (lỗi collection do `.env` máy bật bridge: `enabled Codex bridge requires explicit local tenant, ID and paths`), không liên quan r9.
  - Skip: process/agent-loop-bridge chạy trong container Linux (26), PostgreSQL 127.0.0.1:55437 không có (10), offline harness image (3), flock Linux (1), symlink adversary Linux (1).

## Graph
- `hgraph add codex-bridge tests/test_qa_r9_bridge_receipt.py`: `Đã thêm 1 file vào docs/graphs/codex-bridge.md (tổng 25).`
- `hgraph check`: `6 graph, 460 file source - Không có vấn đề.`
- `hgraph check --changed`: vẫn báo `uncovered-changed` cho 62 file nhưng với tiền tố `auto-at-ui/` (kể cả spool.py, test_codex_bridge_spool.py đã nằm trong graph): lỗi tiền tố git-root đã biết của tool. File QA mới không bị liệt kê. Không có drift/stale-file.

## Quan sát phụ (không chặn)
- Trên Windows, `os.replace` đồng thời với đọc gây `PermissionError` (reader 86/1500 lần, writer 44). Kịch bản này bị bỏ qua khỏi verdict; bridge chạy Linux nên không áp dụng, nhưng cho thấy `stop_reason` không bắt OSError khi đọc receipt (hành vi trước r9, không đổi).
- File rỗng/JSON hỏng làm `stop_reason` raise `ValidationError` (không bao giờ trả None) - fail-closed, khớp test dev `malformed receipt fails`.

## Stress test
Không cần: thay đổi là một điều kiện so sánh, không đụng vòng lặp lớn, query, transaction hay lock. Đã có test đồng thời T17-T20.

## Chưa test được
- Live: không có phiên live, không rebuild control-plane / temporal-worker / claude-bridge; cần r10 live (đúng đề xuất dev) để xác nhận hết `bridge_policy_revoked` ở job 2+.
- Lệch đồng hồ thật giữa container: không đo được; dung sai 1 s chỉ được kiểm bằng mô phỏng recorded_at và lag. Nếu r10 vẫn revoked, nguyên nhân khác (receipt missing/expired do spool mất).
- Linux-only: flock, symlink, process container (skip).
- PostgreSQL repository/migration (skip).

## Phán quyết
QA VERDICT: PASS cho phạm vi r9 (skew 1 s đúng biên, không nới lease, revoke thật vẫn dừng, bug tái hiện đỏ trên skew=0). Lưu ý tồn đọng: manifest benchmark codex lệch hash.
