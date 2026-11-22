STATUS: DONE

# be-developer r1 — phase-01 (A2)

```
CONTEXT_CHECK
- conventions: docs/code-standards.md (chỉ là chỉ mục sang AGENTS.md; AGENTS.md đã đọc). docs/api-conventions.md không tồn tại. Phạm vi này là worker TS nên không áp dụng luật control-plane Python.
- graphs: playwright-vision-worker (docs/graphs/playwright-vision-worker.md)
- blast radius: 19 file phụ thuộc vào vision-dom.ts (depth 2; vision-operations.ts, vision-revalidation.ts, vision-visual-buttons.spec.ts...) / 14 file nó phụ thuộc (hgraph brief)
```

Không có CONVENTION_ISSUE. Chữ ký export của `observeDom`/`DomSnapshot` không đổi; không đổi contract, control-plane hay `equivalentState`.

## Impact inventory
- Database: không đụng.
- Public contract: không đổi (chữ ký hàm, type export, response, env, config). Chỉ thêm trường đếm `motion_retraversals` vào hai log event (`vision.dom.coverage_limited`, `vision.dom.motion_regrounded`).
- Caller của `observeDom`: không đổi chữ ký nên không cần sửa caller (vision-operations.ts, vision-revalidation.ts, các spec).
- File sửa: `vision-dom.ts`, `vision-dom.spec.ts`, `docs/adr/045-observe-moving-visual-buttons.md`, `benchmark/vision/codex/manifest.json` (2 hash). Không tạo hay xoá file nào. Không đụng impact.html, plan.md, qa/.

## Diff tóm tắt (so với HEAD, vì code A chưa commit; phần A2 nằm trong đó)
- `workers/playwright/src/vision-dom.ts`: +110 / -50 so với HEAD (git diff --stat), trong đó A2 gồm:
  - :50 `traverse` bọc lại hai lệnh evaluate cũ (visualButtonSemantics + walk) để gọi lại được; :169 `let found = await traverse()`; `unsupported`, `skipReasons` thành `let`.
  - :181 `motion = { waits, regrounded, retraversals, invalidated }`.
  - :203 khối chờ chỉ chạy khi `motion.retraversals === 0` (một lần chờ mỗi lần quan sát).
  - :221-229 `moved = moving || displaced`; ground lại khi `still && moved`; không verified và hộp cuối không trọn viewport (cùng tiêu chí walk: x>=0, y>=0, x+w<=viewport.width, y+h<=viewport.height) thì `motion.invalidated = true`.
  - :241-296 `for (;;)` bọc vòng `collection` (thụt 2 space, nội dung giữ nguyên). Sau vòng: không cờ hoặc đã duyệt lại thì `break`; ngược lại dispose mọi handle giữ trong `anonymousTargets`, xoá elements/bindings/signature, `traverse()` lần 2, nạp lại `scrollable`/`unsupported`/`truncated`/`skipped`/`skipReasons`. Cổng `equivalentState(before, after)` và `contextSignature` vẫn chạy một lần cho lần cuối. `finally` cũ vẫn dispose khi lỗi.
  - Log: `motion_retraversals` ở `coverage_limited` và `motion_regrounded`; event `motion_regrounded` log khi `regrounded || retraversals`.
- `workers/playwright/src/vision-dom.spec.ts`: thêm helper `observeLoopSwiper` (:329) và `T-loop-out` (:369), `T-loop-jump` (:382). `observeSliding` giờ đếm số lần walk (`walks`) bằng wrapper `page.evaluate`. TC-03 đổi kỳ vọng (:280). Test "never stops" thêm `walks === 1` và `motion_retraversals: 0`. Bốn test chuyển động còn lại (non-control, pointer-control, removed, static) giữ nguyên.
- `docs/adr/045-observe-moving-visual-buttons.md`: viết lại theo A2 (bối cảnh A trượt 4/5 + 1/5, 4 điểm quyết định, giới hạn, rủi ro, test).
- `benchmark/vision/codex/manifest.json`: 2 hash (`vision-dom.ts`, `vision-dom.spec.ts`) sinh lại.

