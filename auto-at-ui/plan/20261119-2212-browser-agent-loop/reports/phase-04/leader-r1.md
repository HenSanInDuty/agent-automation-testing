STATUS: PASS

# Leader review phase 4 (r1)

VERDICT: PASS (khong co BLOCKING trong pham vi file phase 4; 1 dieu kien bat buoc truoc phase 5, xem muc 1)
CONVENTION: AGENTS.md (docs/code-standards.md chi la muc luc tro ve AGENTS.md; khong co api-conventions.md) - khop. domain/vision_agent_safety.py chi import auto_at.contracts + stdlib; application dieu phoi qua uow/worker/exchange; khong hard-code prompt; co test kem.
GRAPH: `hgraph check` hien exit 1, drift duy nhat = tests/test_vision_agent_loop_qa.py (file QA vua them, chua vao graph vision-agent-loop; dev da bao exit 0 voi 453 file, nay 454). Khong phai loi dev; chay `hgraph sync vision-agent-loop --apply`. File moi cua dev da vao graph: co.

## AC 1-5 va an toan (da doc code, vision_agent_loop.py)
- AC1: _run_batch L603-631: action bi chan chi ghi skipped_reason, operation_ids chi append sau _dispatch => len(operation_ids) <= len(actions). Moi lan goi model chi nhan snapshot moi nhat (make_context L545) + memory + 5 history (L548, L601).
- AC2: resolve_ref L118-124 (regex fullmatch => invalid_ref; version khac / khong co trong map / ref bi cat => stale_ref) chay truoc _dispatch => 0 prepare/execute.
- AC3: check_action (safety.py:70-83): kind ngoai 7, origin ngoai allowlist (fail closed khi origin khong ro; chi close_popup/back qua), submit/reset, tu khoa co dau + khong dau, \r\n trong type, secret qua validate_locator_value. Khong co "dang ky"/"nap the". Origin tu checkpoint page_url (L234); op doi URL ma khong checkpoint => page_unknown (fail closed).
- AC4: stop_cause L243-256 du 5 dieu kien; cause lam cac action sau batch_stopped voi 0 request (L611-613); type A/type B giu fingerprint nen chay ca hai.
- AC5: renderer L86-115 cat nguyen dong <= max_chars, marker dung ref dau/cuoi bi cat, dong skipped_count; history co dinh (<=5 dong x 600 + memory 2000).
- Ngan sach: CodexCallBudget.reserve() (codex_candidates.py:98-119) goi cho MOI lan goi trong _ask (retry malformed 1 lan, stage image) va tang calls; tran min(record.max_steps, runtime.max_steps, 20) (L294); vong toan action bi chan van dot 1 call/buoc => agent_step_limit, khong treo. Worker budget 1+200*(2*1+3)=1001 >= 401 (L60-66), co test.
- Lease/fence: check_policy so fencing_token; resume => _recover (evidence-only nhu v4), khong ghi trung step_index.
- v4 khong doi: vision_trace_events.py khong co trong diff; dispatch chi khi exploration_engine == "agent_loop" (vision_publisher.py:45); handler van ghi de ca hai.
- Scope: chi 6 file phase + graph (vision-agent-loop.md moi, vision-exploration.md sync). `git status -- benchmark` rong.

## Phan quyet cac van de developer neu
1. agent_step khong co trong /trace o production: XAC NHAN. routes/vision.py:738-745 truyen SqlAlchemyVisualTraceRepository; agent_steps(scope) chi o SqlAlchemyVisualTraceUnitOfWork (vision_unit_of_work.py:513); VisionResults._agent_steps (vision_results.py:29-44) getattr(..., None) => luon rong. Test chi gan tay repo.agent_steps = uow.agent_steps.
   Phan quyet: KHONG chan phase 4 (code dung chu phase doc "doc qua agent_steps cua unit of work"; loi o gia dinh cua plan, route/repo thuoc phase 1, phase 4 bi cam sua). Nhung la dieu kien bat buoc truoc khi phase 5 bat dau/duoc coi la xong, vi UI phase 5 phu thuoc. De xuat it xao tron nhat: them agent_steps(self, scope) vao SqlAlchemyVisualTraceRepository (apps/control-plane/infrastructure/persistence/repositories.py, canh snapshot; cung truy van select(VisualAgentStepModel).where(*_scope(...)).order_by(step_index)), de UoW:513 goi lai no (tranh trung); khong can sua route. Kem 1 test dung VisionResults + repo SQL that (khong gan tay). Can user duyet mo rong pham vi (repositories.py thuoc phase 1).
