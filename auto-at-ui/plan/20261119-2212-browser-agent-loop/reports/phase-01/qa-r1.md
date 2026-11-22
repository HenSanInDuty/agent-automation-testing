STATUS: FAIL

QA VERDICT: FAIL (chi vi cong graph; hanh vi phase 1 dat)

GRAPH: `hgraph check --changed` exit 1 - `uncovered-changed` (18 file; phan lon do tien to `auto-at-ui/` cua git toplevel, nhung `apps/control-plane/infrastructure/persistence/models.py` va `packages/contracts/src/auto_at/contracts/codex_bridge.py` that su khong thuoc graph nao). `hgraph check` thuong: "Khong co van de".

Da test: 29 nhom case (xem qa/phase-01/test-cases.md) - automation: dev 110 pass + QA 59 pass (tests/test_qa_phase01_edges.py), hoi quy 148 + 71 pass, suite day du chi con 1 do san baseline (test_codex_bridge_benchmark manifest-hash). Pass 28 / fail 1 (cong graph).

FAIL:
- T29 - `hgraph check --changed` -> sach vs uncovered-changed (models.py, contracts/codex_bridge.py chua trong graph). Sua: `hgraph add vision-exploration apps/control-plane/infrastructure/persistence/models.py packages/contracts/src/auto_at/contracts/codex_bridge.py` (hoac lap graph `vision-agent-loop` bang /h-graph), `hgraph sync vision-exploration --apply`, chay lai `hgraph check --changed`; neu con lai chi loi tien to `auto-at-ui/` thi do loi cong cu repo long (phase 0 da qua cong nay khi path khong co tien to) - leader quyet.

Chua test duoc: test_vision_page_batch.py (khong chay lai, ngoai blast radius, cham); mot so file test_v* giua chunk bi cat timeout (khong F); khong e2e UI. Stress: khong can (khong vong lap lon/query khong index/lock moi).

Bang chung doc lap: alembic up/down/up sach tren auto_at_agent_loop_test; CHECK engine, UNIQUE(session_id, step_index), FK 3 cot xac nhan qua pg_constraint; 110 test dev pass khong skip (-rs); sha256 CodexOutput 572143fe...3ef9 va codex-dom-v11 cc45b116...9259 khop fixture; diff TS chi agent_mode + blocked_action_terms; worker typecheck EXIT=0; ruff sach. Rui ro con mo (khong chan): snapshot 24000 ky tu co the vuot gioi han doc request.json 16384 byte cua spool; ref sai regex bi tu choi luc parse (khong toi invalid_ref).

Tai lieu: D:\Person\CaoHoc\KhoaLuanTotNghiep\agent-at\auto-at-ui\plan\20261119-2212-browser-agent-loop\qa\phase-01\test-cases.md, ...\qa\phase-01\test-report.md, D:\Person\CaoHoc\KhoaLuanTotNghiep\agent-at\auto-at-ui\tests\test_qa_phase01_edges.py
