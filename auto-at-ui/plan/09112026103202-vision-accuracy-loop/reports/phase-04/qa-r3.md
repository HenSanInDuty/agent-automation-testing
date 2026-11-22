STATUS: PASS
QA VERDICT: PASS

Phạm vi: phase 04 r9 - `RECEIPT_CLOCK_SKEW` 1 s trong `FileSpool.stop_reason`.

- Automation mới `tests/test_qa_r9_bridge_receipt.py`: 28 passed (3 lần chạy ổn định). Biên now+1s đúng biên chấp nhận, +1us revoked, tương lai xa revoked, hết hạn/thiếu/rỗng/hỏng/deadline/ttl dài đều dừng, revoke thật và cancel khi đang stream, đồng thời re-sign vs poll: 0 revoked sai trong 1414 poll.
- Tái hiện bug: skew=0 (monkeypatch) với poll trễ 30 ms: 76/76 và 78/78 poll bị revoked sai; skew 1 s: 0. Race micro-giây gốc không tự đỏ trên máy này (0/1406).
- `ruff check .`: sạch. Hồi quy 12 file: 253 passed, 46 skipped, 1 failed.
- Failed tồn đọng, không do r9: `tests/test_codex_bridge_benchmark.py::test_offline_manifest_provenance_and_explicit_live_boundary` (hash nguồn trong benchmark/vision/codex/manifest.json lệch 17 file, nhiều file không liên quan). Cần regenerate manifest ở round khác.
- Không collect: test_codex_bridge_end_to_end.py (.env bật bridge làm Settings lỗi).
- Graph: `hgraph add` ok; `hgraph check` sạch; `check --changed` chỉ báo uncovered do lỗi tiền tố `auto-at-ui/` đã biết, không drift/stale.
- Chưa test được: live (cần rebuild 3 service + r10), lệch đồng hồ giữa container, Linux-only/PostgreSQL (skip).

Chi tiết: `qa/phase-04/r9-test-cases.md`, `qa/phase-04/r9-test-report.md`.
