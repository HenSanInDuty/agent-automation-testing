# Phase 13 — test cases (QA r1)

Layers: HTTP route + disposable PostgreSQL (127.0.0.1:55437) = "HTTP/DB". E = `tests/test_agent_task_review_guards.py` (dev), Q = `tests/test_qa_p13_review_guards.py` (QA). All PASS (E+Q: 52 passed).

| ID | Criterion | Case | Expected | Test | Result |
|---|---|---|---|---|---|
| TC-01 | 1 happy | reviewer (not requester) approves values draft with ack, flag on | 200; +1 test_case, +1 test_run, 1 decision; spec has `contains_test_values` | E `test_reviewer_other_than_requester_approves...` | PASS |
| TC-02 | 1 | project_admin, tenant_admin approve | 200 | E `test_admin_roles_with_proposal_permission_can_approve` | PASS |
| TC-03 | 1 error | requester approves own draft (even project_admin) | 409 `reviewer_must_differ_from_requester`; table counts unchanged; draft pending | E `test_requester_cannot_approve_own_draft...` | PASS |
| TC-04 | 1 error | agent draft with no `requested_by` | 409, fail closed, counts unchanged | E | PASS |
| TC-05 | 1 error | contributor (no DECIDE_PROPOSAL) | 404, counts unchanged | E | PASS |
| TC-06 | 1 error | service principal, also `reviewer,service`, `tenant_admin,service` | 404, counts unchanged | E | PASS |
| TC-07 | 1 | reviewer rejects; use case only path to case+run | no case/run; refusals leave both empty | E (2 tests) | PASS |
| TC-08 | 1 edge | requester rejects own draft: contributor 404, reviewer 200 | rule "different person" applies to approval only; needs DECIDE_PROPOSAL | Q `test_requester_may_reject_own_draft...` | PASS |
| TC-09 | 1 edge | `agent_trace_source: {}` still counts as agent draft | contributor refused | Q | PASS |
| TC-10 | 1 error | reviewer from tenant-b | 404, counts unchanged | Q | PASS |
| TC-11 | 1 error | no `X-Tenant-Id` | 401, counts unchanged | Q | PASS |
| TC-12 | 1 local header | no `X-Actor-Id` -> actor `local-developer`; requester = that actor refused, other requester allowed | 409 / 200 | Q | PASS |
| TC-13 | 1 edge | double approval | exactly 1 case, 1 run, 1 decision | Q | PASS |
| TC-14 | 1 edge | Vietnamese reason accepted; 4001-char reason | 200; 422 with no change | Q | PASS |
| TC-15 | 1 regression | legacy (non-agent) draft decided by contributor | 200 as before (DECIDE_GENERATION); spec has no new key | E + `test_generation_provider_routes.py`, `test_generation_preflight.py` | PASS |
| TC-16 | 2 | values draft, ack missing / false | 409 `disposable_credentials_ack_required`, counts unchanged | E (2) | PASS |
| TC-17 | 2 | ack true, project flag off | 409 `owned_test_target_disabled`, counts unchanged | E | PASS |
| TC-18 | 2 | non-boolean / null ack | never unlocks: null/false/[] -> 409/422; counts unchanged | Q `test_non_boolean_acknowledgement_never_passes` (6) | PASS |
| TC-19 | 2 | old request body without the new field | parses; legacy draft 200 | Q | PASS |
| TC-20 | 2 | agent draft without typed values | no ack/flag needed, reviewer rule still applies | E + Q | PASS |
| TC-21 | 2 use case | refusals before any write (memory repo) | no case/decision/request added | E (3) | PASS |
| TC-22 | 3 | preflight fails for values draft | 409 `credentials_in_source`; no `generation_requests`, no outbox; draft pending | E | PASS |
| TC-23 | 3 | after failed preflight the draft is retryable | still `pending_review`; later approval 200 | Q | PASS |
| TC-24 | 3 regression | preflight fails for legacy draft | repair request queued as before | E | PASS |
| TC-25 | 3 | `revised-draft` on values case | 409 `credentials_in_source`; no rows | E | PASS |
| TC-26 | 3 | revised-draft after real approval of a values draft | 409; generation_requests free of sentinel | Q | PASS |
| TC-27 | 3 regression | revised-draft on plain case; `contains_test_values: false` | 202, request created | E + Q | PASS |
| TC-28 | 4 | unique sentinel through refusals, preflight fail, flag-off, reject, approve, revised-draft | absent from `generation_requests`, `audit_events` (row text), `provenance`, caplog (DEBUG, message+exc); present in drafts/test_cases (premise) | Q `test_sentinel_never_reaches...` | PASS |
| TC-29 | 4 | value in outbox (accepted place) | present only there | E | PASS |
| TC-30 | 5 | evidence bundle of values run | no excerpts, no `approved_playwright_test_source` | E | PASS |
| TC-31 | 5 | failed run with `fill('<sentinel>')` in playwright-output and sentinel in worker-result, through `ReportingEventProcessor` + fake model | model payload has no sentinel, no source | Q `test_failed_values_run_sends...` | PASS |
| TC-32 | 5 regression | same harness, ordinary case | sentinel and source present (control) | Q + E + `test_reporting_event_processor.py` | PASS |
| TC-33 | 5 | `worker-result` decision | excluded with `playwright-output` (excerpts empty) | E, Q | PASS |
| TC-34 | 6 | ADR-002 section equals PM text + user edits (a)(b) | identical string | Q `test_adr002_section_matches...` | PASS |
| TC-35 | 6 | Amended line; two changed sentences; unchanged rules kept | present | Q (2) | PASS |
| TC-36 | 7 | ruff; target pytest group; graph | clean | see report | PASS |

Bug-reproduction (fix-type): not applicable, this is a feature phase. Guard sensitivity is shown by the control cases (TC-29, TC-32).
