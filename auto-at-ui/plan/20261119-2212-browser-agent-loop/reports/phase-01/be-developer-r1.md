STATUS: DONE

# Phase 1 - Contract + DB + chon engine (be-developer, r1)

Phase 1 hoan tat theo "File lien quan" va "Cac buoc thuc hien". Khong commit, khong chay migration len DB `auto_at`.
Co 2 diem lech pham vi (sua 3 file test ngoai danh sach, vi hop dong doi) va 3 van de can lead quyet (xem "Van de / ASK_PM").

CONTEXT_CHECK
- conventions: `AGENTS.md` va `docs/code-standards.md` (chi la muc luc tro ve AGENTS.md) da doc nguyen van. `docs/api-conventions.md` KHONG ton tai (theo prompt, bo qua). Bam AGENTS.md "Code organization rules" va pattern 2-3 file cung loai (`test_vision_provider_submission.py`, `test_vision_handoff_repository.py`, migration `f9a0b1c2d3e4`).
- graphs: `vision-exploration`, `codex-bridge`, `playwright-vision-worker` da doc (muc "Cham vao day thi phai kiem tra them": contract sinh tu dong, bang DB + migration, co config, test hoi quy).
- blast radius (hgraph brief, depth 2): 138 file bi phu thuoc / 20 file phu thuoc. `codex_bridge.py` va `models.py` chua thuoc graph nao (hgraph bao tu dau).

## Impact inventory (nop truoc khi sua)

### Database
| Muc | Noi dung |
|---|---|
| Bang | `visual_exploration_sessions` (ADD cot + CHECK); bang moi `visual_agent_steps`. Cung DB/schema `public` cua control-plane. |
| Truong moi | `visual_exploration_sessions.exploration_engine` VARCHAR(20) NOT NULL server_default `'planner'`, khong index. `visual_agent_steps`: `id` uuid PK; `tenant_id` varchar(200) NOT NULL (index `ix_visual_agent_steps_tenant_id`); `project_id`, `session_id` uuid NOT NULL; `step_index`, `snapshot_version` int NOT NULL; `evaluation_previous_goal`, `memory`, `next_goal` text NOT NULL; `actions`, `operation_ids` JSONB NOT NULL; `stop_reason` varchar(80) NULL; `job_id` uuid NULL; `created_at` timestamptz NOT NULL. |
| Rang buoc | CHECK `ck_visual_session_exploration_engine` (`IN ('planner','agent_loop')`); UNIQUE `uq_visual_agent_step_index (session_id, step_index)`; FK 3 cot `fk_visual_agent_step_session` -> `visual_exploration_sessions(tenant_id, project_id, id)` (khuon `fk_visual_operation_session`). |
| Migration | `migrations/versions/b7c9d1e3f5a7_add_agent_loop_engine.py`, `down_revision = "a4c6e8f01234"` (da xac nhan la head qua `alembic heads`). |
| Rollback | `downgrade()`: `drop_table("visual_agent_steps")`, `drop_constraint(ck_visual_session_exploration_engine)`, `drop_column("visual_exploration_sessions","exploration_engine")`. Mat marker engine + step log cua session `agent_loop` -> phai tat `VISION_AGENT_LOOP_ENABLED` truoc rollback (ghi trong docstring migration). |
| Backfill | Khong. Default hang so; moi dong cu doc ra `planner`. So dong anh huong = moi dong hien co cua `visual_exploration_sessions` (metadata-only, khong rewrite). |
| Lock/downtime | ADD COLUMN default hang = metadata-only (PG >= 11, test chay PG 17). ADD CHECK quet bang `visual_exploration_sessions` duoi ACCESS EXCLUSIVE ngan; bang nay nho (moi dong = 1 phien Vision), chap nhan duoc, khong dung NOT VALID. CREATE TABLE khong khoa bang cu. |
| Consumer khac | Khong consumer nao doc cot moi (chi `routes/vision.py::_response` va `application/vision.py`). `ck_codex_job_sequence` khong dung (K1 giu tran 20), co test khang dinh. |
| Index | Them `ix_visual_agent_steps_tenant_id` (tu `TenantRecord`) + index cua UNIQUE (session_id, step_index) phuc vu doc theo thu tu. Khong bo index; khong query cu nao doi plan. |

