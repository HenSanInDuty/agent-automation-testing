STATUS: DONE

CONTEXT_CHECK
- conventions: AGENTS.md, docs/code-standards.md (hgraph brief), be-developer-r13.md. docs/api-conventions.md không đọc: không đổi API.
- graphs: playwright-vision-worker (đọc, đã cập nhật)
- blast radius: 27 file bị phụ thuộc / 11 file phụ thuộc (hgraph). `equivalentState` được vision-dom.ts, vision-history.ts, vision-operations.ts dùng chung nên các điểm so sánh đó đổi hành vi theo (không sửa file nào trong số đó).

# r14 - sửa settle: dung sai hình học (A) + hộp layout giới hạn (B)

Database: không đụng. Public contract: không đổi (xem "Fingerprint lưu trữ").

## Diff theo file
- `workers/playwright/src/vision-checkpoints.ts`
  - Hằng số có tên `BOX_CENTER_TOLERANCE_PX = 3`, `BOX_MIN_IOU = 0.8` (comment lý do).
  - `RuntimeState.privateInteractions` thêm trường chỉ-RAM `box`, `animated`, `hit`, `transparent` (không vào hash, không ra transport).
  - Trong `inspectState`: gom `document.getAnimations()` thành `eligible` (CSSAnimation vô hạn, keyframe chỉ chạm transform [không translate/matrix/perspective], scale, rotate, opacity; không pseudoElement) và `blockedByAnimation` (mọi animation vô hạn còn lại: translate, left/width, Element.animate). Mỗi control: duyệt tổ tiên (đã có sẵn vòng opacity) ghi `underEligible/underBlocked/foreignTransform/crossedRoot`; `animated` chỉ true khi có animation eligible, không bị blocked, KHÔNG có transform nào khác trên chuỗi tổ tiên (loại wrapper carousel/swiper translate), không qua shadow, thuộc document chính. Khi `animated`: hộp = hộp layout (offsetLeft/Top chain, bail với fixed/sticky; bias hằng số không ảnh hưởng so sánh) cắt theo viewport; ngược lại hộp = bounds đã cắt như cũ. Entry không có hộp (anonymous `buttons`, landmark, `visual_buttons`) so sánh chính xác.
  - `equivalentState`: fast path `fingerprint` + `privateForms` như cũ; nếu khác thì so sánh có dung sai: url/form presence/scroll giống hệt, cùng số entry, từng entry (cùng vị trí) content digest giống hệt + `sameBox` (tâm lệch <= 3 px mỗi trục VÀ IoU >= 0.8). Hit/transparent chỉ được miễn khi CẢ HAI trạng thái `animated`, và chỉ bốn hit góc; hit tâm (điểm click) luôn phải khớp. Chặt hơn mô tả plan: control không animation phải khớp nguyên hit/transparent.
  - `settleState`: so sánh mẫu hiện tại với `reference` (trạng thái mở cửa sổ yên), không phải mẫu trước, để drift chậm không trôi lọt dung sai từng bước; reset khi context bị thay. Trả `state` vẫn là mẫu cuối.
- `workers/playwright/src/vision-settle-animation.spec.ts`: viết lại, 14 test (bỏ `test.fail()`; bỏ test pin "state_kept_changing hôm nay" vì hành vi đã đổi).
- `workers/playwright/src/fixtures/settle-animated-control.ts`: thêm fixture strong pulse, rotate+fade, marquee translate, left, width, carousel script-driven.
- `docs/adr/042-settle-geometry-tolerance.md` (mới), `docs/vision-agent-operations.md` (một đoạn), `docs/graphs/playwright-vision-worker.md` (sync + sửa dòng "cổng fingerprint cố ý không đổi" đã lỗi thời).
- `vision-operations.ts`: không phải sửa (mọi điểm so sánh đã đi qua `equivalentState`).

## Fingerprint lưu trữ
`fingerprint`, `interaction_fingerprint`, `semantic_fingerprint`, `form_presence_fingerprint`, hash policy và checkpoint metadata không đổi giá trị/cách băm. Không cần ESCALATE. Hit test + exact-node verify lúc dispatch không đụng.