## Fixture và kỳ vọng test
Viewport 700x400, track 3 slide mỗi slide 700 px, mỗi slide có link `Play` giống hệt (cùng href, style), lớp phủ ở mép trái (0-330) và phải (620-700), `translateX` 600 ms linear, rest ở `-700px`. Test chặn `page.evaluate` để bắt đầu trượt ngay sau khi walk trả `candidates` (walk thấy link ở rest, trọn viewport), rồi chờ 80 ms nên grounding rơi vào lúc link đang nằm dưới lớp phủ (đúng khoảng T0/T1 của ADR).
- T-loop-out: track dừng ở slide kế (`-1400px`). Bản đã thấy nằm ngoài viewport (-400..-300), bản sao trên màn hình ở DOM position khác. Kỳ vọng: không lỗi, `elements == ["Play"]`, `skipped_count == 0`, `bounds.x ≈ 300/700`, event `motion_regrounded` có `motion_retraversals: 1`, không lộ `Play`, `/play`, `dom_path`, `nth-of-type` trong log.
- T-loop-jump: cuối transition reset không animation về `-700px`, bản đã thấy quay đúng chỗ. Kỳ vọng: bind được, `skipped_count == 0`, `bounds.x ≈ 300/700`, event có `motion_regrounded: 1`, `motion_retraversals: 0`.
- TC-03 (trượt hẳn ra, cover toàn chiều ngang), kỳ vọng cụ thể: đúng 2 lần walk, không có snapshot, lỗi chứa `state_changed_during_observation` (không phải skip). Lý do: sau lần walk 2 không còn ứng viên và skipped 0; link duy nhất của trang đã mất nên `equivalentState(before, after)` fail (log thật: `interaction_count_before 1, after 0`).

Lưu ý khi dựng fixture: dom_path dựa vị trí DOM (`nth-of-type`), nên một bản fixture đầu tiên có reorder slide kiểu `loopFix` làm descriptor tự trỏ sang bản sao đang hiện và test xanh trên code A nhưng không tái hiện lỗi. Đã bỏ reorder, dùng "track đứng ở slide kế".

## Red trên code A (trước khi sửa)
Lần 1, đúng code A thật (fixture bản đầu: có reorder và walk giữa slide), hai test đỏ vì thiếu `motion_retraversals`/`motion_regrounded`, nhưng assertion element vẫn qua, tức là fixture yếu, nên đã đổi fixture (walk ngay lúc rest, chờ 80 ms). Lần 2, code A + fixture cuối cùng (vì A chưa commit nên dựng lại A bằng cách tắt hai thay đổi A2 trong vision-dom.ts: `still && moved` → `still && displaced` và bỏ `motion.invalidated = true`, rồi khôi phục file A2 ngay sau):
```
  x  1 src\vision-dom.spec.ts:356:1 › T-loop-out: a copy that slid out of the viewport is re-observed once and its on-show twin is bound (928ms)
  x  2 src\vision-dom.spec.ts:369:1 › T-loop-jump: a copy whose track jumped back to where it was first seen is grounded again (994ms)
  1) T-loop-out ... expect(observation.elements.map(e => e.name)).toEqual(["Play"])
    - Expected  - 3 / + Received  + 1   -> Array [] (nhận mảng rỗng)
  2) T-loop-jump ... expect(observation.elements.map(e => e.name)).toEqual(["Play"])
    - Expected  - 3 / + Received  + 1   -> Array [] (nhận mảng rỗng)
  2 failed
```
Cả hai đỏ vì control bị skip (không có element), đúng triệu chứng live.

## Kết quả test thật (cwd workers/playwright)
- `npx tsc --noEmit`: exit 0, không output (chạy 3 lần, lần cuối sau khi sửa xong).
- `npx playwright test src/vision-dom.spec.ts` (toàn file, lần cuối): `46 passed (27.0s)`.
- Chuyển động + T-loop, `-g "visual button|T-loop|static visual"`:
  - `--repeat-each=20 --workers=1`: `160 passed (3.2m)`, exit 0.
  - `--repeat-each=20 --workers=4`: `160 passed (51.3s)`, exit 0.
  (8 test x 20; 0 flaky, 0 fail. Hai lượt này chạy trước nhận xét "ponytail" cuối, chỉ thêm 1 dòng comment sau đó; toàn file 46 test chạy lại sau đó xanh.)
