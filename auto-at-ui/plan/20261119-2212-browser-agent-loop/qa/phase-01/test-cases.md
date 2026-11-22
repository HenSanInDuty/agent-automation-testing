# Test cases - Phase 1 (Contract + DB + chon engine)

Ket qua thuc te = do QA chay doc lap (xem test-report.md). "dev" = test developer viet, "qa" = `tests/test_qa_phase01_edges.py`.

| ID | Nhom | Tien dieu kien | Buoc / du lieu | Mong doi | Thuc te | Ket qua |
|---|---|---|---|---|---|---|
| T01 | Happy | DB test `auto_at_agent_loop_test` o head | `alembic upgrade head` / `downgrade -1` / `upgrade head` | 3 lenh exit 0; current: head -> a4c6e8f01234 -> head | dung nhu mong doi | PASS |
| T02 | Happy | sau T01 | doc pg_constraint | co CHECK engine IN (planner,agent_loop), UNIQUE(session_id,step_index), FK 3 cot; cot engine NOT NULL default 'planner' | dung | PASS |
| T03 | Happy | trace DB 55437 | dev: step log, CHECK engine, unique, fence, lease het han, redact, tenant khac, FK scope | tat ca pass, 0 skip | 34 test selection pass | PASS |
| T04 | Happy | | dev + qa: sha256 `TypeAdapter(CodexOutput).json_schema()` | = 572143fe...3ef9 (fixture) | chay lai `v4_identity.py`: 572143fe...3ef9; prompt+schema cc45b116...9259; prompt b1ef50be...59a7; schema 6ef40dd1...0368 | PASS |
| T05 | Happy | | export_vision_worker.py roi diff voi `reports/phase-00/vision-contract.generated.ts.txt` | chi `agent_mode`, `blocked_action_terms` | dung (1 dong type + khoi schema) | PASS |
| T06 | Happy | | `npm.cmd run typecheck` (workers/playwright) | exit 0 | EXIT=0 | PASS |
| T07 | Happy | | HTTP POST khong gui engine | 202, engine=planner (v4 on/off) | dev pass | PASS |
| T08 | Loi | | engine in {react,"",AGENT_LOOP,None,3} (dev); {" planner","planner ","Planner","agent-loop","agent_loop\n",["planner"],{a:1},true} (qa) | 422, khong tao session | pass | PASS |
| T09 | Loi | co tat | engine=agent_loop | 422 "disabled", khong ghi | dev pass | PASS |
| T10 | Loi | provider gemini | engine=agent_loop | 422 "bridge" | dev pass | PASS |
| T11 | Loi | allowlist rong / host la | engine=agent_loop | 422 "origin"; planner van 202 | dev pass | PASS |
| T12 | Happy | co bat + bridge | agent_loop, doc lai; policy GET co `agent_loop_enabled`; PUT echo khong 422 | engine=agent_loop; flag khong bi ghi de | dev pass | PASS |
| T13 | Hoi quy | | reload session planner / agent_loop; co tat sau do | giu engine; agent bi tu choi khi co tat | dev pass | PASS |
| T14 | Loi | | idempotency key cung, engine khac | 422 | dev pass | PASS |
| T15 | Bien | | actions 0/1/10/11 | 0,11 loi; 1,10 ok | qa pass | PASS |
| T16 | Bien | | text tieng Viet co dau 1000 / 1001 ky tu | 1000 ok, 1001 loi | qa pass | PASS |
| T17 | Bien | | ref hop le (1:2, 0:0, 123:456) / sai ("", "1", "1:", ":2", "a:b", " 1:2", "1:2 ", "1:2\n", "1:2:3", "-1:2", chu so Arab, 30 chu so) | hop le ok; sai deu loi | qa pass | PASS |
| T18 | Bien | | delta_y 2000/-2000/0 ok; 2001/-2001/1.5 loi; duration_ms 99,0,-5,10001 loi; 100,10000 ok | dung | qa pass | PASS |
| T19 | Loi | | back/close_popup/navigate kem ref/text/delta_y/duration_ms/url | loi (K2: navigate khong co URL) | qa pass | PASS |
| T20 | Bien | | history 5 vs 6 muc; muc 600 vs 601 ky tu | 5, 600 ok; 6, 601 loi | qa pass | PASS |
| T21 | Bien | | snapshot 24000 vs 24001 ky tu tieng Viet; memory 2000 vs 2001 (context + AgentStep) | <=gioi han ok, +1 loi | qa pass | PASS |
| T22 | Loi | | parse_agent_output: rong, null, [], outcome candidates, agent_step thieu field, envelope thua key | loi; 3 outcome hop le ok | qa pass | PASS |
| T23 | Hoi quy | | request v4: canonical bytes khong co `agent_context`; codex-dom + agent_context bi tu choi; prompt `agent-loop-v0/v01/-/v1\n` bi tu choi | dung | qa pass | PASS |
| T24 | Bien | | schema agent: dong, moi object required=all properties, khong oneOf/default, xac dinh | dung | qa pass; dev: thoa enforceable_schema | PASS |
| T25 | Bien | | blocked_action_terms 40 muc / 41 muc / muc 40 / 41 ky tu / rong | 40,40 ok; 41,41,"" loi | qa pass | PASS |
| T26 | Hoi quy | | 9 file hoi quy trong "Tieu chi xong" + handoff_repository + policy_persistence/routes | xanh | 148 + 71 passed, 0 skip | PASS |
| T27 | Hoi quy | | toan bo tests (tru page_batch) theo chunk | chi con test do san baseline | a-m: 1 failed (benchmark manifest-hash, dung baseline) 534 passed; n-w: 156 passed; v*: 0 F (chunk bi cat 540 s o ~97% + 55 passed cho cac file cuoi) | PASS (co ghi chu) |
| T28 | Hoi quy | | `ruff check .` | sach | All checks passed | PASS |
| T29 | Cong | | `hgraph check --changed` | sach | r1: FAIL (2 file chua vao graph). r2: da them vao graph; `hgraph check` day du exit 0 (4 graph, 442 file, khong van de); `--changed` con do chi vi tien to duong dan `auto-at-ui/` cua cong cu - USER DA CHAP NHAN | PASS (user chap nhan) |

