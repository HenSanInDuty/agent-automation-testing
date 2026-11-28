STATUS: PASS (PHÁN QUYẾT CUỐI, vòng 3). Xem mục "Vòng 3" ở cuối file; các mục vòng 1-2 giữ làm lịch sử (FAIL-1 và nợ pageClockStopped đã được sửa).

# Báo cáo QA offline: ADR-048 `agent-frozen-clock-v1`

## Môi trường
Windows 11, host (không docker), Playwright 1.50.1 chromium headless, nhánh `feat/agent-loop-task-testing`, cây làm việc có thay đổi chưa commit của phase khác (giữ nguyên). Không gọi model/bridge, không truy cập mongchiton.vn, không sửa code sản phẩm.

## Lệnh và kết quả thật
| Lệnh | Kết quả |
|---|---|
| `npm.cmd run typecheck` (workers/playwright) | sạch, không lỗi |
| `npx.cmd playwright test` (toàn bộ) | **399 passed, 66 skipped, 0 failed** (6,5 phút). Developer báo 391; chênh 8 = test QA mới |
| `--repeat-each=3` DEV `-g capability` | 15 passed (5 test x 3) |
| `--repeat-each=3` DEV `-g stopped` / `carousel` / `popup` | 9 / 3 / 6 passed |
| `--repeat-each=3` QA `-g QA-C0` | 24 passed (8 test x 3), không flaky |
| `uv run ruff check .` | All checks passed! |
| pytest 11 file (lệnh trong yêu cầu) | **424 passed, 17 skipped, 1 failed** (163 s) |
| `export_vision_worker.py --check` | exit 0 |
| `hgraph check` | "Không có vấn đề" |
| `hgraph check --changed` | 16 `uncovered-changed` (xem dưới) |

## Test fail và phân loại
`tests/test_qa_r8_agent_evidence.py:370::test_worker_dom_skips_private_inputs_and_redacts_sensitive_names` - **CÓ SẴN, không do bản fix.** Bằng chứng: test tìm chuỗi `type === "password" || type === "hidden"` trong `vision-dom.ts`. `git show HEAD:auto-at-ui/workers/playwright/src/vision-dom.ts` đếm chuỗi đó = 0 (HEAD đã là `type === "hidden" || (type === "password" && !credentials)` ở dòng 110, do ADR-046); cây làm việc cũng 0. Test đã đỏ ở HEAD. Phần diff của `vision-dom.ts` chỉ thêm page text (`PAGE_TEXT_SENSITIVE`...), không có `frozenClock`/clock. Không sửa theo yêu cầu.

`hgraph check --changed`: 16 file liệt kê `uncovered-changed` gồm cả file có sẵn trong graph (`vision-operations.ts`, `vision-agent-mode.spec.ts`, `vision-agent-mode.qa.spec.ts`...). Đây là false positive đã biết của file tracked chưa commit; `hgraph check` đầy đủ sạch và `docs/graphs/playwright-vision-worker.md` đã có mục ADR-048. Developer/leader cần xác nhận lại sau commit.

## Test QA đã thêm (`vision-agent-mode.qa.spec.ts`, 8 test, thêm route `/qa-clock`, `/qa-raf`, `/qa-marquee` vào fixture cục bộ của file QA)
C01 chuỗi 12 vòng; C02 close/hết hạn/hết hạn giữa `wait`; C03 hai phiên song song; C04 type/điều hướng/back/reload; C05 6 thay đổi không do timer vẫn bị từ chối khi đồng hồ dừng; C06 rAF; C07 marquee (đặc tả); C08 timer nhanh 100 ms (đặc tả).

## Lỗ hổng của test developer (đã bù)
1. Không có vòng lặp dài >= 10; chỉ 2 vòng (C01 bù).
2. Thay đổi không do timer chỉ được kiểm khi KHÔNG có capability; chưa chứng minh cổng vẫn từ chối khi có capability (C05 bù, 6/6 vẫn `state_mismatch`).
3. Không kiểm close/hết hạn, hai phiên song song, type/back/navigate, rAF, marquee (C02, C03, C04, C06, C07 bù).
4. Timer của test developer đều >= 300 ms; không có ca timer nhanh (C08).
Test tái hiện bug: T01 (không capability, cùng trang, `state_mismatch`) thật sự bắt hành vi cũ; mã không-capability không đổi nên đây là tương đương code trước fix. Mutation thật (tắt `setClock`) CHƯA chạy vì không được sửa code sản phẩm: đây là suy luận, không phải kết quả đo.

