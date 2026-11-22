---
status: completed
progress_url: https://claude.ai/artifact/WbcxrJBn7pk4nZeAknUnSE
auto_continue: false
updated: 2026-11-22
next: user — commit (hook cần [TPLWS-<số>]) và quyết qualification (ngân sách live 1/8). Stack đang chạy --profile claude, preflight passed.
artifact: https://claude.ai/artifact/4ExsW5U9TWBLMkcHHhQEVw (impact.html, same path for updates)
process: h-fix — Gate 1–2 xong, Gate 3 hướng A xong review nhưng trượt kiểm chứng live → A2 cần review mới
---
| Phase | Nội dung | Trạng thái |
|---|---|---|
| phase-01 | A2 (h-cook 2026-11-22) | completed — leader PASS, QA PASS, harness 0/80 skip |
| phase-02 | giữ tín hiệu miss sau duyệt lại (`phase-02-miss-signal.md`) | completed — leader PASS, QA PASS; harness 0 skip/160, 2 miss do "duyệt giữa lúc trượt" (giới hạn đã biết) |

# Fix: skip khung video mct-47 khi swiper nhân vật autoplay

## Bối cảnh (đã chứng minh, chi tiết ở impact.html mục A)

- Control bị skip trong inventory ở Q1–Q3 và live 1 là **mct-47** (`a.video-frame`), không control nào khác.
- Swiper nhân vật dùng autoplay (`delay 3000`, `speed 600`, `slide`, `loop`), trượt mỗi ≈3,6 s, mỗi lần ≈650 ms.
- Lỗi xảy ra khi `observeDom` chồng lên lúc slide đang trượt:
  - Lúc duyệt DOM (`vision-dom.ts:73-75`), bản sao được chọn vì nằm trọn viewport.
  - Lúc grounding sau đó, tâm của nó nằm dưới lớp khác, nên ra `unsupported_target`, `unbound_target` (`locator_target_mismatch`) hoặc `target_outside_viewport`.
- Settle không thấy chuyển động vì entry `visual_buttons` không có hình học (`vision-checkpoints.ts:162-168`).
- Không phải hồi quy: A/B code r21 `8e58cfa` và `84213bd` cùng ≈1/6 lần quét tới 1152.

## Trạng thái cây làm việc (chưa commit)

| File | Nội dung hiện tại |
|---|---|
| `workers/playwright/src/vision-dom.ts` | Hướng A. Hằng số ở dòng 16-17. Khối chờ ở dòng ≈196-218: chỉ chạy khi scope `visual_buttons`, có `expected` và lý do thuộc `MOTION_REASONS`. Poll hộp 50 ms, mỗi lần đọc timeout 250 ms, tối đa 1200 ms. Chỉ ground lại khi `still && displaced`. Log `motion_waits`/`motion_regrounded` ở dòng ≈280-289. |
| `workers/playwright/src/vision-dom.spec.ts` | 6 test chuyển động, helper `observeSliding` (≈232-290). Đều xanh, 0% flaky. Fixture chỉ có link dừng trong viewport, chưa mô phỏng swiper `loop`. |
| `docs/adr/045-observe-moving-visual-buttons.md` | Mô tả hướng A, phải sửa theo A2. |
| `benchmark/vision/codex/manifest.json` | Hash `vision-dom.ts`/`spec` theo bản A. Phải sinh lại sau A2. |
| `plan/.../qa/` | `test-cases.md` và `test-report.md` của hướng A (leader PASS và QA PASS ở vòng 2). |

## Vì sao hướng A trượt trên site

Harness A/B với code A cho skip ở 7/30 lần quét. Log chẩn đoán từ bản sao probe (`.pytest-artifacts/s4-ab-diag.log`, dòng `DIAG`):

1. **4/5 ca:** ứng viên là bản sao đang trượt RA, dừng ở tâm x≈-399 (ngoài màn hình).
   - Ground lại cho `unsupported_target`.
   - Cổng `equivalentState` không báo đổi vì các bản sao được coi là hoán đổi được.
   - Kết quả: skip im lặng, và bản sao đang hiển thị không được liệt kê.
2. **1/5 ca:** swiper `loop` nhảy slide về chỗ cũ (tâm cuối 901 bằng tâm lúc duyệt).
   - `displaced` = false nên không ground lại.

## A2: thiết kế (chỉ sửa `vision-dom.ts`, chỉ đọc, không đổi contract hay control-plane)

