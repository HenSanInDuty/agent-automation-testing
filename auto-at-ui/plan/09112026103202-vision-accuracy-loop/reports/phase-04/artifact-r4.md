STATUS: DONE

# Artifact phase 04, vòng r9 (r4 của artifact)

## Đã làm
- `progress.html` (chỉ Edit): subtitle thêm r9; dòng phase 04 trong bảng trạng thái thêm câu vòng r9 (vẫn in progress); thêm section "Phase 04 · vòng r9 — phiên live A1+A3 và sửa race receipt bridge (2026-11-21)" sau section r8: mục tiêu + người làm, kết quả live, điểm diagnostic (ghi rõ không chính thức), nguyên nhân + fix, diff thật, DB, test, convention/graph/ponytail, kết luận + bước kế.
- `README.md` của plan (chỉ Edit): nối "### Agent loop round 01 r10 offline fix handoff - 2026-11-21", 6 bullet, ở cuối file. Không sửa phần khác.

## Nguồn số liệu
- Diff: `git diff --numstat` cho `spool.py` +14/-4, `tests/test_codex_bridge_spool.py` +57/-2, `docs/graphs/codex-bridge.md` +101/-54 (tích luỹ so với HEAD, đã bẩn từ trước). `AGENT-LOOP-01-20261120.md` là untracked nên không có numstat: 311 dòng (`wc -l`). Untracked: ADR 041 24 dòng, `tests/test_qa_r9_bridge_receipt.py` 255 dòng.
- Test, live, nguyên nhân: nguyên văn từ be-developer-r8/r9, leader-r4, qa-r3, r9-test-report.

## Lưu ý trung thực
- Prompt gọi nguyên nhân là "đã chứng minh": nguồn chỉ chứng minh offline (test đỏ/xanh, QA tái hiện bằng poll trễ 30 ms; race micro-giây gốc 0/1406 không tự đỏ). Trang ghi đúng điều đó và nói chưa chứng minh live.
- Số "459 file" của `hgraph check` (leader) và "460" (QA, sau khi thêm file test) cùng được ghi.
- Không chạy test, không docker, không publish artifact. Không mở tiến trình nào.
