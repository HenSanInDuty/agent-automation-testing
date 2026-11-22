STATUS: PASS

# Leader review phase 5 (Dashboard) r1

CONVENTION: AGENTS.md / docs/code-standards.md (chi muc) - khop (TS chi dashboard+worker, test node:test canh code, khong file moi). Repo khong co convention UI rieng; so voi pattern ledger/vision-dashboard san co.
GRAPH: `hgraph check --changed` exit 1 la loi so duong dan (da biet). `hgraph sync vision-dashboard` (khong --apply): chi canh bao "file ngoai dang goi vao graph" (22 file, co tu truoc, khong lien quan phase), KHONG co canh bao import thieu/thua => graph da phan anh import moi ledger -> vision-provider-model. Chua ghi gi. Khong co file moi.

## BLOCKING
Khong co.

## Checklist
1. Acceptance: select `#vision-engine` chi khi `savedPolicy.agent_loop_enabled === true` (vision-dashboard.tsx:78, 253); planner khong gui key `engine` (provider-model.ts engineRequestFields); ledger 3 truong + Blocked (vision-operation-ledger.tsx:32-36); 10 ma loi moi (provider-model.ts failureMessages); gating `trace_version === "v4"` khong bi dung trong diff. Planner session: agentStepView tra null khi khong co `agent_step` => khong co khoi.
2. Shape khop BE: vision_results.py:29-43 tao `step_index, evaluation_previous_goal, memory, next_goal, skipped_actions` (actions co `skipped_reason`) = type `VisualAgentStep` (generation-types.ts). `engine` tra o routes/vision.py:278; `agent_loop_enabled` o routes/vision.py:95,293,333; request `engine` Literal planner|agent_loop (vision.py:112,162) khop payload. `agent_loop_enabled` bi loai khoi PUT (vision.py:328) nen FE chi doc la dung.
3. Test phu: mapping ma (khong trung, khong roi fallback), fallback ma la/`__proto__`/500 ky tu, agent step rong/dai/co dau/kind dai, engine la -> planner, payload engine. E2E 3 case moi (gating+payload, ledger+planner khong khoi, 400px scrollWidth). E2E khong chay theo yeu cau (QA).
4. Lint/type/test chay lai (dashboard): xem EVIDENCE.
5. Scope: chi 6 file phase + spec. Khong file moi, khong dependency moi. Lech nho: generation-api.ts mat khoang trang sau dau phay o `"/api/v1/vision/explorations",{` (cosmetic).

## Diem kiem them
1. Khang dinh dev "/trace chua tra agent_step o production" - SAI (da loi thoi). Chuoi noi: routes/vision.py:738-744 `_results` truyen `SqlAlchemyVisualTraceRepository(session)` lam `trace`; repositories.py:1273 co `agent_steps(scope)`; vision_results.py:29-31 `getattr(self.trace,"agent_steps")` + :90 goi + :112 gan `agent_step` vao item. (vision_unit_of_work.py:513 la ban UoW; route dung repository truc tiep, van co reader.) Chi gan khi `exploration_engine == "agent_loop"`. Khoi agent se hien o production khi engine dung.
2. hgraph: xem GRAPH o tren.

## Over-engineering (ponytail)
- Khong co `delete:`/`yagni:`/`stdlib:`/`native:`; khong dependency moi.
- vision-operation-ledger.tsx:32: shrink: `style={{ overflowWrap:"anywhere", minWidth:0 }}` inline - dung class san co neu co; khong chan (globals.css ngoai pham vi).
- vision-provider-model.ts engineRequestFields/explorationEngine: shrink: hai helper rat nho, chap nhan duoc vi can test duoc (ledger .tsx khong import duoc tu node test).
- Ngoai diff: khong.

## OPTIONAL / luu y cho QA
- Dev bao 2 e2e fail (spec :238 va :336, `toBeInViewport` ratio 0) chua co baseline HEAD. Diff khong dung DOM cua 2 luong do (select/hint chi render khi flag bat; khoi agent chi khi co agent_step), nen nhieu kha nang san co; QA nen chay baseline de chot, vi tieu chi "E2E xanh" cua phase phu thuoc dieu nay.
- Nhan tron Anh/Viet ("Danh gia buoc truoc", "Blocked") - can user chot, khong chan.
- Phase noi "nhan advisory doi cho session agent loop": dev doi hint o form theo engine da chon, khong doi nhan theo session da luu; khong co nhan advisory nao khac theo session trong code. Chap nhan.

## EVIDENCE
- `node --experimental-strip-types --test` (apps/dashboard): `tests 48 / pass 48 / fail 0`.
- `tsc --noEmit` (apps/dashboard): khong output, khong loi.
- eslint `.` (apps/dashboard): khong output, khong loi (pnpm khong co trong PATH bash; chay truc tiep binary).
- `hgraph sync vision-dashboard`: chi canh bao caller ngoai, khong import lech.
- Khong chay e2e / worker lint (QA; worker lint da co 22 no-explicit-any o file ngoai phase theo bao cao dev).
