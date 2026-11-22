STATUS: DONE

# Khao sat BE control-plane + contracts: engine "agent_loop"

CONTEXT_CHECK
- conventions: AGENTS.md (convention duy nhat; repo khong co docs/code-standards.md, docs/api-conventions.md; hgraph brief xac nhan). Da doc them plan/.../contract.md, docs/vision-agent-operations.md (phan lien quan), ADR 020/022/023/025/027/032/036/037 (doc tieu de + quyet dinh chinh). Bam pattern vision_trace_events.py / codex_batch.py / codex_candidates.py, noi ro: khong co convention rieng cho API.
- graphs: khong graph nao phu vung nay (docs/graphs rong, brief "0 graph"). De xuat user chay /h-graph; ten graph goi y: `vision-v4-trace`, `codex-bridge`.
- blast radius: vision_trace_events.py = 14 file bi phu thuoc (vision_events.py, vision_publisher.py, temporal_worker.py, 10 test) / 18 file no phu thuoc (hgraph brief, depth 2). Lien quan: working tree dang co ~55 file sua chua commit (git status), gom nhieu file tren duong di nay (codex_bridge.py, codex_candidates.py, vision_policy.py, vision_trace_events.py, rustfs.py...). Phase implement phai cho/hop nhat voi cac thay doi do.

Chi khao sat, khong sua code san pham. Moi dan chieu la `file:line` tinh tu tree hien tai (apps/control-plane = CP).

---------------------------------------------------------------------
## 1. Cho cam engine "agent_loop"

### 1.1 Cach chon engine: KHONG dung trace_version
`trace_version` (models.py:135, String(20), default "legacy") duoc so sanh `== "v4"` / `!= "v4"` o 9 noi, tat ca la dieu kien de vao ha tang lease/trace/worker. Dat "agent_loop" vao day se pha het:

| File:line | Vai tro |
|---|---|
| CP/infrastructure/persistence/repositories.py:927 | `claim` lease chi cho `trace_version == "v4"` |
| repositories.py:957 | `_fence` (moi commit_* dua vao no) tu choi neu != v4 |
| CP/infrastructure/workflows/vision_publisher.py:39 | publisher bo qua session != v4 |
| CP/application/vision_trace_events.py:72 | processor raise neu != v4 |
| CP/application/vision_events.py:66 | legacy processor "deferred" chi khi == v4 |
| CP/application/vision_screen.py:21 | live screen chi cho v4 |
| CP/application/vision_results.py:82,152,156 | `legacy` flag cho result/trace/links |
| CP/api/v1/routes/vision.py:157,272 | response `trace_version` |
| CP/infrastructure/vision_worker.py:128 + contracts vision_worker.py:26 | `contract_version: "v4"` o transport worker |

=> Giu `trace_version="v4"` (ha tang chung), them truong rieng chon engine.

Da tim cho tai dung truoc khi de xuat cot moi:
- `model_input_policy` JSONB (models.py:124): bi parse bang `CodexConsentSnapshot.model_validate(record.model_input_policy)` (vision_trace_events.py:~90) la ClosedModel extra=forbid (codex_bridge.py:46) => them key se hong v4/Codex. Khong dung duoc.
- Hau to `prompt_version` (models.py:123, String(100)): khong can migration, dispatch bang `startswith("agent-loop")`. Dung duoc nhung la "magic string", prompt_version bi `uow.running(lease, VISION_PROMPT_VERSION)` (vision_trace_events.py:80) va `proposals()` (vision_unit_of_work.py:254) ghi de/doc lai. Chi dung lam phuong an du phong neu PM khong muon migration.
- => De xuat: **cot moi `exploration_engine` String(20) NOT NULL server_default 'planner'** tren `visual_exploration_sessions` (gia tri: `planner`|`agent_loop`). 1 cot, an toan voi row cu (backfill = default).

### 1.2 Cac diem sua (khi implement)
1. API: `SubmitExplorationRequest` (routes/vision.py:99-108, `extra="forbid"`) them `engine: Literal["planner","agent_loop"] = "planner"`; `ExplorationResponse` (routes/vision.py:~157) them `engine`; `submit_exploration` (routes/vision.py:330-352) truyen xuong `service.execute(...)`.
2. Application: `RequestVisualExploration.execute` (CP/application/vision.py:~76 chu ky, 160-183 tao `VisualExplorationSessionModel`): them tham so `engine`; chi cho `agent_loop` khi `trace_v4_enabled` va provider la bridge (khop dong 119-122: Codex/Claude "requires v4"); them co `vision_agent_loop_enabled: bool = False` o config.py:58 (ben canh `vision_trace_v4_enabled`, config.py la noi duy nhat doc env — AGENTS.md). `prompt_version` luu `AGENT_LOOP_PROMPT_VERSION`. `VisionReload` (application/vision_reload.py:80) cung goi submit => reload giu engine cua session goc (hoac mac dinh planner; can chot).
3. Model + ORM: `models.py` (VisualExplorationSessionModel) them cot; Pydantic `VisualExplorationSessionRecord` neu co trong domain/entities (kiem khi lam).
4. Dispatch: `infrastructure/workflows/vision_publisher.py:20-47` hien tao 1 `processor = handler or VisionTraceEventProcessor(...)` truoc vong lap roi `await processor.execute(event)` (dong 44). Can chon theo `record.exploration_engine` ngay sau `uow.get_session` (dong 35-39): `VisionAgentLoopProcessor` (file moi `application/vision_agent_loop.py`) vs `VisionTraceEventProcessor`. `handler` test-injection phai giu nguyen. `temporal_worker.py:46-92` KHONG phai sua (chi goi `publish_vision_once`, dong ~90).
5. Legacy `VisionEventProcessor.execute` (vision_events.py:66) da tra "deferred" cho v4 => khong dung them.

