---
phase: 2
title: Giữ tín hiệu khi lần duyệt lại không cứu được control
status: completed
owner: be-developer
qa: required
dependencies: [phase-01 (A2)]
---
# Phase 02: không để miss im lặng sau lần duyệt lại

## Vì sao (user chọn 2026-11-22, sau QA phase-01)

QA phase-01 (`reports/phase-01/qa-r1.md`) phát hiện: `vision-dom.ts:293` gán `skipped = found.skipped` của lần duyệt lại và xoá dấu skip của lần duyệt đầu. Harness ghi 1/80 lần quét có video hiện mà không bind, và lần đó `skipped_count` 0. Trước A2, mọi miss đều kèm skip, nên control-plane (`vision_coverage.py`, `vision_conclusion.py`) và gate inventory (`rescore.py:49`) luôn thấy được.

## Luật (phải giữ được thắng lợi của A2)

KHÔNG cộng dồn skip của lần đầu một cách mù quáng. Ở 4/5 ca A2 sửa được, ứng viên lần đầu là bản sao trượt ra ngoài, còn lần duyệt lại bind được bản sao đang hiện. Những ca đó phải giữ `skipped_count` 0.

Sau lần duyệt lại:
- Mỗi ứng viên lần đầu bị đánh dấu do chuyển động (cái đặt cờ `motionInvalidated`) cần kiểm: lần cuối có bind được control **tương đương** không. "Tương đương" phải dùng đúng khoá danh tính mà fingerprint `visual_buttons` dùng để coi các bản sao là hoán đổi được (`vision-checkpoints.ts:162-168`). Tái dùng hàm hoặc khoá sẵn có, không tự chế tiêu chí mới.
- Không bind được bản tương đương nào → tính vào `skipped_count` của kết quả cuối, kèm lý do gốc trong `unsupported`, để `coverage_limited` được log. Contract không đổi.
- Bind được → không tính.

## File liên quan (ngoài đây là cấm)
- `workers/playwright/src/vision-dom.ts`
- `workers/playwright/src/vision-dom.spec.ts`
- `docs/adr/045-observe-moving-visual-buttons.md` (thêm mục luật này và giới hạn còn lại)
- `benchmark/vision/codex/manifest.json` (sinh lại hash)

## Test
- **T-loop-lost (mới, đỏ trên A2 hiện tại):** fixture loop swiper. Ứng viên lần đầu trượt ra, và lúc duyệt lại không có bản sao nào nằm trọn viewport (ví dụ lớp phủ che bản sao mới, hoặc track dừng lệch). Kỳ vọng: `skipped_count` 1, có `motion_retraversals` 1.
- **T-loop-out, T-loop-jump giữ nguyên:** `skipped_count` 0. Đây là hàng rào chống đảo ngược A2.
- **Test đặc tả "duyệt giữa lúc trượt":** lần duyệt đầu chạy khi không bản sao nào nằm trọn viewport. Ghi lại hành vi thật hiện có (không ứng viên, không skip), coi đó là giới hạn đã biết và ghi trong ADR. KHÔNG sửa đường này trong phase này: nó có từ code cũ và chung cho mọi scope.
- Giữ mọi test chuyển động khác. Chạy `--repeat-each=20` với `--workers=1` và `--workers=4`.

## Xong khi
- Đủ kiểm chứng 1–2 của `plan.md` (tsc, 4 spec, manifest).
- Harness live (phiên chính chạy) vẫn 0 skip trên ≥30 lần quét tới 1152. Nếu có dòng `videoVisible && !videoBound` thì dòng đó phải kèm `skipped>0`, hoặc có giải thích bằng đường "duyệt giữa lúc trượt" đã ghi.
- Leader PASS, QA PASS.
