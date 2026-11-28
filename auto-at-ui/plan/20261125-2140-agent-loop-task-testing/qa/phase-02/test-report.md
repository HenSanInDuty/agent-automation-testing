STATUS: FAIL

# QA phase 02 — báo cáo (page-text-v1, contract + worker)

QA VERDICT: FAIL

## Lỗi tìm thấy

**F1 (FAIL, case W06/C08/C09) — bộ lọc TS rộng hơn Python: chữ worker để lọt làm Python từ chối CẢ observation.**
- `workers/playwright/src/vision-dom.ts:82` lọc bằng `safeLocatorValue` (`vision-contract.ts:23`, regex ASCII: `\d`, `\w`, `\b` của JS).
  `CodexPageTextItem.safe_text` (`codex_bridge.py:~140`) dùng `validate_locator_value` (`vision.py:227`, regex Python: Unicode).
- Tái hiện: trang có `<p>Mã ١٢٣٤٥٦٧٨ ở đây</p>` (số Ả Rập-Ấn 8 chữ số) hoặc `<p>đ@example.com</p>`. Worker giữ cả hai (`skipped`=0).
  `CodexDomObservation.model_validate(<JSON worker>)` ném `ValidationError: locator identity requires redaction`
  (`page_text.0.text`, `page_text.1.text`). Kết quả: một đoạn chữ ngoài ASCII (cũng chữ số full-width, tiếng Ả Rập, Nhật) làm cả observation
  (kể cả elements) mất ở control plane, trái yêu cầu "mục bị lọc... không làm hỏng observation".
- Kỳ vọng: worker bỏ mục đó và đếm vào `page_text_skipped`, hoặc Python không hỏng cả observation.
  Lưu ý: lỗi lệch regex đã có sẵn với tên element, nhưng chữ trang là văn bản tự do nên khả năng gặp cao hơn nhiều.
- Gợi ý (dev quyết): trong `collectPageText` lọc thêm bằng regex Unicode tương đương (`\p{Nd}{7,}`, `[\p{L}\p{N}_.+-]+@`), hoặc phía Python bắt lỗi từng mục và bỏ + đếm thay vì làm hỏng cả observation.
- Bằng chứng: `uv run pytest tests/test_qa_p2_page_text.py` -> 3 failed (c08 x2, c09), 21 passed; log W06: `DIGITS [{"kind":"paragraph","text":"Mã ١٢٣٤٥٦٧٨ ở đây"},{"kind":"paragraph","text":"đ@example.com"},...] skipped 0`.

**F2 (rủi ro, không FAIL riêng) — `validateVision` TS không kiểm `page_text`.** Xác nhận bằng hành vi: không tìm thấy đường nào chữ nhạy cảm
(e-mail, `password=`, token, số dài, URL, trong h1/h2/alert, trước/sau/ngay tại mốc 160 ký tự, bật hay không `owned-test-target-v1`) lọt ra khỏi worker, vì
`collectPageText` lọc trước (W01, W02, DEV sensitive spec). Hàng rào thứ hai ở TS vẫn thiếu: mọi lệch của bộ lọc ở `vision-dom.ts` (như F1) không có lưới đỡ phía TS, chỉ còn Python ở control plane (từ chối cả observation).
Ghi nhận cho dev; không tính FAIL riêng.

## Môi trường
Windows 11, Node + Playwright Chromium (spec worker, trang loopback dựng ngay trong spec), uv/pytest host, `CODEX_BRIDGE_ENABLED=false`, basetemp `.pytest-artifacts/tmp-p2-qa`. Không đụng docker/model/migration.

