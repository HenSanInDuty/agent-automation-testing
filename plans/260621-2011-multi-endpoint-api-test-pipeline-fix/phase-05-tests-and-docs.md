# Phase 05 — Tests + docs

## Context Links
- `backend/tests/test_md_api_spec_validator.py`
- `backend/tests/test_adaptive_api_test_planner.py`
- `backend/tests/test_senior_coverage_review_loop.py`
- `backend/tests/test_execution_persistence_and_exports.py`
- Sample fixture: `TodoCode/api_documentation-pipeline.md`
- `docs/pipeline-execution.md`, `docs/data-models.md`, `docs/api-flow.md`
- Depends on Phases 01-04.

## Overview
- **Priority:** P1
- **Status:** pending
- **Description:** Add/adjust tests proving the two bugs are fixed and no regression. Update docs
  describing the now-multi-endpoint `md_spec_parsed` contract + the runner base_url source.

## Key Insights
- Existing tests construct single-endpoint `ParsedSpec` via legacy kwargs
  (`test_adaptive_api_test_planner.py:38-55`, `test_senior_coverage_review_loop.py:65-69`) and assert
  on `.endpoint`/`.responses`/`.request`. Phase 01's compat fold + properties keep these GREEN with
  zero edits — confirm, do not rewrite.
- New coverage must assert the END-TO-END symptoms: 9 endpoints → many cases over multiple paths,
  honest coverage (< 100% when gaps exist), and bullet base_url no-skip.
- Tester owns test files only; do not edit implementation files here.

## Requirements
**Functional (new/updated tests)**
1. **Parser multi-endpoint** (`test_md_api_spec_validator.py`):
   - Parse the sample doc (or an inline multi-endpoint fixture) → `len(parsed.endpoints) == 9`.
   - Assert distinct methods/paths present (GET/POST/PUT/DELETE /api/tasks, GET/POST/DELETE
     /api/goals, GET /api/stats).
   - Backward-compat: `parsed.endpoint.method == "GET"`, `parsed.endpoint.path == "/api/tasks"`.
   - Round-trip: `ParsedSpec.model_validate(parsed.model_dump())` equals `parsed`.
2. **Generator multi-endpoint** (`test_adaptive_api_test_planner.py` or new
   `test_multi_endpoint_pipeline.py`):
   - `generate_test_cases(parsed_9ep).total_test_cases > 2`; case `api_endpoint`s span ≥ 4 paths.
   - TC ids unique + contiguous.
3. **Coverage honesty** (`test_senior_coverage_review_loop.py` or new):
   - `extract_obligations(parsed_9ep)` spans all endpoints; header obligations counted once.
   - `compute_coverage(baseline_not_citing_all, obligations)` < 100% (no false full coverage).
4. **Runner base_url** (`test_execution_persistence_and_exports.py` or new):
   - `execute_test_cases([exec_case], document_content="- Base URL: http://localhost:8080\n")`
     → case is NOT skipped for "No Base URL" (regex fix; monkeypatch `run_api_request`).
   - `ApiTestRunnerCrew.run({"test_cases":[exec_case], "md_spec_parsed":{"base_url":"http://x"}})`
     → resolves from parsed spec, not skipped for missing base URL.
   - No base_url anywhere → still skipped with existing reason (no regression).

**Non-functional**
- Tests deterministic, no live network (monkeypatch `app.tools.api_runner.run_api_request`).
- Keep new test file < 200 lines; split if needed.

## Architecture
- Prefer a single new fixture loading `TodoCode/api_documentation-pipeline.md` via path, OR an inline
  minimal 2-endpoint markdown string to avoid coupling tests to the external sample file. **Decision:**
  use BOTH — an inline 2-endpoint fixture for unit determinism, plus one integration assertion that
  the real sample yields 9 endpoints (guards the actual reported regression).
- Runner tests monkeypatch `run_api_request` to return a canned dict so no server is needed; assert
  on `ExecutionOutput.summary.skipped`/`runnable_count`.

## Related Code Files
**Modify**
- `backend/tests/test_md_api_spec_validator.py` — add multi-endpoint + round-trip cases.
- `backend/tests/test_execution_persistence_and_exports.py` — add base_url-from-parsed + bullet tests.

**Create (if cleaner than extending)**
- `backend/tests/test_multi_endpoint_pipeline.py` — end-to-end: sample doc → parse → generate →
  obligations → coverage, asserting the fixed symptoms.

**Docs to update**
- `docs/data-models.md` — `ParsedSpec` now `endpoints: list[ParsedEndpointSpec]` + compat properties.
- `docs/pipeline-execution.md` — runner resolves base_url from `md_spec_parsed` (carry-forward).
- `docs/api-flow.md` — note multi-endpoint coverage semantics (per-endpoint obligations).

## Implementation Steps
1. Add inline 2-endpoint fixture + sample-doc integration assertion to validator tests.
2. Add generator/obligations/coverage multi-endpoint tests.
3. Add runner base_url tests (parsed override + bullet regex + no-base-url regression),
   monkeypatching `run_api_request`.
4. Run full suite: `cd backend && uv run pytest -q`. Fix any compat regressions surfaced.
5. Update the three docs.

## Todo List
- [ ] Validator: 9-endpoint parse + distinct paths + compat + round-trip tests
- [ ] Generator: > 2 cases over ≥ 4 paths, unique TC ids
- [ ] Obligations/coverage: multi-endpoint span, headers once, honest < 100%
- [ ] Runner: parsed-override path, bullet-regex path, no-base-url regression (monkeypatched)
- [ ] `uv run pytest -q` green (incl. all pre-existing tests)
- [ ] Update `data-models.md`, `pipeline-execution.md`, `api-flow.md`

## Success Criteria
- New tests fail on `main`/pre-fix code and pass after Phases 01-04.
- Full `backend` pytest suite passes (no regression in single-endpoint tests).
- Docs describe the multi-endpoint contract + runner base_url source.

## Risk Assessment
| Risk | L×I | Mitigation |
|------|-----|-----------|
| Pre-existing tests break from compat-property edge cases | M×H | Run full suite step 4; treat any break as a Phase 01 compat bug, not a test edit. |
| Runner tests accidentally hit a live server | M×M | Monkeypatch `run_api_request`; never depend on localhost:8080 being up. |
| Sample-doc integration test brittle if doc edited | L×M | Assert `>= 9` endpoints + presence of key paths, not an exact full snapshot. |
| Obligation-id literal assertions in old tests drift | M×M | grep `OBL-`/`TC-` literals before asserting; align with Phase 02's documented order. |

## Security Considerations
- Tests must not embed real secrets; use placeholder headers. Assert redaction still applies where
  relevant (planner crew path).

## Next Steps
- Final phase. On green, hand to `code-reviewer`, then `ship`/journal per workflow.
