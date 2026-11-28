# Phase 11 — test report (QA r1)

QA VERDICT: PASS

## Environment
Windows 11, `uv run`, Python venv of the repo, node present (literal read-back and `node --check` ran, 0 skipped), `CODEX_BRIDGE_ENABLED=false`.
No Docker stack, no DB. Pytest's default temp base `C:\Users\hen\AppData\Local\Temp\pytest-of-hen` is not writable for this session
(`PermissionError`), so files using `tmp_path` need `--basetemp=<writable dir>`; my QA file uses `tempfile` and does not depend on it.

## Commands and output
```
uv run ruff check .                       -> All checks passed!
pytest tests/test_qa_p11_agent_task_renderer.py -q -rsx
  -> 122 passed, 1 xfailed in 6.43s
     XFAIL ...test_p11_c1_renderer_never_emits_garbage_for_a_kind_it_does_not_know (note N1)
pytest <phase + regression set of 14 files> (renderer, QA p11, source renderer, handoff, event processor,
  generation contracts, codex generation, agent_task_trace, QA p08/p09/p10, verified_text, verified_artifacts,
  vision_agent_task_assessment, agent_boundaries, healing_proposals, reporting_routes)
  -> 609 passed, 2 xfailed, 3 warnings, 11 errors in 98.03s
     the 11 errors are all PermissionError on pytest-of-hen (tmp_path); rerun of those files with --basetemp:
  -> tests/test_agent_task_renderer.py tests/test_codex_generation.py tests/test_verified_artifacts.py
     tests/test_vision_source_renderer.py : 71 passed in 3.52s
pytest provenance users (codex_bridge_end_to_end, codex_bridge_benchmark, vision_live_persistence,
  vision_locator_pipeline, vision_results, vision_benchmark, qa_r11_agent_loop_prompt, playwright_worker_compose)
  -> 1 failed, 85 passed, 3 skipped in 215.25s
     SKIPPED test_codex_bridge_benchmark.py:59,145 "run in offline harness image" (pinned planner hash test passes)
     FAILED tests/test_vision_benchmark.py::test_gehihi_manifest_provenance_and_mocked_response_gates
hgraph check          -> hgraph check — 8 graph, 544 file source / Không có vấn đề.
hgraph check --changed -> uncovered-changed list of tracked files with `auto-at-ui/` prefix (known false positive,
                          e.g. generation.py is in agent-task-draft per `hgraph which`); no phase 11 file is listed.
```
Full `uv run pytest tests` not run: plan.md records 40+ minutes, over the 540 s cap. The 14 + 8 files above cover every test file that
mentions provenance, plus phases 08-10.

The one failure is pre-existing and unrelated: `tests/test_vision_benchmark.py` (gehihi manifest) compares a sha256 of
`workers/playwright/src/fixtures/vision-target.ts`, a file that is committed and unmodified (`git status` clean for it; not in the phase
scope). Most likely line endings of the Windows checkout. Not caused by phase 11.

## Criteria coverage
1. kinds/order/locators: C1.1-C1.8 + developer builder-based test. Password label cannot even become a descriptor.
2. codes: `locator_unavailable`, `input_value_missing`, `input_value_mismatch`, `input_value_rejected_by_source_policy`, `source_policy_rejected` all exercised; 19 policy values, step named, value never in str/repr/args/vars/traceback/cause chain.
3. literals: 13 hostile values; node read-back equals the original values; `node --check` of the whole file passes.
4. hash, canonical `allowed_origins` (6 URL shapes), tampered hash refused, three fixture snapshots (dev exact text + QA line grammar).
5. sentinel (ASCII and Vietnamese) scanned over every output field, provenance, trace, logs, and 8 refusal paths including the chained exception.
6. old provenance validates; dumps differ only by four `null` keys; `exclude_none` dump equals the old dict; closed/validated new fields.
7. determinism in-process (5 runs) and across processes with 3 PYTHONHASHSEED values.
8. ruff clean, regression files green, `hgraph check` clean, graph `agent-task-draft` updated (I also added my QA test file with `hgraph add agent-task-draft ... --role test`, as the phase 10 QA file was).

## Extra check asked: 4 null provenance keys for every new draft (`application/generation.py:179`)
- Reading old rows: fine (new fields optional; C6.1, C6.3). Reading rows written with the nulls: fine (round trip equal).
- Hashes: no hash is derived from the provenance dump (`source_hash` is over the source only; `vision_generation_key` does not include provenance); planner hash test in `test_codex_bridge_benchmark.py` passes. No test in the repo compares a whole provenance dict (only single keys such as `provenance["vision_source"]`), so no regression.
- Visible side effects: API `provenance: dict[str, object]` (`routes/generation.py:67,141`) now returns four extra `null` keys; the dashboard types it `Record<string, unknown>` and only prints the JSON (`generation-dashboard.tsx:199`), so cosmetic only. `exclude_none` at `generation.py:179` would remove it; left to phase 13/14 as the developer noted.

## Notes (non-blocking)
- N1 `agent_task_renderer.py:105-106` — the `else` branch treats any step kind that is not navigate/click/type/scroll as `wait`. A hand-built step of an unknown kind yields `await active.waitForTimeout(None);` (strict xfail documents it). Unreachable through `AgentTaskTraceStep` (closed Literal; C1.1), so not a defect today; an explicit `elif step.kind == "wait"` plus a refusal would make the renderer fail closed.
- N2 The source policy is word-based, so typed values or page text equal to `fs`, `net`, `vm`, `dns`, `tls`, `cluster`, `Worker`, `Buffer` are refused (value: `input_value_rejected_by_source_policy`, page text: candidate dropped and counted). Over-rejection, not a leak; phase 14 should surface the code to the requester.
- N3 `_check_values` calls `len()` on `input_values`, so a one-shot iterator would raise `TypeError`; the signature says `Sequence`, callers must pass one.

## Not tested, and why
- Stress test: not needed. Pure function with no I/O, no lock or transaction; the only loop of note is the culprit search (one render per typed step), measured with 300 type steps (C2.10, well under the 20 s bound).
- Real Playwright run of the rendered source against the task fixture (`.first()` and the `getByText().or(getByLabel())` forms): phase 16 per plan; here only `node --check`, literal read-back and the runner contract validators.
- Full 40+ minute suite and the offline-harness-only benchmark cases (3 skips): out of the time cap / need the harness image.
- Persistence, API mapping of the refusal codes, `input_value_not_allowed` flag check: phase 13/14, not built.
