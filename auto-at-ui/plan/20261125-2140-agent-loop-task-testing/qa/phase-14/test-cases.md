# Phase 14 - test cases (QA r1)

Legend: DEV = covered by the developer tests (`tests/test_agent_task_draft.py` U, `tests/test_agent_task_draft_routes.py` R);
QA = added in `tests/test_qa_phase14_agent_task_draft.py` (Q). All results are PASS on the final run (see test-report.md).

| ID | Criterion | Case (expected) | Covered by | Result |
|---|---|---|---|---|
| C1-01 | 1 | session not `completed` -> 409 `session_not_completed`, 0 rows | DEV R, U; QA Q (failed/cancelled/queued/running) | PASS |
| C1-02 | 1 | `not_achieved`/`blocked`/`inconclusive` -> 409 `assessment_not_achieved` | DEV R, U | PASS |
| C1-03 | 1 | no assessment -> 409 `assessment_unavailable` | DEV R, U | PASS |
| C1-04 | 1 | engine `planner`, unknown status, `{}`, `status:null`, list -> `assessment_unavailable`, 0 rows | QA (5 params) | PASS |
| C1-05 | 1 | inconsistent group -> 409 `assessment_inconsistent` + report | DEV R, U | PASS |
| C1-06 | 1 | origin outside allowlist / no policy row -> 409 `origin_not_allowed` | DEV R, U | PASS |
| C1-07 | 1 | typed chain, flag off -> 409 `input_value_not_allowed` | DEV R, U | PASS |
| C1-08 | 1 | missing / wrong length / extra value -> 422 with step, no value | DEV R, U | PASS |
| C1-09 | 1 | evidence deleted -> 409 `evidence_expired` | DEV R, U | PASS |
| C1-10 | 1 | `Role.SERVICE` -> 404; `service=True` + CONTRIBUTOR -> 404 (observed 404) | DEV R (role); QA (flag) | PASS |
| C2-01 | 2 | request + draft + 2 audits in one transaction; failure on 2nd audit -> 500, no rows | DEV R | PASS |
| C2-02 | 2 | audit actor = requester; provenance has trace source, flags, `requested_by`, `consistency` | DEV R, U | PASS |
| C2-03 | 2 | draft planning_request_id = request id, 1 draft | QA | PASS |
| C3-01 | 3 | same (session, trace) again -> 200 same draft, `created=false`, whatever key/values | DEV R, U | PASS |
| C3-02 | 3 | replay with other values (marker B) stores nothing, source unchanged | QA | PASS |
| C3-03 | 3 | replay with wrong-length value still replay (no value compared) | QA | PASS |
| C3-04 | 3 | replay by viewer / other tenant -> 404 | QA | PASS |
| C3-05 | 3 | same key, different body -> NOT 409: observed 200 replay (design deviation, see report D1) | DEV R; QA (C3-02) | PASS vs ADR, DEVIATION vs phase text |
| C3-06 | 3 | key hits request row of another target -> 409 `idempotency_key_conflict` | DEV R, U | PASS |
| C3-07 | 3 | empty `Idempotency-Key` -> 422, missing header -> 422; key never stored | DEV R; QA (empty) | PASS |
| C3-08 | 3 | `redacted_request` fixed sentence; key = 64 hex | DEV R, U; QA | PASS |
| C3-09 | 3 | two concurrent requests, same session: exactly 1 request + 1 draft; retry -> 200 | QA | PASS (loser got 500, see D2) |
| C4-01 | 4 | one value only in `generated_test_drafts.playwright_test_source` (scan of every column of every table) | DEV R | PASS |
| C4-02 | 4 | same for Vietnamese values; source stores them as JS `\uXXXX` (dev scan is ASCII-blind, QA scan checks 4 spellings) | QA | PASS |
| C4-03 | 4 | scan is not blind (leak planted in audit actor, ASCII and Vietnamese) | DEV R; QA | PASS |
| C4-04 | 4 | refused request (flag off, not finished, evidence gone, origin) with values A,B: nothing stored, not echoed, not logged | QA (4 params) | PASS |
| C4-05 | 4 | 422 request (short value, missing, extra) with marker values: not stored, not echoed | QA (3 params) | PASS |
| C4-06 | 4 | malformed bodies (6 shapes), 500 path, caplog DEBUG + capfd | DEV R | PASS |
| C4-07 | 4 | allowed places after approval (case, run request, outbox) | DEV R | PASS |
| C4-08 | 4 | 201 value > 200 entries -> 422 `request_invalid`; 20000x16-char value -> 422 without echo | QA | PASS |
| C4-09 | 4 | hostile values (quote break-out, `${}`, backslashes, CR/LF/U+2028/9) -> 422 policy or kept in one literal (observed: 422, 201, 422, 201) | QA | PASS |
| C5-01 | 5 | pending_review, `test_cases`/`test_runs`/`outbox_events` unchanged | DEV R, U | PASS |
| C6-01 | 6 | no migration / models diff (`git diff -- migrations models.py` empty); response keys fixed, no value | DEV R; QA (git) | PASS |
| C7-01 | 7 | viewer/reviewer/service 404; other tenant / project / session 404; all 404 bodies identical | DEV R; QA (identical) | PASS |
| C7-02 | 7 | CSRF cookie without token -> 403, also before session lookup | DEV R; QA | PASS |
| C7-03 | 7 | empty `{}` and empty body -> 422 (`input_value_missing`/`request_invalid`) | QA | PASS |
| C8-01 | 8 | provider routes, event processor, vision routes, run routes | regression run | PASS (see report) |
| C8-02 | 8 | `ruff check .` | lint | PASS |
| C8-03 | 8 | `hgraph check` clean; QA test file added to graph `agent-task-draft` | graph | PASS |