## Lệnh và kết quả thật
```
$ uv run python packages/contracts/export_vision_worker.py --check ; echo $?      -> 0
$ git status --short packages/contracts/fixtures                                   -> ?? .../dom-observation.page-text.accepted.json  (không file cũ bị sửa)
$ uv run ruff check .                                                              -> All checks passed!
$ CODEX_BRIDGE_ENABLED=false uv run pytest tests/test_vision_worker_contracts.py tests/test_codex_bridge_contracts.py tests/test_vision_dom_transport.py tests/test_agent_loop_contracts.py tests/test_agent_loop_bridge.py tests/test_codex_bridge_benchmark.py tests/test_qa_p2_page_text.py -q --basetemp=.pytest-artifacts/tmp-p2-qa -p no:cacheprovider
   3 failed, 254 passed, 13 skipped   (3 failed = c08 x2 + c09 của QA, tức F1; test developer + benchmark đều qua)
$ npm.cmd run typecheck                                                            -> tsc --noEmit, không lỗi
$ npx.cmd playwright test src/qa-page-text.spec.ts                                 -> 9 passed (32.7s)   (W06 chỉ ghi nhận/in; F1 bắt bằng pytest C08/C09)
$ npx.cmd playwright test src/vision-dom.spec.ts src/vision-agent-mode.spec.ts     -> 87 passed (3.7m)
$ npx.cmd playwright test src/vision.spec.ts src/vision-visual-buttons.spec.ts src/vision-target-preflight.spec.ts src/vision-agent-mode.qa.spec.ts src/vision-locators.spec.ts -> 49 passed (1.6m)
$ npx.cmd playwright test src/vision-operations.spec.ts src/vision-click-evidence.spec.ts src/vision-agent-evidence.spec.ts src/vision-readiness.spec.ts -> 124 passed (6.4m)
```
Không gặp `invalid_step_deadline`, không phải chạy lại. Không có test flaky. Trong quá trình viết có 4 spec của chính tôi đỏ lần đầu do lỗi test (kỳ vọng sai, gõ làm đổi fingerprint, quan sát nhầm phiên); đã sửa, chạy lại 9/9.

## Phủ 8 tiêu chí
| # | Kết quả | Ghi chú |
|---|---|---|
| 1 byte/hash không đổi | PASS | C01-C03, C10 (observation thật của worker không capability hash đúng như hình dạng cũ), test hash cố định của developer |
| 2 exporter/--check/generated | PASS | exit 0, test_vision_worker_contracts qua |
| 3 capability + gating | PASS | W09 6 tổ hợp. Lưu ý: JSON TS luôn mang 3 khoá mặc định (`page_text:[]`...); Python bỏ khi serialize (C10) |
| 4 thu/bỏ/cắt/trần | PASS | W03-W05, W07, W08 + DEV specs |
| 5 lọc nhạy cảm (kể cả owned) | **FAIL** | lọc ASCII đúng (W01, W02, DEV), nhưng F1 |
| 6 typecheck + specs + ruff | PASS | xem trên |
| 7 manifest + benchmark | PASS | test_codex_bridge_benchmark qua (file QA không làm đỏ nó) |
| 8 ADR-046 mục 9 | PASS (đọc, không kiểm hành vi) | có trong diff, 25 dòng |

## Chưa test được / giới hạn
- Gõ giá trị trực tiếp vào ô mật khẩu rồi observe: `state_mismatch` (fingerprint đổi, hành vi sẵn có), nên W05 dùng thuộc tính `value` có sẵn; luồng gõ qua worker `type` không dựng riêng.
- Nội dung ADR-046 mục 9 chỉ xác nhận có mặt, không đối chiếu từng câu.
- `hgraph check --changed` (dưới) báo drift/uncovered: 9 file tiền tố `auto-at-ui/` là lỗi giả đã biết (developer báo), nhưng file QA mới `workers/playwright/src/qa-page-text.spec.ts` báo `drift`, và `tests/test_qa_p2_page_text.py` + 2 test Python của developer + fixture chưa thuộc graph. Tôi không chạy `hgraph add/sync` (không phải việc của QA, và phase chưa PASS).
- Stress: 1500 đoạn (W07, 123 ms) là đủ; không có vòng lặp lớn/index/transaction ngoài `PAGE_TEXT_NODES=400` quét tối đa. Stress riêng không cần.
- Phụ: chạy `vision-visual-buttons.spec.ts` viết lại `benchmark/vision/visual-buttons/offline-result.json` (chỉ đổi line ending, `git diff` rỗng nội dung); không thuộc phase, không tự hoàn tác.

## GRAPH
```
hgraph check --changed
✖ [drift] playwright-vision-worker: workers/playwright/src/qa-page-text.spec.ts
✖ [uncovered-changed] 9 file auto-at-ui/... (lỗi giả tiền tố đã biết) + tests/test_qa_p2_page_text.py, workers/playwright/src/qa-page-text.spec.ts
```

