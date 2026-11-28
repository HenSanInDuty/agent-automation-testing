STATUS: PASS

# Phase 10 — QA report (r1)

QA VERDICT: PASS (no criterion violated; 5 notes below do not block)

## Environment
- Branch `feat/agent-loop-task-testing`, uncommitted phase 08-10 code. Python via `uv run`, `CODEX_BRIDGE_ENABLED=false`.
- Postgres fixture 127.0.0.1:55437 (running): 0 DB skips.
- Live: stack rebuilt 08:26; `curl /openapi.json` contains `/consistency` (container runs new code).

## Commands and real output
| Run | Result |
| --- | --- |
| `tests/test_qa_p10_verified_text.py` | `62 passed` |
| 10 files: verified_text, qa_p10, agent_task_trace, qa_p08, agent_task_consistency, qa_p09, vision_results, codex_bridge_benchmark, vision_agent_task_assessment, qa_p3_page_text_snapshot | `436 passed, 7 skipped, 1 xfailed in 129.20s` |
| `test_vision_agent_loop.py test_vision_agent_loop_qa.py` | `201 passed in 163.57s` |
| `test_agent_loop_prompt.py test_qa_r11_agent_loop_prompt.py` | `42 passed in 1.68s` |
| `uv run ruff check .` | `All checks passed!` |
| `apps/dashboard`: `npm.cmd run typecheck` / `npm.cmd test` | tsc clean / `tests 56, pass 56, fail 0` |
| `refresh_manifest.py` | `0 refreshed` |
| `hgraph add agent-task-draft ...` / `hgraph add vision-agent-loop ...` | `tổng 17` / `tổng 34` |
| `hgraph check` | `8 graph, 541 file source / Không có vấn đề.` exit 0 |

Skips (7, none DB): `test_codex_bridge_benchmark.py:59` (1) and `:145` (2) "run in offline harness image"; `test_qa_p3_page_text_snapshot.py:213` (4) "contract refuses this payload before it can reach the renderer". xfail (1): the phase 09 strict xfail (status as list) noted in plan.md, pre-existing.
Warnings: Pydantic serializer warnings in `test_qa_p08...::test_p08_hash_changes...` (pre-existing, from `model_construct`).
`hgraph check --changed` not used (known false positives for uncommitted tracked files, memory note); full `hgraph check` clean.

## Criterion 7 — live run (2 sessions, exactly one per task, no third)
Commands (from `auto-at-ui/`): `uv run python scripts/run_task_stability.py run --project "Task UI fixture" --base-url http://task-target:7300 --task todo-add|search-empty --repeat 1 --out .pytest-artifacts/task-stability/p10`.

| Task | Session id | Outcome |
| --- | --- | --- |
| todo-add | `6f9049cb-fd9e-4340-98fb-106afd64418d` | completed, achieved, 35.8 s |
| search-empty | `5089e2be-3377-4b2e-af44-0af438bd06fe` | completed, achieved, 25.6 s |

`task_assessment.verified_text` verbatim (full read-back in `.pytest-artifacts/task-stability/p10/live-readback.json`):

todo-add: `{"items":[{"kind":"control_name","text":"hoàn thành: Viết báo cáo","check_index":0},{"kind":"control_name","text":"Xoá Viết báo cáo","check_index":0},{"kind":"status","text":"2 việc, 1 đã xong","check_index":1},{"kind":"status","text":"3 việc, 1 đã xong","check_index":1}],"dropped":1,"truncated":false}`

search-empty: `{"items":[{"kind":"status","text":"Không tìm thấy sản phẩm","check_index":1}],"dropped":0,"truncated":false}`

