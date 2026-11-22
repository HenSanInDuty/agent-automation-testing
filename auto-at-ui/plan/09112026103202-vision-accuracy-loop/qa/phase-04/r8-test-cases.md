# QA phase 04 r8 - test cases (ADR-040 flags A1/A2/A3)

Automation: `tests/test_qa_r8_agent_evidence.py` (49 test items, QA-owned) plus the developer files
`tests/test_vision_agent_evidence_flags.py` (20), `tests/test_vision_accuracy_agent_evidence.py` (23) and the worker spec
`workers/playwright/src/vision-agent-evidence.spec.ts` (6). Result column = result of the run documented in `r8-test-report.md`.

| ID | Group | Pre-condition / data | Steps | Expected | Test | Result |
|---|---|---|---|---|---|---|
| QA-R8-01a | Regression | Stored r6 run `1c56623e...` copied to a temp dir (offline; frame GET stubbed), assessments from `rescore-role-binding.json`, detection from `detection.json` | `Loop.evaluate` with `sources` in none / default / all / click_context / inventory | C 5/47, A 5/12, R 0/47, P n/a, inventory incomplete, passed=false, oracle hash `9242b33d...`, equal to the stored r7 score | `test_r6_stored_session_still_scores_as_r7` x5 | PASS |
| QA-R8-01b | Regression | same | `Loop.detect` with none/all/inventory | old empty detection, no `inventory.json` created | `test_r6_detect_without_inventory_is_the_old_empty_detection` | PASS |
| QA-R8-01c | Regression | same | evaluate with label | only `assessments/detection/score.<label>.json` added; every pre-existing file byte-identical; stored grounding has no `contexts` | `test_r6_grounding_has_no_contexts_and_default_artifacts_untouched` | PASS |
| QA-R8-02a | Flags off | default `Settings` | `worker_capabilities`; dump `VisualExecutedClick` (python, json, `model_dump_json`) | capabilities `dom-observation-v1`,`step-timeout-v1` only; click keys = the 6 old keys, no null `scroll_*`/`url_fingerprint` | `test_flags_off_capabilities_and_click_shape_are_the_old_ones` | PASS |
| QA-R8-02b | Flags off | fake API trace without context/pages | `start`+`collect` | `grounding.json` keys = old 4; no `inventory.json`; no `executed_click` in evidence | `test_flags_off_grounding_and_collect_keep_old_artifacts` | PASS |
| QA-R8-02c | Flags off | dev tests | inventory not written, `/trace` dump old shape, worker without capability shows no scroll/url | unchanged | dev `test_inventory_is_not_written_while_its_flag_is_off`, `test_an_operation_dump_keeps_the_old_click_shape_without_context`, worker spec 1 and 5 | PASS |
| QA-R8-03a | Combination | 8 combinations of A1/A2/A3 | `worker_capabilities`, build `VisualWorkerOpen` | A1 adds only `click-context-v1`, A2 only `agent-dom-path-v1`, A3 nothing; no duplicates; contract accepts all | `test_each_flag_only_adds_its_own_capability` x8 | PASS |
| QA-R8-03b | Combination | one stored session with context + inventory | `detect`/`evaluate` with inventory / click_context / none | detection only from inventory; context-only = none; in-flow click credited only with click_context, raises `binding does not match oracle` otherwise; default `score.json` untouched | `test_source_selection_does_not_leak_between_sources` | PASS |
| QA-R8-03c | Combination | dev tests | A1/A3 together, A2 live property | all vs none give different scores from the same data without file collision | dev `test_each_source_combination_scores_...`; worker spec 2,3 | PASS |
| QA-R8-04a | Capability | Mock worker response lacking one capability | `HttpVisualWorker.open` with all four capabilities requested | typed `VisualWorkerUnavailable` (fail closed, no crash) for each missing capability | `test_old_worker_without_the_new_capability_fails_closed_with_a_typed_error` x2 | PASS |
| QA-R8-04b | Capability | pre-r8 worker, flags off | `open` with flags-off request | succeeds, returns fingerprint | `test_flags_off_request_is_satisfied_by_a_pre_r8_worker` | PASS |
| QA-R8-04c | Capability | worker spec | without capability: unnamed controls invisible, no scroll/url on clicks, capabilities inert outside agent mode | as stated | `vision-agent-evidence.spec.ts` x6 | PASS |
| QA-R8-05a | Corrupt data | inventory `[]`, `[{}]`, `[None]`, non-list, missing/None fingerprint, controls None/`[{}]` | `export_inventory` + `derive_detection` | no exception, 0 identified, 0 unexpected | `test_corrupt_or_missing_inventory_never_crashes_and_never_credits` x8 | PASS (observation O1) |
| QA-R8-05b | Corrupt data | oracle-page state with empty controls | derive | no identified, 1 page on oracle url | `test_empty_controls_page_is_not_complete_credit_free` | PASS |
| QA-R8-05c | Duplicates | same dom_path key twice, same name via two keys, same unmatched key twice | derive + `metrics.score` | identified `h1,u1` once each; unmatched keys deduped; recall numerator 2 | `test_duplicate_dom_path_and_duplicate_names_count_each_target_once` | PASS |
| QA-R8-05d | Corrupt data | inventory control named like a non-expected oracle control (`Thoát`) | derive + score | recall 0, precision numerator 0 (no credit) | `test_non_expected_oracle_control_in_inventory_earns_no_recall` | PASS |
| QA-R8-05e | Corrupt data | 10 click shapes (empty, partial, short hash, negative, bool, float, string, null) | `click_context` | None (never partial) | `test_missing_or_corrupt_click_context_is_absent_never_partial` x10 | PASS |
| QA-R8-05f | Corrupt data | in-flow click with scroll but no fingerprint | evaluate with credit | refused (`binding does not match oracle`) | `test_corrupt_context_cannot_credit_an_in_flow_click` | PASS |
| QA-R8-05g | Duplicates | two clicks on the same target | evaluate with both credited / one | `already credited` / coverage 1 | `test_a_repeated_click_on_one_target_is_credited_once` | PASS |
| QA-R8-05h | Corrupt data | inventory of another page | derive | 0 identified, 0 pages on oracle url, not complete | `test_inventory_of_another_page_or_url_missing_fingerprint_is_ignored` | PASS |
| QA-R8-06a | Sensitive | click context with extra `typed`/`page_url` carrying a secret; inventory control with `value`/`text`, page_url with token | `collect` | secret absent from `grounding.json`, `inventory.json`, `evidence.json`; inventory keys allowlisted; context keys = `scroll`,`url_fingerprint` | `test_no_form_value_or_url_reaches_inventory_or_context_artifacts` | PASS |
| QA-R8-06b | Sensitive | worker source | static guard + worker spec | password/hidden skipped before name read, sensitive-name regex present; `VisualExecutedClick` rejects free-text fields | `test_worker_dom_skips_private_inputs_and_redacts_sensitive_names`, `test_executed_click_contract_rejects_free_text_fields` | PASS |
| QA-R8-07 | Integrity | repo | content hash of oracle JSON; `git diff HEAD` on `metrics.py` and oracle | hash `9242b33d5e4cdd155b6642262c32f166b365edeec7d7b9642c5b88df35147a4e`; no diff | `test_oracle_content_hash_and_frozen_files_unchanged` | PASS |
| QA-R8-08 | Static | repo | `uv run ruff check .`; worker `npx tsc --noEmit` | clean | n/a | PASS |
| QA-R8-09 | Regression | blast radius | agent loop / safety / engine selection / config / contracts / results python tests; worker specs `vision-agent-evidence` + `vision-agent-mode` (1 worker) | green apart from DB skips | see report | PASS |

Not a "fix" task: there is no bug-reproduction case.

QA VERDICT: PASS