1. **Ground lại khi đã chuyển động rồi dừng.** Trong khối chờ, đổi điều kiện `still && displaced` thành `still && (moving || displaced)`. Thêm bước kiểm tra hộp cuối có nằm trọn trong viewport không, cùng tiêu chí như lúc duyệt DOM.
2. **Duyệt lại một lần khi tập control nhìn thấy đã đổi.** Nếu có ứng viên chuyển động, dừng ngoài viewport và vẫn lỗi sau khi chờ, đặt cờ `motionInvalidated`. Sau vòng `collection`:
   - Nếu cờ được đặt và đây là lần đầu: dispose mọi handle đã giữ, rồi chạy lại toàn bộ phần duyệt DOM và grounding đúng **một lần**. Lúc này trang vừa dừng, còn ≈2,9 s trước lượt autoplay kế tiếp.
   - Lần thứ hai không duyệt lại nữa và giữ hành vi hiện tại (skip).
   - Cổng `equivalentState(before, after)` và `contextSignature` vẫn kiểm cho lần cuối.
   - Gợi ý cài đặt: tách phần duyệt DOM + `collection` thành hàm nội bộ nhận `attempt`, hoặc dùng vòng `for (attempt of [0, 1])`. Giữ nguyên quy ước browser callback dạng object method (tsx `__name`) và dispose handle ở mọi nhánh.
3. **Quan sát được:** thêm `motion_retraversals` (chỉ số đếm) vào `coverage_limited` và `motion_regrounded`.
4. **Giới hạn:** tối đa một lần chờ (≤1,2 s mỗi batch) cộng một lần duyệt lại cho mỗi lần quan sát. Chuyển động liên tục thì vẫn skip như hôm nay.

## Test phải thêm (đỏ trên code A hiện tại, xanh sau A2)

Fixture cục bộ mô phỏng swiper `loop`: track gồm 3 slide, mỗi slide có một link visual-button giống hệt nhau (cùng href và thuộc tính, chỉ khác vị trí DOM). Có lớp phủ ở hai mép như cột nhân vật và panel TẢI GAME. Transition `translateX` 600 ms, và cuối transition track nhảy về vị trí cũ (reset transform không animation, đổi slide active).

- **T-loop-out:** observe đúng lúc slide đang hiện bắt đầu trượt ra. Kỳ vọng: bản sao đang hiện sau khi dừng được bind, `skipped_count` 0, `motion_retraversals` 1.
- **T-loop-jump:** slide trượt rồi track nhảy về đúng vị trí ban đầu. Kỳ vọng: bind được (ground lại dù không `displaced`).
- **Giữ nguyên** 6 test chuyển động hiện có. Riêng TC-03 "trượt ra khỏi viewport" phải xem lại kỳ vọng: với A2, một link duy nhất trượt hẳn ra thì sau khi duyệt lại không còn ứng viên. Khi đó lần quan sát không có skip, còn `equivalentState` sẽ quyết định có reject hay không. Ghi rõ kỳ vọng mới trong test, đừng nới thành "hoặc A hoặc B".
- Chạy lặp `--repeat-each=20 --workers=1` và `--workers=4`.

## Kiểm chứng bắt buộc trước khi coi là xong

1. Worker: `npx tsc --noEmit`, `vision-dom.spec.ts`, `vision-visual-buttons.spec.ts`, `vision-operations.spec.ts`, `vision-settle-animation.spec.ts` (cwd `workers/playwright`, lệnh `npx playwright test src/<file>`).
2. Sinh lại hash manifest (công thức của test `test_offline_manifest_provenance_and_explicit_live_boundary`: sha256 của text đã chuẩn hoá LF). Chạy `uv run python benchmark/vision/codex/run_offline.py -q --tb=short tests/test_codex_bridge_benchmark.py -k manifest`.
3. **Harness trên site, chỉ đọc, là cổng chính** (bước mà hướng A đã trượt):
   ```bash
   cd auto-at-ui/workers/playwright
   mkdir -p .probe-ab/fixed && cp src/*.ts .probe-ab/fixed/ && rm -f .probe-ab/fixed/*.spec.ts
   cp ../../.pytest-artifacts/s4-ab-harness/ab.mts .probe-ab/ab.mts
   npx tsx .probe-ab/ab.mts fixed 10 30 > ../../.pytest-artifacts/s4-ab-a2.stdout 2> ../../.pytest-artifacts/s4-ab-a2.log
   grep "AB SUMMARY" ../../.pytest-artifacts/s4-ab-a2.log
   rm -rf .probe-ab   # xoá sau khi chạy, tránh lẫn vào test
   ```
   Đạt khi **0 skip trong ≥30 lần quét tới 1152** (code cũ ≈1/6, code A 7/30). Log `vision.dom.*` nằm ở stderr (file `.log`).
4. Review mới theo h-fix: `leader` (kèm lượt over-engineering) và `qa` chạy song song, tối đa 2 vòng.
5. Sửa ADR-045 theo A2. Rebuild `playwright-worker`, chạy preflight. Cập nhật `impact.html` (cùng đường dẫn) với kết quả thật.
6. Không commit khi người dùng chưa yêu cầu. Qualification mới cần người dùng quyết định ngân sách (còn 1/8 live run).

## Nợ ngoài phạm vi (cần duyệt riêng)

- `boundingBox()` đầu tiên trong `groundCandidate` (`vision-dom.ts` ≈184) không có timeout. Lỗi có từ trước, áp dụng cho mọi scope.
- `hgraph check --changed` báo `uncovered-changed` sai, do lệch tiền tố đường dẫn (git root là thư mục cha). `hgraph check` đầy đủ thì sạch.
