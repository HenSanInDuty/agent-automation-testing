# Phase 12 — test cases (QA r1)

Files: D = `tests/test_generation_policy_audit.py` (developer), Q = `tests/test_qa_p12_policy_audit.py` (QA, new).
D uses an in-memory transaction fake (stage + publish on success). Q `db*` cases use a real PostgreSQL disposable database
(`disposable_database`, 127.0.0.1:55437, own `CREATE DATABASE`, never the app DB) with the real repositories and real
`transactional_session`. All results: PASS.

| ID | Criterion | Case | Expected | Result |
|---|---|---|---|---|
| D-flag-on | 1 | PUT false (first) then true | `[updated, enabled]` | PASS |
| D-flag-off | 1 | true then false | `[enabled, disabled]` | PASS |
| D-first-on | 1 | no policy before (None), flag true | one `enabled` | PASS |
| D-omit | 1 | flag omitted / unchanged | `updated`; stored flag kept | PASS |
| D-actor | 2 | actor/tenant/entity/correlation uuid4, no hash, no origin in repr | as stated | PASS |
| D-corr | 2 | two calls | different correlation_id | PASS |
| D-tenant | 2,3 | tenant-b write | events carry own tenant/actor; tenant-a policy untouched | PASS |
| D-reject x5 | 3 | contributor, viewer, no tenant, javascript: origin, origin with path | 401/404, no event, policy same | PASS |
| D-fail-set | 3 | set_policy raises | 500, no event, no policy | PASS |
| D-fail-append | 3 | append raises | 500, policy rolled back, no event | PASS |
| Q-a1 | 1 | change only origins / hops / states with flag unchanged | `updated` each | PASS |
| Q-a2 | 1 | first write, flag omitted | `updated`, response flag false | PASS |
| Q-a3 | 4 | response shape | exactly 4 keys, equals request; omitted flag echoes stored true | PASS |
| Q-a4 | 2 | 4 calls | 4 events, distinct ids and correlation ids, actor never `system` | PASS |
| Q-a5 | 3 | empty origins, hops 0, states 201, flag "maybe", 5000-char host, Vietnamese host/path | 404/422, nothing written | PASS |
| Q-a6 | 2 | origin string / hashes in any event | absent | PASS |
| Q-db1 | 1,2 | real DB: false, true, omit, false | 4 rows, actions updated/enabled/updated/disabled, correct fields, 4 correlation ids | PASS |
| Q-db2 | 3 | real DB: append raises on an existing policy | 500; flag and origins unchanged in DB; only the first event | PASS |
| Q-db3 | 3 | real DB: append raises on first write | 500; no policy row, no event | PASS |
| Q-db4 | 3 | real DB: `set_policy` raises | 500; policy unchanged; no new event | PASS |
| Q-db5 x2 | 3 | real DB: viewer role / bad origin | 401/404; flag still true; event ids unchanged | PASS |
| Q-db6 | 3 | real DB: tenant-b PUT on tenant-a project id | tenant-a policy untouched, no extra event (response 500, see note) | PASS |
| Reg | 4 | dashboard_route_contracts, vision_agent_task_assessment, vision_tree_capacity, vision_policy_routes, vision_agent_engine_selection, vision_policy_persistence | green | PASS (155 total) |
| Bug-repro | — | feature, not a fix: the old behaviour (no event) is covered by every case expecting one event | n/a | n/a |

Note N1 (not a phase 12 defect): `project_execution_policies` primary key is `project_id` only, so a different tenant writing to
an existing project id gets 500 (key collision, rolled back, no leak, no event). Pre-existing schema, outside phase scope.