### File & contract
- Tao: migration (72 dong), `tests/test_agent_loop_contracts.py` (499), `tests/test_vision_agent_engine_selection.py` (484).
- Sua: xem bang +/- o duoi. Caller doi chu ky: `SubmitVisualExploration.execute` them tham so co default (`engine="planner"`, `agent_loop_enabled=False`) - caller duy nhat: `RequestVisualExploration.execute` (application/vision.py) va `ReloadVisualExploration.execute` (application/vision_reload.py); grep `SubmitVisualExploration|RequestVisualExploration` tren apps+tests: chi `routes/vision.py`, `dependencies/vision.py`, hai file tren. `get_policy`/`set_policy` them tham so `settings` (Depends) - chi route.
- Public contract: `CodexBridgeRequest` (+`agent_context`, regex `prompt_version`), `CodexBridgeResponse.output` (union rong hon), `VisualWorkerOpen` (+2 field), response `ExplorationResponse` (+`engine`), `VisionPolicyReadResponse` (+`agent_loop_enabled`), env var `VISION_AGENT_LOOP_ENABLED`, `VISION_AGENT_SNAPSHOT_CHARS`, stage activity `agent.step`, 7 reason code moi, TS generated.
- Test phu vung nay: `test_codex_bridge_contracts.py`, `test_claude_bridge.py`, `test_vision_contracts.py`, `test_vision_worker_contracts.py` (so khop TS sinh), `test_vision_routes.py`, `test_vision_provider_submission.py`, `test_vision_reload.py`, `test_vision_migration_compatibility.py`, `test_codex_bridge_migrations.py`, `test_vision_policy*.py`. Chua co test truoc phase nay cho: engine selection, step log, migration moi (da them).

## File tao / sua / xoa

| File | +/- | Ly do |
|---|---|---|
| `migrations/versions/b7c9d1e3f5a7_add_agent_loop_engine.py` (moi) | +72 | cot engine + CHECK + bang step log, downgrade day du |
| `tests/test_agent_loop_contracts.py` (moi) | +499 | contract agent, schema strict, identity v4 |
| `tests/test_vision_agent_engine_selection.py` (moi) | +484 | route + application + migration + step log |
| `packages/contracts/src/auto_at/contracts/codex_bridge.py` | +131/-2 | `AgentAction`, `AgentStep`, `AgentLoopOutput`, `BridgeOutput`, `AgentLoopContext`, `parse_agent_output`, `agent_loop_output_schema`, `agent_context`, regex prompt, serializer giu byte v4 |
| `packages/contracts/src/auto_at/contracts/vision_worker.py` | +7/-1 | `VisualWorkerOpen.agent_mode`, `blocked_action_terms` |
| `workers/playwright/src/vision-contract.generated.ts` | +17/-1 | sinh lai bang `export_vision_worker.py` (khong sua tay) |
| `apps/control-plane/infrastructure/persistence/models.py` | +40 | cot `exploration_engine` + CHECK, `VisualAgentStepModel` |
| `apps/control-plane/infrastructure/persistence/vision_unit_of_work.py` | +45 | `record_agent_step` (fence + redact), `agent_steps(scope)` |
| `apps/control-plane/api/v1/routes/vision.py` | +15/-3 | `engine` request/response, `agent_loop_enabled` o policy |
| `apps/control-plane/application/vision.py` | +16/-2 | tham so `engine`, kiem co/provider/allowlist, idempotency theo engine |
| `apps/control-plane/application/vision_reload.py` | +2 | giu engine session goc (K5) |
| `apps/control-plane/config.py` | +3 | `vision_agent_loop_enabled`, `vision_agent_snapshot_chars` |
| `.env.example` | +3 | hai bien moi |
| `apps/control-plane/domain/activity.py` | +14 | stage `agent.step`, 7 reason code |
| `tests/test_vision_handoff_repository.py` | +1/-1 | **ngoai danh sach**: assert `version_num == "a4c6e8f01234"` cung head -> `b7c9d1e3f5a7` |
| `tests/test_vision_policy_persistence.py` | +2/-1 | **ngoai danh sach**: so response PUT voi policy da luu, loai them `agent_loop_enabled` |
| `tests/test_vision_policy_routes.py` | +2/-1 | **ngoai danh sach**: nhu tren |
| `docs/graphs/vision-exploration.md` | auto-block | `hgraph add` + `sync --apply` (xem GRAPH_UPDATE) |
| (khong xoa file nao) | | |