Cross-check against `benchmarks/targets/task-ui/server.mjs`: counter `<p id="counter" role="status">${n} việc, ${done} đã xong</p>` (line 146) gives both `status` items; `<label>hoàn thành: ${todo.text}</label>` (131) and `aria-label="Xoá ${todo.text}"` (136) give the two control names; `<p id="empty" role="status">Không tìm thấy sản phẩm</p>` (185) gives the search item. Every candidate text is on the real page, with the right kind. The dropped quote in todo-add is `'Viết báo cáo'` (the check expectation): the todo title as a list item is not a page-text kind, only its control labels are, so it is not whole-equal to any observed item; correctly dropped, not invented.
Hit rate: 2/2 sessions with non-empty `items`; 5 of 6 quotes became candidates (83%), 1 dropped; 0 candidates not on the page. The `search-empty` check 0 and 2 quoted nothing, so no candidate for them (the model quotes only the text it asserts on).
Phase 09 on the live stack (read only): `GET .../6f9049cb.../consistency` -> 200, `group_sessions 12, assessed 12, achieved 12, agreement_rate 1.0, eligible true, small_sample false`.
Phase 08 live (read only, `read_agent_task_trace` from host through Postgres 127.0.0.1:5432, no write; script in scratchpad, rolled back): todo-add trace built, hash `65cc95a1...4a4`, 2 steps, carries the same 4 items; search-empty trace built, hash `5dc5cf4d...946e`, 2 steps, carries 1 item.

## Criteria map
1-4, 5, 6, 8: see `test-cases.md` (all PASS). Criterion 7: PASS (above). Criterion 5 also: same model-call count and same worker call list with/without candidates (2 vs 2; retry path 3 calls/3 observes).
Stress test: không cần — the work is bounded (200 observed items x at most a few dozen quotes per check, 12 checks, 100-item output cap, in memory, one pass at session end); no query, lock, batch job or hot endpoint changed.

## Notes (do not block)
- N1 tiny quotes (measured): 1-char quotes (`1`,`3`,`a`,`o`) never matched inside a paragraph (0/4); whole-item match only. 2+ char quotes do match as fragments of a paragraph, by spec: `OK` equals a control name (control_name), `12` inside a paragraph (hit), `ok` matched inside `Book` and `OK` inside `TOKYO` (hits). So a 2-3 char quote can give a low-value candidate; `domain/verified_text.py:20` `FRAGMENT_MIN_CHARS = 2` is the knob (developer already marked it with a ponytail comment). Not a criterion 2 violation (the spec allows "nằm trong một mục page_text").
- N2 quote styles outside the three listed give no candidate: curly single `‘…’` and guillemets `«…»` (test `test_p10_quote_styles`). Harm is a missing candidate only; if the model uses `‘ ’`, the hit rate drops.
- N3 `domain/verified_text.py:22-27` pairing quirk: evidence `says "" and "x"` pairs the 2nd and 3rd double quote, so `and` is read as a quote (`test_p10_note_an_empty_quote_pair_...`). It can only make a junk candidate when that word also sits in a paragraph. Rare (model writes empty quotes).
- N4 accepted exception (user decision 2026-11-27): a typed value that the page shows (e.g. todo title) appears in `verified_text` (live: `Xoá Viết báo cáo` carries the typed title). A sensitive typed value cannot (R5, R6). The phase 08 "no typed value" scans do not cover `verified_text`; QA R4-R6 pin the exception explicitly.
- N5 dashboard: no TS test feeds a `verified_text` key through `validTaskAssessment`; evidence is typecheck + 56 tests + reading `vision-task-assessment-model.ts:49-52` (checks only `status`, `checks`, `facts`; no strict parse). Candidates are not rendered anywhere yet.
- `trace` JSON of a session without candidates still shows `"verified_text":null` (hash omits it) — developer already noted.

## Not tested
- Real dashboard rendering of the new key (nothing renders it); browser e2e not needed (no UI change).
- Real browser worker sensitive-word filtering (covered through contract validators `CodexPageTextItem`, not by driving the TS worker).
- Cross-run stability of the hit rate (1 run per task, as instructed).

## Process
Processes opened: none left running (no servers started; only one-shot commands). No product code or developer test edited; no commit. Files added: `tests/test_qa_p10_verified_text.py`, this report, `test-cases.md`.
