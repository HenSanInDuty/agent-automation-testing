STATUS: PASS

# Phase 2 â€” leader review r1

VERDICT: PASS
CONVENTION: AGENTS.md / docs/code-standards.md (chi muc tro ve AGENTS.md) â€” khop. Khong sua tay vision-contract.generated.ts trong phase 2 (diff cua file la do phase 1 sinh tu Python). Khong co api-conventions.md.
GRAPH: `hgraph check` day du exit 0 ("4 graph, 444 file source, Khong co van de"). `hgraph which` cho vision-agent-mode.spec.ts, fixtures/agent-loop-target.ts, vision-operations.ts deu thuoc playwright-vision-worker. File moi da vao graph: co.
BLOCKING: khong co.

## Checklist
1. AC/plan: buoc 1-8 deu co (vision-operations.ts: evictSnapshots :338, stale_dom_snapshot :545, sequential :558-585, K3 :521-526, sensitiveFacts :623-628, re-baseline :930-936, K4 :181-195/:846). 23 test phu moi muc "Unit test phai viet".
2. v4 khong doi: moi nhanh sau session.agentMode/sequential; v4 chay cung path cu; test doi chung v4 (limit, invalid_*_purpose, policyFailure khoa) xanh. Report ghi hoi quy 99+110+26 xanh, khong sua spec v4.
3. An toan: K3 khong abort sub-resource; K4 chi recover khi activeOperation, unknown/ngoai op van khoa; submit/reset/image-in-form/a[download]/tu khoa chan; type co \n chan (action kind khong co `press`, nen Enter chi qua type).
4. Contract: khong doi chu ky export; Session la type noi bo.
5. Lint/type: tsc exit 0; eslint 3 file phase 2 exit 0 (22 loi lint baseline nam o file ngoai phase, theo report, khong kiem lai).

## 5 diem developer tu quyet
(a) 25 -> 20 vong: CHAP NHAN. operation_budget = 1+max_states*(2*max_hops+3)=22 la cong thuc plan "Sua sau review"; 20 vong van >> max_states=3/max_hops=2 va v4 doi chung cham limit.
(b) K3 theo URL hien tai o prepare: CHAP NHAN. Phu redirect/popup/cung tab, khong them state; hanh vi dung K3. Luu y about:blank duoc loai tru hop ly.
(c) Chan type co \r/\n: CHAP NHAN (dung AC3 "type khong gui Enter"); nen ghi vao plan phase 4 de Python khong tao text co xuong dong.
(d) close_popup voi purpose explore: CHAP NHAN (can cho "close_popup chay" trong test plan; chi trong sequential).
(e) NFC + lowercase, khong bo dau: CHUYEN PHASE 4. Dung plan buoc 5; danh sach blocked_action_terms (Python) phai chua ca dang co dau va khong dau neu can; phase 4 phai test.

## Graph (muc 3 cua prompt)
`--changed` exit 1 do (i) git root la thu muc cha nen duong dan co tien to `auto-at-ui/` khong khop duong dan graph (vision-operations.ts va vision-contract.generated.ts bi liet ke du da thuoc graph â€” hgraph which xac nhan); (ii) 12 file Python/test cua phase 1 chua thuoc graph. Khong co file phase 2 nao thieu graph. Phase 2 DAT dieu kien graph. Viec can lam (khong thuoc phase 2): chay hgraph tu git root hoac bo qua tien to; lap graph cho vision.py/codex_bridge.py/vision_worker.py cua phase 1 khi gop.

## Over-engineering (ponytail)
Khong co delete:/yagni:/stdlib:/native:, khong dependency moi.
- workers/playwright/src/vision-operations.ts:L637-641 (shrink) khong bat buoc: `session.recovered = null` dat 2 lan (truoc dispatch va finally); lan truoc dispatch du roi neu finally da xoa â€” ghi chu, khong chan.
OPTIONAL:
- sensitiveFacts :48 dung `el` truc tiep; neu target la span ben trong nut submit thi typed=null va bo sot. Snapshot chi ground vao control tuong tac nen kha nang thap; co the dung `el.closest("button,input")` o phase sau.
- Tu khoa "chua" co the chan qua tay ("xoa" trong "Xoa bo loc") â€” quyet dinh danh sach o phase 4.

EVIDENCE
- `npm.cmd run typecheck` (workers/playwright): tsc --noEmit, khong loi.
- `npx eslint src/vision-operations.ts src/vision-agent-mode.spec.ts src/fixtures/agent-loop-target.ts`: exit 0.
- `npm.cmd test -- src/vision-agent-mode.spec.ts --workers=1`: 23 passed (2.4m).
- `hgraph check`: khong co van de, exit 0. `hgraph check --changed`: exit 1 (nguyen nhan o tren).
- Khong chay lai hoi quy v4 (dua vao bao cao developer).
