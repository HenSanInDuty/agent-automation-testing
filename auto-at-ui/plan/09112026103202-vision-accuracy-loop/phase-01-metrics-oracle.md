# Phase 01 — Oracle và thước đo độc lập

Status: completed, 2026-11-09 11:34 +07. Thay đổi và exact commands nằm trong
README canonical. 37 Python tests và 6 worker tests passed; Ruff/typecheck passed.
Oracle giữ 47 positives/14 negatives, viewport và Chromium version trùng worker.
Audit cuối precision 100%, recall 46/47 (97,87%), mct-47 vẫn missing; strict-all
audit exit 1 được giữ. Không có click accuracy claim. Rủi ro chuyển tiếp:
video/carousel động, destination redirects và kết quả UI cần evidence adjudication.

## Mục tiêu, phạm vi, điều kiện trước

Chốt định nghĩa >95% và dataset đúng viewport trước khi tối ưu runtime.
Đọc README kế hoạch, baseline ngày 09/11, dataset và classifier tests.
Áp dụng giả định cả C/A >95% nếu người dùng chưa điều chỉnh; không coi 27 completed
click hiện tại là 27 kết quả đúng nếu chưa review evidence.

## File thêm/sửa dự kiến

- Thêm `benchmark/vision/accuracy/README.md`: protocol, phạm vi, annotation rules.
- Thêm `benchmark/vision/accuracy/oracle-mongchiton-1280-v1.json`: mục tiêu dương,
  âm, stable annotation ID, vị trí riêng của duplicate, expected UI outcome và
  evidence references; danh sách nằm ngoài runtime.
- Thêm `benchmark/vision/accuracy/metrics.py`: pure scoring, threshold gates.
- Thêm `tests/test_vision_accuracy_metrics.py`: unit tests bộ chấm.
- Sửa `workers/playwright/src/fixtures/visual-buttons-audit.ts`: tham số dataset,
  viewport/output; không ghi đè artifact cũ, không hard-code expected=47.
- Thêm `workers/playwright/src/fixtures/visual-buttons-audit.spec.ts` nếu tách
  matcher/export để kiểm tra duplicate/annotation matching.
- Tham chiếu, không sửa nhãn cũ để khớp runtime:
  `benchmark/vision/visual-buttons/mongchiton-desktop.json`,
  `workers/playwright/src/vision-button-semantics.ts`,
  `apps/control-plane/domain/vision_conclusion.py`.

## Thực hiện

1. Audit chỉ đọc tại 1280×720, cùng browser version với worker. So ảnh toàn trang,
   DOM và các nút được gán nhãn 1440×900; ghi rõ khác biệt responsive.
2. Gán nhãn independent từ ảnh/DOM theo scope; classifier output chỉ để đối chiếu.
   Nếu site đổi, version dataset mới, giữ dữ liệu cũ. Không giảm denominator vì
   nút fail/ẩn tạm thời sau một hành động.
3. Khai báo outcome oracle cho từng mục: ví dụ popup đúng destination,
   tab có đúng active state, carousel đổi slide hợp lệ. No-op chỉ đúng nếu được
   xác định trước; download chỉ xác minh sự kiện/metadata, không chạy file.
4. Gắn từng operation với annotation ID bằng binding + vị trí/context/evidence,
   không chỉ text trùng nhau. Mục chưa thể adjudicate là unverified.
5. Tính C/A và precision/recall như README. Lưu đúng/sai/unverified/missing,
   denominator, source hashes và phiên bản metric. Không ghi đè API conclusion.
6. Oracle có mục vượt quyền thì ghi unresolved và giữ việc đó trong acceptance;
   cần định lại scope minh bạch trước qualification, không âm thầm loại bỏ.

## Contract, tests và validation

Không đổi API/DB/execution contract. Artifact mới có schema version riêng,
từ chối version không biết và hashes không khớp.

Chạy từ repo:
`uv run pytest tests/test_vision_accuracy_metrics.py tests/test_vision_conclusion.py -q`.
Chạy tại `workers/playwright/`:
`npm.cmd run typecheck`;
`npm.cmd test -- src/vision-visual-buttons.spec.ts src/fixtures/visual-buttons-audit.spec.ts --workers=1`.

Tests: 45/47 đạt; 44/47 trượt; đúng 95% trượt; denominator=0 không đạt; duplicate
không tăng C; restore/wait không tăng A; rejected/unknown/unverified không tính
đúng; thiếu frame không tính đúng; false click làm fail safety; dataset đổi
không gộp điểm; completed status một mình không tạo positive.

## Acceptance, rủi ro và non-goals

Oracle có scope/viewport/hash/outcome đầy đủ và được review trước qualification.
Bộ chấm deterministic, không phụ thuộc model. Ghi baseline C/A thật hoặc
“accuracy not established”. Không sửa classifier, prompt, policy hoặc UI trong phase này.

## Kết quả thực thi

Completed 2026-11-09 11:34 +07. Oracle 47 positives/14 negatives đã được review
tại 1280×720; scorer và audit có provenance riêng. 37 Python + 6 worker tests,
Ruff và typecheck passed. Audit oracle: 46/47, precision 100%, recall 97,87%;
miss mct-47 được giữ nguyên. Accuracy tương tác chưa established.
Danh sách file, commands, development audit và deviations nằm trong README chuẩn.

