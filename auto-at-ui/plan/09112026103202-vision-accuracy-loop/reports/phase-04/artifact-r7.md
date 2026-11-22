STATUS: DONE

Cập nhật artifact tiến độ phase 04, vòng r13-r14.

- `progress.html` (Edit): subtitle thêm r13-r14; dòng phase 04 thêm câu r13/r14; thêm section "Phase 04 · vòng r13–r14 — settle_timeout trang chủ và ADR-042 (2026-11-21)" (quyết định user, người làm, r13 chẩn đoán, r14 triển khai, review 1 FAIL, r14b, review 2 PASS, Diff thật, DB, Test, Convention/Graph/Ponytail, NỢ, Bước kế).
- `README.md` (Edit): nối "### Agent loop round 01 r13-r14 handoff - 2026-11-21", 8 bullet.
- Diff thật: lấy từ `git diff --numstat`/`status --short` (chỉ đọc). File tracked ghi là tích luỹ so với HEAD; untracked ghi `wc -l`. Số test lấy nguyên từ báo cáo; không chạy test.
- Không publish, không docker, không đụng file worker.
