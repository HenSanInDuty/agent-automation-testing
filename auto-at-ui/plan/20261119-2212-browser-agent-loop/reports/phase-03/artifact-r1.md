STATUS: DONE

# Artifact phase 3 (progress.html), r1

Edit đã làm (chỉ trên `plan/20261119-2212-browser-agent-loop/progress.html`, không publish):
1. Bảng "Trạng thái 7 phase": phase 3 -> `completed` (pill ok) và tên phase thành link `#phase-3`.
2. Dòng ghi chú dưới bảng: thêm "phase kế: Phase 4 — Agent loop processor + safety" (phase 4 giữ pending).
3. Thêm `<section id="phase-3" class="phase">` sau phase 2, đúng khuôn: mục tiêu, ai làm, báo cáo, tài liệu QA (link test-cases.md, test-report.md), convention (kèm lệch quy trình heredoc spool.py), Diff thật, Database (không đụng), Test, Graph, Ponytail, Nợ và rủi ro, kết luận.
4. Sửa số net Ponytail: 8 file sửa +63/−15 (cộng từ numstat).

Số liệu: numstat từ `git diff --numstat`, `wc -l` cho file untracked; file sửa ghi là diff tích luỹ so với HEAD (không tách được phần phase trước). `tests/fixtures/v4_identity.json` ghi "chưa đếm" dòng. Test lấy từ be-developer-r1, leader-r1, qa-r1 (không chạy lại).
Không có comment `ponytail:` trong file phase 3 (grep rỗng).
