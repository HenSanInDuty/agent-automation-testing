# QA phase 04 r8 - test report

Environment: Windows 11, `uv run`, Python 3.14 harness venv, branch `mantaray`, HEAD `f85091a` + uncommitted r8 working tree. No docker, no live session, no model/bridge call, no DB (PostgreSQL 55437 unavailable). Playwright worker specs run with `--workers=1`, never in parallel.

## Results (real output)

```
uv run ruff check .                                       -> All checks passed!
pytest tests/test_qa_r8_agent_evidence.py                 -> 49 passed in 2.13s
pytest qa_r8 + test_vision_agent_evidence_flags + test_vision_accuracy_{agent_evidence,binding,loop,metrics} + test_vision_worker_contracts
                                                          -> 159 passed in 6.64s
pytest tests/test_vision_agent_loop*.py test_vision_agent_*.py test_agent_loop_contracts.py test_config*.py test_vision_results.py
                                                          -> 463 passed, 149 skipped in 312.14s  (all skips: "isolated PostgreSQL fixture unavailable on 127.0.0.1:55437")
workers/playwright: npx tsc --noEmit                      -> exit 0
workers/playwright: npx playwright test src/vision-agent-evidence.spec.ts src/vision-agent-mode.spec.ts --workers=1
                                                          -> 37 passed (3.4m)
hgraph check                                              -> 6 graph, 459 file source / Không có vấn đề.
hgraph check --changed                                    -> exit 1: only `uncovered-changed` entries carrying the `auto-at-ui/` git-root prefix
                                                             (known tooling issue; `hgraph which` confirms config.py -> codex-bridge, vision-agent-loop, vision-exploration
                                                             and vision_coverage.py -> vision-agent-loop). One real `drift` was my own new test file; fixed with
                                                             `hgraph add vision-agent-loop tests/test_qa_r8_agent_evidence.py`, after which no drift remains.
```
Oracle: content hash `9242b33d5e4cdd155b6642262c32f166b365edeec7d7b9642c5b88df35147a4e` recomputed by the harness; `git diff HEAD` on `metrics.py` and the oracle JSON is empty.

The first QA test run had 3 failures, all in my own tests (viewport `1` rejected by contract, one wrong assumption about a regex literal, one wrong expectation about `inventory_complete`); corrected, no product code touched.

## Coverage vs request
1. r6 regression: done offline from the stored run folder (copied to a temp dir; only the frame GET stubbed). C 5/47, A 5/12, R 0/47, inventory incomplete, passed=false for every `--sources` value; equals the stored r7 score exactly. No API/DB call.
2. Flags off: capabilities, click dump shape, grounding/collect artifacts, inventory write, worker behaviour unchanged (QA and dev tests). `/result` has no r8 code path (`vision_results.py` untouched per developer; its tests are DB-gated, skipped).
3. Combinations: all 8 flag combinations at the capability layer; source selection leakage between A1 and A3 at the harness layer.
4. Missing capability: control plane fails closed with `VisualWorkerUnavailable`; worker without capability emits no new data (worker spec).
5. Corrupt/missing/duplicate data: no crash, no credit, no double count.
6. No secrets: allowlists on the harness side, `extra=forbid` on the contract, password/hidden skipped in the worker.
7. Oracle/metrics: unchanged.
Stress test: không cần - no loop over large sets beyond the contract cap of 100 controls (covered by dev merge-cap test), no new query/index/lock/transaction; A3 reuses the planner's existing `uow.page_inventory` call.

## Observations (not failures)
- O1 `benchmark/vision/accuracy/evidence.py:derive_detection` (`complete = ...`): completeness comes from the page flags only. A valid oracle-page state whose control rows are all junk (dropped by `export_inventory`) reports `inventory_complete=true` with 0 identified. It earns no credit (recall stays 0 and `passed` also needs recall/precision above 95%), so it is not a scoring bug, but a stricter harness could require at least one exported control.
- O2 `export_inventory` drops the inventory `page_url` (good); the stored DB `page_inventory.page_url` is the planner's existing field and may include a query string. Unchanged by r8, not exercised.
- O3 The worker always advertises both new capabilities; only requests with the capability activate behaviour. An old worker + flag on gives a typed unavailable error (session does not start), not silent degrade: this is the intended fail-closed behaviour but means turning a flag on requires the rebuilt `playwright-worker` first.

## Not tested and why
- Live negotiation with the rebuilt worker container, `dom_path` stability on the real carousel, real inventory size/truncation, model behaviour with unnamed controls: need a live session (forbidden here).
- DB-gated tests (149 skipped in this run, 153 + 81 in the developer's wider run): PostgreSQL fixture unavailable; `_save_inventory`, capabilities and checkpoint tracking were covered with stubs; the real `uow.page_inventory` path and `/result`, `/trace` HTTP output with flags on/off were not exercised end to end.
- Worker regression specs beyond `vision-agent-evidence` and `vision-agent-mode` (dom, operations, locators, visual-buttons, preflight, click-evidence) were not re-run; the developer reported them green (111 + 123 passed). The `vision-dom.ts` change with flag off is covered by the 37 specs run here.
- Dashboard reading changed `/result` `observed_controls`/`remaining_controls` with A3 on: not exercised.

QA VERDICT: PASS
