STATUS: PASS

VERDICT: PASS
CONVENTION: AGENTS.md, docs/code-standards.md - khop.
GRAPH: `hgraph check` bao drift do file `fixtures/vision-tsx-runtime-flow-probe.ts` (untracked, cua QA, khong phai developer) chua vao graph. Hai file moi cua developer (probe, spec) da co trong playwright-vision-worker.md.
BLOCKING: khong co.
OPTIONAL:
- QA chay `hgraph add playwright-vision-worker workers/playwright/src/fixtures/vision-tsx-runtime-flow-probe.ts` (va vision-tsx-runtime.qa.spec.ts neu chua) de het drift.
- Shim addInitScript chi phu context tu open(); openVisualSession trong vision.ts khong co. Hien khong co named closure trong callback o do nen chua loi.

EVIDENCE
1. Goc loi: `npx esbuild --keep-names` tren moi src/*.ts khong phai spec, loc `__name(` co thut le. Moi hit deu la closure phia Node, ngoai callback evaluate: contract.ts:56, execute.ts:134/136, vision.ts:32, vision-dom.ts skip/ground/groundCandidate (source 163-170, sau callback ket thuc o dong 156), vision-locators.ts candidate (source 141, sau callback ket thuc o dong 137), vision-operations.ts onFrameNavigated/onNavigation/onPage (handler page.on), vision-screen.ts capture (CDP phia Node). vision-checkpoints.ts chi con `__name(` o muc module (ke ca boc ngoai isPresentationOnlyAnimated), khong co trong than callback inspectState. Object method geometry.layoutBox khong bi boc, dung pattern `traversal` san co.
2. Shim: `globalThis.__name = globalThis.__name || ((fn) => fn)` khong ghi de __name co san cua trang; no-op, rui ro thap. Probe co nhanh inspect_without_guard dung context tran (khong qua open()), nen chung minh callback tu sach ma khong nho shim. Bao cao r18 ghi red `__name is not defined` truoc khi sua.
3. Log: visionErrorDetails chi chay voi unexpected_error; tra error_name (allow-list ^[A-Za-z]{1,40}$, khong khop thi Error), error_origin (prefix API Playwright co dinh), error_digest (sha256 8 hex cua message). Khong log message/stack. Observability spec test 10 assert khong lo du lieu.
4. Test (chay that): `npx tsc --noEmit` exit 0. `npm test -- vision-tsx-runtime.spec.ts vision-observability.spec.ts --workers=1` -> `11 passed (5.5s)`, spec tsx 2.3s. Probe tu thoat (process.exit), browser.close + rm trong finally. Khong con chromium sau khi chay.
5. ADR-042: diff vision-checkpoints.ts chi doi `const layoutBox` thanh object method `geometry.layoutBox` va call site; phan toan giu nguyen.
6. Over-engineering: khong co delete:/yagni:/stdlib:/native:, khong them dependency, package.json khong doi.