## Phát hiện (không phải fail, nên ghi vào ADR Limits)
- Đồng hồ chạy trong suốt một op, nên mọi thứ đổi trạng thái liên tục trong op đều không settle: timer chu kỳ < 160 ms (C08: click ở trang timer 100 ms → `failed:settle_timeout`) và rAF vô hạn (C06: navigate `failed:settle_timeout`, quiet 800 ms trong 10 s). ADR Limits mới nhắc CSS animation vô hạn và video. Không phải hồi quy (trang đó cũng không settle trước fix) và op lỗi vẫn để trang đứng yên (đã kiểm). Swiper thật (delay 3000 ms) không thuộc loại này, cần L02 xác nhận.
- C07: marquee CSS vẫn chạy khi đồng hồ dừng (x đổi), `observe` sau đó `state_mismatch` đúng như ADR mô tả.
- C06/C07: lệnh `navigate` đầu của `open()` thất bại ở các trang đó, nên phiên không thể bắt đầu bình thường.

## Stress test
Không cần: không đụng vòng lặp trên tập lớn, query, job hàng loạt hay lock; C01 (12 vòng) và `--repeat-each=3` đủ cho độ ổn định. Số lần start/stop log clock của phiên rất dài chưa đo (L04).

## Chưa test được
- Trang thật (3 Swiper, transition 300-600 ms), `Date.now()` lệch so với giờ server: chỉ đo được live.
- Mutation test trên code trước fix (không được sửa code).
- Docker/stack control-plane đầy đủ và `tests/test_vision_page_batch.py` (dao động sẵn, không dùng).

## Đo live: CHỜ
(Phiên chính điền: L01 tỷ lệ phiên dừng vì `state_mismatch` trước/sau; L02 settle khi click/wait trên 3 Swiper; L03 trang so giờ; L04 phiên dài.)

| Chỉ số | Trước (17/21 dừng) | Sau | Ghi chú |
|---|---|---|---|
| | | | |

## Phán quyết offline
PASS: mọi tiêu chí offline đã kiểm bằng lệnh thật, 0 fail do bản fix, 1 fail có sẵn đã chứng minh. Phán quyết cuối chưa ra khi chưa có số đo live.

## Vòng cuối (có số đo live + delta vòng 2)

### Đo live: tự đối chiếu với `runs.jsonl` (đã chạy)
| Bộ | Completed | Ghi chú |
|---|---|---|
| mongchiton r5 (code vòng 1) | 14/15 | home-license #4 `initial_capture_failed` 10,3 s |
| mongchiton r6 (code cuối) | 14/15 (93%) | home-requirements #3 `68856665-...` `initial_capture_failed` 10,3 s; requirements 4/5 achieved, license 5/5 not_achieved (kỳ vọng achieved, 0/5), missing-shop 5/5 đúng. Khớp đúng kỳ vọng 9/14 (summary: 60% trên 15 run) |
| fixture task-ui r5 | 30/30, đúng kỳ vọng 30/30 | 10 task x 3 |

Lưu ý: `run.log` trong thư mục r5/r6 là log của script thử, KHÔNG phải log worker, nên "0 `vision.state.mismatch`, 0 `freeze_failed`" không kiểm lại được từ file; chỉ nhận theo lời phiên chính. Phiên hỏng r5 nằm ở home-license #4 (coordinator mô tả nguyên nhân là lỗi dừng đồng hồ; không có log worker r5 để xác nhận), phiên hỏng r6 ở home-requirements #3; cả hai cùng 10,3 s. `home.html` có 14 lần "Mộng Chí Tôn", 0 `<iframe>` (khớp mô tả).

Tiêu chí: fixture >= 90% (100% đạt); mongchiton completed >= 90% (93,3% đạt, biên mỏng: một phiên hỏng nữa là 87%); không phiên nào dừng vì hai mã carousel (0 phiên non-completed mang mã đó trong r5/r6 theo `safe_failure_reason`). L01 đạt, L02 đạt (settle ok trên Swiper thật, 14/15), L03/L04 không có dữ liệu riêng (chưa đo).