## Test red -> green
- Đỏ (trước khi sửa, đã bỏ `test.fail`): `vision-settle-animation.spec.ts` -> `a presentation-only pulse should not block settle`: `Expected: true Received: false` (`1 failed, 3 passed`).
- Xanh sau sửa: `npx playwright test src/vision-settle-animation.spec.ts --workers=1` -> `14 passed (12.4s)`. Test pulse settle trong 938 ms (800 ms yên + 1 mẫu), không phát `settle_timeout`.
- Adverse (đều trong 14 test, mỗi test có đối chứng "chụp lại chưa mutate thì equivalent"): dời 20 px / rộng thêm 30% -> đổi (dời 2 px -> vẫn bằng nhau); đổi aria-label/text/disabled -> đổi; thêm/xoá control -> đổi; overlay div không phải control che pulse (hit tâm) -> đổi; overlay button -> đổi; carousel translate 300 px (slide khác vào) và 20 px (slide dời) cạnh pulse eligible -> đổi; marquee translateX, animation left, animation width -> đổi (không eligible); `left` animation khiến settle `state_kept_changing`; drift 2 px/50 ms không lọt dưới dung sai (so với reference); pulse 1.06 / 1.5 / rotate+opacity -> các pha bằng nhau dù fingerprint lưu trữ khác (ca 1.5 chỉ B cứu được, IoU 0.44).
- Hồi quy (`--workers=1`): settle-observability + dom + history + readiness + target-preflight + sample-guard + visual-buttons + observability -> `97 passed (55.0s)`; `vision-operations.spec.ts` -> `99 passed (6.5m)`; agent-mode + agent-evidence + outcome-capture -> `46 passed (4.0m)` (flaky đã biết `vision-outcome-capture.spec.ts:10` không xuất hiện lần này); agent-mode.qa + locators + vision.spec -> `35 passed (1.6m)`.
- `npx tsc --noEmit` -> exit 0 không output; `npx eslint` trên 3 file đụng -> exit 0.

## Giới hạn / rủi ro
- B chỉ phủ CSS animation vô hạn thuần scale/rotate/opacity; marquee/carousel translate, left/top/width, Element.animate, animation hữu hạn/transition KHÔNG được miễn (trang như vậy vẫn `state_kept_changing`). Control trong iframe/shadow chỉ có A.
- Cổng pass khi control lệch tới 3 px / IoU 0.8 so với lúc model thấy; click vẫn dùng hộp đo lại + hit test + exact-node verify tươi. Dung sai áp cho mọi control, không riêng animated (theo yêu cầu A).
- Chưa kiểm live: tỷ lệ hit/transparent dao động của widget thật (r13: 9-10 lần) chưa xác nhận hit TÂM luôn ổn định; nếu live vẫn `state_kept_changing`, bật `STATE_MISMATCH`/settle diag và xem entry nào đổi. Trường hợp dư địa: nới transparent cho control không animated (hiện cố ý chặt).
- Chi phí inspect: thêm 1 lần `document.getAnimations()` và đọc thêm 4 thuộc tính style/tổ tiên mỗi control; chưa đo trên trang lớn (giới hạn 5000 node vẫn có).
- `hgraph check` exit 0. `hgraph check --changed` exit 0 (còn danh sách uncovered cũ ngoài phạm vi).

## Service cần rebuild
`playwright-worker` (không rebuild trong vòng này theo yêu cầu). Không đổi control-plane/contract.

## Đề xuất bước kế
Rebuild playwright-worker, chạy lại phiên live trang chủ (cùng cấu hình r12) và kiểm `vision.state.settle_timeout` biến mất khi scroll 600 px và `state_mismatch` geometry-only không còn. Nếu còn: dump entry đổi (thứ tự, hit tâm, transparent) trước khi nới tiếp.

GRAPH_UPDATE
- graph đã cập nhật: playwright-vision-worker (sync --apply; sửa dòng mô tả cổng fingerprint)
- file mới đã đưa vào graph: không có file source mới (spec/fixture r13 đã trong graph); ADR 042 là tài liệu, ngoài graph
- hgraph check --changed: exit 0 (liệt kê uncovered cũ ngoài phạm vi); hgraph check: "✔ Không có vấn đề." exit 0

Tiến trình còn chạy: không (mỗi test tự đóng browser).