`docs/graphs/README.md`, `docs/graphs/codex-bridge.md` co diff san tu truoc (lead), toi khong dung toi.

## Thiet ke chinh va quyet dinh

- `AgentAction` phang: moi kind chi mang dung field cua no (`click:ref`, `type:ref+text`, `scroll:delta_y`, `wait:duration_ms`, `back/close_popup/navigate:` khong field), `expected_outcome` tuy chon (<=300). `navigate` luon `ref=null`, khong co field URL (K2). `ref` regex `^[0-9]+:[0-9]+$`, `max_length=24`. `text` 1..1000 ky tu. `delta_y` -2000..2000 (am hop le = cuon len, dung nhu `VisualWorkerAction`), `duration_ms` 100..10000.
- `AgentStep`: `evaluation_previous_goal`/`next_goal` 1..500, `memory` 0..2000, `actions` 1..10. `AgentLoopOutput` = `AgentStep | CodexNeedScreenshot | CodexStop` (discriminator `outcome`). `CodexOutput` KHONG them bien the.
- `CodexBridgeResponse.output` dung `BridgeOutput` = `CodexCandidates | AgentStep | CodexNeedScreenshot | CodexStop` (mot discriminated union phang cho thong bao loi sach).
- `CodexBridgeRequest.agent_context`: bat buoc khi `prompt_version` la `agent-loop-vN`, cam khi la `codex-dom-*` (hai chieu).
- **Byte v4 khong doi**: them field `agent_context` se lam `canonical_bytes`/`content_hash` cua moi request v4 co them `"agent_context":null` (request.json + request_hash doi, host cu se tu choi field la `extra=forbid`). Giai phap: `model_serializer(mode="wrap")` bo key khi `None`. Hash request mau phase 0 do TRUOC khi sua = `7d124f62...3f5e` (1422 byte) va sau khi sua van bang; test khoa gia tri nay.
- `agent_loop_output_schema()` dat o contract (khong dat o `codex_service.py` vi file do thuoc phase 3). Cung kieu `strict()` cua `output_schema()`: moi field required (nullable), `additionalProperties=false`, `oneOf->anyOf`, `const->enum`. Khong co `anyOf` cua cac bien the co `properties` nen `enforceable_schema` di qua khong doi (test khang dinh bang `==`). Phase 3 co the bao `agent_output_schema()` quanh ham nay.
- `blocked_action_terms`: moi muc 1..40 ky tu, toi da 40 muc; khong co validator "chi khi agent_mode" (worker bo qua khi `agent_mode=False`; phase 2 quyet). 
- Policy: `agent_loop_enabled` dat o lop co so `VisionPolicyResponse` (default False) de PUT chap nhan echo (dashboard gui nguyen ban doc o `generation-api.ts:47`; neu `extra=forbid` thi PUT 422 ngay khi backend tra field moi, truoc phase 5). `set_policy` loai field khoi payload luu va tra gia tri tu server. Co test.
- `exploration_engine`: kiem o application (`"unknown exploration engine"`), cam khi co tat/provider khong phai bridge, allowlist (`agent_loop` bat buoc target nam trong `allowed_origins` kem danh sach khong rong; planner v4 van khong kiem o submit nhu cu). Idempotency: cung key khac engine -> 422 "different exploration".
- `agent_steps(scope)` nhan `VisualSessionScope` (tenant+project+session) thay vi `session_id` tran nhu phase ghi, de co co lap tenant (yeu cau test "tenant khac khong doc duoc").
- `record_agent_step`: `redact_value` len 3 truong text va `actions`; tu choi `len(operation_ids) > len(actions)` (tieu chi 1 cua plan). Unique vi pham -> `IntegrityError` (khong nuot).
- Activity `agent.step`: metadata cho phep `step_index<=20, snapshot_version, action_count<=10, executed_count<=10, reason_code`; khong chua goal/memory/text.
- `/trace` tra `JSONResponse(dict)`, khong phai model Pydantic -> khong them field `agent_step` (phase 4 dien truc tiep vao dict).