### Delta vòng 2 (đã chạy)
- typecheck sạch; ruff sạch; `playwright test src/vision-agent-mode.spec.ts src/vision-agent-mode.qa.spec.ts`: 78 passed (trước khi thêm C09/C10 đang là 76+2), 0 fail ở các test của developer.
- `--repeat-each=3`: 2 test mới của developer (child frames: 3 passed; ép pauseAt lỗi: 6 passed gồm khớp lọc), QA-C09 3 passed, QA-C10 3 passed. Không flaky.
- Logic "chấp nhận lỗi quá khứ khi mọi frame đứng yên" (`vision-operations.ts:264` + `pageClockStopped` 272-281): có thể chấp nhận nhầm. Đo bằng probe `.pytest-artifacts/fix-state-mismatch/probe.mjs`: sau `resume`, `Date.now()` của trang chỉ nhảy mỗi ~110 ms (114, 210, 332, 446 ms...), nên hai lần đọc cách 40 ms (dòng 277) thường bằng nhau dù đồng hồ đang chạy. QA-C10 giả `pauseAt` ném "Cannot fast-forward to the past" mà không dừng gì: 6/6 op vẫn `completed` và trang tiếp tục trôi (falseAccepts=6, lặp 3 lần). Điều kiện kích hoạt (Playwright ném lỗi mà không dừng) chưa thấy ngoài giả lập, nên mức rủi ro thấp; hậu quả nếu xảy ra là quay về `state_mismatch`, không nguy hiểm. Sửa: tăng khoảng đọc ở dòng 277 từ 40 lên >= 250 ms (chỉ trên đường lỗi hiếm).

### Phiên hỏng r6: phân loại = LỖI DO BẢN FIX (đã tái hiện)
Cách đọc của phiên chính ĐÚNG. `settleState` (`vision-checkpoints.ts:324-387`): quiet được tính từ lúc mẫu đầu xong; vòng kiểm điều kiện thoát ở dòng ~358 đòi `Date.now() < deadline`. Lần settle thứ hai có trần cứng 1000 ms (`vision-operations.ts:953`), không phụ thuộc loại thao tác (lần đầu có 10 s cho navigate). Nếu mỗi `inspectState` mất ~480-520 ms thì mẫu 1 xong ~500 ms, nghỉ 80 ms, mẫu 2 xong ~1030 ms > 1000: trang đã đứng yên >= 160 ms nhưng vòng lặp hết hạn, lý do `insufficient_quiet_window`, `samples` 2, `state_changes` 0 - đúng số của log live.
Bằng chứng chạy: QA-C09 dựng trang tĩnh có `document.getAnimations` chặn bằng XHR đồng bộ 480 ms (làm `inspectState` chậm, không đổi trang). Không capability: `completed:observed`. Có capability: `failed:settle_timeout`, log `reason=insufficient_quiet_window, state_changes=0, quiet_required_ms=160, samples=2, longest_observed_stable_ms>=160, timeout_ms<=1000`. Cùng trang với 150 ms mỗi lần đọc: `completed`. Vậy lỗi do bản fix (lần settle thứ hai không có trước fix), không phải có sẵn, không phải flaky; xác suất thực tế phụ thuộc tốc độ đọc trang (quan sát 1/15 ≈ 6,7% ở mongchiton).

### Phán quyết cuối: FAIL
- Tiêu chí số đo đã ghi: đạt. Nhưng bản fix đưa vào một lỗi xác định (trên) với tần suất quan sát 6,7% làm mất phiên ở thao tác đầu, biên 93% so với ngưỡng 90% quá mỏng, và cách sửa nhỏ.
- FAIL-1 `workers/playwright/src/vision-operations.ts:953`: đổi `Date.now() + 1000` thành ngân sách theo loại thao tác, ví dụ `Date.now() + (viewportChanged ? 10_000 : 1500)` (cùng `settleTimeout` đã tính ở dòng ~946) hoặc ít nhất 3000. Sau khi sửa, QA-C09 sẽ đổi kết quả (cần cập nhật kỳ vọng thành `completed:observed`).
- Nợ nhỏ kèm theo (không chặn riêng): `vision-operations.ts:277` khoảng đọc 40 ms quá ngắn (QA-C10); ADR Limits cần thêm timer < 160 ms và rAF vô hạn (QA-C06/C08). `hgraph check --changed` vẫn liệt kê các file tracked chưa commit (false positive đã biết; `hgraph check` sạch), phải chạy lại sau commit.
- Sau khi sửa dòng 953: chạy lại QA-C09 (đổi kỳ vọng), toàn bộ spec worker, rồi đo live lại home-requirements (>= 5 run) trước khi PASS.


