STATUS: FAIL

QA VERDICT: FAIL
GRAPH: hgraph add playwright-vision-worker ...qa.spec.ts ok (tổng 32 file); `hgraph check` "✔ Không có vấn đề." exit 0; `hgraph check --changed` vẫn liệt kê uncovered-changed cũ (66 file, tool so tiền tố auto-at-ui/; file playwright thực ra đã trong graph).
Đã test: 22 case (QA-B1..QA-P1, REG-1..4, GR-1) — pass 21 / fail 1.

FAIL:
- QA-P1 — prepare click tâm link pulse -> chờ 700 ms -> execute => mong đợi `completed` + click đúng node, thực tế `action_outcome_unknown`, executed_click null, không click (Playwright "element is not stable", `workers/playwright/src/vision-operations.ts` ~780-790 `click({ timeout })`). Đối chứng trang tĩnh: completed. Raw repro: QA-P0. Spec `vision-settle-animation.qa.spec.ts` khoá bằng `test.fail`.

Hồi quy: tsc exit 0; 111 passed (settle/dom/history/readiness/preflight/sample-guard/visual-buttons/observability); operations 99 passed; agent-mode+qa+evidence+outcome-capture 66 passed (flaky outcome-capture:10 không xuất hiện).
Dung sai/biên/drift/hoán vị/reorder/overlay/relabel+pulse/marquee/wrapper translate/opacity/dừng giữa chừng/trang không animation: tất cả PASS (xem r14-test-cases.md).

Chưa test được: widget thật mongchiton, hit-test thật của site, iframe/shadow, Element.animate/transition (không miễn theo thiết kế), chi phí inspect trang lớn.
Stress test: không cần (so sánh in-memory, không đụng vòng lặp tập lớn/lock).

Tài liệu: plan/09112026103202-vision-accuracy-loop/qa/phase-04/r14-test-cases.md, r14-test-report.md; workers/playwright/src/vision-settle-animation.qa.spec.ts
Tiến trình mở: không (mỗi test tự đóng browser).
