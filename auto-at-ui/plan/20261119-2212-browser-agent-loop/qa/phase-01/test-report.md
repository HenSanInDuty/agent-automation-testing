STATUS: FAIL

# Test report - Phase 1 (QA r1)

Moi truong: Windows 11, uv + Python venv cua repo, PostgreSQL 127.0.0.1:55437 (fixture UUID-DB), DB test `auto_at_agent_loop_test` (5432, khong cham `auto_at`), CODEX_BRIDGE_ENABLED=false, `-p no:cacheprovider`. Khong start/stop docker.

## Ket qua (bang chung that, doc lap)
- alembic (DATABASE_URL = DB test): current b7c9d1e3f5a7 -> `downgrade -1` ("Running downgrade b7c9d1e3f5a7 -> a4c6e8f01234") -> current a4c6e8f01234 -> `upgrade head` -> current b7c9d1e3f5a7 (head). pg_constraint sau upgrade: `ck_visual_session_exploration_engine`, `fk_visual_agent_step_session`, `uq_visual_agent_step_index UNIQUE (session_id, step_index)`; cot `exploration_engine` NOT NULL default 'planner'.
- Test moi cua dev (`test_agent_loop_contracts.py`, `test_vision_agent_engine_selection.py`): `110 passed in 33.00s`, `-rs` khong co SKIPPED (DB-gated chay that tren fixture 55437).
- Test QA moi `tests/test_qa_phase01_edges.py`: `59 passed`.
- Hoi quy nhom 1 (codex_bridge_contracts, claude_bridge, vision_contracts, vision_worker_contracts, vision_routes): `148 passed`. Nhom 2 (provider_submission, reload, migration_compatibility, codex_bridge_migrations, handoff_repository, policy_persistence, policy_routes): `71 passed`, 0 skip.
- Toan bo suite theo chunk: a-m `1 failed, 534 passed, 19 skipped` (failed = `test_codex_bridge_benchmark.py::test_offline_manifest_provenance_and_explicit_live_boundary`, san tu baseline phase 0; skip la Linux/offline-image); n-u+w `156 passed, 1 skipped (RUSTFS_STRESS)`; v* (tru page_batch) bi cat o 540 s sau ~97% khong co F, phan duoi chay lai rieng `55 passed`.
- sha256: chay lai `v4_identity.py`: schema CodexOutput 572143fe...3ef9, prompt+schema 9269 byte cc45b116...9259, prompt b1ef50be...59a7, schema bridge 6ef40dd1...0368, deu khop `tests/fixtures/v4_identity.json`.
- TS: `export_vision_worker.py` roi `diff` voi ban sao phase 0: chi 18 dong `agent_mode` + `blocked_action_terms`. `npm.cmd run typecheck`: EXIT=0.
- `uv run ruff check .`: All checks passed (5 loi cua phase-00/v4_identity.py ma dev bao da het).
- Baseline: test do san duy nhat van la manifest-hash benchmark (gia tri hash doi 3b1c.. -> 07bf.. vi `codex_bridge.py` duoc manifest ghim; cung assertion, khong phai hoi quy moi).

## Graph gate
`hgraph check --changed`: exit 1, 18 file doi, `uncovered-changed`. Phan lon la loi duong dan cong cu (git toplevel la `agent-at/` nen path co tien to `auto-at-ui/`; `hgraph check` thuong: "Khong co van de", 442 file). Nhung doi chieu frontmatter graph: `apps/control-plane/infrastructure/persistence/models.py` va `packages/contracts/src/auto_at/contracts/codex_bridge.py` KHONG thuoc graph nao (that su uncovered; plan phase 1 yeu cau lap graph `vision-agent-loop`). Theo luat cong cuoi -> FAIL.
Lenh phai chay (developer / leader): `hgraph add vision-exploration apps/control-plane/infrastructure/persistence/models.py packages/contracts/src/auto_at/contracts/codex_bridge.py` (hoac lap graph `vision-agent-loop` bang /h-graph), roi `hgraph sync vision-exploration --apply`, roi `hgraph check --changed` va ghi ro neu phan con lai chi la loi tien to duong dan.

## Chua test duoc / han che
- `test_vision_page_batch.py` (81 test, rat cham, tu ghi doi `benchmark/vision/visual-buttons/flow-result.json`): khong chay lai, khong thuoc blast radius phase 1; dev bao 81 pass.
- Vai file `test_v*` o giua chunk v* bi cat boi timeout 540 s, khong co F truoc diem cat; chi chay lai rieng 8 file cuoi. Phan nay dua vao chunk dev G4/G4b.
- Stress test: khong can - khong co vong lap tap lon, query khong index, job hang loat hay lock moi (chi ADD COLUMN default hang, CREATE TABLE).
- Khong e2e UI/worker that: phase 1 khong doi hanh vi runtime (chi contract/DB/HTTP).
- Rui ro ghi nhan (khong chan phase 1, da co ASK_PM cua dev): snapshot 24 000 ky tu tieng Viet nam trong `request.json` co the vuot gioi han doc 16 384 byte cua spool (`spool.py:245`) - phai quyet truoc phase 3/4. `invalid_ref` vs parse that bai (ref sai regex bi tu choi ngay luc parse) - phase 4 can quyet.

## Phan quyet
Hanh vi: tat ca tieu chi "Tieu chi xong" thoa. Cong graph: chua sach (2 file that su chua vao graph). 

---
# Vong r2
Pham vi: doi contract duoc user duyet (AgentRef = str 1..24 + `AGENT_REF_PATTERN`; agent request > 131 072 byte bi chan). Khong chay lai DB/alembic va hoi quy rong cua r1 (r2 khong dung DB).
- Cap nhat test cua QA (`tests/test_qa_phase01_edges.py`): 10 ca `test_qa_ref_bad` cu thay bang hanh vi moi (ref sai dang <=24 parse duoc nhung khong khop pattern; rong/>24 bi tu choi; navigate co ref van bi tu choi) + ca bien tran 131 072 byte chinh xac (+1 byte bi tu choi). Developer da phu ca vuot tran va 24 ky tu; ca chinh xac 131 072 la bo sung moi.
- Ket qua: 7 file test lien quan `CODEX_BRIDGE_ENABLED=false`: **330 passed**, 0 skip. Hash v4 khop fixture (52 passed khi loc identity/v4/ref/ceiling). `ruff check .`: All checks passed. `hgraph check`: exit 0 (4 graph, 442 file, khong van de).
- Cong graph: `hgraph check --changed` van do chi do tien to duong dan `auto-at-ui/` cua cong cu; user da chap nhan coi dat.
- Luu y moi truong: chay test_qa_phase01_edges.py rieng ma thieu `CODEX_BRIDGE_ENABLED=false` loi collection Settings (khong lien quan thay doi).
- Chua test duoc: nhu r1 (page_batch, e2e UI/worker). Stress test: khong can - khong co vong lap tap lon/lock moi.

QA VERDICT: PASS
