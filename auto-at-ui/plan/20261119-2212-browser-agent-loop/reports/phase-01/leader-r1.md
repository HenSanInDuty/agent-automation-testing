STATUS: PASS

# Leader review phase 1 (r1) - Contract + DB + chon engine

VERDICT: PASS (khong co BLOCKING)
CONVENTION: AGENTS.md "Code organization rules" + docs/code-standards.md (muc luc) - khop: route chi validate + goi use case, env chi doc o config.py, contract o packages/contracts, test focused. docs/api-conventions.md khong ton tai (bo qua theo prompt).
GRAPH: `hgraph check` (day du) = "Khong co van de". `hgraph check --changed` exit 1 la loi duong dan voi repo long (da xac nhan boi phien chinh). File moi (migration + 2 test) da vao graph vision-exploration. Xem muc 4.

## BLOCKING
Khong co.

## Quyet dinh 4 diem developer neu
1. 3 file test ngoai pham vi (handoff_repository:214, policy_persistence:49, policy_routes:155): PASS. Moi file 1-3 dong, bat buoc do hop dong doi dung phase (head revision b7c9d1e3f5a7; response policy them agent_loop_enabled). Khong co cach khong sua test cu ma van dung contract.
2. ruff: PASS co dieu kien (no, khong phai loi code phase 1). Chay lai `uv run ruff check .` -> 5 loi, tat ca o plan/.../reports/phase-00/v4_identity.py (I001 + 4 E501: dong 95,96,105,106). Code/test phase 1 sach. Cach re nhat: lead/pm dung `uv run ruff check --fix plan/20261119-2212-browser-agent-loop/reports/phase-00/v4_identity.py` (sua I001) va them dong dau file `# ruff: noqa: E501` (file la du lieu/chuoi dai, khong cat dong). Khong nen sua pyproject (exclude plan/) vi doi cau hinh chung. Phai lam truoc khi tick "ruff sach"; khong tra ve be-developer.
3. Validator JSON Schema tu viet (tests/test_agent_loop_contracts.py ~L305-460): PASS. `jsonschema` khong co trong uv.lock (grep = 0) nen them la dependency moi ngoai plan -> bi cam. Validator la tap con, tu choi keyword la, co test chong "pass rong" (test_schema_helper_would_notice_a_broken_merge, test_strict_schema_is_stricter_than_pydantic...). Chap nhan. Neu sau nay jsonschema vao dev group thi thay.
4. Graph: xac nhan THAT SU chua thuoc graph nao: `packages/contracts/src/auto_at/contracts/codex_bridge.py` va `apps/control-plane/infrastructure/persistence/models.py`. Ca hai chi duoc nhac trong van xuoi (codex-bridge.md:75-76, vision-exploration.md:159), khong co trong `files:` cua graph nao. Cac file con lai bi bao "uncovered" (routes/vision.py, application/vision.py, vision_reload.py, config.py, activity.py, vision_unit_of_work.py, vision_worker.py, TS sinh, 3 test sua) deu da nam trong graph (grep xac nhan) -> chi la loi tien to `auto-at-ui/`. Hai file tren la no co san tu truoc phase; phase ghi lap graph `vision-agent-loop` sau phase. Khong chan phase 1; de nghi pm giao viec lap graph (hoac gom codex_bridge.py/models.py vao graph hien co) truoc phase 6.

