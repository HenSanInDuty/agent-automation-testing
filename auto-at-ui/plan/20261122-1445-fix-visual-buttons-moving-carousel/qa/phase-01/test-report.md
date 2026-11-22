QA VERDICT: PASS (kèm 1 rủi ro còn lại, mục 3)

# Test report - phase-01 (A2), QA r1, 2026-11-22

## 1. Môi trường
Windows 11, cwd `auto-at-ui/workers/playwright`, tree chưa commit (A2). Stack docker không đụng. Harness live chỉ đọc mongchiton.vn, chromium headless 1280x720.

## 2. Kết quả chạy (output thật, rút gọn)
- `npx tsc --noEmit`: `tsc=0`, không output.
- `npx playwright test src/vision-dom.spec.ts`: `46 passed (27.2s)`.
- `-g "visual button|T-loop|static visual" --repeat-each=20 --workers=4`: `160 passed (51.8s)` (8 test x 20; `--list` xác nhận 8 test gồm T-loop-out, T-loop-jump, TC-03 mới, 5 test cũ). `--workers=1` do QA không chạy lại; dev đã báo `160 passed (3.2m)`.
- `vision-visual-buttons.spec.ts`: `3 passed (2.2s)`. `vision-settle-animation.spec.ts`: `14 passed (11.6s)`. `vision-operations.spec.ts`: `99 passed (6.0m)`.
- `run_offline.py -q --tb=short tests/test_codex_bridge_benchmark.py -k manifest`: `1 passed, 9 deselected in 0.15s`, `"summary": {"passed": 1, "failed": 0 ...}`.
- Harness lần 1 (phiên chính): `AB SUMMARY {"observations":40,"withSkip":0,"errors":0,"videoVisibleButUnbound":1}`.
- Harness lần 2 (QA, `.pytest-artifacts/s4-ab-a2-qa.log`): `AB SUMMARY {"dir":"fixed","observations":40,"withSkip":0,"errors":0,"videoVisibleButUnbound":0,"errorCodes":[]}`. 40/40 dòng `elements:18`. `.probe-ab` đã xoá.
- Hồi quy cũ để so: code cũ 84213bd 1 skip/30, 8e58cfa 1/30, code A 7/40 và 5/20. A2: 0/40 và 0/40.
- `hgraph check`: `6 graph, 474 file source / Không có vấn đề.` `hgraph check --changed`: `uncovered-changed` cho hai file vision-dom (lệch tiền tố đường dẫn; plan đã ghi là báo sai). Không tính là lỗi sản phẩm.

## 3. Dòng visible-but-unbound (skip 0)
Dữ kiện:
- Dòng `scan@1152`: `elements:17, skipped:0, unbound:false, videoBound:false, videoVisible:true`. Không có tín hiệu skip hay `unbound_target`.
- `ab.mts` đo `videoVisible` SAU `observeDom` (cả bind lẫn visible), nên là mẫu đo trễ. Lần 2 QA ghi thêm vị trí khung video trước và sau observe: 6/40 lần quan sát có carousel trượt trong lúc observe (observeDom 408-1059 ms, mỗi bước 1300 px/slide), và cả 6 vẫn bind video (`videoBound:true`, 18 elements). Tức là đo trễ xảy ra thường, nhưng chỉ cho ra "visible-but-unbound" khi walk không thấy bản nào trọn viewport.
- Cơ chế khả dĩ (suy luận từ code, KHÔNG chứng minh được bằng mẫu): (a) walk chạy giữa lúc slide đang trượt, không bản sao nào nằm trọn viewport (vision-dom.ts:84-86), nên không có ứng viên, không có ground, không skip; slide dừng sau đó. Đường này có cả ở code cũ và code A, không phải do A2. (b) Đường chỉ có ở A2: walk 1 thấy bản đang trượt ra, ground hỏng, `motion.invalidated`, duyệt lại (:287-293) gán `skipped = found.skipped` của walk 2 (:293), nên xoá dấu skip của walk 1; nếu walk 2 cũng rơi vào lúc trượt thì ra 17 elements, skip 0, im lặng.
- Chưa phân biệt được (a) với (b): lần 2 không tái hiện (0/40); log `vision.dom.*` không thấy được trong harness.

Đánh giá: 1 mẫu im lặng / 80 quan sát của A2; trên code cũ và code A, mọi miss đều có skip (videoVisibleButUnbound == withSkip trong cả 4 log: 1/1, 1/1, 5/5, 7/7). Nên mô hình "inventory thiếu mct-47 mà không báo" là có thật nhưng hiếm, và khác loại với trước (trước: miss có tín hiệu). Về tổng thể A2 tốt hơn rõ (miss có tín hiệu 1/30 -> 0/80, tổng miss 1/30 -> 1/80), nhưng miss còn lại không có tín hiệu. Mức độ: không phải lỗi hồi quy đã chứng minh, nên không FAIL; ghi là rủi ro cần quyết định riêng. Gợi ý cho developer/PM nếu muốn đóng hẳn: sau duyệt lại, nếu `found.candidates` ít hơn walk 1 (hoặc walk 1 đã có skip) thì giữ skip của walk 1 (`skipped = max(...)`) hoặc báo `coverage_limited`; và/hoặc chờ yên (box của `a.video-frame` ổn định) trước walk 1. Cách nào cũng cần test fixture "walk giữa lúc trượt", hiện chưa có.

## 4. Chưa test được
- Đỏ của T-loop-out/jump trên code A: QA không sửa `src/`, dựa vào bằng chứng của be-developer-r1.md.
- `--repeat-each=20 --workers=1`: không chạy lại (dev đã chạy, 160 passed).
- Rò rỉ ElementHandle: không có assertion tự động, chỉ review code.
- Stress/độ tải: không cần, thay đổi giới hạn (<=1,2 s chờ + 1 duyệt lại mỗi quan sát), không thêm vòng lặp trên tập lớn, không đổi transaction/lock.
- Full Python suite: không chạy (ngoài phạm vi; chỉ test manifest theo plan).

## 5. Phán quyết
Mọi tiêu chí "Test phải thêm" và "Kiểm chứng bắt buộc" mục 1-3 đạt; hồi quy xanh; harness 0 skip/40 hai lần liên tiếp. Rủi ro miss im lặng ghi ở mục 3.

QA VERDICT: PASS