### 1.3 Migration
- Tool: **Alembic** (alembic.ini o root, `migrations/versions/`, `migrations/env.py`). Head hien tai (do bang `uv run alembic heads`, offline): **`a4c6e8f01234`** (`migrations/versions/a4c6e8f01234_vision_twenty_model_calls.py`, down_revision f3a4b5c6d7e9). Migration moi: `down_revision = "a4c6e8f01234"`.
- Test migration mau: tests/test_codex_bridge_migrations.py, tests/test_vision_migration_compatibility.py.

### 1.4 Step log (evaluation_previous_goal / memory / next_goal / actions): can bang moi
Da xet cac cho tai dung:
| Ung vien | Vi sao khong du |
|---|---|
| `visual_action_proposals.action` JSONB (models.py:~155-170; ghi qua `uow.proposals` vision_unit_of_work.py:229-265) | la ban ghi theo tung action, unique(session_id, sequence); khong co cho cho field cap-step; docstring "without raw image content" va bat bien. Van PHAI dung cho tung action (xem 2.1) vi `VisualWorkerPrepare` bat buoc proposal_id. |
| `visual_operations.payload` JSON (models.py:~378) | luu serialize `VisualOperation` (contract `extra=forbid`) - khong them truong. |
| activity/progress events (`uow.progress`, vision_unit_of_work.py:112-124; `ActivityEvent.create_vision_progress` domain/activity.py:~248-310) | allow-list dong (stage->allowed_keys), gia tri chi scalar, `reason_code` closed set, `call_sequence <= 20` => khong chua duoc van ban tu do memory/next_goal. Nen dung de bao tien do (them stage `agent.step`), khong de luu log. |
| `codex_bridge_jobs` (models.py:183-222) | metadata job (hash/usage), "filesystem payloads are never copied" (docstring); khong chua noi dung. |
=> **Tao moi** bang `visual_agent_steps` (cung migration voi cot engine): `id, tenant_id (TenantRecord), session_id FK, step_index (unique cung session_id), snapshot_version int, evaluation_previous_goal text, memory text, next_goal text, actions JSONB, operation_ids JSONB, stop_reason null, job_id null, created_at` + `UniqueConstraint(session_id, step_index)`, FK cung kieu `fk_visual_operation_session` (models.py:350-358). Noi dung phai qua `redact_value` (agents/shared/redaction.py) + `validate_locator_value` truoc khi luu (van ban do model sinh, co the chua du lieu trang). Retention: gan theo `intent_retention_until` (models.py:122) - **can PM chot** (xem ASK_PM).
Rollback migration: `op.drop_table("visual_agent_steps"); op.drop_column("visual_exploration_sessions","exploration_engine")`. Backfill: khong (default 'planner' cho moi row cu). Lock: ADD COLUMN NOT NULL voi server_default hang so tren PG>=11 la metadata-only, khong rewrite bang.
Repository: them 1 method vao `SqlAlchemyVisualTraceUnitOfWork` (vision_unit_of_work.py, ben canh `proposals`, dung `_fence(lease)` de fenced write) thay vi class moi. API doc step (tuy chon, phase sau): them vao `vision_results.py` trace payload, KHONG can cho benchmark.

---------------------------------------------------------------------
## 2. Tai dung cho vong lap

### 2.1 Primitive operation: dung duoc, nhung `primitive()` la closure
- `ExecuteVisualOperation` (CP/application/vision_operations.py): `execute()` dong 228-305 (guard -> commit_prepared -> worker.prepare -> merge -> `_capture(before)` -> commit executing -> worker.execute -> merge -> `_capture(after)` -> `_ack`), `reconcile` 307+. **Dung nguyen** cho tung action cua agent: no chi can `VisualOperation` + `VisualWorkerPrepare`. Khoi tao giong vision_trace_events.py:165-176. Khong doi.
- Chi dan duoc nhu "primitive" la `async def primitive(...)` long trong `execute()` (vision_trace_events.py:250-342, ~90 dong, dung `nonlocal sequence, fingerprint, browser_parent, active_page` + `check_policy` dong 104-163). Khong import duoc. Acceptance #7 (v4 khong doi) => KHONG sua file nay; engine moi co `OperationRunner` nho (~60 dong) trong `application/vision_agent_loop.py` tai tao: build `VisualWorkerPrepare` + `VisualOperation` roi `operations.execute`. Day la lap co chu dich (nen ghi no ky thuat, hop nhat sau khi v4 dong bang).
- Rang buoc contract cho tung action (contracts/vision_worker.py):
  - click/type bat buoc `state_id` va `proposal_id` (references(), dong ~178-179) va FK sang `visual_exploration_states` / `visual_action_proposals` (models.py:~375-376; check tai repositories.py:1008-1016: proposal.originating_state_id == operation.state_id, edge khop). => moi click/type cua agent can: 1 state row (sinh boi op truoc voi `checkpoint_id`+`checkpoint_state_id`, nhu vision_trace_events.py:344-350 va 1367-1368), 1 proposal + 1 `VisualTrajectoryEdgeRecord` qua `uow.proposals(lease, state_id, candidates)` (vision_unit_of_work.py:229-265; edge xay o vision_trace_events.py:795, `candidates` tuple `(proposal_id, sequence, safe_action, edge, binding)`). Day la phan tai dung lon nhat, giu duoc evidence `locator` + `proposal`.
  - `VisualWorkerAction.kind` chi gom `click|type|scroll|wait|navigate|back|close_popup` (vision_worker.py:~118); `navigate` KHONG co truong url (action_fields: required = rong, dong ~131-143) = chi load lai target_url. => cac tool trong paper (press_key, hover, select_option, wait_for, navigate toi URL tu do, take_screenshot) CHUA co. Mo rong phai doi contract `VisualWorkerAction` + worker TS (ngoai pham vi khao sat nay) va `benchmark/vision/accuracy/evidence.py:10 ACTIONS` + `export_operation` (evidence.py:33-51) neu them kind moi; benchmark se `raise ValueError("unknown operation status/action")` voi kind la. Khuyen: giai doan dau CHI dung 7 kind co san (click/type/scroll/wait/back/close_popup + navigate-reload), "navigate url" de phase sau.
  - `purpose` chi `setup|explore|restore|replay` (vision_worker.py:~158; evidence.py:36; activity.py `purpose` set). Agent: op dau `navigate` purpose="setup" (nhu vision_trace_events.py:344), moi action cua agent purpose="explore". Khong dung "replay" (khong co replay).
