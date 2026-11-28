# Phase 14 - test report (QA r1)

QA VERDICT: PASS

## Environment
Host Windows, `uv run pytest`, `CODEX_BRIDGE_ENABLED=false`, disposable `postgres:17-alpine` on `127.0.0.1:57557`
(container `p14-qa-pg`, stopped). Fixture URL redirected by an out-of-repo pytest plugin (`-p p14qa_port`), `tests/vision_trace_fixtures.py` untouched.
Real agent-loop session (fake worker) as in the developer tests. `-rs` lists no skipped test: 0 skip for DB tests.

## Real output
```
tests/test_qa_phase14_agent_task_draft.py (final)             35 passed (75s)   -> QA race observation: RACE_CODES [201, 500]
test_agent_task_draft_routes.py + test_qa_phase14...py        72 passed, 4 warnings in 150.76s
test_agent_task_draft.py + test_generation_provider_routes.py + test_generation_event_processor.py
  + test_vision_routes.py + test_run_routes.py                65 passed, 1 warning in 14.54s
uv run ruff check .                                           All checks passed!
hgraph check                                                  8 graph, 552 file source - Khong co van de.
hgraph check --changed                                        exit 1: only tracked, uncommitted files of other phases
                                                              (known false positive, memory hgraph-run-from-auto-at-ui);
                                                              no phase-14 file listed after `hgraph add agent-task-draft
                                                              tests/test_qa_phase14_agent_task_draft.py` (total 32)
git diff --stat -- migrations apps/control-plane/infrastructure/persistence/models.py   empty (criterion 6)
```
Total: 47 (unit) + 37 (route) + 35 (QA) = 119 phase tests, 0 fail, 0 skip. Regression groups: 18 + others in the 65 above, 0 fail.
Out of scope, not run: `test_qa_r8_agent_evidence.py::test_worker_dom_skips_private_inputs_and_redacts_sensitive_names` (red before this phase), the whole suite.

## Gaps found in the developer tests and added (QA file)
1. `where_is` json-dumps with `ensure_ascii` and the renderer writes non-ASCII as `\uXXXX`, so a Vietnamese value would be invisible to the scan (false negative). QA scan checks raw, JSON-escaped, JS-escaped spellings; Vietnamese values pass (only in source).
2. Values sent in refused (409) and 422 requests and in replays were not scanned in the DB/log: now covered, nothing stored.
3. 404 bodies not compared; replay permission; `service=True` flag; unknown assessment shapes; request over 200 values; huge value; hostile values; concurrency.

## Findings (none blocks the verdict)
- D1 (deviation from phase text, matches ADR-047 line 122): criterion 3 says "cung key khac body -> 409". Real result: the client key is not stored and not compared; same session+trace with another key/body returns 200 `created=false` with the old draft (test C3-02, DEV `test_asking_again_...`). 409 `idempotency_key_conflict` happens only when the stored request row belongs to another target/project. Leader should accept this wording change (it is what keeps values out of any hash).
- D2 (risk, disclosed by dev): two simultaneous first requests for the same session: observed `[201, 500]`. Exactly one request + one draft exist, rollback clean, no value in the 500 body, retry returns 200 with the same draft. The loser sees a 500 instead of the replay. Reproduce: `tests/test_qa_phase14_agent_task_draft.py::test_qa_two_requests_at_once_never_make_two_drafts` (barrier after `get_request_by_key`). Suggested follow-up: catch `IntegrityError` on the unique `(tenant_id, idempotency_key)` and replay.
- D3: `provenance.consistency` is outside `PlanningProvenance` (extra="forbid"): `PlanningProvenance.model_validate(stored provenance)` would fail. Nobody validates today; dev disclosed.
- `service=True` with a human role: observed 404 (`OBS_SERVICE_FLAG 404`).

## Not tested and why
- Real uvicorn access log / proxy request-body logging: TestClient does not start uvicorn; `main.py` logs only status/ids (read), caplog DEBUG + capfd clean.
- Stress test: not needed - one transaction of two inserts per request, no loop over large sets, no new query without index; the only concurrency risk is D2.
- Dashboard (phase 15), runner execution of approved drafts: out of phase.
- Value typed from an astral emoji: length is counted in Python code points on both sides (trace `len(action.text)` and renderer), consistent; not tested end to end.
