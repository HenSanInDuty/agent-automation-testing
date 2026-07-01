# Phase 03 — Complexity, prompts & crew preview consumers

## Context Links
- `backend/app/services/api_test_planning/complexity.py`
- `backend/app/services/api_test_planning/planner_prompts.py`
- `backend/app/crews/api_test_case_crew.py`
- `backend/app/crews/md_spec_verifier_crew.py`
- `backend/app/crews/adaptive_api_test_planner_crew.py`
- Depends on Phase 01 (`ParsedSpec.endpoints`)

## Overview
- **Priority:** P2
- **Status:** pending
- **Description:** Migrate the remaining `ParsedSpec` consumers from the single-endpoint compat
  surface to multi-endpoint awareness. These do not block the core bug fix (compat properties keep
  them running), but leaving them single-endpoint means complexity scoring and planner prompts only
  "see" the first endpoint → weak plans + wrong agent counts for multi-endpoint specs.

## Key Insights
- `complexity._count_signals` (`complexity.py:57-73`) reads `parsed.endpoint.method`,
  `parsed.request.body_fields`, `parsed.responses`, `parsed.headers`, `parsed.endpoint.auth` — all
  single-endpoint. For a 9-endpoint spec it would under-count and pick too few planner agents.
- `planner_prompts._spec_summary` (`planner_prompts.py:68-91`) renders ONE endpoint into the prompt
  JSON. Planner agents thus only ever propose cases for the first endpoint.
- `api_test_case_crew.py:113-121` and `md_spec_verifier_crew.py:135-137` build human-facing preview
  strings from `parsed.endpoint.method/.path` and `len(parsed.responses)`. These are log/preview
  only — must not crash on empty `endpoints`, and should reflect the endpoint count.
- `adaptive_api_test_planner_crew.py` reads `parsed.base_url` (`:138`) — spec-level, unaffected —
  and passes `parsed` to `compute_complexity`, `extract_obligations`, `generate_test_cases`,
  `build_planner_prompt`, `_spec_summary`. Once those handle `endpoints`, the crew itself needs only
  preview/log tweaks.

## Requirements
**Functional**
- Complexity scoring aggregates signals across ALL endpoints (sum responses, params, rules across
  endpoints; state-changing if ANY endpoint mutates; header/auth counted at spec + per-endpoint auth).
- Planner prompt summary lists ALL endpoints (compact) so agents can propose cases for each.
- Crew preview/log strings reflect endpoint count and do not assume a non-empty `endpoints`.

**Non-functional**
- Keep files < 200 lines (complexity.py 128, planner_prompts.py 153, crews well under).
- Determinism preserved in complexity + prompt rendering.

## Architecture

### complexity.py
- `_count_signals(parsed)` → iterate `parsed.endpoints`:
  - `response_count = sum(len(ep.responses))`
  - `parameter_count = sum(len(ep.request.body_fields))`
  - `validation_rule_count = sum(required-or-ruled fields across endpoints)`
  - `header_auth_count = len(parsed.headers) + count(ep.endpoint.auth for ep if auth)`
  - `state_changing = 1 if any(ep.endpoint.method in _STATE_CHANGING_METHODS)`
- Banding/role-selection logic unchanged. A 9-endpoint spec now scores higher → more planner agents
  (still clamped 1-5 by `_agent_count`).
- **Decision point (ask if unsure):** higher aggregate scores will more often hit the top band (5
  agents). That is desired here (richer spec ⇒ more planners) and still capped at 5. No threshold
  change to the user-chosen bounds.

### planner_prompts.py
- `_spec_summary(parsed)` → emit spec-level `base_url`/`headers` plus an `endpoints: [ {method, path,
  auth, body_fields, responses} … ]` array. Keep it compact + secret-free. Truncate field rules as
  today (`[:120]`).
- `build_planner_prompt` text unchanged except the summary now covers all endpoints; obligation
  lines already come from `extract_obligations` (multi-endpoint after Phase 02).

### Crew previews
- `md_spec_verifier_crew.py:135-137`: change preview to
  `valid · {len(parsed.endpoints)} endpoint(s) · {sum(len(ep.responses))} response(s)`.
- `api_test_case_crew.py:113-121`: change log/preview to reference endpoint count
  (e.g. `{output.total_test_cases} case(s) across {len(parsed.endpoints)} endpoint(s)`).
- Both must guard `parsed.endpoints` possibly empty (fall back to compat property safely).

## Related Code Files
**Modify**
- `backend/app/services/api_test_planning/complexity.py`
- `backend/app/services/api_test_planning/planner_prompts.py`
- `backend/app/crews/md_spec_verifier_crew.py`
- `backend/app/crews/api_test_case_crew.py`
- `backend/app/crews/adaptive_api_test_planner_crew.py` (preview strings only, if needed)

**Delete** — none.

## Implementation Steps
1. Rewrite `_count_signals` to aggregate over `parsed.endpoints`; keep weights/bands.
2. Rewrite `_spec_summary` to emit an `endpoints` array; keep secret-free + truncation.
3. Update `md_spec_verifier_crew` + `api_test_case_crew` preview/log strings; guard empty endpoints.
4. Scan `adaptive_api_test_planner_crew` for any `.endpoint`/`.responses` preview usage (none found
   beyond `parsed.base_url`); adjust only if a preview reads single-endpoint fields.
5. py_compile all; smoke test: `compute_complexity(parsed_9ep)` picks ≥ 3 agents.

## Todo List
- [ ] Aggregate signals across endpoints in `_count_signals`
- [ ] Multi-endpoint `_spec_summary` (endpoints array, secret-free)
- [ ] Update `md_spec_verifier_crew` preview (endpoint count)
- [ ] Update `api_test_case_crew` log/preview (endpoint count)
- [ ] Verify/adjust `adaptive_api_test_planner_crew` previews
- [ ] py_compile + complexity smoke test

## Success Criteria
- `compute_complexity(parsed_9ep).signals["response_count"]` equals the sum across all 9 endpoints
  (≥ 10 given multiple 200s + a 404).
- `_spec_summary(parsed_9ep)` JSON contains an `endpoints` array of length 9; no secret values.
- `md_spec_verifier` preview shows `9 endpoint(s)`; no crash on a spec with empty `endpoints`.
- Existing complexity tests on single-endpoint specs still pass (compat fold gives `endpoints==[one]`).

## Risk Assessment
| Risk | L×I | Mitigation |
|------|-----|-----------|
| Aggregated score always maxes to 5 agents → latency/cost up | M×M | Capped at `max_planner_agents` (user config); document that richer specs intentionally use more agents. Surface in rationale string. |
| Existing complexity unit tests assert exact scores for single-endpoint specs | M×M | Single-endpoint compat fold keeps `endpoints==[1]` so per-endpoint sums equal old single values → scores unchanged. Verify in Phase 05. |
| Prompt grows large for many endpoints → token blowup | M×M | Compact summary; rely on existing prompt truncation downstream; acceptable for 9 endpoints. |
| Empty `endpoints` (invalid spec passed non-strict) crashes preview | L×M | Guard with compat property / `or []`. |

## Security Considerations
- `_spec_summary` must keep emitting header NAMES only (not values) — preserve current behaviour
  (`[h.name for h in parsed.headers]`). No secret leakage into prompts.

## Next Steps
- Independent of Phase 02/04 (distinct files); run in parallel after Phase 01.
- Phase 05 adds complexity + prompt assertions.