- Tham chieu ref/phien ban snapshot: `VisualWorkerObserveDom.snapshot_id: UUID` (vision_worker.py:~65) + `expected_state_fingerprint`; ket qua `CodexBoundObservation` (codex_bridge.py:153-168) co `bindings` (descriptor + bounds) theo `element_id` (`^e_[a-f0-9]{32}$`, codex_bridge.py:24). "ref v:n" = anh xa **phia control-plane**: moi lan `worker.observe_dom` tang `version` va gan `n` theo thu tu element => map `{(version,n): element_id}` trong RAM. Ref khac version moi => tu choi truoc khi goi worker (dap ung AC2, khong co browser action). Worker van chong stale lop 2 qua `dom_snapshot_id/dom_element_id` + `check_target` (vision_trace_events.py:1340-1346; contract `VisualWorkerCheckTarget`). Observation toi da 100 element/65 536 byte (codex_bridge.py:64-65,122-137) va co `truncated/skipped_count/unsupported` => "marker [refs a-b trimmed]" khi cat theo `max chars` tinh ra phia control-plane khi render prompt (observation da bi worker cat o 100 element).
- Quan sat DOM: dung lai logic `scan_page` (vision_trace_events.py:453-482) nhung la closure => engine moi goi truc tiep `self.worker.observe_dom(VisualWorkerObserveDom(... snapshot_id=uuid4(), expected_state_fingerprint=fingerprint, max_elements, max_bytes))`. Quan sat bat buoc `fingerprint` khop sau moi op (primitive cap nhat tu `result.state_fingerprint`, vision_trace_events.py:333).

### 2.2 Budget / rate: `CodexCallBudget` tai dung nguyen
- `CodexCallBudget` (CP/application/codex_candidates.py:76-128): `max_calls`, `max_rate`, `deadline`, `check_policy`, `reserve()`, `wait_for_slot()` - tong quat, dung nguyen (khoi tao nhu vision_trace_events.py:397-405). `AgentStepGuard.reserve_external_call` (agents/shared/runtime.py:~183-192).
- `CodexCandidateService._propose` (codex_candidates.py:~150-290) KHONG tai dung: gan chat voi 2-stage dom->image, `validate_candidates`, `CodexCandidates`, retry malformed, revalidate. Engine moi: `AgentStepService` nho dung `budget.reserve()` + `exchange(...)` (cung `CodexExchange` Protocol, codex_candidates.py:68-73) + `CodexBridgeResponse`.
- **TRAN CUNG 20 LAN GOI MODEL/PHIEN** o 6 cho: `VisionPolicy.max_steps le=20` (runtime.py:47), `StepGuardPolicy.max_steps_per_run le=20` (runtime.py:27), `CodexBridgeRequest.request_sequence le=20` (codex_bridge.py:~207), `CodexBridgeResponse.request_sequence le=20` (codex_bridge.py:~345), CHECK `ck_codex_job_sequence BETWEEN 1 AND 20` (models.py:~190; migration a4c6e8f01234 vua nang tu 10 len 20, downgrade bi chan), activity `call_sequence <= 20` (activity.py:~277). Vong lap click-all-47-controls chi kha thi bang bulk action (nhieu action/lan goi) trong 20 buoc; muon >20 buoc thi can migration + nang 6 cho (phase rieng, **can PM**).
- Bridge exchange: `CodexModelBatch.__call__` (CP/infrastructure/vision/codex_batch.py:43-162) tai dung gan het (register -> spool.publish -> poll -> validate_response -> finish -> ack, cancel path). Phai tong quat hoa 3 cho cung (mac dinh giu hanh vi cu): `PROMPT_VERSION` import cung (dong 10, dung dong ~77), `output_schema(max_candidates)` (dong ~64, tu `agents/vision/codex_service.py:27-62`), `stage="image" if image else "dom"`. Them tham so tuy chon `prompt_version`, `schema_bytes` (ham tao schema do caller truyen), mac dinh = cu => v4 khong doi byte schema (schema_sha256 nam trong request hash, dung de doi chieu).
- `CodexTaskContext` (codex_bridge.py:188-198): `task_intent<=4000`, `observed_actions <=10 muc x 120 ky tu`, tong <=8192 byte => KHONG du de mang memory + last-K history. Can truong moi (xem 2.3).

