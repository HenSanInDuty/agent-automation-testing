# Phase 04 r14 - test report (QA r5)

QA VERDICT: FAIL

Môi trường: Windows 11, Playwright 1.50.1 (chromium headless), `--workers=1`, fixture cục bộ, không docker/mạng/bridge/model. Không sửa product code.

## Kết quả
- Spec QA mới: 16 test, 16 "passed" theo runner, trong đó QA-P1 là `test.fail` (kỳ vọng fail, đang fail đúng như mô tả) -> 15 pass thật, 1 FAIL thật.
- Hồi quy: tsc exit 0; nhóm settle/dom/history/readiness/preflight/sample-guard/visual-buttons/observability 111 passed (1.1m); operations 99 passed (6.4m); agent-mode + agent-mode.qa + agent-evidence + outcome-capture 66 passed (5.3m). Flaky `vision-outcome-capture.spec.ts:10` không tái hiện lần này.
- Dung sai: biên 3 px / 4 px và IoU 0.8 / 0.787 đúng đặc tả; drift 1 px/40 ms không settled; hoán vị, reorder, overlay, relabel+pulse, marquee, wrapper translate đều bị coi là đổi; opacity vô hạn được miễn; trang không animation không đổi hành vi.

## FAIL: QA-P1 - dispatch lên target đang pulse
- Tái hiện: `npx playwright test src/vision-settle-animation.qa.spec.ts -g "QA-P1" --workers=1` (gỡ `test.fail` ở spec để thấy đỏ).
- Các bước: mở phiên, route `/` trả `pulsingControlHtml` (link `aria-label` "Play now" trong `.widget` scale vô hạn), navigate setup, `prepare` click vào tâm link, chờ 700 ms, `execute`.
- Mong đợi: `completed`, click đúng node. Thực tế: `status=unknown`, `outcome_code=action_outcome_unknown`, `executed_click=null`, không có `data-clicked`; ~4 s từ `started_at` đến `ended_at`. Đối chứng cùng luồng với `staticControlHtml`: `completed`, `data-clicked=1`.
- Nguyên nhân (QA-P0, raw Playwright): `locator.click` chờ actionability "element is not stable" vì hộp control luôn thay đổi do scale vô hạn; hết timeout thì ném lỗi, `vision-operations.ts` quanh dòng 780-790 (`target.click({ timeout })` / `locator.click({ timeout, position })`) không có `force`/xử lý stability. `force: true` thì click được. Hệ quả: r14 gỡ `settle_timeout` ở bước settle nhưng bước dispatch vẫn thất bại với widget pulse thật; trước khi dispatch, mọi cổng (prepare, `equivalentState`, hit test, verify node) đều qua.
- Gợi ý cho developer (không tự sửa): cần chiến lược dispatch cho control animated (vd. tạm dừng animation của target bằng `Animation.pause()` rồi click và khôi phục, hoặc `force` sau khi đã verify hit tâm/exact-node), kèm test; sau đó bỏ `test.fail` ở QA-P1. Ưu tiên cao vì ảnh hưởng đúng ca live mongchiton.

## Graph
`hgraph add playwright-vision-worker workers/playwright/src/vision-settle-animation.qa.spec.ts` -> "Đã thêm 1 file ... (tổng 32)". `hgraph check` -> "✔ Không có vấn đề." (6 graph, 464 file), exit 0.
`hgraph check --changed` -> vẫn liệt kê `uncovered-changed` 66 file, gồm cả file playwright đã có trong graph (vision-checkpoints.ts, vision-operations.ts, ...) và file ngoài phạm vi (dashboard, benchmark, contracts); đây là danh sách cũ do tool so tiền tố `auto-at-ui/`, giống mô tả của be-developer-r14; `hgraph check` đầy đủ sạch nên không coi là lỗi của r14.

## Chưa test được
- Widget thật trên mongchiton (tần suất hit/transparent dao động, hit tâm có ổn định không): chỉ live mới biết.
- Hành vi hit-test thật của site, iframe/shadow DOM (chỉ có dung sai A), `Element.animate`/transition (không được miễn theo thiết kế): không có fixture thật.
- Chi phí inspect trên trang lớn: không đo (không stress vì không đổi độ phức tạp đáng kể).

## Tệp
- `workers/playwright/src/vision-settle-animation.qa.spec.ts`
- `plan/09112026103202-vision-accuracy-loop/qa/phase-04/r14-test-cases.md`, `r14-test-report.md`

# r2 (QA r6) - kiểm r14b

QA VERDICT: PASS

Phạm vi: FAIL QA-P1 (qa-r5) và BLOCKING leader-r6 (so sánh hash trực tiếp). Môi trường như trên (Windows 11, Playwright 1.50.1, `--workers=1`, fixture cục bộ, không docker/bridge/model). Không sửa product code; chỉ thêm 4 test vào `vision-settle-animation.qa.spec.ts` (đã sửa 1 lỗi tsc ở chính spec QA).

- QA-P1 xanh, không còn `test.fail`. Ổn định: qa + dev settle spec 2 lần `34 passed (52.8s)` / `34 passed (51.0s)`; qa spec sau khi thêm case `24 passed` 3 lần liên tiếp. Không flaky.
- Case mới: observe/prepare/execute nhiều vòng không `state_mismatch`; drift 1 px/vòng không trôi baseline (bắt từ 4 px so với hash đã giữ, giữ bị bắt ở 5/6 px; prepare sau 10 px bị từ chối); fingerprint kỳ vọng sai vẫn `state_mismatch`; `force` không quyết cho Element.animate (scale/translate), transition, wrapper translate, marquee, bị che.
- Hồi quy: `tsc --noEmit` exit 0; nhóm agent-mode/evidence/outcome-capture/dom/history/readiness/preflight/settle-observability `145 passed (6.2m)`; `vision-operations.spec.ts` `99 passed (6.3m)`.
- Graph: `hgraph check` "6 graph, 464 file source. Không có vấn đề."; `hgraph check --changed` vẫn liệt kê `uncovered-changed` 66 file do lỗi so tiền tố `auto-at-ui/` của tool (như r5/r14; các file playwright đã thuộc graph, full check sạch, file ngoài phạm vi). Không có file mới của r14b.
- Observation (không FAIL): DOM mode click theo toạ độ nên control che nhận click, op `completed` (`.qa.spec.ts` case "covered"); có sẵn, không do r14/r14b; để leader quyết nếu muốn chặn ở vision-locators.
- Dung sai tích luỹ: tối đa ~3 px so với state đã giữ (ADR 042); drift chậm hơn mỗi vòng mà baseline đổi qua execute (re-baseline) là thiết kế, không kiểm sâu hơn.

Chưa test được: widget live mongchiton; iframe/shadow DOM thật; Stress test: không cần (không đổi vòng lặp/query/lock).
