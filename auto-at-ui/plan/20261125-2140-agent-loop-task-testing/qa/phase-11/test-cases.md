# Phase 11 — test cases (QA r1)

Automation: `tests/test_qa_p11_agent_task_renderer.py` (123 collected: 122 PASS, 1 xfail strict = note N1) plus the developer
files `tests/test_agent_task_renderer.py` (46) and `tests/test_generation_contracts.py` (read, run, not edited).
Names below are suffixes of `test_p11_...`.

| ID | Criterion | Case | Expected | Result |
| --- | --- | --- | --- | --- |
| C1.1 | 1 | `c1_unsupported_action_kind_is_not_a_step_at_all` (kind `hover`) | contract refuses | PASS |
| C1.2 | 1 | `c1_renderer_never_emits_garbage_for_a_kind_it_does_not_know` (hand-made step, bypasses contract) | refusal or clean source | XFAIL (N1): emits `waitForTimeout(None)`; unreachable through the contract |
| C1.3 | 1 | `c1_first_unusable_locator_is_named_even_with_two_bad_steps` (2 positions) | step 3 named, `locator_unavailable` | PASS (2) |
| C1.4 | 1 | `c1_locator_error_wins_over_value_errors` | `locator_unavailable` before `input_value_*` | PASS |
| C1.5 | 1 | `c1_dom_path_locator_is_never_rendered` | `locator_unavailable` | PASS |
| C1.6 | 1 | `c1_password_labelled_locator_cannot_exist_in_any_strategy` (role/label/placeholder "Password") | descriptor refused (Q4 unchanged) | PASS |
| C1.7 | 1 | `c1_order_and_every_kind_in_a_long_mixed_trace` (navigate, type, scroll +-2000, wait 100/10000, click) | markers in trace order | PASS |
| C1.8 | 1 | `c1_trace_with_zero_steps_never_reaches_the_renderer` | contract refuses empty steps | PASS |
| C2.1 | 2 | `c2_policy_value_...` 19 values: process, fetch, require, eval, Function, XMLHttpRequest, WebSocket, Worker, Buffer, `__dirname`, child_process, fs, net, vm, `import(1)`, `import  (x)`, `export 'evil'`, "say fetch now", "a process b" | `input_value_rejected_by_source_policy`, step 2 named, operation_id right, value absent from str/repr/args/vars/traceback/chain | PASS (19) |
| C2.2 | 2 | `c2_first_bad_value_is_named_when_two_are_bad` | step 1 | PASS |
| C2.3 | 2 | `c2_words_outside_the_word_boundary_rule_are_accepted` (Process, processing, prefetch, FETCH, refs, netto) | rendered | PASS (6) |
| C2.4 | 2 | `c2_missing_value_zero_given_names_first_type_step` | `input_value_missing`, step 2 | PASS |
| C2.5 | 2 | `c2_extra_values_and_generator_free_input` (1 extra, 2 extra, tuple input) | `input_value_mismatch`; tuple works | PASS |
| C2.6 | 2 | `c2_length_mismatch_counts_characters` (shorter, longer, empty, 2 emoji vs 4, e-acute vs 2) | `input_value_mismatch`, step 1, value not echoed | PASS (5) |
| C2.7 | 2 | `c2_decomposed_unicode_has_longer_length_than_composed` | NFC 1 char ok, NFD 3 chars refused | PASS |
| C2.8 | 2 | `c2_mismatch_checked_before_policy` | `input_value_mismatch` wins | PASS |
| C2.9 | 2 | `c2_policy_trip_not_from_values_is_source_policy_rejected` (control named `fetch`) | `source_policy_rejected`, no step | PASS |
| C2.10 | 2 | `c2_many_steps_refusal_search_stays_fast` (300 type steps, last value `eval`) | step 300, < 20 s | PASS |
| C3.1 | 3 | `c3_value_literal_is_ascii_json_on_one_line` 13 hostile values: `"`, `'`, `\`, `\\b\`, `\"`, tab, CR/LF, C0+DEL+C1+U+2028/9+BOM+ZWSP, backtick/`${`, `</script><!--`, tiếng Việt + emoji + CJK, lone surrogate, 1000 x | `.fill(json.dumps(v, ensure_ascii=True))`, source pure ASCII, no raw CR/BEL | PASS (13) |
| C3.2 | 3 | `c3_node_reads_back_exactly_the_values_and_texts` (node evaluates the generated literals) | values identical after JS parse | PASS |
| C3.3 | 3 | `c3_whole_rendered_file_parses` (`node --check`) | exit 0 | PASS |
| C3.4 | 3 | `c3_candidate_with_every_hostile_text_is_one_line_literal` | `getByText(literal).first()`, ASCII; contract-refused texts (lone surrogate) skipped, >= 8 rendered | PASS |
| C3.5 | 3 | `c3_assertion_placement_is_after_last_step_and_before_close` | asserts after last action, before `});` | PASS |
| C3.6 | 3 | `c3_no_candidates_states_the_gap_in_stop_conditions` (`[]` and no key) | no `getByText`, "kết quả task chưa được assert" | PASS |
| C3.7 | 3 | `c3_all_candidates_refused_by_policy_is_treated_as_no_assertion` | "2 candidate(s) were left out" + gap note | PASS |
| C4.1 | 4 | `c4_every_line_matches_the_linear_grammar_and_contract` x3 (login-success, todo-add, search-results): every line fits a closed whitelist of 12 line shapes, no `if/for/while/try/evaluate/route`, `PlaywrightTestSourceMode` valid, tampered hash refused | valid | PASS (3) |
| C4.2 | 4 | `c4_allowed_origin_is_canonical_for_any_target_url_shape` (upper-case host+path/query/fragment, :80, https :443, no path, IPv6 :8080) | canonical origin | PASS (6) |
| C4.3 | 4 | `c4_url_with_quote_or_backslash_is_still_a_json_literal` | JSON literal | PASS |
| C4.4 | 4 | `c4_each_snapshot_is_distinct_and_stable_across_calls` | 3 different, stable hashes | PASS |
| C4.5 | 4 | developer exact-text snapshots `test_fixture_task_sources_match_their_snapshot_and_pass_the_runner_contract` x3 | exact source | PASS (dev) |
| C5.1 | 5 | `c5_success_path_sentinel_only_in_the_source` (ASCII + Vietnamese sentinel, plus its reverse): title, assumptions, stop_conditions, output dump/repr minus source, provenance JSON/dump, trace JSON/repr/hash, log records | absent everywhere | PASS (2) |
| C5.2 | 5 | `c5_sentinel_in_the_ascii_source_is_the_json_literal` | exactly once in source | PASS (2) |
| C5.3 | 5 | `c5_no_refusal_surface_ever_holds_the_sentinel` 8 refusals (mismatch, extra, policy+process, policy+fetch, bad control name, missing, bad url, source limit) x 2 sentinels: str, repr, args, vars, full traceback, `__cause__`/`__context__` chain, log | absent | PASS (16) |
| C5.4 | 5 | `c5_pydantic_validation_text_on_the_output_never_leaks`, `c5_provenance_helper_fields_do_not_carry_values` | provenance only `session_id`+`trace_hash` | PASS |
| C6.1 | 6 | `c6_old_stored_provenance_validates_and_new_keys_default_to_none` (full v4 with vision_source, minimal) | validates, 4 keys None | PASS |
| C6.2 | 6 | `c6_dump_of_old_provenance_differs_only_by_the_four_null_keys` (+ `exclude_none` equals the old dict) | only 4 added null keys | PASS |
| C6.3 | 6 | `c6_row_written_with_null_keys_reads_back_and_equals` | round trip equal | PASS |
| C6.4 | 6 | `c6_draft_hash_check_unaffected_by_new_keys` (with and without new keys; wrong hash refused) | `source_hash` rule intact | PASS |
| C6.5 | 6 | `c6_new_fields_are_closed_and_validated` 9 bad shapes (empty/201-char requested_by, non-bool, upper-case/short hash, bad uuid, missing hash, extra key, unknown key) | ValidationError | PASS (9) |
| C6.6 | 6 | `c6_boundary_values_of_requested_by` (1, 200, Vietnamese) | accepted | PASS |
| C6.7 | 6 | `c6_agent_trace_source_is_frozen` | assignment refused | PASS |
| C6.8 | 6 | `c6_contains_test_values_matches_the_trace` | true with `type`, false without | PASS |
| C6.9 | 6 | `c6_planner_provenance_dump_is_what_application_generation_stores` (`generation.py:179`) | 4 null keys, JSON-serialisable | PASS |
| C6.10 | 6 | developer provenance tests in `tests/test_generation_contracts.py` and `tests/test_codex_generation.py` | pass, planner hash unchanged | PASS (see report) |
| C7.1 | 7 | `c7_repeat_is_identical_and_inputs_are_untouched` (5 renders) | equal output + hash; trace and values unmodified | PASS |
| C7.2 | 7 | `c7_output_has_no_clock_or_random_content` | no timestamp, no tenant/project id | PASS |
| C7.3 | 7 | `c7_same_hash_in_separate_processes_whatever_the_hash_seed` (PYTHONHASHSEED 0, 1, random) | same 3 hashes as in-process | PASS (3) |
| M1 | misc | title/notes fixed vocabulary; page text "Password changed" is just text; URL sample canonical | as stated | PASS (3) |
| R1 | 8 | `uv run ruff check .` | clean | PASS |
| R2 | 8 | `tests/test_vision_source_renderer.py`, `test_vision_handoff.py`, `test_generation_event_processor.py` | no regression | PASS |
| R3 | 8 | `hgraph check` | clean | PASS |
| R4 | 8 | `hgraph check --changed` | no phase 11 file uncovered (tracked-file prefix false positives remain) | PASS with known caveat (report) |