### 2.3 Contract output schema moi: dat o `packages/contracts/src/auto_at/contracts/codex_bridge.py`
Ly do dat o day (tim cho tai dung truoc): `CodexBridgeResponse.output: CodexOutput` (codex_bridge.py:~352) va `parse_codex_output` (dong 323-328) la duong duy nhat bridge tra ket qua, `ClosedModel` (dong 46) co san; tao module moi se phai nhan doi validate_response (domain/codex_bridge.py) va spool. Doi sau day:
- Them `AgentAction` (flat: `kind`, `ref: str|None pattern ^[0-9]+:[0-9]+$`, `text`, `delta_y`, `duration_ms`, `expected_outcome`) va `AgentStep(outcome="agent_step", evaluation_previous_goal, memory, next_goal, actions: tuple[AgentAction,...] (min 1,max N))`. Dung lai `CodexNeedScreenshot`, `CodexStop` (codex_bridge.py:308-319). `done`/`stop` = `CodexStop` (reason them gia tri hoac field rieng - `reason: Literal["complete","no_safe_action","unsupported_state"]` hien tai; "done" co the map vao `complete`).
- **Khong them vao `CodexOutput` hien tai**: `output_schema()` (codex_service.py:28) dung `TypeAdapter(CodexOutput).json_schema()` => them bien the lam doi schema v4 (schema_sha256) va pha benchmark identity + claude `enforceable_schema`. Tao `AgentLoopOutput = Annotated[AgentStep | CodexNeedScreenshot | CodexStop, Field(discriminator="outcome")]` rieng, va `BridgeOutput` (union phang tat ca 4 outcome) chi dung cho `CodexBridgeResponse.output` + ham `parse_agent_output`. Dieu kien: outcome literal khac nhau.
- `CodexBridgeRequest` (codex_bridge.py:201-251): `prompt_version` pattern `^codex-dom-v[1-9][0-9]*$` (dong ~215) => mo rong regex cho `agent-loop-v1`; `valid_job` (dong ~225-230) liet ke cac version bat buoc `context`; them `agent_context: AgentLoopContext | None` (closed: `memory` <=N chars, `history` <=K x {step, evaluation, next_goal, action summaries+result}, `snapshot_version`, `allowed_hosts`) co gioi han byte rieng. `candidate_limit le=10` (dong ~232) va `dom_element_count` giu nguyen.
- Parser: `output_parser: Callable = parse_codex_output` la tham so injectable (process.py:152, 223; claude_process.py:255, 320) nhung chi nhan `data` (bytes), khong nhan request => bridge phuc vu ca 2 ho prompt can chon parser theo `request.prompt_version` (sua nho o process.py:223 / claude_process.py:320 hoac parser thu lan luot BridgeOutput). Day la cho can doc ky khi implement.
- **Claude `enforceable_schema`** (infrastructure/codex_bridge/claude_process.py:39-70): hop nhat `properties` cua node cha vao moi bien the `anyOf` neu tat ca bien the deu co `properties`. Vong 21 attempt #2 that bai vi schema dung chung khong satisfiable (benchmark/vision/accuracy/ROUND21-20261119.md "Failed attempts"). Schema agent PHAI: (a) `strict()` (codex_service.py:46-58) dat `required = tat ca properties` va `additionalProperties=false` => moi field cua AgentAction phai nullable (dung null cho truong khong dung, nhu CodexCandidate), (b) tranh `anyOf` cap action (dung 1 object phang + validator Pydantic kiem to hop kind/field) de `merge` khong can xu ly, (c) union cap `result` chi co `anyOf` khong co `properties` nen `merge` la no-op. Them test tuong tu tests/test_claude_bridge.py cho schema agent (kiem bang jsonschema rang mau hop le thoa va mau sai bi tu choi). Code ClaudeProcess khong can sua neu theo (a)-(c).

---------------------------------------------------------------------
## 3. Prompt

