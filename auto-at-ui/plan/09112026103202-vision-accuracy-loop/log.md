# Nhật ký sprint (phase 06)

Lịch sử trước 2026-11-22: `history/README-rounds-01-21-until-20261121.md`.

## 2026-11-22 — ngày 1 (offline + probe chỉ đọc), 0/8 live run

- Đánh giá lại plan; người dùng chọn: quay về v4 + Claude, đóng lỗi r21, sprint 3 ngày; agent loop đóng băng.
- 3 key lạ r21 = khung video mct-47 slot 4/1/2 (dò ngược `descriptor_key`). Probe live chỉ đọc
  (`.pytest-artifacts/s1-video-probe.mts`, `s1-video-click-probe.mts`): một swiper/nhân vật, cùng video
  `_llS1gbeknQ`, click → `#true` + iframe embed đúng video.
- Oracle v2 `2795c44f…` (alternate_paths mct-47), harness + `rescore.py`, 16 test mới; 96 accuracy tests
  passed, Ruff toàn repo sạch.
- r21 chấm lại theo v2: C=A=46/47, P=R=47/47, passed (lượt cũ, không phải qualification).
- Phát hiện: ADR-042 áp dụng cả v4 → lượt live đầu ngày 2 là lượt thử cho source mới.
- Người dùng: cho commit, tiêu chí 4/5, cho live ngày 2. Commit `d351561` (agent loop trước sprint);
  `qualify_batch` 4/5 + 9 test (104 accuracy tests passed, Ruff sạch).