## Phán quyết
```
QA VERDICT: FAIL
Đã test: 33 case (bảng test-cases.md) — pass 30 / fail 3 (W06->C08 x2, C09 cùng gốc F1)
Automation: 9 spec Playwright (qa-page-text.spec.ts) + 24 test pytest (test_qa_p2_page_text.py, 3 đỏ cố ý = F1)
FAIL:
- C08/C09 (W06) — worker để lọt "Mã ١٢٣٤٥٦٧٨" và "đ@example.com" -> Python từ chối cả observation (vision-dom.ts:82 vs codex_bridge.py safe_text)
Trả về be-developer: sửa F1 rồi báo QA chạy lại C08/C09 (tests/test_qa_p2_page_text.py) và `hgraph` theo mục graph.
```

Tài liệu: `qa/phase-02/test-cases.md`, `qa/phase-02/test-report.md`; automation: `workers/playwright/src/qa-page-text.spec.ts`, `tests/test_qa_p2_page_text.py`.


---

# Vòng 2

QA VERDICT (vòng 2): FAIL

## Đánh giá C08
Đồng ý với developer: C08 vòng 1 đòi Python chấp nhận chuỗi nhạy cảm Unicode, ngược với yêu cầu "không nới bộ lọc Python". Đã đổi C08 thành "Python vẫn từ chối" (PASS) và chuyển bất biến thật sang C09 + C11b ("chuỗi worker giữ thì Python chấp nhận"). F1 gốc (số Ả Rập, `đ@`) đã đóng: C09 xanh, 790/838 chuỗi tấn công bị worker bỏ.

## F3 (FAIL, C11b/W10) — worker giữ chuỗi mà Python từ chối: gập chữ Thổ Nhĩ Kỳ i/İ/ı
- `workers/playwright/src/vision-dom.ts:34-40` (`PAGE_TEXT_SENSITIVE`, cờ `iu`) không gập `İ` (U+0130) và `ı` (U+0131) về `i`, còn `re.IGNORECASE` của Python thì gập (vision.py `_SENSITIVE_LOCATOR`).
- Tái hiện: `<p>apİ key</p>`, `<p>cookıe</p>`, `<p>authorızatıon</p>`, `<p>apı_key</p>` (kể cả có `_`, U+203F, dấu kết hợp xung quanh) -> worker giữ, `skipped` không tăng; `CodexPageTextItem` từ chối => cả observation mất ở control plane. 48/838 chuỗi tấn công lọt, toàn bộ thuộc nhóm từ có chữ `i` (api key, authorization, cookie) với İ/ı.
- Bằng chứng: `tests/test_qa_p2_page_text.py::test_qa_c11b...` -> `worker kept 48 of 838 Python-rejected strings: ['apİ key', 'x apİ key y', ...]`; log spec `ATTACK sent 838 kept 48 skipped 790`.
- Gợi ý: trước khi test, thay `İ`/`ı` bằng `i` (`text.replace(/[İı]/g, "i")`) rồi so regex; hoặc cho lọc thêm mọi chữ `[iİı]`. Ảnh hưởng thực tế thấp (cần chữ Thổ Nhĩ Kỳ kiểu "APİ key") nhưng là đúng loại lỗi làm mất observation.
- Các hướng đã thử và KHÔNG lọt: Kelvin K, ſ, ö, full-width, ZW (U+200B/C/D/FEFF/00AD/2060 chen giữa: Python cũng không khớp), NFD/dấu kết hợp, `_`/Pc/No/Nl/Lm ở ranh giới, chữ số mọi hệ Nd, ＠/﹫/．/。, URL/`[REDACTED]` biến thể. Cắt 160 ký tự theo code point: không lệch (W03 + Python max_length cùng code point); lone surrogate: Chromium thay bằng U+FFFD, không lỗi encode (W11/C12).