- `vision-visual-buttons.spec.ts`: `3 passed (2.3s)`.
- `vision-operations.spec.ts`: `99 passed (6.0m)`.
- `vision-settle-animation.spec.ts`: `14 passed (11.6s)`.
- `npx eslint src/vision-dom.ts src/vision-dom.spec.ts`: 0 lỗi ở `vision-dom.ts`; 6 lỗi `no-explicit-any` ở `vision-dom.spec.ts` dòng 413-450 (test cũ "failed DOM collection...", không phải code tôi viết, đã có từ trước; không sửa vì ngoài phạm vi).
- Manifest: `uv run python benchmark/vision/codex/run_offline.py -q --tb=short tests/test_codex_bridge_benchmark.py -k manifest`:
  `1 passed, 9 deselected in 0.16s` và `{"summary": {"passed": 1, "failed": 0, ...}}`.
  Hash mới: `vision-dom.ts` `ccfadd2147431786e50063dd7ec6fc61807f01e41d9912e345ea89dddc62a247`, `vision-dom.spec.ts` `01fdd7a877f2c620a3a18f56c511bef67e8ec748158ae3f9cde41a6b99d9b12f` (sha256 của text chuẩn hoá LF; file làm việc đang là CRLF).

Chưa chạy: harness live trên site (`ab.mts`, cổng chính của plan), rebuild docker, preflight, review leader/qa. Phiên chính chạy.

## Ladder (tái dùng và đơn giản hoá)
- Không file mới, không helper export mới, không dependency mới.
- `traverse` (vision-dom.ts:50): arrow cục bộ bọc hai lệnh evaluate sẵn có để gọi hai lần, không đổi nội dung walk. Phương án khác (tách module, hàm export, `attempt` param) bị loại vì phình diff.
- Duyệt lại bằng `for (;;)` bọc vòng `collection` sẵn có, tái dùng `ground`, `skip`, `retained`/`finally`, `anonymousTargets`. Chỉ thụt 2 space vòng cũ.
- Hộp cuối trọn viewport: biểu thức inline 1 dòng, cùng tiêu chí walk (vision-dom.ts walk dòng ≈80-82), dùng `viewport` có sẵn. Không tạo hàm.
- Chặn lặp: dùng chính `motion.retraversals` (đã là bộ đếm cần log) làm cờ "đã duyệt lại", không thêm biến thứ hai.
- Spec: `observeLoopSwiper` là helper mới vì trigger và fixture khác `observeSliding` (spec:227); mẫu wrapper `page.evaluate` tái dùng từ test "anonymous inventory resolves a fresh point..." (spec:206). Đếm `walks` thêm vào `observeSliding` thay vì tạo helper thứ ba.
- Cố ý đơn giản có trần, có comment `ponytail:` (đúng convention sẵn có ở vision-dom.ts:16): trần một lần duyệt lại (:286). Trần chờ 1200 ms giữ nguyên comment `ponytail` cũ (:16).

## Diễn giải cần PM/leader biết
- Plan điểm 4 "tối đa 1 lần chờ + 1 lần duyệt lại": tôi hiểu là mỗi lần quan sát chỉ chờ ở lượt walk đầu; lượt walk thứ hai ground một lần (kèm retry tức thì sẵn có) và không chờ nữa, lỗi thì skip. Nếu muốn lượt hai cũng được chờ, đổi một điều kiện (`motion.retraversals === 0` ở :203), nhưng worst case tăng thêm 1,2 s mỗi batch.
- Ứng viên biến mất khi chờ (box đọc ra null) và chuyển động liên tục (không bao giờ still) không đặt cờ duyệt lại, đúng "vẫn skip như hôm nay" (test "removed" và "never stops" xác nhận; test sau kiểm `walks === 1`).
- Cờ chỉ đặt khi reground không verified. Nếu reground verified dù hộp chỉ trọn một phần viewport thì giữ binding (groundLocator đã kiểm viewport).

## GRAPH_UPDATE
- graph đã cập nhật: không cần — không thêm/xoá file, không đổi quan hệ import (`hgraph which`: cả hai file thuộc `playwright-vision-worker`)
- file mới đã đưa vào graph: không có
- `hgraph check` (đầy đủ): `hgraph check — 6 graph, 474 file source` / `✔ Không có vấn đề.`
- `hgraph check --changed`: báo `uncovered-changed` cho `auto-at-ui/workers/playwright/src/vision-dom.ts` và `vision-dom.spec.ts` (đã biết: lệch tiền tố đường dẫn do git root là thư mục cha; hai file đã thuộc graph theo `hgraph which`). Ghi nhận, không sửa.

## Dọn dẹp
Không mở tiến trình/server/docker nào. File scratch chỉ ở thư mục scratchpad của phiên; đã xoá file tạm `src/zz-debug.spec.ts` (rỗng). Working tree chỉ còn các file trong phạm vi (cộng `plan/09112026103202-vision-accuracy-loop/log.md` sửa từ trước, không phải của tôi).
