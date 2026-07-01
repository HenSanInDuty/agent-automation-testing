---
phase: 3
title: "Add senior coverage review loop"
status: complete
priority: P1
dependencies: [2]
---

# Phase 3: Add senior coverage review loop

## Overview

Add one senior-review agent and a deterministic coverage gate. Feed concrete gaps back into planning until accepted or the configured limit is reached.

## Requirements

- Numeric coverage comes from obligation-to-test mappings, not an LLM self-score.
- Senior review assesses correctness, contradictions, unsafe assumptions, executability, and missing edge cases.
- Each iteration persists plan, score, verdict, gaps, and feedback.
- Retry limit is configurable from 0-5 and cannot create an infinite DAG cycle.

## Architecture

The adaptive planner node owns an internal bounded loop:

```text
baseline -> planners/debate -> consolidate -> deterministic coverage -> senior review
              ^                                              |
              +----------- targeted gap feedback ------------+
```

Gate passes only when deterministic coverage meets threshold and senior verdict is not `reject`. On exhaustion, select the highest-scoring valid iteration, set `coverage_gate_exhausted`, and continue according to config.

## Related Code Files

- Create: `D:/CV/auto-at/backend/app/services/api_test_planning/coverage.py` — obligation matrix and score.
- Create: `D:/CV/auto-at/backend/app/services/api_test_planning/review_loop.py` — bounded iteration controller.
- Create: `D:/CV/auto-at/backend/app/crews/senior_api_test_reviewer_crew.py` — senior qualitative review.
- Modify: `D:/CV/auto-at/backend/app/schemas/pipeline_io.py` — review verdict, gap, iteration, and gate summary models.
- Modify: `D:/CV/auto-at/backend/app/db/seed.py` — senior agent config plus validated node defaults.
- Add tests under `D:/CV/auto-at/backend/tests/` for pass, feedback retry, exhaustion, reviewer failure, score ties, and zero-retry configuration.

## Implementation Steps

1. Define coverage unit and formula: covered required obligations divided by total required obligations; optional/speculative scenarios do not inflate score.
2. Require each generated case to cite obligations; validate mappings against the inventory.
3. Implement senior output schema with verdict `approve|revise|reject`, evidence, gaps, unsafe assumptions, and targeted feedback.
4. Resolve and validate threshold/retry values from template defaults plus per-run overrides.
5. Iterate only for actionable gaps; short-circuit on accepted gate or deterministic no-progress detection.
6. Keep complete iteration audit, but pass only the selected plan and summary downstream.
7. Emit progress events with iteration number, score, threshold, verdict, and remaining attempts.

## Success Criteria

- [x] Coverage is reproducible from persisted obligation mappings.
- [x] Below-threshold plan receives targeted feedback and is regenerated up to configured `n`.
- [x] Accepted plan stops early.
- [x] Exhaustion cannot fail the run when continuation is enabled; warning is explicit in DB, events, UI, and exports.
- [x] Reviewer timeout/invalid output follows a documented fallback and never causes an unbounded retry.
- [x] Test proves no-progress detection selects the best iteration deterministically.

## Implementation Notes (sync-back)

- New: `services/api_test_planning/coverage.py`, `review_loop.py`; `crews/senior_api_test_reviewer_crew.py`.
- Config flows via node `config_overrides` injected into pure-python input under non-propagating `__node_config__`; per-run `run_params` override at input top-level. Defaults: threshold 90, max_review_iterations 3, continue_on_exhaustion true.
- Open decision (M1): `continue_on_exhaustion=false` currently escalates the warning only; it does not fail the run (matches plan Unresolved Q2 "execute + warn"). Confirm if hard-fail is desired.
- Tests: `tests/test_senior_coverage_review_loop.py` (24).

## Risk Assessment

Reviewer approval can conflict with numeric coverage. Deterministic threshold is authoritative; reviewer may reject but cannot fabricate coverage. Retain complete audit for diagnosis and cost accounting.