- File moi: `apps/control-plane/agents/prompts/agent_loop.py` voi `PROMPT_VERSION = "agent-loop-v1"`, `INSTRUCTIONS`, `build_prompt(request, dom)`; dong moi trong bang `agents/prompts/README.md` (AGENTS.md bat buoc cap nhat README + version). KHONG sua `codex_exploration.py` (codex-dom-v11): ten/ban nay la danh tinh benchmark (ROUND21 ghi "same prompt codex-dom-v11") va `build_prompt` kiem `request.prompt_version != PROMPT_VERSION` (codex_exploration.py:~84) se tu choi version khac. Claude: tai dung nguyen `claude_bridge.SYSTEM_PROMPT` (claude_bridge.py:12-19, "proposal model... structured output") - khong can prompt he thong moi.
- Bridge chon builder: `codex_bridge_cli.py:52` truyen `build_prompt` co dinh vao `BridgeService` (application/codex_bridge.py:61: `with_response_schema(self.prompt(request, dom), schema)`). Can mot dispatcher nho theo `request.prompt_version` (vi du dict trong codex_bridge_cli.py) - khong tao lop moi.
- **Thu tu cache**: hien tai `build_prompt` = INSTRUCTIONS + json(context{stage, limit, task, observation}) va `with_response_schema` NOI schema SAU cung (codex_exploration.py:70-73, application/codex_bridge.py:61) => phan bien dong (observation) truoc schema, khong co prefix tinh dai de cache. Voi agent-loop thu tu bat buoc: (1) INSTRUCTIONS tinh, (2) response schema tinh, (3) session context (task, allowed hosts, gioi han), (4) memory + last-K history, (5) snapshot hien tai (cuoi). => builder agent tu nhung schema o vi tri (2) va `application/codex_bridge.py:61` bo qua `with_response_schema` cho version agent (nhanh co dieu kien theo prompt_version). Codex dua chi dan tinh qua `model_instructions_file` (process.py:~57) + stdin; Claude dua `--system-prompt` (claude_process.py:83) => phan (1) da tinh cap CLI. Moi job la 1 tien trinh moi, `--ephemeral`/`--no-session-persistence` (process.py:67, claude_process.py:~80) nen chi co prefix-cache cap nha cung cap. Do duoc bang `CodexUsage.cached_input_tokens` (codex_bridge.py:331-335, da co cot `usage` JSONB o codex_bridge_jobs, models.py:~216).
- Giu nguyen: du lieu trang la khong tin cay; `redact_value`/`task_context` (codex_service.py:16-24) ap cho task + memory.

---------------------------------------------------------------------
## 4. An toan bang code: hien co gi, dat o dau

Hien co (file:line):
| Co che | Noi | Ghi chu |
|---|---|---|
| Allowlist origin cua project | `ProjectExecutionPolicy.allows` (packages/contracts/.../execution.py:72-100), `origin_for_url` (generation.py:64-69), policy lay qua `uow.context(scope)` | submit v4 CHI goi `origin_for_url(target_url)` (application/vision.py:137-141); kiem allowlist chi cho legacy (vision.py:143-150, `not trace_v4_enabled and ...`). v4 `check_policy` (vision_trace_events.py:104-163) khong so allowed_origins; allowlist chi duoc truyen cho worker `VisualWorkerOpen.allowed_origins` (vision_trace_events.py:221) => **thuc thi o worker (TS)**. |
| Quan sat origin ngoai | `RecordVisualOrigins` (application/vision_origins.py:1-40) | chi ghi (docstring "without gating browser execution"), khong chan. |
| Scope tuong tac | `interaction_scope(intent)` (domain/vision_scope.py:7-18) | chi nhan dien cau "test all buttons", khong phai safety. |
| Du lieu nhay cam | `redact_value` (agents/shared/redaction.py:1-60), `validate_locator_value` (contracts/vision.py:220-226), kiem typed text (codex_service.py:78-82), `_SENSITIVE_KEYS` (domain/activity.py:11) | cho van ban, khong cho hanh dong. |
| Keyword/form-submit/download block | **khong co trong control-plane** | ROUND21: 2 download da bi click ("47 explore clicks completed (45 observed, 2 downloads)"). `CodexDomElement` chi co role/name/input_type(submit,reset)/enabled/editable/button_kind (codex_bridge.py:103-120): khong co href/form/download => rule "form submit" duoc 1 phan (input_type submit), "download" can them truong vao observation (worker TS) hoac chan bang popup/download event o worker. |

De xuat (tao moi, vi khong co cho tai dung):
- `apps/control-plane/domain/vision_agent_safety.py` (domain thuan, AGENTS.md: domain khong import ha tang): `check_action(action, element, allowed_origins) -> Decision` (keyword deny-list tren `name`, `input_type in {submit,reset}`, kind khong ho tro, host cua URL theo `ProjectExecutionPolicy.allows`/`origin_for_url` tai dung). Test thuan trong `tests/test_vision_agent_safety.py`. Goi trong engine truoc moi `worker.prepare`; vi pham => khong goi worker, ghi step log + `rejected` o phia control-plane (khong tao operation) hoac ghi operation `rejected` neu benchmark can thay (xem muc 5).
- Allowlist theo session: tai dung `policy.allowed_origins` cua project (da duoc truyen cho worker o `VisualWorkerOpen`) lam allowlist; target phai thuoc no (them check tai submit cho agent_loop - hien v4 bo qua, vision.py:143-150). Neu muon thu hep theo session (khac project) thi can luu o dau do (cot/JSONB) - **ASK_PM** (khong co cho luu hien tai: `model_input_policy` bi ClosedModel khoa, xem 1.1).
- Popup/navigate ngoai allowlist dong/chan: thuc thi o worker (ADR-022 popup, `close_popup` kind co san); control-plane chi ghi nhan qua `RecordVisualOrigins` (da co) + chan hanh dong tiep.

---------------------------------------------------------------------
## 5. Evidence tuong thich benchmark (`run.py collect/evaluate`)

