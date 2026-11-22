# Test cases - phase-01 (A2), QA r1, 2026-11-22

Runner: Playwright test, cwd `workers/playwright`. Spec `src/vision-dom.spec.ts` (line numbers from `--list`). Live harness: `.pytest-artifacts/s4-ab-a2.log`, `s4-ab-a2-qa.log`.

| ID | Tiêu chí plan | Bước | Mong đợi | Loại | Kết quả |
|---|---|---|---|---|---|
| A2-01 | T-loop-out (spec:369) | Fixture swiper loop 3 slide, observe lúc slide trượt ra | bản sao đang hiện bind được, skipped 0, `motion_retraversals` 1 | auto | PASS (20/20 w4) |
| A2-02 | T-loop-jump (spec:382) | Track trượt rồi nhảy về chỗ cũ | bind được (ground lại dù không displaced), skipped 0 | auto | PASS (20/20 w4) |
| A2-03 | Tái hiện bug cũ | T-loop-out/jump trên code A (dev tắt 2 thay đổi A2) | đỏ trên A, xanh trên A2 | auto | PASS theo bằng chứng dev (be-developer-r1.md "Red trên code A": 2 test đỏ, elements rỗng). QA không dựng lại vì không được sửa src/ |
| A2-04 | TC-03 kỳ vọng mới (spec:280) | Link duy nhất trượt hẳn ra | đúng 2 walk, không snapshot, lỗi `state_changed_during_observation` (không "hoặc/hoặc") | auto | PASS (20/20 w4) |
| A2-05 | Giữ 5 test chuyển động cũ (spec:258,271,292,300,314) | sliding-under-layer, under-control, removed, never-stops, static | xanh, không đổi kỳ vọng | auto | PASS (20/20 w4 mỗi test) |
| A2-06 | Giới hạn chờ | never-stops (spec:300): `walks===1`, `motion_retraversals:0`, elapsed [1100,4000) ms; static: không chờ | tối đa 1 lần chờ + 1 duyệt lại | auto | PASS; đọc code vision-dom.ts:203 (`retraversals===0`), :287 (`retraversals>0` thì break) |
| A2-07 | Dispose handle | Đọc code: nhánh duyệt lại dispose mọi `anonymousTargets` (:288) trước clear; `finally` (:277) dispose non-retained | không rò handle | review | PASS (không có assertion rò rỉ riêng; ghi vào rủi ro) |
| A2-08 | `motion_retraversals` quan sát được | assert trên JSON event của T-loop-out/jump và never-stops; thấy trong log `coverage_limited` ở output suite | có trường, giá trị 1/0/0 | auto | PASS |
| A2-09 | Log không lộ identity | assertion no `Play`, `/play`, `dom_path`, `nth-of-type` | không lộ | auto | PASS |
| A2-10 | Harness live: 0 skip, >=30 quét tới 1152 | `ab.mts fixed 10 30` (lần 1 của phiên chính) | withSkip 0 | live | PASS: observations 40, withSkip 0, errors 0, videoVisibleButUnbound 1 |
| A2-11 | Harness live lần 2 (QA) | cùng lệnh + chẩn đoán trước/sau trong bản sao | withSkip 0 | live | PASS: observations 40, withSkip 0, errors 0, videoVisibleButUnbound 0 |
| A2-12 | Miss im lặng (visible-but-unbound, skip 0) | Phân tích | không có tín hiệu mất control | phân tích | KHÔNG KẾT LUẬN ĐƯỢC nguyên nhân (1/80); xem test-report.md mục 3. Rủi ro còn lại, không chặn |
| A2-13 | Typecheck | `npx tsc --noEmit` | exit 0 | auto | PASS |
| A2-14 | `vision-dom.spec.ts` toàn file | playwright | xanh | auto | PASS 46/46 |
| A2-15 | Hồi quy `vision-visual-buttons.spec.ts` | playwright | xanh | auto | PASS 3/3 |
| A2-16 | Hồi quy `vision-operations.spec.ts` | playwright | xanh | auto | PASS 99/99 (6.0 phút) |
| A2-17 | Hồi quy `vision-settle-animation.spec.ts` | playwright | xanh | auto | PASS 14/14 |
| A2-18 | Manifest hash | `run_offline.py ... -k manifest` | pass | auto | PASS 1 passed, 9 deselected |
| A2-19 | Graph gate | `hgraph check` / `--changed` | sạch | auto | `check` đầy đủ sạch; `--changed` báo `uncovered-changed` do lệch tiền tố đường dẫn (đã biết trong plan, hai file thuộc graph) |
| A2-20 | Biên: unicode, chuỗi dài, nhiều control | Không có test mới cho A2; đường tên dài/sensitive nằm trong test cũ của vision-dom.spec.ts | xanh | auto | PASS (trong 46/46) |
