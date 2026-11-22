STATUS: DONE

# artifact r6, phase 04, vòng r11-r12

- File: `progress.html` (chỉ Edit, không viết lại, không publish, không chạy test/docker).
- Đã sửa: subtitle thêm r11, r12; ô Validation dòng phase 04 (vẫn in progress); thêm một section "Phase 04 · vòng r11–r12 — prompt agent-loop-v2 và phiên live (2026-11-21)" trước `</div>` cuối.
- Section gồm: quyết định user, mục tiêu và người làm, r11 bằng chứng/thay đổi prompt/Diff thật/DB/Test/Convention-graph-ponytail, r12 phiên/hành vi/settle_timeout/diagnostic (ghi rõ KHÔNG chính thức)/so sánh r6-r9-r10-r12, kết luận, bước kế.
- Diff thật: lấy từ `git status --short` và `git diff --numstat` thật. Chỉ README prompts (+1/-0) và docs/graphs/codex-bridge.md (+108/-54) là tracked-modified; agent_loop.py, vision-agent-loop.md và 5 file test (đường dẫn thật `auto-at-ui/tests/`, không phải apps/control-plane/tests) là untracked, ghi `wc -l`. Tích luỹ ghi rõ; không tách phần r11.
- Số liệu lấy nguyên văn từ be-developer-r11/r12, leader-r5, qa-r4, r11-test-*; không chạy lại gì. Không đọc nội dung coordinator-r12-*.log ngoài phần cuối (build/recreate thành công).
- Lưu ý: README prompts +1/-0 là số git, không thể tách chính xác phần v2 so với các vòng trước.