`collect` (benchmark/vision/accuracy/run.py:178-241) doc: `GET /result` (`schema_version=="v1"`, `exploration_state` terminal, `completion_reason`, `exploration_report.conclusion` - toan bo conclusion la `.get` tuy chon, run.py:215-232), phan trang `GET /trace` (`items`, `locators`, `revision`, `has_more`, `next_sequence`, run.py:196-212), frames `/operation-frames/{id}` (run.py:244-251, kiem sha256+byte_count). `export_operation` (evidence.py:33-51) can moi op: `status in STATUSES`, `action_kind in ACTIONS`, `purpose in {setup,explore,restore,replay}`, `id` safe, `sequence` int, `state_id/checkpoint_id/locator_id/proposal_id/parent_operation_id/before_page_id/after_page_id`, `url_change/visual_change`, `before/after` frame metadata. `export_locator` (evidence.py:54-62): `status` (verified...), `path` chi neu `descriptor.strategy=="dom_path"` va khop regex PATH.
`evaluate` (run.py:262-306): moi operation phai co assessment (khong bo sot); `status/purpose/action_kind` khop; voi target dung can `locators[op.locator_id]` co `status=="verified"` va `path == oracle.reference_path`; checksum frame before/after.
Engine moi phai ghi:
1. Op dau `navigate`, purpose `setup` (+ checkpoint) nhu vision_trace_events.py:344-350.
2. Moi click: purpose `explore`, `action_kind="click"`, **co `dom_snapshot_id` + `dom_element_id` (binding) trong `VisualWorkerPrepare`** (vision_trace_events.py:~288-292) thi worker moi tao `VisualLocatorEvidence` verified voi `descriptor.strategy="dom_path"` (dau vao cua `binding["path"]`); click bang toa do (khong binding) khong cho locator verified => khong ghi diem oracle. Do do ref "v:n" phai luon resolve thanh `(snapshot_id, element_id)` va truyen binding, khong truyen toa do tu do.
3. Frame before/after day du moi op (ExecuteVisualOperation lo, vision_operations.py:228-305 + ack).
4. Khong dung purpose "replay"/`restore` that bai => khong co `unsafe_replay` (chi phat o vision_trace_events.py:1037) - AC6 thoa neu engine khong bao gio phat replay. Khi trang doi (popup) dung `close_popup`/`back` purpose "explore"? (doc: o v4, `close_popup`/`back` dung purpose `restore`; benchmark chap nhan ca 4 purpose; chon "explore" cho agent vi `exploration_conclusion` va `findings` chi dem `purpose=="explore"`, vision_results.py:210; vision_conclusion.py:9-12).
5. `result` : `exploration_conclusion` tinh `observed_controls` tu `pages` (page inventory, vision_conclusion.py:23-26) - agent khong co inventory => `status="partial"`, `coverage="not_established"`, `interaction_scope="unknown"`: khong loi, collect van chay (cac truong la tuy chon). KHONG de `unsafe_replay`. Neu muon `completed` cho goal-driven thi dinh nghia conclusion moi (ngoai pham vi, khong doi metrics).
6. `completion_reason` = `safe_failure_reason` khop regex `^[a-z][a-z0-9_]{0,79}$` (vision_results.py:164-171). `uow.finish(lease, reason)` (vision_unit_of_work.py:138): dung ma moi `agent_done`, `agent_step_limit`, ... — luu y `reason_code` cua activity bi gioi han tap dong (activity.py:~262-272) nen ma moi phai them vao set do (hoac chi dung ma co san: `exploration_call_limit`, `session_timeout`, `policy_disabled`...). `finish` cung tu dong chuyen edge "proposed" chua chay thanh `failed/terminal` (vision_unit_of_work.py:146-155).
7. Frame `purpose` tren API trace: `trace_version` response phai la "v4" (da dung), `legacy=False` => `evidence_status` bat dau tu frames (vision_results.py:157-160).

---------------------------------------------------------------------
## 6. Do tre bridge: rui ro cho vong lap tung buoc

- Du lieu that (ROUND21-20261119.md:45): 20 job / 829 s => ~41 s/job (claude_cli opus-5-5, effort low; 150 205 token vao / 9 061 ra). Rate toi da trong round: 5 req/phut (interval 12 s, `CodexCallBudget.wait_for_slot`, codex_candidates.py:92-101) khong phai nut that; thoi gian CLI moi job moi la nut that. Codex: round 20 tuong tu (Codex `model_reasoning_effort="low"`, process.py:47).
- Cau truc moi job: `register` (DB) -> `spool.publish` (file) -> poll 0.2 s (`poll_seconds`, codex_batch.py:36-37, 118-143) -> bridge host `claim` -> **spawn 1 tien trinh CLI moi** (`codex exec --ephemeral`, process.py:65-72; `claude -p --no-session-persistence`, claude_process.py:73-86) -> doc ket qua. **Khong co co che giu phien/stream giua cac buoc**: moi buoc la cold start CLI + toan bo prompt gui lai; flag `--ephemeral/--no-session-persistence` chu dong tat persistence (phuc vu bao mat/isolation, ADR-037). `authorize` moi 2 s/8 s (codex_batch.py:128-135) them cho phep.
- Anh huong vong lap: 20 buoc ≈ 14 phut model + thoi gian browser; session duoc dat `max_session_seconds` (policy) + `step_timeout_seconds` (v4 dung gia tri nay lam deadline tung buoc, vision_trace_events.py:81-92, models.py:131); `CodexBridgeRequest.deadline - created_at <= 3600 s` (codex_bridge.py:~246). Giam rui ro: (a) bulk actions (nhieu action/lan goi, AC4), (b) prompt nho + prefix cache tinh (muc 3), (c) khong dung screenshot tru khi `need_screenshot`, (d) `max_output_bytes` mac dinh 32 768 (codex_bridge.py:~233) du cho AgentStep co chu thich ngan.
- Giu phien/stream (khong khuyen o giai doan nay): doi bridge host sang tien trinh song (`claude -p --input-format stream-json` da dung stream-json 1 chieu, claude_process.py:84) can doi mo hinh bao mat (doctor/spool.claim 1 job = 1 process), nam ngoai pham vi; neu can thi la ADR rieng. Khong lam trong phase nay.
- Rui ro khac: bridge "CODEX_BRIDGE_ENGINE" chon 1 engine (codex hoac claude) cho ca bridge (codex_bridge_cli.py:31-45) - agent_loop dung chung bridge hien co, khong them provider/model (dung rang buoc contract.md).