## Output that

### Hash dinh danh v4 (test `test_agent_loop_contracts.py`)
- sha256 `TypeAdapter(CodexOutput).json_schema()` (3797 byte) = `572143fe...3ef9` khop `tests/fixtures/v4_identity.json`.
- prompt + schema `codex-dom-v11`: `sha256(with_response_schema(build_prompt(...), output_schema(3)))` = `cc45b116...9259` (9269 byte), `prompt_sha256` = `b1ef50be...59a7`, `bridge_schema_sha256` = `6ef40dd1...0368` - tat ca khop fixture (test xanh).
- request hash mau = `7d124f62ef381607ccb68fb5dac8fcbdefa59efc4ecfb3c125a4365a2b5e3f5e`, khong doi.

### Diff TS sinh so voi `reports/phase-00/vision-contract.generated.ts.txt`
Lenh: `uv run python packages/contracts/export_vision_worker.py` roi `diff`. Ket qua: 18 dong khac, toan bo la `agent_mode` + `blocked_action_terms` (dong type `VisualWorkerOpen` + khoi schema `agent_mode`/`blocked_action_terms`). Khong dong nao khac. `test_vision_worker_contracts.py::test_generated_worker_contracts_are_current` xanh.

### Worker
- `npm.cmd run typecheck` (workers/playwright): `tsc --noEmit`, exit 0 (log `worker-typecheck.log`).
- Spec dai dien (qua `powershell.exe`; `npm`/`npx` tu Git Bash loi "'C:\Program' is not recognized", van de moi truong): `src/vision-operations.spec.ts -g "HTTP endpoints"`: 1 passed (log `worker-http-spec.log`).
- `npm.cmd run lint` exit 1: 22 loi `no-explicit-any`/`no-require-imports` o `vision-contract.ts`, `vision-dom.spec.ts`, `fixtures/*`, `origin-guard.cjs`... KHONG co loi o file toi dong (`vision-contract.generated.ts` khong bi lint hoac khong co loi). Co san truoc phase nay; phase khong yeu cau lint worker (log `worker-lint.log`).

### Alembic tren DB test `auto_at_agent_loop_test` (khong cham `auto_at`)
Moi lenh: `DATABASE_URL=postgresql://auto_at:...@127.0.0.1:5432/auto_at_agent_loop_test CODEX_BRIDGE_ENABLED=false uv run alembic ...`; da kiem `get_settings().database_url` tro dung DB test. Log day du: `alembic-test-db.log`.
```
upgrade head   -> ... a4c6e8f01234 -> b7c9d1e3f5a7 (exit 0)
current        -> b7c9d1e3f5a7 (head)
downgrade -1   -> b7c9d1e3f5a7 -> a4c6e8f01234 (exit 0)
current        -> a4c6e8f01234
upgrade head   -> exit 0 ; current -> b7c9d1e3f5a7 (head)
downgrade -1 ; upgrade head -> exit 0 (them mot vong)
```
DB test de o `head` luc ket thuc. `alembic check` chi liet ke lech cu (index/nullable tren bang khac), KHONG co muc nao ve `visual_agent_steps`, `exploration_engine` hay CHECK moi.

### pytest (CODEX_BRIDGE_ENABLED=false, `-p no:cacheprovider`, `--basetemp` scratchpad, moi lenh < 540 s, log trong thu muc nay)
Test DB-gated chay tren fixture co san `vision_trace_fixtures` (PostgreSQL 127.0.0.1:55437, database UUID, tu tao/xoa) - da bat nen KHONG skip; `-rs` khong in skip nao cho file moi. Fixture nay khong dung `DATABASE_URL`; DB `auto_at_agent_loop_test` duoc dung cho CLI alembic o tren.

