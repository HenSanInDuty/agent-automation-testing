STATUS: DONE

Cập nhật `progress.html` (chỉ Edit, không publish, không chạy test, không docker):
- Subtitle: thêm "r20–r21".
- Bảng trạng thái, dòng phase 04: thêm câu r20 và r21 đúng nội dung yêu cầu.
- Thêm một section "Phase 04 · vòng r20–r21 — churn mount-switcher và thăm dò tắt animation (2026-11-21)" ở cuối: quyết định user; người làm; r20 (cơ chế, số liệu đợt, vì sao ADR-042 không hấp thụ, bảng A/B/C, giới hạn); r21 (bảng 9 biện pháp có số liệu và lý do loại, B2 tốt nhất, 4 giới hạn); thiết kế đề xuất; Diff thật; Test; Graph; Bước kế chờ user.

Số liệu diff lấy từ `git status --short`, `wc -l`, `git diff --numstat`: hai spec mới 64 và 140 dòng (untracked); AGENT-LOOP-01-20261120.md 458 dòng (cộng dồn); plan README +221/-1; graph +156/-80 (cộng dồn). Không có file fixture mới (fixture để inline). Test lấy nguyên văn từ báo cáo r20/r21 (3 passed 12,6 s; 6 passed 28,0 s; tsc/eslint sạch).

Ghi chú: `benchmark/vision/accuracy/README.md` (+37) đang sửa nhưng thuộc r8, đã nêu rõ trong section là không thuộc vòng này. Lưu ý số ADR-043 trước đây thuộc r15 đã gác (ghi trong section).
