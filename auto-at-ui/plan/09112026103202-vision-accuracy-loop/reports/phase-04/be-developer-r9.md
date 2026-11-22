STATUS: DONE

CONTEXT_CHECK
- conventions: AGENTS.md, docs/code-standards.md (index to AGENTS.md); ADR 040 as format reference
- graphs: codex-bridge (spool.py, codex_bridge.py, test_codex_bridge_spool.py already in it)
- blast radius: 29 dependents / 4 dependencies (hgraph brief)

## Impact inventory
- Database: không đụng. Contract: không đổi chữ ký; hằng mới `RECEIPT_CLOCK_SKEW`.
- Files: spool.py (hằng + điều kiện), tests/test_codex_bridge_spool.py (4 test), docs/adr/041-bridge-receipt-clock-skew-tolerance.md (mới).
- application/codex_bridge.py: không cần sửa (không đụng).

## Nguyên nhân (đã chứng minh)
`FileSpool.stop_reason` yêu cầu `receipt.recorded_at <= now`. Bridge lấy `now` trước khi đọc file; control-plane re-sign receipt mỗi ~2 s. Receipt ghi giữa hai thời điểm có `recorded_at > now` -> `bridge_policy_revoked`.
Loại trừ: ghi không atomic (`_write` đã temp + fsync + `os.replace`, kiểm trong code, line ~153-179); lệch đồng hồ giữa container (cùng kernel host, không chứng minh được, nhưng dung sai 1 s cũng che sub-second drift); rule ttl (test ttl quá dài vẫn dừng, không liên quan).

## Bằng chứng
Đỏ trước sửa (code cũ, chỉ có hằng được thêm):
`test_reauthorization_between_poll_clock_and_read_is_not_revoked`: `AssertionError: assert 'bridge_policy_revoked' is None` (1 failed, 22 passed, 1 skipped). 3 adverse test còn lại đã xanh sẵn.
Xanh sau sửa: `134 passed, 29 skipped` cho test_codex_bridge_spool, test_claude_bridge, test_agent_loop_bridge, test_agent_loop_bridge_qa, test_codex_bridge_process, test_codex_bridge_service (skip = Postgres/CLI-gated).
`uv run ruff check .`: All checks passed!
Không chạy được: tests/test_codex_bridge_end_to_end.py lỗi collection do `.env` của máy bật bridge (`enabled Codex bridge requires explicit local tenant, ID and paths`), không liên quan thay đổi.
Lưu ý môi trường: pytest cần `--basetemp=.pytest-artifacts/r9tmp` (Windows tmp `pytest-of-hen` bị Access denied).

## Diff
- spool.py: `RECEIPT_CLOCK_SKEW = timedelta(seconds=1)` (comment lý do); `recorded_at <= now` thành `recorded_at - RECEIPT_CLOCK_SKEW <= now`; expiry/deadline/ttl/status giữ nguyên.
- Test mới: re-authorize giữa lấy now và đọc (xanh), recorded_at xa hơn skew (revoked), thiếu file / hết hạn / deadline (dừng), ttl quá dài (revoked).
- ADR 041.

## Rủi ro
Receipt được chấp nhận sớm tối đa 1 s theo đồng hồ bridge; lease vẫn bị chặn bởi expiry (ttl <= 10 s). Chưa kiểm chứng live; nếu r10 vẫn revoked thì nguyên nhân khác (spool folder đã mất ở r9 nên chưa loại hẳn missing/expired).

## Rebuild
control-plane, temporal-worker, claude-bridge (đều import spool.py). Không rebuild bởi tôi.

## Đề xuất live (chỉ đề xuất)
Sau khi rebuild 3 service, chạy lại r9-style session một lần, theo dõi log bridge có `bridge_policy_revoked` hay không ở job 2+.

GRAPH_UPDATE
- graph đã cập nhật: không cần — không thêm/xoá file source, không đổi import (test file đã trong graph; ADR không thuộc graph)
- hgraph check: "✔ Không có vấn đề." ; `hgraph check --changed`: báo uncovered-changed cho docs/adr/041 (ADR không thuộc graph nào; tiền tố git-root là lỗi tool đã biết)