| Nhom | Ket qua | Log |
|---|---|---|
| Test moi: `test_agent_loop_contracts.py` | 76 passed | `pytest-new-tests.log` (chay chung) |
| Test moi: `test_vision_agent_engine_selection.py` | 34 passed, 0 skipped (HTTP/DB chon engine + policy + reload, 5 test application bang mock, 1 test migration up/down, test step log/CHECK/FK) | `pytest-new-tests.log` |
| Chay lai 4 file sau khi sua ruff: contracts + selection + `policy_persistence` + `policy_routes` | 137 passed | `pytest-new-tests.log` |
| Hoi quy yeu cau 1: `codex_bridge_contracts`, `claude_bridge`, `vision_contracts`, `vision_worker_contracts`, `vision_routes` | 148 passed | `pytest-regression-1.log` |
| Hoi quy yeu cau 2: `vision_provider_submission`, `vision_reload`, `vision_migration_compatibility`, `codex_bridge_migrations`, `vision_handoff_repository` | 44 passed | `pytest-regression-2.log` |
| G1 `test_[a-c]*` + `test_codex_bridge_*` (glob chong lap nen cac file `test_codex_bridge_*` chay 2 lan: 345 passed/38 skipped gap doi so thuc) | 2 failed (cung 1 test, 2 lan), 345 passed, 38 skipped | `pytest-G1.log` |
| G2 `test_[d-m]*` (tru file da chay) | 116 passed | `pytest-G2.log` |
| G3 `test_[n-u]*` + `test_w*` | 97 passed, 1 skipped (`RUSTFS_STRESS`) | `pytest-G3.log` |
| G4 vision a-p (22 file) | 1 failed, 312 passed (xem duoi) | `pytest-G4.log` |
| G4b `policy_persistence` (chay lai) + vision p-w (15 file) | 248 passed | `pytest-G4b.log` |
| `test_vision_page_batch.py` 81 test chia 5 lenh (1-21, 22-41, 42-59 qua timeout 540 s nhung 18 dau cham khong co F, 60-69, 70-81) | 21 + 20 + 18 (khong co summary vi timeout) + 10 + 12 = 81 test, 0 fail | `pytest-page-batch-1..5.log` |

Giai thich cac do:
1. `tests/test_codex_bridge_benchmark.py::test_offline_manifest_provenance_and_explicit_live_boundary` do (1 test, hien 2 lan do glob chong lap): **co san tu baseline phase 0** (`be-developer-junior-r2/r3`: `assert '3b1c1ca08a19...' == 'dfbd0cbf...'`). `manifest.json` ghim sha256 nhieu file nguon, trong do co file toi khong dung (`docker-compose.codex.yml`, `doctor.py`, `domain/codex_bridge.py`, `application/codex_bridge.py`, `spool.py`, `vision_trace_events.py`, `vision_operations.py`) va da lech tu truoc. Sua `codex_bridge.py` (file toi buoc phai sua) lam hash dau tien doi gia tri (3b1c... -> 07bf...), nhung test do ca truoc lan sau. Khong sua (ngoai pham vi).
2. G4 1 failed: `test_vision_policy_persistence.py::test_http_success_commits_policy_snapshot_and_audit_before_response` do do response PUT policy gio co `agent_loop_enabled` ma test so voi policy luu. Hop dong doi theo dung phase -> sua 1 dong test (loai field khoi phep so sanh), tuong tu `test_vision_policy_routes.py:155`. Chay lai: xanh (G4b + `pytest-new-tests.log`).
3. `test_vision_page_batch.py` chay xong lam `benchmark/vision/visual-buttons/flow-result.json` doi (`operations` 99->96, `model_batches` 6->5) giong ghi chu baseline r3 (chi tro lai dung khi chay du 81 test cung mot lan). Toi da khoi phuc 2 dong ve noi dung da commit bang Edit; `git status --short benchmark` rong.

### ruff
`uv run ruff check . --output-format concise` -> 5 loi, **tat ca o `plan/20261119-2212-browser-agent-loop/reports/phase-00/v4_identity.py`** (I001 + 4 E501; file do lead tao o phase 0, ngoai pham vi, truoc do baseline ruff "All checks passed" vi file chua ton tai). Code/test cua phase 1: sach (da sua F401/F811 trong test moi). Log `ruff-check.log` la lan chay cuoi (sau khi sua F401/F811 trong test moi): `Found 5 errors`, chi file phase 0.
Tieu chi "ruff sach" chua dat nguyen van vi file cua phase 0 - xem ASK_PM.

