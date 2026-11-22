STATUS: DONE

Đã sửa `plan/20261119-2212-browser-agent-loop/progress.html` bằng Edit (không viết lại trang, không publish).

- Bảng "Trạng thái 7 phase": dòng phase 1 từ pending thành completed, tên phase thành link `#phase-1`.
- Thêm một `<section id="phase-1" class="phase">` sau section phase 0, cùng khuôn: mục tiêu, ai làm, báo cáo, link QA (test-cases.md, test-report.md), convention; bảng diff thật (22 dòng, số +/- lấy từ `git diff --numstat` và `wc -l`); Database (cột, CHECK, bảng, migration b7c9d1e3f5a7, rollback, up/down/up trên auto_at_agent_loop_test); Test (110 dev, 148/44 hồi quy, r2 junior 263 pass + 10 fail, QA r1, QA r2 330 pass, 1 test đỏ baseline, hash v4); Lệch convention; Graph (check exit 0, --changed exit 1 do tiền tố, nợ sửa hgraph); Quyết định user 2026-11-20; Ponytail; Nợ và rủi ro; kết luận leader/QA và phase kế.

Ghi chú: báo cáo không có comment `ponytail:` trong code (đã grep, không có) nên ghi "không có". Tổng diff 454/102 gồm cả file docs/plan sửa trước phiên, đã nói rõ trong chú thích bảng.
