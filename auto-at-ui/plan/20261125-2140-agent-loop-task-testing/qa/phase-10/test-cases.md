# Phase 10 — test cases (QA r1)

Automation: `tests/test_qa_p10_verified_text.py` (62 cases, all PASS) plus developer files
`tests/test_vision_verified_text.py`, `tests/test_agent_task_trace.py` (read, run, not edited).
Live cases L1-L5 ran on the rebuilt stack (see test-report.md).

| ID | Criterion | Case | Expected | Result |
| --- | --- | --- | --- | --- |
| C1.1 | 1 | `test_p10_field_values_never_enter_the_observed_set` | only page text + control names kept | PASS |
| C1.2 | 1 | `test_p10_observed_cap_200_...`, `..._exactly_200_...` | 200 kept, `truncated` only above 200 | PASS |
| C1.3 | 1 | `test_p10_observations_without_page_text_never_raise` (4 shapes) | no error, empty | PASS |
| C2.1 | 2 | quote styles (13 param cases: `"`, curly double, `'`, curly single, guillemets, unclosed, lone, apostrophes, none, empty) | per documented styles; unsupported styles give [] | PASS (notes N2, N3) |
| C2.2 | 2 | nested quotes; apostrophe then real quote | outer + inner; apostrophe ignored | PASS |
| C2.3 | 2 | odd whitespace in quote: many spaces, tab, newline, NBSP, em space, outer spaces | squashed, matches | PASS (6) |
| C2.4 | 2 | zero-width space | no match | PASS |
| C2.5 | 2 | near miss: case, upper case, accents stripped, lower-case accents | dropped, counted | PASS (4) |
| C2.6 | 2 | NFD vs NFC Vietnamese | dropped (rule is whitespace only) | PASS |
| C2.7 | 2 | fragment with collapsed whitespace | candidate, kind of the item | PASS |
| C2.8 | 2 | tiny quotes `1 3 a o OK ok 12 bảo Thê xx` | 1-char only whole item; fragments of control names never | PASS; numbers in report (N1) |
| C2.9 | 2 | 160 chars ok, 161 dropped; page item over 160 cannot exist | per cap | PASS |
| C2.10 | 2 | check_index counts all checks; same quote in 2 met checks gives 2 items | index = position in `checks` | PASS |
| C3.1 | 3 | `not_met` / `not_checked` with matching and invented quotes | no item, no drop | PASS |
| C3.2 | 3 | loop: not_met check stores empty candidates | `{items:[],dropped:0}` | PASS |
| C3.3 | 3 | bare stop and step limit | no `verified_text` key | PASS |
| C4.a | 4a | match gives kind + text + index (dev + QA) | candidate | PASS |
| C4.b | 4b | invented quote(s) | dropped, counted each | PASS |
| C4.c | 4c | "Password: hunter2", "Enter your password", "token=..." cannot be built as page text; quoting them finds nothing | dropped | PASS |
| C4.d | 4d | 3 hostile page strings ("ignore previous instructions", fake JSON, closing tag) | plain candidate, result keys unchanged, no verdict field | PASS |
| C4.e | 4e | 250 observed items -> truncated; 150 matching quotes -> 100 items, dropped 50, contract accepts | cap + flag | PASS |
| C4.f | 4f | no page_text (None, missing, `()`) | empty, no error | PASS |
| C5.1 | 5 | loop with quoting vs plain task_result: same model-call count (2), same worker call list, same prompt context | identical | PASS |
| C5.2 | 5 | retry path (`bridge_stale_result`) with candidates | 3 calls, 3 observes as before | PASS |
| C5.3 | 5 | regression files (prompt v4, r11, loop, loop_qa, assessment, p3 snapshot) | green | PASS (see report) |
| C5.4 | 5 | text from several observations is unioned | both quotes match | PASS |
| C6.1 | 6 | `VisionResults.result` returns `task_assessment.verified_text` | present | PASS |
| C6.2 | 6 | HTTP `GET .../result` returns the key | 200 + key | PASS |
| C6.3 | 6 | dashboard `npm.cmd run typecheck`, `npm.cmd test` | clean, 56/56 | PASS |
| X8.1 | 8 | ruff, manifest refresh (0 refreshed), benchmark test, `hgraph check` | clean | PASS |
| R1 | cross 08 | assessment with `verified_text` builds a trace; hash differs per text / kind / count; hash equals independent sha256 of the dumped payload | 4 distinct hashes | PASS |
| R2 | cross 08 | assessment without the key: hash == independent sha256 of the pre-phase-10 shaped payload; reload keeps the hash | equal | PASS |
| R3 | cross 08 | explicit `verified_text: None` hashes like an absent key | equal | PASS |
| R4 | cross 08 | accepted exception: page-visible typed todo title may appear in `verified_text` | present (documented as accepted) | PASS |
| R5 | cross 08 | quoted sensitive typed value cannot become a candidate; trace JSON has no such value | absent | PASS |
| R6 | cross 08 | loop: typed password never in `verified_text`; typed todo shown on page is (accepted) | as stated, `dropped == 1` | PASS |
| R7 | cross 08 | stored assessment has no raw page text, only the matched segment | no "Overview", no sentinel | PASS |
| R8 | cross 09 | `GET .../consistency` with `verified_text` on 2 sessions of the group | 200, counts unchanged, key not echoed | PASS |
| L1 | 7 | live `todo-add` x1 | completed, `verified_text` non-empty, texts on page | PASS |
| L2 | 7 | live `search-empty` x1 | completed, candidate `Không tìm thấy sản phẩm` | PASS |
| L3 | 6/7 | live `GET .../result` of both sessions | `task_assessment.verified_text` present | PASS |
| L4 | cross 09 | live `GET .../consistency` of the todo-add session | 200, group of 12, eligible | PASS |
| L5 | cross 08 | live `read_agent_task_trace` of both sessions (read-only, host to port 5432) | trace built, carries `verified_text` | PASS |