## Ladder (Ponytail)
1. Khong lam gi / dung cai co san: dung lai fixture `submission`, `trace_database`, `disposable_database`, `Readiness`, `session_values`, helper `request()/response()`; khong them dependency (`jsonschema` khong co trong `uv.lock`).
2. Xoa/giam: `AgentLoopOutput` tai dung `CodexNeedScreenshot`/`CodexStop`; khong them validator "terms chi khi agent_mode"; khong them `agent_step` vao `/trace` (khong phai model Pydantic); khong them index/CHECK ngoai yeu cau (khong CHECK `step_index`).
3. Viet moi toi thieu: model/ham/cot/bang chinh phase nay yeu cau, mot ham `agent_loop_output_schema` (copy `strict()` nho cua `output_schema`, can thiet vi `codex_service.py` thuoc phase 3).
4. Hai quyet dinh co chu dich them code: serializer giu byte v4 (tranh doi hash/`extra=forbid` host cu), `agent_loop_enabled` o lop co so (tranh PUT 422 khi dashboard echo).

## Van de / ASK_PM

ASK_PM
- question: Spool doc `request.json` toi da 16 384 byte (`apps/control-plane/infrastructure/codex_bridge/spool.py:245`) va ghi toi da 65 536 byte (`spool.py:294`). `AgentLoopContext.snapshot` cho phep toi 24 000 ky tu (toi 72 KB UTF-8 tieng Viet) nam NGAY TRONG `request.json` qua `agent_context`. Request agent voi snapshot > ~15 KB se bi bridge tu choi. Chon huong nao? (a) nang gioi han doc `request.json` o `spool.py` (hien khong thuoc phase nao), (b) chuyen snapshot ra file rieng trong spool (vd `snapshot.txt` co hash trong `inputs`), (c) them gioi han byte vao `AgentLoopContext`.
  context: `packages/contracts/.../codex_bridge.py` `AgentLoopContext.snapshot` (max 24 000 ky tu); `spool.py:245,294`; phase 3 chi sua `application/codex_bridge.py`, `codex_bridge_cli.py`, `process.py`, `claude_process.py`, `codex_batch.py`, `codex_service.py`.
  blocked_on: khong chan phase 1 (contract da theo dung phase); chan phase 3/4 truoc khi gui request agent that.
- question: Acceptance 2 noi "ref sai regex => `invalid_ref`" nhung contract phase 1 (theo dung phase) tu choi ref sai regex ngay luc parse (`AgentAction.ref` co `pattern`), nen mot output co ref sai se bi `parse_agent_output` nem `ValidationError` thay vi di den buoc kiem an toan. Phase 4 xu ly the nao: coi parse that bai = `model_output_invalid` (nhu v4), hay noi `AgentAction.ref` thanh `str` va de `invalid_ref` o domain?
  context: `codex_bridge.py` `AgentRef`; plan.md acceptance 2.
  blocked_on: thiet ke phase 4 (phase 1 khong chan).
- question: `uv run ruff check .` o phase 1 khong sach chi vi `plan/.../reports/phase-00/v4_identity.py` (5 loi). Lead muon sua file do, loai `plan/` khoi ruff, hay chap nhan?
  context: `ruff-check.log`.
  blocked_on: tieu chi xong "ruff sach".

CONVENTION_ISSUE
- file: `docs/api-conventions.md`
- van de: file khong ton tai (da biet; prompt cho bo qua). Cung khong co convention cho test JSON Schema: phase yeu cau "mau sai fail bang jsonschema" nhung `jsonschema` khong cai (khong co trong `uv.lock`/`pyproject.toml`); them dependency can duyet (AGENTS.md "Required checks" muc 3).
- toi can lam gi: da viet validator tap con JSON Schema (~60 dong, tu choi keyword la) trong `tests/test_agent_loop_contracts.py` (co test kiem chung validator khong "pass rong": bo mot field khoi schema thi mau hop le bi tu choi). Neu lead cho them `jsonschema` vao nhom dev thi thay validator nay.

