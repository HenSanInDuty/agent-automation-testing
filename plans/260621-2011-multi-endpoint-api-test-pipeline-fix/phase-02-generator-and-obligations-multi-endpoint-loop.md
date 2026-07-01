# Phase 02 — Generator + obligations loop over all endpoints

## Context Links
- `backend/app/tools/api_test_case_generator.py` (`generate_test_cases`)
- `backend/app/services/api_test_planning/consolidator.py` (`extract_obligations`)
- Depends on Phase 01 (`ParsedSpec.endpoints`)

## Overview
- **Priority:** P1
- **Status:** pending
- **Description:** Make both deterministic producers iterate every endpoint in
  `parsed.endpoints` instead of the single compat `parsed.endpoint`. This is the fix that turns
  "2 test cases / false 100% coverage" into a real multi-endpoint suite + honest coverage.

## Key Insights
- `generate_test_cases` (`api_test_case_generator.py:122-124`) reads `parsed.endpoint/.request/.responses`
  and emits cases for ONE endpoint. The TC id counter (`counter`) and `full_url`/`method` derivation
  all assume a single endpoint.
- `extract_obligations` (`consolidator.py:34-90`) walks `parsed.responses`, `parsed.endpoint.auth`,
  `parsed.headers`, `parsed.request.body_fields` once → one endpoint's obligations. Coverage
  (`coverage.py`) divides covered/total of these → with 1 endpoint's obligations all satisfied by
  the baseline, score is a false 100%.
- `coverage.py` operates purely on the obligation list + cited ids — **no change needed** (verified:
  it never touches `ParsedSpec`). More obligations from more endpoints flow through automatically.
- Obligation ids must stay deterministic `OBL-NNN` in a fixed traversal order; with multiple
  endpoints the order becomes (endpoint 0: responses→auth→headers? →fields) then endpoint 1, etc.
  **Decision:** headers are spec-level — emit header obligations ONCE (not per endpoint) to avoid
  duplicate `header` obligations inflating the denominator. Per-endpoint: responses, auth, fields, rules.

## Requirements
**Functional**
- `generate_test_cases` emits the full per-endpoint case matrix (happy-path per 2xx, required-field,
  type-mismatch, path-param 404) for EVERY endpoint, with globally unique `TC-NNN` ids.
- Each generated case maps to obligations via `obligation_ids` so coverage is real.
- `extract_obligations` returns obligations spanning all endpoints; header obligations emitted once.
- Coverage denominator now includes every required obligation across all endpoints.

**Non-functional**
- Keep both files < 200 lines. `api_test_case_generator.py` is 446 lines (already over). Extract the
  per-endpoint case-building into a helper (e.g. `_cases_for_endpoint(...)`) to keep the public
  function thin; if still large, split helpers into `api_test_case_builders.py` and import.
- Deterministic, no LLM.

## Architecture

### Generator data flow (per endpoint)
```
for idx, ep in enumerate(parsed.endpoints):
    endpoint, request, responses = ep.endpoint, ep.request, ep.responses
    # derive full_url/method/flags exactly as today, but per ep
    # append cases with a SHARED, monotonically increasing counter for unique TC ids
```
- **Critical:** the `counter` must be shared across endpoints so ids stay unique `TC-001…TC-NNN`.
- `obligation_ids` linkage: today the baseline cases do not set `obligation_ids` explicitly here
  (the planner/consolidation path links them; baseline cases rely on coverage via cited ids). VERIFY
  during impl whether baseline cases currently cite obligation_ids — if they do not, coverage of the
  baseline-only path depends on planner agents. Keep current linkage behaviour per endpoint; do not
  change the coverage contract, only multiply it across endpoints.
- `CoverageSummary` block at `:315-330` uses `len(requirement_ids)` and a hardcoded
  `by_type={"functional": 1}` / `covered_requirements=1` — this is requirement-level, not
  obligation-level, coverage. Update the human-facing counts to reflect endpoint count
  (e.g. notes line lists N endpoints) but the AUTHORITATIVE coverage gate is `coverage.py` on
  obligations — do not duplicate logic here.