## Lệnh vòng 2
```
$ npx.cmd playwright test src/qa-page-text.spec.ts src/vision-agent-mode.spec.ts src/vision-dom.spec.ts   -> 99 passed (3.6m)
$ npm.cmd run typecheck                                                                                    -> sạch
$ CODEX_BRIDGE_ENABLED=false uv run pytest tests/test_qa_p2_page_text.py tests/test_codex_bridge_contracts.py tests/test_vision_worker_contracts.py tests/test_vision_dom_transport.py tests/test_codex_bridge_benchmark.py -q --basetemp=.pytest-artifacts/tmp-p2-qa2 -p no:cacheprovider
   1 failed, 173 passed, 3 skipped      (failed = C11b / F3)
$ uv run ruff check .                                                                                      -> All checks passed!
$ hgraph check --changed -> chỉ còn [uncovered-changed] (lỗi giả tiền tố auto-at-ui/ đã biết + test Python); không còn drift
```
Thứ tự chạy bộ tấn công: `pytest -k c11a` (ghi ứng viên vào temp) -> playwright W10 (ghi `qa-p2-kept.json`) -> `pytest -k c11b`.
Không chạy `vision-visual-buttons.spec.ts` theo yêu cầu.

QA VERDICT: FAIL (còn F3; sửa xong chạy lại c11a -> W10 -> c11b).


---

# Vòng 3 (cuối)

QA VERDICT (vòng 3, và cho cả phase): PASS

## Kết quả
- F3 đóng: bộ tấn công 847 chuỗi (838 cũ + 9 mới có İ/ı biến thể) qua worker thật: `ATTACK sent 847 kept 0 skipped 847`; `test_qa_c11b` xanh.
- Thử quanh bản sửa: İ/ı + zero-width, U+0307, dấu kết hợp, `_`, full-width ｉ/Ｉ, İ trong e-mail/URL và các từ khoá khác — những chuỗi Python từ chối đều bị worker bỏ (danh sách trong `build_candidates`, `tests/test_qa_p2_page_text.py`). Danh sách chỉ chứa chuỗi Python từ chối; chuỗi Python chấp nhận mà worker bỏ là chiều an toàn.
- Chữ vô hại giữ nguyên bản (W12): `Işık açık`, `İstanbul ılık`, `İLK SIRA`, `Çıkış yapıldı` không bị đổi thành `i`, `skipped`=0.

## Lệnh vòng 3
```
$ npx.cmd playwright test src/qa-page-text.spec.ts src/vision-agent-mode.spec.ts src/vision-dom.spec.ts  -> 100 passed (3.3m)
$ npm.cmd run typecheck                                                                                   -> exit 0
$ CODEX_BRIDGE_ENABLED=false uv run pytest tests/test_qa_p2_page_text.py tests/test_codex_bridge_contracts.py tests/test_vision_worker_contracts.py tests/test_vision_dom_transport.py tests/test_codex_bridge_benchmark.py -q --basetemp=.pytest-artifacts/tmp-p2-qa3 -p no:cacheprovider
   178 passed, 3 skipped
$ uv run ruff check .                                                                                     -> All checks passed!
$ uv run python packages/contracts/export_vision_worker.py --check                                        -> exit 0
$ git status --short packages/contracts/fixtures                                                          -> chỉ 2 mục mới (`??`), fixture cũ không đổi
```
Không chạy `vision-visual-buttons.spec.ts`. Không gặp `invalid_step_deadline`.

## 8 tiêu chí (cuối)
1 PASS · 2 PASS · 3 PASS · 4 PASS · 5 PASS (F1, F3 đã đóng; tấn công 847 chuỗi giữ 0) · 6 PASS · 7 PASS (benchmark qua) · 8 PASS (mục 9 ADR-046 có mặt).

## Rủi ro còn lại (không chặn)
- Worker lọc chặt hơn hoặc bằng Python bằng hai regex tách rời; bộ mẫu dùng chung `vision-page-text-v1/samples.json` + bộ tấn công QA (`pytest -k c11a` -> spec W10 -> `pytest -k c11b`) là lưới bắt lệch. Không chứng minh toàn bộ không gian Unicode; đã phủ các nhóm trong danh sách vòng 2-3.
- `validateVision` TS vẫn không đệ quy vào `page_text` (F2, ghi nhận).
- Lệch ASCII/Unicode cho TÊN ELEMENT (planner v4) có sẵn từ trước, ngoài phạm vi phase (be-developer-r2).
- Gõ trực tiếp vào ô mật khẩu rồi observe không dựng được (`state_mismatch` sẵn có).
- `hgraph check --changed`: chỉ lỗi giả tiền tố `auto-at-ui/` + file test Python chưa thuộc graph (đã biết); không drift.

QA VERDICT: PASS