Cac lech pham vi / ghi chu khac (khong chan):
- `tests/test_vision_handoff_repository.py:214`, `tests/test_vision_policy_persistence.py:49`, `tests/test_vision_policy_routes.py:155`: sua toi thieu vi hop dong doi theo dung phase (head revision, response policy). Lead can chap nhan 3 file nay ngoai danh sach.
- `apps/control-plane/domain/codex_bridge.py:43` (`BridgeProcessResult.output: CodexOutput | GeneratedTestPlannerOutput | VisionGroundedPlannerOutput | None`) chua nhan `AgentStep`; `domain/codex_bridge.py:100-103` va `process.py`/`claude_process.py` dung `parse_codex_output`. Phase 3 phai mo rong (file khong thuoc phase 1).
- Reason code moi chi them vao tap `reason_code` cua `create_vision_progress` (`domain/activity.py`); chua them vao `VISION_MODEL_FAILURE_REASONS` (`domain/vision.py`, ngoai danh sach) nen `safe_failure_reason` cua session voi cac ma `agent_*` can phase 4 xu ly.
- `hgraph check --changed` thoat 1: xem GRAPH_UPDATE.
- Dashboard TS chua biet `engine`/`agent_loop_enabled` (phase 5); echo PUT da duoc test khong vo.

## GRAPH_UPDATE
- graph da cap nhat: `vision-exploration` (`hgraph add` 3 file + `hgraph sync vision-exploration --apply`; sync them `apps/control-plane/agents/shared/redaction.py` vi `vision_unit_of_work.py` gio import `redact_value`).
- file moi da dua vao graph: `migrations/versions/b7c9d1e3f5a7_add_agent_loop_engine.py`, `tests/test_vision_agent_engine_selection.py`, `tests/test_agent_loop_contracts.py` (vao `vision-exploration`; `sync` ghi nhan migration la file la khong import/duoc import nhung van de lai trong graph).
- chua vao graph nao: `packages/contracts/src/auto_at/contracts/codex_bridge.py` va `apps/control-plane/infrastructure/persistence/models.py` (hgraph bao tu dau la "chua thuoc graph nao"; toi khong them vao `codex-bridge.md` vi file do co diff san cua lead). De xuat: lap graph `vision-agent-loop` (codex_bridge, vision_worker, models, vision_unit_of_work, routes/vision, application/vision, vision_reload, migration, 2 test moi) nhu phase 1 ghi.
- `hgraph check` (khong `--changed`): `Khong co van de.` exit 0.
- `hgraph check --changed`: **exit 1**. Output that (rut gon):
```
File vua doi: 17
x [uncovered-changed] file vua doi/moi nhung chua thuoc graph nao
  auto-at-ui/apps/control-plane/api/v1/routes/vision.py
  auto-at-ui/apps/control-plane/application/vision.py
  auto-at-ui/apps/control-plane/application/vision_reload.py
  auto-at-ui/apps/control-plane/config.py
  auto-at-ui/apps/control-plane/domain/activity.py
  auto-at-ui/apps/control-plane/infrastructure/persistence/models.py
  auto-at-ui/apps/control-plane/infrastructure/persistence/vision_unit_of_work.py
  auto-at-ui/packages/contracts/src/auto_at/contracts/codex_bridge.py
  auto-at-ui/packages/contracts/src/auto_at/contracts/vision_worker.py
  auto-at-ui/tests/test_vision_handoff_repository.py  (+ policy_persistence, policy_routes)
  auto-at-ui/workers/playwright/src/vision-contract.generated.ts
```
  Nguyen nhan chinh: git toplevel la `agent-at/` nen `git diff` tra duong dan co tien to `auto-at-ui/`, khong khop duong dan trong graph (vd `routes/vision.py`, `config.py`, `vision_unit_of_work.py`, `activity.py`, `vision_worker.py`, TS sinh DA nam trong graph nhung van bi bao "uncovered"). Day la loi cua cong cu voi repo long (khong sua duoc trong phase). Phan that su chua co graph: `codex_bridge.py`, `models.py` (xem tren). Log: `hgraph-check.log`.

## Don dep
Khong con tien trinh nao do toi mo (pytest/npm/powershell deu da thoat; task nen `b3e2af58b` cua lenh G1 da hoan tat). Khong server/stack docker. Khong sua `.env`, khong commit, khong chay migration len `auto_at`. DB `auto_at_agent_loop_test` o revision `b7c9d1e3f5a7`.
