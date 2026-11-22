STATUS: DONE

# artifact-r8: cập nhật progress.html cho phase 04, r15 đến r19

Chỉ Edit `plan/09112026103202-vision-accuracy-loop/progress.html` (không publish, không test, không docker).

## Đã sửa
- Subtitle: thêm "r15 đến r19".
- Bảng trạng thái, dòng phase 04: nối r15 gác (patch `.pytest-artifacts/r15-shelved/`), r16 live hỏng ở open (hồi quy r14, `__name` dưới tsx), r18 sửa (leader PASS, QA PASS), r19 live `6eef105a…` (open OK, 6 click, 5 oracle, settle_timeout sau nút TOP, không điểm chính thức, diagnostic C 3–5/47). Vẫn in progress.
- Một section mới "Phase 04 · vòng r15–r19 — gác tab panel, hồi quy tsx và phiên live r19 (2026-11-21)": quyết định user; bảng người làm (có link báo cáo); r15, r16, r17, r18; Diff thật; Database; Test; Convention/graph/ponytail; r19 live (operations, clicks, settle_timeout, state_mismatch, calls 8/20, bảng diagnostic không chính thức, bảng so sánh r6/r10/r12/r19); Bài học; NỢ; Bước kế (chờ user).

## Diff thật (nguồn)
`git -C agent-at diff --numstat` + `status --short` + `wc -l` cho 12 file r18. Số +/− là tích luỹ so với HEAD vì file tracked bẩn từ trước (ghi rõ trong ghi chú). Các số: vision-checkpoints.ts +173/−18, vision-operations.ts +131/−23, vision-observability.ts +13/−0, vision-http.ts +4/−2, vision-observability.spec.ts +61/−2, vision-agent-operations.md +101/−0, graph playwright-vision-worker +146/−80; untracked: tsx spec 25, probe 44, qa spec 45, flow probe 112, ADR-042 112 dòng. Cây không còn dấu vết r15 (status không có file panel/c8d0e2f4a6b8; patch có ở `.pytest-artifacts/r15-shelved/`).

## Lưu ý
- Số "tích luỹ" không tách riêng phần của r18 cho các file bẩn từ trước; section ghi chú rõ phần r18 trong cột tóm tắt.
- `hgraph check --changed` lỗi do tiền tố `auto-at-ui/` (đã ghi).
- Không bịa số: mọi số test lấy từ báo cáo be-developer r15/r15-shelve/r18/r19, leader-r8, qa-r7, r18-test-report.
- Token counts r19 không thu thập (báo cáo r19 ghi vậy), section không nêu.