## Vòng 3 (code cuối) - PASS
### Số đo live r7 tự đối chiếu (đã chạy)
- `runs.jsonl`: 15/15 `completed`. home-requirements 4 achieved + 1 not_achieved (#4 `6020ccba-...`), home-license 5 not_achieved (kỳ vọng achieved, 0/5), home-missing-shop 5 not_achieved (đúng). Đúng kỳ vọng 9/15 = 60% (summary.md khớp: completed 100%, agreement 93%).
- `worker.log` (486 event): `vision.request_completed` 388, `vision.dom.page_text` 49, `vision.dom.coverage_limited` 49; `vision.state.mismatch`, `vision.clock.freeze_failed`, `vision.state.settle_timeout`, `vision.operation.failed` đều 0. Khớp lời phiên chính, lần này kiểm lại được từ file.
- Phiên `6020ccba` not_achieved: không phải lỗi worker (0 op hỏng, 0 mismatch); là chất lượng đánh giá của agent (chưa xem ảnh), cùng loại `bef6fc15` trước fix; việc riêng, không thuộc bản fix. Không chứng minh được "không liên quan đồng hồ dừng", nhưng không có log nào chỉ về phía đồng hồ.
- Tiêu chí: mongchiton completed 100% (>= 90%), 0 phiên dừng vì mã carousel; fixture 30/30 (vòng 2). L01, L02 đạt; L03, L04 vẫn chưa đo riêng (r7 không cho thấy dấu hiệu lỗi).

### Delta vòng 3 (đã chạy)
- Diff: `vision-operations.ts` lần settle thứ hai dùng `Math.min(session.deadline, Date.now() + settleTimeout)`; `pageClockStopped` đọc cách 250 ms.
- C09 mới: đối chứng không capability (completed), có capability trên trang đọc 480 ms/mẫu phải `completed:observed`, không log settle_timeout <= 1000 ms, và 150 ms vẫn completed: còn kiểm đúng lỗi cũ (trần cố định 1000 ms sẽ ra `failed:settle_timeout`). C10 mới: 6 x `failed:settle_timeout`, `falseAccepts=0`, `clockRunning=true`: còn kiểm đúng việc từ chối khi pauseAt nói dối. Hai ca đã được đỏ/xanh theo báo cáo developer; tôi đã thấy chúng đỏ ở kỳ vọng cũ khi sửa code ở vòng trước (C09, C10 đặc tả xanh trên code cũ).
- typecheck sạch. Toàn bộ `npx.cmd playwright test` một lệnh: 402 passed, 66 skipped, 1 failed (`vision-settle-suppression.spec.ts:84`, `-0` vs `0`). Log `.pytest-artifacts/fix-state-mismatch/r3-full.log`. Dòng `x` của `vision-settle-switcher.spec.ts:59` là `test.fail()` có chủ đích (ghi nhận lỗi mở), không phải fail.
- Hai test từng đỏ: `vision-outcome-capture.spec.ts` `--repeat-each=5`: 45 passed; `vision-settle-suppression.spec.ts` `--repeat-each=5`: 30 passed. Phân loại: FLAKY có sẵn, không dấu hiệu liên quan bản fix: cả hai spec không dùng `agent_mode`/capability, không có `frozenClock` (grep không thấy), nên `setClock` là no-op; diff vòng 3 chỉ đổi biến `settled` trong nhánh `if (session.frozenClock)`. Lưu ý: chưa xác nhận trên code gốc (không stash/checkout), nên là kết luận bằng đọc code + lặp 5 lần, không phải so sánh trước/sau. suppression:84 đỏ ở 2 trong 3 lần chạy toàn bộ song song, xanh 30/30 khi chạy riêng: nhạy với tải máy.
- Fixture không đo lại: chấp nhận 30/30 vòng 2. Vòng 3 chỉ nới ngân sách lần settle thứ hai (trang fixture settle nhanh nên đường đi giống hệt) và 250 ms nằm trên đường lỗi; test worker cục bộ phủ cả hai. Không yêu cầu đo lại.

### Phán quyết cuối: PASS
Nợ còn lại: (1) `vision-settle-suppression.spec.ts:84` flaky dưới tải, chưa đối chiếu trên code gốc; (2) ADR Limits cần nhắc timer < 160 ms và rAF vô hạn (QA-C06/C08); (3) `hgraph check --changed` có false positive do file chưa commit, chạy lại sau commit; (4) L03/L04 chưa đo riêng; (5) home-license kỳ vọng `achieved` chưa ai đối chiếu bằng mắt, và nhận định not_achieved chưa xem ảnh (ngoài phạm vi fix).