## Vong r2 (doi contract: AgentRef str<=24 + AGENT_REF_PATTERN; request agent <= 131 072 byte)
| ID | Nhom | Buoc | Mong doi | Thuc te | KQ |
|---|---|---|---|---|---|
| R2-01 | Bien | `test_qa_ref_off_format_parses_but_fails_pattern` (11 ref sai dang, <=24 ky tu, gom unicode so Arab, xuong dong, khoang trang) | parse duoc, `re.fullmatch(AGENT_REF_PATTERN)` khong khop | pass | PASS |
| R2-02 | Loi | `test_qa_ref_empty_or_over_24_rejected` ("" / 25 / 32 ky tu / 25 chu 'e' dau) | ValidationError | pass | PASS |
| R2-03 | Bien | `test_qa_ref_24_accepted_and_navigate_with_ref_still_rejected` | ref dung 24 ky tu duoc nhan; navigate co ref bi tu choi | pass | PASS |
| R2-04 | Bien | `test_qa_request_byte_ceiling_exact_boundary`: tinh chinh tung byte ASCII | kich thuoc canonical == 131 072 duoc nhan; +1 byte bi tu choi ("byte limit") | pass | PASS |
| R2-05 | Hoi quy | 7 file test lien quan (lenh trong prompt) | xanh | 330 passed, 0 skip | PASS |
| R2-06 | Hoi quy | hash v4 theo `tests/fixtures/v4_identity.json` (test_agent_loop_contracts, loc `identity or v4`) | khop | 52 passed | PASS |
| R2-07 | Hoi quy | `uv run ruff check .` | sach | All checks passed | PASS |
| R2-08 | Cong | `hgraph check` | exit 0 | exit 0, "Khong co van de" | PASS |