## Kiem tra theo checklist
- Acceptance/phase: AgentAction (kind/field combos qua _AGENT_ACTION_FIELDS, ref regex, navigate khong ref), AgentStep 1..10, AgentLoopOutput, AgentLoopContext (memory 2000, history 5x600, snapshot 24000), prompt_version mo regex, valid_job doi agent_context, BridgeOutput cho response, parse_agent_output, CodexOutput khong them bien the. Dung phase.
- v4 khong doi (acc 7): test sha256 CodexOutput schema = fixture v4_identity.json va test prompt+schema+request hash v11 deu xanh. model_serializer wrap bo agent_context khi null de giu byte canonical v4: hop ly, co ly do. TS regenerate: diff chi them agent_mode va blocked_action_terms.
- Migration: down_revision a4c6e8f01234, upgrade/downgrade doi xung (drop_table, drop_constraint, drop_column), dev chay up/down/up tren DB test (alembic-test-db.log), 1 test migration up/down trong test file. ADD COLUMN default hang = metadata-only; CREATE TABLE khong khoa bang cu. Luu y nho: create_check_constraint tren visual_exploration_sessions lay ACCESS EXCLUSIVE ngan va quet bang de validate; bang nho, chap nhan (ghi OPTIONAL).
- record_agent_step: dung _fence(lease); evaluation/memory/next_goal/actions qua redact_value; step doc theo scope tenant/project/session, order theo step_index; test fence, lease het han, unique, redact, tenant khac, FK scope, CHECK engine deu co.
- Route/application/reload: engine Literal mac dinh planner; tu choi khi co tat/provider khong phai bridge/ngoai allowlist; idempotency khong doi engine; reload giu engine (+ bi tu choi khi co da tat). agent_loop_enabled dat o lop co so VisionPolicyResponse de PUT echo khong 422 va bi loai khoi payload ghi: chap nhan, co test.
- Public contract: doi duoc neu ro (engine, agent_loop_enabled, agent_mode, blocked_action_terms, prompt_version regex, env 2 bien); khong doi lan.

## Over-engineering (ponytail)
Khong co delete/yagni/stdlib/native, khong dependency moi.
- apps/control-plane/application/vision.py:L124: shrink: `if engine not in {"planner","agent_loop"}` lap lai Literal o route; chi can neu co caller ngoai route (reload doc tu DB co CHECK). Giu cung duoc, ghi chu.
- apps/control-plane/infrastructure/persistence/vision_unit_of_work.py:L~495: shrink: kiem `len(operation_ids) > len(actions)` khong co trong plan; nho, co test. Giu.
- codex_bridge.py agent_loop_output_schema: strict() la ban sao nho cua output_schema o codex_service.py; plan buoc 3 yeu cau, phase 3 co the gop. Ghi chu.
Ngoai diff: khong co.

## ASK_PM dev neu
- spool 16KB: phase 1 khong can sua; contract cho snapshot 24 000 ky tu co the vuot gioi han doc request.json (spool.py:245) -> pm quyet truoc phase 3. Khong can doi phase 1 (neu chon cach (c) them gioi han byte thi sua AgentLoopContext o phase sau).
- invalid_ref: ref sai regex bi tu choi luc parse; khong can sua phase 1 neu phase 4 coi parse fail = model_output_invalid. Chua thay can sua phase 1.

## Ghi chu khac (OPTIONAL)
- Reason code agent_* chua vao VISION_MODEL_FAILURE_REASONS (domain/vision.py); phase 4 phai xu ly safe_failure_reason.
- domain/codex_bridge.py:43 BridgeProcessResult.output chua nhan AgentStep; phase 3.
- tests/test_codex_bridge_benchmark.py::test_offline_manifest_provenance... do san tu baseline phase 0 (dev xac nhan), khong do phase 1.

## EVIDENCE
- `uv run ruff check . --output-format concise` -> 5 loi, chi o reports/phase-00/v4_identity.py (I001, E501 x4).
- `CODEX_BRIDGE_ENABLED=false uv run pytest tests/test_agent_loop_contracts.py tests/test_vision_agent_engine_selection.py -q -p no:cacheprovider` -> 110 passed, 6 warnings (khong skip). (Khong dat CODEX_BRIDGE_ENABLED=false thi collection loi Settings do moi truong cua toi, khong phai loi code.)
- `node hgraph.mjs check` -> "4 graph, 441 file source. Khong co van de."
- Cac log hoi quy cua developer (pytest-G1..G4b, regression-1/2, page-batch) khong chay lai; chi 1 fail co san (benchmark manifest) da duoc phase 0 ghi nhan.