---------------------------------------------------------------------
## 7. Test

### 7.1 Hoi quy v4 (phai xanh)
Truc tiep (hgraph "bi phu thuoc" cua vision_trace_events/vision/vision_operations): tests/test_vision_event_processor.py, test_vision_live_persistence.py, test_vision_locator_pipeline.py, test_vision_operation_failure_stage.py, test_vision_page_batch.py, test_vision_provider_integration.py, test_vision_target_preflight.py, test_vision_viewport_scan.py, test_vision_progress.py, test_codex_exploration_integration.py, test_codex_bridge_end_to_end.py.
Them cac file cham contracts/prompt/bridge/schema/migration: test_codex_bridge_contracts.py, test_codex_bridge_process.py, test_claude_bridge.py, test_codex_bridge_spool.py, test_codex_bridge_repository.py, test_codex_bridge_migrations.py, test_codex_candidate_service.py, test_codex_model_batch.py, test_codex_revalidation.py, test_vision_contracts.py, test_vision_worker_contracts.py, test_vision_operation_repository.py, test_vision_routes.py, test_vision_provider_submission.py, test_vision_reload.py, test_vision_results.py, test_vision_conclusion.py, test_vision_migration_compatibility.py, test_vision_policy*.py, test_vision_accuracy_loop.py / test_vision_accuracy_metrics.py (benchmark collect/evaluate/evidence).
Lenh (AGENTS.md:~40-45): `uv run ruff check .` va `uv run pytest` (`pyproject.toml:44-45` testpaths=tests, pythonpath=apps/control-plane + packages/contracts/src). Du kien chia theo nhom <= 9 phut khi chay that (>=117 file test).
### 7.2 Test moi (dat o tests/, quy uoc `test_vision_*.py`)
- `tests/test_vision_agent_loop.py`: processor loop bang fake worker + fake exchange, dung `tests/vision_trace_fixtures.py` (fixtures san) va mau `test_vision_event_processor.py`: happy path, ref cu bi tu choi khong goi worker (AC2), batch dung sau khi doi trang (AC4), gioi han buoc/rate/deadline, safety block, stop/done, operation purpose/action_kind dung cho evidence.
- `tests/test_vision_agent_safety.py` (domain thuan), `tests/test_agent_loop_contracts.py` (schema/AgentStep/AgentLoopContext, request prompt_version moi, parse_agent_output, claude `enforceable_schema` satisfiable), `tests/test_agent_loop_prompt.py` (thu tu static->schema->session->history->snapshot, bien dong o cuoi, version trong README), migration test cho cot `exploration_engine` + bang `visual_agent_steps` (mau test_vision_migration_compatibility.py), route test `engine` field + default planner (mau test_vision_routes.py).

---------------------------------------------------------------------
## IMPACT INVENTORY (phan backend, truoc khi sua)

### Database
| Muc | Noi dung |
|---|---|
| Bang | `visual_exploration_sessions` (them cot), `visual_agent_steps` (moi) — cung schema Postgres cua platform |
| Truong | `visual_exploration_sessions.exploration_engine` String(20) NOT NULL server_default 'planner', khong index (loc theo session id). `visual_agent_steps`: id UUID PK, tenant_id (TenantRecord), session_id FK `visual_exploration_sessions.id` + FK scope (tenant_id,project_id,session_id) theo `fk_visual_operation_session` mau, step_index int, snapshot_version int, evaluation_previous_goal/memory/next_goal Text (bounded), actions JSONB, operation_ids JSONB, stop_reason String(80) null, job_id UUID null, created_at timestamptz. Unique(session_id, step_index). |
| Thay doi | ADD COLUMN + CREATE TABLE. Khong ALTER/DROP gi cua v4. |
| Migration | `migrations/versions/<rev>_add_agent_loop_engine.py`, `down_revision="a4c6e8f01234"`. Rollback: `drop_table visual_agent_steps; drop_column visual_exploration_sessions.exploration_engine`. |
| Backfill | Khong; row cu nhan default 'planner' (so dong = so session hien co, metadata-only tren PG>=11). |
| Lock/downtime | ADD COLUMN const-default khong rewrite; CREATE TABLE khong khoa bang hien co (chi FK check). Gan nhu 0 downtime. |
| Consumer khac | Moi doc `visual_exploration_sessions`: repositories.py (claim/_fence), vision_results, vision_screen, dashboard API response (them `engine`, optional). Bang moi chi engine moi doc. |
| Index | Khong doi plan query hien co; unique index cua bang moi (session_id, step_index). |
Neu PM khong muon migration: phuong an du phong zero-migration = hau to `prompt_version` + log buoc vao `visual_action_proposals.action` JSONB (rui ro: tron lan, khong bat bien theo action, phai bo qua `evaluation/memory`). Khong khuyen.
Rang buoc CHECK: tran 20 request_sequence neu muon >20 buoc (models.py:~190) — migration phan rieng, **khong** nam trong de xuat hien tai.

