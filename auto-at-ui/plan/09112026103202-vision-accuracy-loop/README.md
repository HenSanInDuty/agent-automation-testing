# Vòng lặp cải thiện Vision đến >95%

Lập: 2026-11-09. Viết lại: 2026-11-22 sau đánh giá lại (plan cũ chạy 13 ngày, tuần cuối không có kết quả).
Trạng thái: **in progress, phase 06 (sprint 3 ngày)**. Phase 01–03 completed; phase 04/05 superseded bởi phase 06.
progress_url: https://claude.ai/artifact/7Wpg2znWAUaQAPGrx6PQxP (`progress.html`, chưa cập nhật cho sprint) · auto_continue: false

Lịch sử đầy đủ round 1–21 và agent loop r1–r21 (120KB, không sửa):
`history/README-rounds-01-21-until-20261121.md`. Chỉ đọc khi cần tra một round cụ thể.

## Mục tiêu

Tác vụ Mongchiton đã lưu, trang chủ desktop 1280×720, 47 mục tiêu dương + 14 âm trong oracle.
Đo độc lập (không do model tự chấm): C coverage, A accuracy, detection precision P, recall R, mỗi lượt
**>95% theo so sánh nghiêm ngặt** (`100*num > 95*den`), safety (sai mục tiêu, unsafe, unsettled) = 0.
Business outcome vẫn `unverified`. Runtime conclusion không bị benchmark ghi đè.

## Quyết định 2026-11-22 (người dùng duyệt)

1. **Engine**: quay về engine v4 (planner, `codex-dom-v11`) với provider `claude_cli / claude-opus-5-5`.
   Agent loop tạm đóng băng (`plan/20261119-2212-browser-agent-loop/plan.md` status `paused`).
2. **Đóng lỗi còn lại của round 21** offline trước, rồi qualification trong **một sprint 3 ngày**,
   tối đa **8 live run**. Hết hạn thì dừng và báo cáo bằng số thật, không kéo dài vòng lặp.
3. **Cách chạy**: smoke gate bắt buộc trước mọi live run; một lần duyệt cho cả loạt qualification;
   không bắt buộc phiên mới mỗi round; fix nhỏ một reviewer; nhật ký ngắn trong `log.md`.
4. **Tiêu chí qualification (chốt 2026-11-22)**: một loạt 5 lượt liên tiếp khai báo trước, cùng candidate;
   **≥4/5 lượt đạt mọi gate**, safety = 0 ở cả 5 lượt, ≥100 interaction attempts tổng
   (`metrics.qualify_batch`). `metrics.qualify` (3 liên tiếp) giữ để tham chiếu.
5. Commit được phép (2026-11-22); live run ngày 2 được phép trong ngân sách 8 lượt.

## Vì sao (tóm tắt đánh giá lại)

- Đã gần đạt: round 16 (Codex) đạt mọi gate; round 21 (Claude, v4) C=A=45/47, chỉ trượt P=47/50.
  Chuyển sang agent loop (20–21/11) làm điểm về 1–5/47; 7/11 live session chết vì lỗi tích hợp.
- Lỗi chắc chắn (mct-47, 3 key lạ) lặp từ round 15 nhưng chưa từng được chọn sửa.
- Phase 04 không có timebox/điểm dừng; điểm outcome chấm tay nên hầu hết round chỉ có "ceiling".
- Live run bị dùng làm integration test; overhead dev→leader→QA→artifact→phiên mới cho mỗi fix.

## Kết quả ngày 1 (2026-11-22, offline + probe chỉ đọc)

- **mct-47 và precision cùng một gốc**: 3 key lạ của r21 (`50f0e9d3`, `52249891`, `eefb0880`) là
  dom_path descriptor v3 của khung video ở swiper slot 4, 1, 2; oracle v1 chỉ ghi slot 3.
  Probe chỉ đọc trên site thật: 4 bản là slide của một swiper, một bản/nhân vật, đúng một bản trên màn
  hình, cùng href `watch?v=_llS1gbeknQ`; click bản đang hiện → URL `https://mongchiton.vn/#true` + iframe
  `youtube-nocookie.com/embed/_llS1gbeknQ` (video đã khai báo). Bằng chứng:
  `benchmark/vision/accuracy/video-copies-probe-20261122.json` (+ ảnh `...-character2.png`).
- **Oracle v2** `oracle-mongchiton-1280-v2.json` (hash `2795c44f…`): chỉ thêm `alternate_paths` +
  `alternate_evidence` cho mct-47; nhãn, box, outcome, mẫu số 47 không đổi. v1 giữ nguyên (`9242b33d…`).
- Harness: `metrics.validate_oracle` nhận v1/v2 (v1 cấm alternates; alternate không được trùng path
  nào khác; phải có evidence); `metrics.oracle_paths`; `evidence.binding_error` và `derive_detection`
  dùng mọi path. Mới: `benchmark/vision/accuracy/rescore.py` chấm lại offline từ evidence đã lưu,
  ghi vào `runs/<id>/rescore-<hash12>/`, không ghi đè điểm gốc.
- **Round 21 chấm lại**: theo v1 tái tạo đúng điểm gốc (45/47, 45/47, P 47/50); theo v2
  **C=46/47, A=46/47, P=47/47, R=47/47, passed** (`runs/39de5dc7…/rescore-2795c44ffdcc/score.json`).
  Op 109 được tính cho mct-47 với finding `runs/39de5dc7…/oracle-v2-findings-20261122.json`
  (giới hạn: run không export iframe src; video id lấy từ probe cùng URL `#true`).
  Còn lại duy nhất mct-57 (mũi tên lùi; after-frame bị autoplay che) — miss được phép.
- Kiểm tra: `tests/test_vision_accuracy_oracle_v2.py` (16) + 4 file accuracy cũ: 96 passed;
  `uv run ruff check .` sạch. Pytest cần `--basetemp=.pytest-artifacts/tmp-s1` (Temp ACL Windows).
- Đây là chấm lại một lượt cũ, **không phải qualification**: r21 và lượt mới khác source/oracle.

## Các phase

| # | Mục tiêu | Trạng thái |
| --- | --- | --- |
| 01 | [Oracle và bộ chấm](phase-01-metrics-oracle.md) | completed 2026-11-09 |
| 02 | [Harness vòng chạy](phase-02-loop-evidence.md) | completed 2026-11-09 |
| 03 | [Restoration](phase-03-restoration.md) | completed 2026-11-09 |
| 04 | [Vòng cải thiện mở](phase-04-iterate.md) | superseded 2026-11-22 (r16 đạt; agent loop đóng băng) |
| 05 | [Qualification cũ](phase-05-qualification.md) | superseded; attempt 1 (r17) fail giữ nguyên |
| 06 | [Sprint 3 ngày: đóng lỗi r21 + qualification](phase-06-sprint.md) | in progress — ngày 1 xong |

## Ràng buộc giữ nguyên

Không sửa nhãn để khớp runtime, không chuyển miss thành negative, không bỏ lượt xấu, không nới guard
runtime, không đổi caps (20 calls, 5/phút, 100 states, 20 hops, 120 s/bước) hay prompt, không tắt
animation site. Oracle đổi → version mới + bằng chứng, chấm lại lượt cũ tách riêng. Dữ liệu an toàn
chỉ metadata; không form value/token/cookie. Không commit/push khi chưa được yêu cầu.
