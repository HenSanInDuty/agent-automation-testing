# Phase 05 — Xác nhận >95% và bàn giao

## Mục tiêu và prerequisites

Phase 04 có candidate đạt. Đóng băng candidate source/config/oracle/prompt, browser
version và image digests. Bất kỳ sửa đổi nào ảnh hưởng hành vi đều reset chuỗi
qualification; không gộp lượt của các phiên bản.

## File và dữ liệu

- Thêm `benchmark/vision/accuracy/QUALIFICATION-<date>.md`.
- Thêm `benchmark/vision/accuracy/qualification-<id>.json`: hashes, tất cả run IDs,
  numerator/denominator, false targets, missing IDs, calls và gate results.
- Cập nhật `benchmark/vision/accuracy/README.md`, root `README.md` với link report,
  README kế hoạch với status và bằng chứng của từng phase.
- Giữ nguyên lịch sử `benchmark/vision/sequential/COMPLETION-20261109.md`;
  có thể thêm link tiếp nối, không sửa kết quả cũ.

## Quy trình xác nhận

1. Chạy `uv run ruff check .` và
   `uv run python benchmark/vision/codex/run_offline.py -q --tb=short`.
   Đây là full isolated suite cho final source; configured-stack test vẫn bị
   harness loại để không phát sinh provider call ngoài protocol. Ghi mọi skip.
2. Worker: `npm.cmd run typecheck` và spec liên quan thay đổi (visual buttons,
   operations, revalidation/readiness/observability theo file thực tế).
   Nếu dashboard thay đổi: `npm.cmd run typecheck`, `npm.cmd test`.
3. Gate oracle detection precision/recall >95%; negative safety matrix 100%;
   race repeats phase 03 đều qua. Kiểm manifest provenance và `git diff --check`.
4. Deploy source đã khóa; xác nhận local services và không còn phiên active.
5. Chạy **3 lượt live liên tiếp** với context mới, cùng task/model/config/oracle.
   Mỗi lượt C>95%, A>95%, zero unsafe/wrong-target actions, evidence hợp lệ.
   Tổng ít nhất 100 interaction attempts; nếu chưa đủ thì thêm lượt liên tiếp
   cùng candidate, không hạ yêu cầu mẫu.
6. Lượt fail/unknown/quota không bị xóa hoặc loại để chọn best-of; reset chuỗi,
   phân tích ở phase 04. Không sửa trong khi qualification đang chạy.
7. Review các mục unresolved, giới hạn scope và API conclusion. Nêu rõ nếu
   benchmark đạt >95% nhưng runtime vẫn partial do mục còn lại/rejected operation.
8. Cập nhật tất cả phase đạt, report final, giữ stack local, không tự commit/push.

## Acceptance cuối

- Mỗi lượt qualification có raw counts và oracle/evidence references, không chỉ %.
- C/A >95% theo phép so sánh nghiêm ngặt; detection >95%; safety failures bằng 0.
- Không có phiên hoặc operation pending/unknown chưa đối soát.
- Full final-source validation qua (skip được giải thích); không dùng baseline
  1.046 pass trước sửa để thay cho final-source suite.
- Báo cáo giới hạn: desktop homepage, phiên bản đã kiểm; business unverified nếu
  không có test nghiệp vụ. Không khẳng định độ tin cậy thống kê từ 3 lượt.
- Toàn bộ run thất bại và fix audit vẫn truy vết được; secrets không vào report.

Không đổi API/schema ở phase này. Không tăng ngưỡng timeout/call/state, xóa
negative case, tắt carousel hoặc sửa oracle để làm qualification xanh.
Nếu chưa đạt thì quay phase 04, **không đánh dấu kế hoạch hoàn thành**.

## Qualification attempt 1, 2026-11-17

Recovered full isolated final-source suite: 1151 passed, 2 explained RustFS skips;
separate RustFS repeat and three stability checks passed after a retained initial
connection failure. Original candidate source/config/oracle and image digests
matched at fresh round 17. Detection P=47/48 and R=47/47 pass, but carousel outcome
evidence fails the accuracy gate (available-evidence upper bound 44/47).
Qualification streak is 0/3. Return to phase 04; do not run attempts 2/3 blindly.
See `benchmark/vision/accuracy/QUALIFICATION-20261117-round17.md` and the canonical
README handoff. This is an unsuccessful attempt, not final qualification.



## Superseded 2026-11-22

Qualification chuyển sang ngày 3 của `phase-06-sprint.md` (engine v4 + claude_cli, oracle v2). Attempt 1 (round 17) giữ nguyên là lượt fail.