2. 665 dong: khong bat buoc tach. AGENTS.md khong dat nguong dong; chi plan phase 4 noi "chi tach lop neu > ~400" va liet ke dung 1 file. Tach = them file ngoai danh sach (+graph) trong khi cac ham da tach module-level. Ghi no cho phase 6 (co the tach render_snapshot/resolve_ref/allowed_hosts ~70 dong), khong chan.
3. finish(lease,"agent_done") => state unavailable: chap nhan. Plan AC6 ghi ro reason in {agent_done,...} la terminal va safe_failure_reason luu dung; activity cuoi thieu reason_code vi tap o vision_unit_of_work.py:211-217 khong co agent_*. Khong sai tinh dung dan; phase 5 map tu safe_failure_reason. Goi y (ngoai phase): them cac ma agent_* vao tap do neu muon activity co chi tiet.
4. hgraph check --changed exit 1: XAC NHAN loi tien to. --changed liet ke `auto-at-ui/apps/control-plane/...` (git goc o thu muc cha) la "uncovered-changed" cho ca file DA thuoc graph (vision_results.py, routes/vision.py, codex_service.py...); cung trieu chung phase 1-3, khong do phase 4. `hgraph check` thuong: dev bao exit 0; hom nay exit 1 chi vi file test cua QA.
5. benchmark: git status --short -- benchmark rong. Dung script Python khoi phuc la vi pham nhe quy trinh (Write/Edit) nhung ket qua sach, khong chan.

## Over-engineering (ponytail)
Khong co delete:/yagni:/stdlib:/native:; khong dependency moi ngoai plan. Ghi chu:
- vision_agent_loop.py:L69: shrink: STOP_REASONS dict 1 muc dung 1 lan (L561). Thay bang `"agent_done" if output.reason == "complete" else "agent_stopped"`.
- vision_agent_loop.py:L74-76: shrink: worker_operation_budget co tham so mac dinh chi de test; chap nhan duoc vi test ap cong thuc worker.
- vision_agent_loop.py:L109-111: shrink: vong while dung lai chuoi moi lan giam 1 (O(n^2) tren toi da max_dom_elements). Du nhanh cho ~1000 phan tu; neu can, tinh do dai cong don.
- _recover + run_operation lap v4: no co chu dich (AC7, ADR-038 phase 6).

## OPTIONAL
- vision_agent_loop.py:L582-595: nhanh loi dung next(reversed(run.results)) dua thu tu dict; dung hien tai (co test), mong manh neu run_operation sau nay ghi them results.
- Them tests/test_vision_agent_loop_qa.py vao graph (QA).

## EVIDENCE
- `uv run ruff check .` => All checks passed!
- `CODEX_BRIDGE_ENABLED=false uv run pytest tests/test_vision_agent_safety.py tests/test_vision_agent_loop.py -q -p no:cacheprovider -x` => 102 passed, 1 warning in 104.17s
- `hgraph check` => exit 1, drift vision-agent-loop: tests/test_vision_agent_loop_qa.py (file QA)
- `hgraph check --changed` => exit 1, uncovered-changed toan bo voi tien to auto-at-ui/ (40 file)
- `git status --short -- benchmark` => rong
- Khong chay lai hoi quy dai (QA chay song song).

NEEDS_USER_INPUT
- cau hoi: duyet mo rong pham vi: them agent_steps(scope) vao SqlAlchemyVisualTraceRepository (apps/control-plane/infrastructure/persistence/repositories.py, file phase 1) + test dung repo SQL that qua VisionResults, de /trace thuc su co agent_step o production?
- mac dinh neu khong tra loi: phase 4 van PASS; phase 5 khong bat dau cho toi khi quyet (UI se khong bao gio thay agent_step).