### File & contract
Tao moi (moi cai da tim cho tai dung o tren):
- `apps/control-plane/application/vision_agent_loop.py`: processor vong lap (khong tai dung duoc `execute()`/`primitive` closure cua v4, 1510 dong, acceptance #7 cam sua).
- `apps/control-plane/domain/vision_agent_safety.py`: rule an toan thuan (control-plane khong co rule keyword/submit/download, 4 bang tren).
- `apps/control-plane/agents/prompts/agent_loop.py` + dong README: AGENTS.md bat buoc prompt tap trung, codex-dom-v11 la danh tinh benchmark.
- `migrations/versions/<rev>_add_agent_loop_engine.py`.
- Tests: xem 7.2.
Sua:
- `packages/contracts/.../codex_bridge.py`: AgentAction/AgentStep/AgentLoopOutput/AgentLoopContext, regex `prompt_version`, `valid_job`, `CodexBridgeResponse.output`, `parse_agent_output` (khong doi `CodexOutput`).
- `CP/infrastructure/persistence/models.py`: cot + model `VisualAgentStepModel`; `vision_unit_of_work.py`: method ghi step (fenced); (co the) `repositories.py` doc step.
- `CP/api/v1/routes/vision.py` (request/response `engine`, truyen xuong), `CP/application/vision.py` (+`vision_reload.py:80`), `CP/config.py:58` (`vision_agent_loop_enabled`; config.py la noi doc env duy nhat), `.env.example`.
- `CP/infrastructure/workflows/vision_publisher.py:20-47` (dispatch theo engine).
- `CP/infrastructure/vision/codex_batch.py` (tham so tuy chon prompt_version/schema), `CP/agents/vision/codex_service.py` (them ham schema agent, khong doi `output_schema`), `CP/application/codex_bridge.py:61` + `codex_bridge_cli.py:52` (dispatch prompt/parse theo prompt_version), `infrastructure/codex_bridge/process.py:223` / `claude_process.py:320` (chon parser).
- `domain/activity.py` (them stage `agent.step` + reason code moi neu can), `agents/shared/runtime.py` (chi khi nang tran 20).
Caller cua ham doi chu ky (grep that): `RequestVisualExploration.execute` <- routes/vision.py:~335 va vision_reload.py:~80; `CodexModelBatch.__call__` <- codex_candidates.py (exchange) va test_codex_model_batch.py. Them tham so co mac dinh nen caller cu khong vo.
Public contract dung toi: API `POST /explorations` (them `engine`, mac dinh `planner`), `ExplorationResponse`, bridge `CodexBridgeRequest/Response` schema (v1 khong doi hanh vi voi request cu), activity metadata allow-list, env `VISION_AGENT_LOOP_ENABLED` (ten du kien). `VisualWorkerAction` KHONG doi trong phase nay (neu can tool moi -> doi contract + worker TS + benchmark evidence.py ACTIONS).
Test hien co phu vung nay: xem 7.1; **chua co test** cho: dispatch engine, engine=agent_loop, schema agent, safety.

---------------------------------------------------------------------
## Cau hoi cho PM

ASK_PM
- question: Giu tran 20 lan goi model/phien (6 cho rang buoc) hay mo len (vd 40-60 buoc) cho agent_loop? Mo len = migration CHECK + doi contract request_sequence/policy/activity, anh huong v4.
  context: runtime.py:47,27; codex_bridge.py request_sequence le=20; models.py ck_codex_job_sequence; migration a4c6e8f01234 (downgrade bi chan)
  blocked_on: kha nang chay click-all-47-controls bang agent_loop (neu 20 buoc thi bat buoc bulk action ~3+ action/buoc)
- question: Tool moi cua paper (press_key, hover, select_option, wait_for, navigate toi URL, take_screenshot) co nam trong pham vi dau tien khong? Hien worker chi co click/type/scroll/wait/navigate(reload)/back/close_popup va navigate khong co URL.
  context: contracts/vision_worker.py:~118-143; benchmark evidence.py:10 ACTIONS
  blocked_on: pham vi `AgentAction.kind` va co can doi contract worker + benchmark
- question: Allowlist theo session co can khac allowlist cua project khong (can cot/JSONB luu)? Va "download/form submit" can chan o muc nao khi observation khong co href/form?
  context: vision.py:143-150 (v4 khong kiem allowlist luc submit), codex_bridge.py:103-120 (CodexDomElement khong co href)
  blocked_on: thiet ke domain/vision_agent_safety.py va co can mo rong observation tu worker
- question: Retention cho `memory/next_goal/evaluation` (noi dung do model sinh, co the chua du lieu trang): gan theo intent_retention_until hay luu ngan hon? Reload cua session agent_loop giu engine cua session goc?
  context: models.py:122; vision_reload.py:80
  blocked_on: schema bang visual_agent_steps va hanh vi reload

GRAPH_UPDATE
- graph da cap nhat: khong can — khao sat, khong them/xoa file, khong doi quan he import
- file moi da dua vao graph: (khong co)
- hgraph check --changed: chua chay (khong sua code). Khi implement: tao graph moi de xuat `vision-agent-loop` (application/vision_agent_loop.py, domain/vision_agent_safety.py, agents/prompts/agent_loop.py, contracts AgentStep) vi chua graph nao phu vision v4/codex-bridge; khong nhoi vao graph khac.
