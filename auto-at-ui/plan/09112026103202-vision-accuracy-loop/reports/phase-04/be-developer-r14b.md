STATUS: DONE

CONTEXT_CHECK
- conventions: docs/code-standards.md (hgraph brief), ADR-042, plan README
- graphs: playwright-vision-worker
- blast radius: 27 file bi phu thuoc / 10 file phu thuoc (hgraph brief)

## Impact inventory
Database: khong dung. Contract/wire: khong doi (hash, policy, metadata giu nguyen).
File sua: vision-checkpoints.ts (them `isPresentationOnlyAnimated`), vision-dom.ts, vision-operations.ts,
vision-settle-animation.qa.spec.ts, docs/adr/042-..., docs/vision-agent-operations.md, docs/graphs/playwright-vision-worker.md.

## 1. Leader BLOCKING (so sanh hash truc tiep)
- vision-dom.ts: `observeDom` nhan `options.held` (= `session.state`). Neu co: `held.fingerprint === expected && equivalentState(held, fresh)`; snapshot tra `state_fingerprint = held.fingerprint` (de buoc prepare `snapshot.state_fingerprint === expected` van dung). Khong co `held` (goi truc tiep) giu so sanh hash chinh xac nhu cu.
- vision-operations.ts prepare: `session.state.fingerprint === expected && equivalentState(fresh, session.state)`, roi `runtime.before = session.state` (hash da phat la dinh danh; drift khong cong don qua cac vong).
- refresh (`:543`): da la held vs expected (khong co inspect moi), giu nguyen, them comment.
- Grep `fingerprint` toan `workers/playwright/src` (khong spec): cac diem con lai la held-vs-wire hoac held-vs-held (snapshot hash vs expected, re-baseline sau execute), `url_fingerprint`/`semantic_fingerprint`/`form_presence` so truong chinh xac (giu chat, khong phai hash tong), `vision-history.ts:15` url digest, `vision.ts` parent_url_fingerprint (visual tree, khac luong). Khong con so sanh inspect-moi vs hash wire. Da ghi vao ADR.
- Test: `observe, prepare, execute on the pulse fixture` (qa spec): 3 vong observe -> cho 450ms -> prepare -> cho 450ms -> execute tren strong pulse (1.5), khong state_mismatch, click rot dung. Xac minh test bat loi: tam bo `held` thi test FAIL, khoi phuc thi PASS.

## 2. QA-P1
- Chon `force: true` (khong tam dung animation: force khong doi trang thai trang, pause phai khoi phuc tren moi duong loi).
- `isPresentationOnlyAnimated(target, point?)` (checkpoints): cung quy tac co `animated` (CSS animation vo han thuan scale/rotate/opacity, khong blocked, khong foreign transform, main document) VA diem click phai resolve ve target/descendant ngay luc do (vi force bo qua hit-target check cua Playwright).
- vision-operations.ts dispatch: `force` truyen vao ca nhanh dom_path lan locator click; sau hit test + exact-node verify hien co. Loi => false.
- QA-P1: bo `test.fail`, xanh. Them: ma tran true/false (pulse, strong, spin = true; static, marquee, left, width, carousel, diem bi che = false); marquee e2e khong click (setup khong settle, link khong bi click); pulse bi che: link khong bi click.
- PHAT HIEN (co san, khong do force): DOM mode ground click theo toa do (descriptor css), nen control che len pulse (nhin thay tren cung) NHAN click va operation `completed`; khong phai link bi xuyen qua. Test chi khang dinh link khong bi click xuyen. Neu muon chan "che" o DOM mode thi la thay doi ngoai pham vi phase (vision-locators/groundLocator) -> de leader quyet.

## 3. Docs
ADR-042: diem so sanh fingerprint, dispatch/force + ly do, gioi han ~6 px cong don, test. vision-agent-operations.md + graph playwright-vision-worker.md cap nhat noi dung. `hgraph check`: "6 graph, 464 file source. Khong co van de." (khong file moi, khong doi import, khong can sync --apply).

## 4. Output that
- `npx tsc --noEmit` -> exit 0, khong output
- `npx eslint` 4 file doi -> exit 0 (lan dau 5 loi no-explicit-any o spec, da sua)
- settle dev + QA + settle-observability + agent-mode + agent-mode.qa + agent-evidence + outcome-capture (--workers=1): `103 passed (5.8m)`
- dom, history, readiness, target-preflight, sample-guard, visual-buttons, observability, locators (--workers=1): `104 passed (49.3s)`
- vision-operations.spec.ts (--workers=1): `99 passed (6.4m)`
- qa spec rieng: `20 passed (41.9s)`

Tien trinh mo: khong (browser tu dong dong). Khong commit, khong docker, khong bridge.

GRAPH_UPDATE
- graph da cap nhat: playwright-vision-worker.md (van ban muc chan doan, khong doi quan he import)
- file moi: khong
- hgraph check: "6 graph, 464 file source. Khong co van de."
