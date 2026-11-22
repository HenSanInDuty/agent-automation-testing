# Measured exploration stability results — 2026-11-05

The target-scoped prototype completed the two benign-change scenarios that the
checkpoint-gate baseline rejected. This supports integrating and testing that
policy next. It does **not** establish that a complete sequential runner is more
reliable than the deployed BFS system on the user's website.

## Browser comparison

Chromium **133.0.6943.16**, Playwright **1.50.1**, 1280x720, new browser context per
trial. **480 trials**: 12 scenarios × 20 repetitions × 2 policies. Deterministic
planner, no real model calls. Policy order alternates between repetitions.

Both paths are sequential microbenchmark drivers. The baseline uses the actual
production state fingerprint/equality functions in the default `all` interaction
scope (matching the failed session's logged scope), plus common live-node and
Playwright actionability checks. It is not an execution of the full BFS workflow.
The prototype changes the pre-action guard to selected-target validation with
URL/form context checks. Therefore the comparison isolates the guard policy;
it does not isolate a BFS-to-sequential architectural change.

| Scenario | Expected outcome | Checkpoint gate | Target-scoped prototype |
|---|---|---:|---:|
| Stable page | Complete all 3 actions | 20/20 | 20/20 |
| Passive text update | Complete all 3 actions | 20/20 | 20/20 |
| Unrelated link changes | Complete all 3 actions | 0/20 | 20/20 |
| Target moves, identity unchanged | Complete all 3 actions | 0/20 | 20/20 |
| Popup, close, continue on parent | Complete all 3 actions | 20/20 | 20/20 |
| Target renamed | Block without click | 20/20 | 20/20 |
| Target replaced by identical-looking node | Block without click | 20/20 | 20/20 |
| Target covered | Block without click | 20/20 | 20/20 |
| Duplicate matching target | Block without click | 20/20 | 20/20 |
| Form context changes | Block without click | 20/20 | 20/20 |
| URL changes | Block without click | 20/20 | 20/20 |
| Lost acknowledgement after first click | Stop unknown; no second click | 20/20 | 20/20 |

- Completion on the five tasks expected to complete: **60/100 vs 100/100**.
- Correct behavior on all scenarios, including expected stops: **200/240 vs 240/240**.
- Forbidden clicks: **0 vs 0**. Duplicate clicks: **0 vs 0**.
- Physical clicks recorded across all trials: **200 vs 320**. The prototype
  completes more tasks; extra clicks are not retries.
- In stable tasks, both paths use three synthetic proposals. This experiment
  cannot measure how real-model cost differs from batched BFS planning.

### Timing (milliseconds)

| Scenario | Checkpoint p50 / p95 | Prototype p50 / p95 |
|---|---:|---:|
| Stable page | 429 / 570 | 481 / 601 |
| Passive text update | 443 / 517 | 520 / 615 |
| Popup | 467 / 519 | 488 / 609 |
| Unrelated link changes | 97 / 123, stopped | 477 / 562, completed |
| Target moves | 100 / 124, stopped | 483 / 566, completed |
| Covered target | 101 / 151 | 376 / 427 |

The prototype has additional checks and waits for Playwright actionability when a
target is covered. It is not faster in this measurement. Stopping early must not
be compared to completing three actions as a speed improvement. Timing includes
page setup and a synthetic 10 ms planner delay per proposal, excludes context
creation, and was measured while the regression suite also ran on this machine.

## Actual candidate-service reservation behavior

The current Python `CodexCandidateService` ran **80 trials** using the existing
synthetic exchange fixture. Each schedule was repeated 20 times:

| Injected schedule | Actual exchanges | Reported calls used | Result | Zero-call refresh gate |
|---|---:|---:|---|---|
| Stable | 1 | 1 | Completed | Not needed |
| Stale before reservation | 0 | 0 | `bridge_stale_result` | Eligible |
| Stale after reservation, before exchange | 0 | 1 | `bridge_stale_result` | Ineligible |
| Stale after exchange | 1 | 1 | `bridge_stale_result` | Ineligible |

The reservation/refresh mismatch reproduced **20/20** times. Reserving budget
conservatively is not itself a billing error; the defect is using that count as
evidence that a request was sent when deciding whether a fresh observation is
allowed. This benchmark does not modify or refund the production budget.

## Full-workflow regression run

Command: the three-file regression invocation in `README.md`.
Initial result: **73 passed, 2 failed, 0 skipped**, 542.24 seconds including
pytest setup. This uses real PostgreSQL, Chromium and the existing workflow
fixtures with synthetic planning, separately from the A/B prototype.

1. `visual_dataset`: all assertions for 47 expected clicks, no extra targets,
   completed operations and retained click evidence passed; writing
   `benchmark/vision/visual-buttons/flow-result.json` then raised `PermissionError`.
   The offline image now grants its non-root test user ownership of that artifact
   directory. This changes benchmark filesystem permissions only.
2. `visual_navigation`: the exploration reached its completed-state assertions,
   but its ledger contained no `close_popup` operation although the test requires
   one. A completed status therefore did not establish this coverage criterion.

Initial machine-readable summary:
[regression-initial-20261105.json](regression-initial-20261105.json).
The two failing cases were rerun independently of the browser microbenchmark
after the benchmark permission correction: **1 passed, 1 failed**, 251.851 seconds.
`visual_dataset` passed completely; `visual_navigation` failed at the same missing
`close_popup` assertion. Thus **74 of the 75 distinct tests have a passing result**
across the initial run and targeted rerun; one failure reproduced twice. This is
not a claim that a second full 75-test run passed.

Rerun summary: [regression-rerun-20261105.json](regression-rerun-20261105.json).
Rerun command:

```powershell
uv run --no-sync python benchmark/vision/codex/run_offline.py -q --tb=short 'tests/test_vision_page_batch.py::test_restored_tabs_and_viewport_coverage_keep_verified_targets[visual_dataset]' 'tests/test_vision_page_batch.py::test_restored_tabs_and_viewport_coverage_keep_verified_targets[visual_navigation]'
```

The benchmark Python files pass Ruff and the worker TypeScript project passes
`tsc --noEmit`. Application source, deployed containers, provider settings and
execution verdicts were not changed. Only benchmark sources/artifacts and the
offline image's artifact-directory permissions were added or updated.

## Interpretation and next gate

The evidence supports a narrowly scoped next step: separate reserved attempts
from dispatched requests, then integrate fresh observation and selected-target
validation behind a new exploration mode. Keep the old mode for comparison.

Do not declare production stability yet. This prototype is not integrated with
Temporal, persistence, bridge lifecycle, leases, consent revocation, durable
operation IDs, or branch coverage. It does not measure model quality, quota,
network failures, or real-site behavior. Exact-node/context checks can still
miss application-specific semantic changes outside the measured context;
the race between final validation and dispatch needs dedicated integration tests.

The original website/session was not replayed. Repetition of fixed synthetic
scenarios is repeatability evidence, not a statistical estimate of uptime.
The production execution contract and approval boundary were not changed.

Raw per-trial data and source hashes: [results-20261105.json](results-20261105.json).
Protocol and commands: [README.md](README.md).

A subsequent user-authorized live trial on Mongchiton completed three real Codex
exchanges but stopped with `bridge_stale_result` after the third response. See
[the separate live report](LIVE-MONGCHITON-20261105.md). This confirms that the
post-response state-validation path also needs work; reservation accounting alone
does not resolve the live failure. It is not a live trial of the prototype.