### Obligations data flow
```
def extract_obligations(parsed):
    counter = 1
    # spec-level headers ONCE
    for header in parsed.headers: _add("header", …, required=header.required)
    for ep in parsed.endpoints:
        for resp in ep.responses: _add("response", …)
        if ep.endpoint.auth: _add("auth", …)
        for field in ep.request.body_fields: _add("field"/"rule", …)
```
- **Order decision:** emit spec-level header obligations first (stable), then per-endpoint blocks in
  document order. Document this ordering in the docstring (it is the determinism contract).
- Evidence strings unchanged.

## Related Code Files
**Modify**
- `backend/app/tools/api_test_case_generator.py` — loop `parsed.endpoints`; shared counter; helper extraction.
- `backend/app/services/api_test_planning/consolidator.py` — `extract_obligations` loops endpoints; headers once.

**Create (only if size demands)**
- `backend/app/tools/api_test_case_builders.py` — extracted per-endpoint builders.

**No change (verified)**
- `backend/app/services/api_test_planning/coverage.py` — operates on obligation list only.

## Implementation Steps
1. Refactor `generate_test_cases`: wrap existing single-endpoint body in `_cases_for_endpoint(ep, base_url, …, start_counter)` returning `(cases, next_counter)`; loop `parsed.endpoints` accumulating.
2. Recompute `CoverageSummary`/notes for N endpoints; keep `executable = bool(base_url)` (spec-level).
3. Refactor `extract_obligations`: emit spec-level headers once, then per-endpoint responses/auth/fields/rules with the shared `OBL-NNN` counter.
4. Update docstrings to state the new deterministic traversal order.
5. py_compile both; smoke test on the sample doc → assert > 2 cases spanning ≥ 4 distinct paths.

## Todo List
- [ ] Extract `_cases_for_endpoint` helper, shared TC counter
- [ ] Loop `parsed.endpoints` in `generate_test_cases`
- [ ] Update `CoverageSummary`/design notes for N endpoints
- [ ] Loop endpoints in `extract_obligations`; spec-level headers emitted once
- [ ] Update both docstrings (determinism/order contract)
- [ ] py_compile + smoke test on sample doc

## Success Criteria
- `generate_test_cases(parsed_9ep).total_test_cases > 2` and cases span paths
  `{/api/tasks, /api/tasks/:id, /api/goals, /api/goals/:id, /api/stats}`.
- POST/PUT endpoints with declared 4xx (PUT /api/tasks/:id has 404) yield validation + 404 cases.
- `extract_obligations(parsed_9ep)` returns obligations for every endpoint's responses; ids are
  contiguous `OBL-001…` and stable across re-parse.
- `compute_coverage` against a baseline that does not cite all obligations now reports < 100%
  (honest gaps), not a vacuous 100%.

## Risk Assessment
| Risk | L×I | Mitigation |
|------|-----|-----------|
| TC id collisions if counter resets per endpoint | M×H | Single shared counter threaded through helper; assert ids unique in test. |
| Obligation id order changes break a snapshot/golden test | M×M | grep tests for `OBL-` literals before changing; update intentionally; document order. |
| Header obligations double-counted (per endpoint) inflate denominator | M×M | Emit spec-level headers exactly once (design decision above); unit test counts header obligations == header count. |
| `coverage.py` assumed unchanged but secretly reads parsed | L×H | Verified by read: it imports only schema models, not ParsedSpec. Re-confirm during impl. |

## Security Considerations
- No new secret handling. Header redaction stays in the planner crew (`adaptive_..._crew.py:219-221`).

## Next Steps
- Feeds Phase 05 tests (multi-endpoint count + coverage assertions).
- Independent of Phase 03/04 (distinct files) — may run in parallel after Phase 01.
