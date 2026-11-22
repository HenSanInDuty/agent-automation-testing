STATUS: FAIL

CONTEXT_CHECK
- conventions: AGENTS.md, docs/code-standards.md (hgraph brief), be-developer-r12/r16/r18 (full), plan README handoffs (tail), AGENT-LOOP-01-20261120.md (r10, r12, r16 sections), benchmark README harness section. r14b / r17 / ADR-042 not re-read in full (context taken from r18 and the README handoffs). docs/api-conventions.md not applicable (no API change).
- graphs: hgraph brief for benchmark/vision/accuracy: no graph covers the folder. No source touched.
- blast radius: not applicable (no source change)

# Agent loop round 01 r19 - live A1+A3, prompt v2, ADR-042, r18 tsx fix

## Summary
The one approved live session opened (the r18 fix works live) and ran 14 operations, but ended `unavailable` / `settle_timeout`: a worker page-readiness outcome, not a valid agent terminal. Per the instructions it was NOT imported into `runs/`; diagnostic only in a scratch directory. No official score. ADR-042 helped (6 clicks and a scroll settled where r12 failed) but the page top after scrolling back still never settles. No second session was created.

## Session
| Item | Value |
| --- | --- |
| Session | `6eef105a-ae98-44cf-9b09-e5a6d0ad1262`, correlation `5075d594-b471-49d7-8366-4583bb4fc797` |
| Terminal | `unavailable`, `safe_failure_reason=settle_timeout` (invalid terminal) |
| Time | submit 20:53 local (13:53:17 UTC first op), last op 13:55:38 UTC (about 2 min 20 s) |
| Bridge | 8 proposals (`agent_step`, 0 schema rejections), 8 of 20 calls, 0 `bridge_policy_revoked`; token counts not collected (no safe read path used) |
| Flags | loop, A1, A3 on; A2 off |
| Operations | 14: navigate 1; scroll 3 (seq 2 ok, 9 failed `settle_timeout`, 12 rejected `state_mismatch`); click 6 (all completed); wait 4 (10, 11 ok; 13 rejected `state_mismatch`; 14 setup rejected `settle_timeout`) |
| Frames | 22 retained, 6 missing (rejected ops) |

## Steps and outputs (abridged)
1. 20:51-20:52: `GET /vision/providers` x4 at 20 s intervals: `claude_cli` `online=true, authenticated=true, capabilities_qualified=true, busy=false`, stable over 60 s.
2. `agent_loop_round.py check`: `mismatches: []` (163/163/163/56).
3. `mv agent-loop-session.json agent-loop-session.r16.json`; one `submit`: `202`, session `6eef105a...`, `max_steps=20`, `max_session_seconds=120`. Polled to terminal (`running` 20:53:21, `unavailable settle_timeout` 20:55:43). Dumps `.pytest-artifacts/agent-loop-r19-{trace,result,locators}.json` (58,172 / 24,774 / 5,048 bytes).
4. Invalid terminal: `run.py import --directory <scratch r19runs>` -> iteration `8ba0e586-c07e-4a37-8761-eddf33aca298`, state `unavailable`; `collect` -> diagnosis `capture_or_readiness/settle_timeout` x2 (ops cb145ad0 scroll, 6a4c42ee setup wait), `state_drift_stage_unavailable/state_mismatch` x2, `missing_evidence_operations` 3; `detect --sources all` -> `{"identified": 14, "unexpected": 21, "inventory_complete": false}`. Scoring via scratch `score_r19_diag.py` (copy of the r12 diagnostic script with the r19 review table). `git status` of `runs/`: only the two pre-existing untracked dirs (1c56623e, 396af7e4).

## Monitoring items
| Item | Result |
| --- | --- |
| `settle_timeout` / `state_kept_changing` (ADR-042 live) | 2. First at scroll seq 9 right after the TOP click (page at top): 52 changes in 10 s (14 visible, 0 URL, 1 scroll), longest stable 240 ms (needs 800). Second at setup wait seq 14: 52 changes (9 visible), longest stable 353 ms. All 6 clicks and the first scroll (page at y=600, pulsing play-now link visible) settled: ADR-042 worked there |
| scroll | 3 issued: seq 2 ok (`scroll_y=600`); seq 9 failed; seq 12 rejected (`state_mismatch`). Agent never went below y=600 |
| `state_mismatch` (`vision.state.mismatch`) | 4. observe_start 275 ms after failed scroll (geometry_only=1); dom_collection 654 ms (geometry_only=3, visual_semantics_changed=true); prepare_start x2, state_age 7.5 s / 20.6 s (geometry_only=3). All: 18 controls, 0 added, 0 removed, no tag change, no URL/scroll change; drifting controls are not named in the log |
| force click | none (no force indication in worker log or trace) |
| `unexpected_error` | 0 |
| calls / cap | 8 / 20 |
| `bridge_policy_revoked` | 0 |
| return to start page | not applicable: every click is on the oracle page (`url_fingerprint a21c4cf7...`); never left |
| final skipped_count | 8 inventory states, all homepage, `scrollable=true`; skipped 12 while scrolled, 9 at top; not truncated |

## Click review (frames read through the harness, checksums verified by `Loop.frame`)
Each click's viewport box + scroll 600 equals an oracle box exactly (grounding.json, oracle `reference_box`):
| seq | control | oracle | before -> after | outcome |
| --- | --- | --- | --- | --- |
| 3 | Su Kien tab | mct-19 | b281e675 -> 72bbb288 | tab active, event list visible: correct |
| 4 | Cam Nang tab | mct-20 | 72bbb288 -> d1a58d3a | tab active, guide list visible: correct |
| 5 | Tin Tuc tab | mct-18 | d1a58d3a -> b281e675 | tab active, news list visible: correct |
| 6 | NHAN VAT | mct-30 | b281e675 -> b281e675 | already active, frame unchanged, panel below frame: strict not credited, lenient credited |
| 7 | THU CUOI | mct-31 | b281e675 -> 3c07dc6e | tab active, panel below frame: strict not credited, lenient credited |
| 8 | TOP (fixed back-to-top) | none (box 1184,1070 matches no oracle control) | 3c07dc6e -> e09ea5d1 (= initial top frame) | page scrolled to top; counted as attempted, not credited |

Safety invariant (click landing on a control other than the intended one): none observed. All 6 locators are verified `role=button` with name and box equal to the intended control and the after frames show the expected effect. The r14 covered-control debt (a visible control covering the target) was not exercised; this run neither proves nor disproves it.

mct-30/31 graded strictly under the rule in force (matching content visible); lenient shown separately.

## Diagnostic score (NOT official; invalid terminal; scratch dir)
| reading | `--sources` | C | A | P | R |
| --- | --- | --- | --- | --- | --- |
| strict | all, click_context,inventory | 3/47 = 6.38% | 3/6 | 14/35 | 14/47 |
| strict | click_context | 3/47 | 3/6 | 0/0 | 0/47 |
| strict | none, inventory | refused `no_oracle_match` | - | - | - |
| lenient | all, click_context,inventory | 5/47 = 10.64% | 5/6 | 14/35 | 14/47 |
| lenient | click_context | 5/47 | 5/6 | 0/0 | 0/47 |
| lenient | none, inventory | refused `no_oracle_match` | - | - | - |
passed=false, unsafe 0, inventory incomplete. Identified: mct-01 to 06, 11, 18, 19, 20, 30, 31, 37, 43; 21 unmatched controls (article links).

## Comparison
| Run | C | A | P | R | Clicks | Scroll | Calls | Terminal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| r6 | 5/47 official (no page check) | 5/12 | n/a | 0/47 | 12 (8 ok) | 2 | 20 | `agent_stopped` valid |
| r10 | 1/47 official | 1/10 | 7/7 | 7/47 | 10 (1 on oracle page) | 0 | 14 | `agent_done` valid |
| r12 | 3/47 strict, 5/47 lenient (diag) | 3/5, 5/5 | 14/35 | 14/47 | 5 | 2 (1 failed) | 5 | `settle_timeout` invalid |
| r19 | 3/47 strict, 5/47 lenient (diag) | 3/6, 5/6 | 14/35 | 14/47 | 6 (5 oracle targets + TOP) | 3 (1 ok) | 8 | `settle_timeout` invalid |
Official: only r6 and r10. r19 equals r12 on C/P/R. No improvement is claimed; no regression either. The data supports only: open works (r18), ADR-042 lets clicks and a scroll at y=600 settle, but the top of the homepage after scrolling back still does not settle.

## Findings
- The r18 fix works live: open succeeded, 0 `unexpected_error`.
- ADR-042 is effective for the r12 failure (settling after tab clicks at y=600) but not for the page top reached via TOP/scroll back: 52 changes in 10 s, geometry-only drift of 1-3 controls, so it still caps the session. Cause not isolated (not the pulsing play-now link alone; at the top other animated widgets such as the hero/swiper are the hypothesis).
- The agent batched 3 clicks per step (seq 6-8 in step 5), clicked the back-to-top button (TOP) which resets scroll and starts the unstable top state; it then wanted to scroll further for the 9-12 remaining controls and never got a stable state. It did not click the WINDOW link on purpose (download risk): reasonable.
- After a settle failure the held state ages (7-20 s) and the next prepare is rejected `state_mismatch`, so recovery waits do not rescue the session while the page keeps drifting.

## Risks
- The approved session is consumed; a valid terminal needs a new user approval.
- A rerun without a worker decision will probably hit the same top-of-page settle failure.
- TOP clicks cost A (counted as attempted, not creditable).
- Oracle, `metrics.py`, thresholds, policy, prompt untouched; no source change.

## Stack
control-plane, temporal-worker, claude-bridge, playwright-worker, dashboard, rustfs, temporal, temporal-postgres, postgres, redis up (12 containers; not rebuilt, not stopped). No process of mine left (poll script finished). Bridge token valid to about 22:10.

## Recommendations (proposals only)
1. Offline diagnosis of the top-of-page settle (probe the live homepage after scroll-to-top for what changes: geometry-only hits per control and which animation), then extend ADR-042 or a bounded recovery; needs a user decision/ADR.
2. Prompt/policy question: discourage the agent from clicking the fixed TOP control (scroll reset), or accept it as attempted-but-unscored.
3. Then one new approved live run; A2 stays a separate session.

## Files changed
- `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md` (r19 section appended)
- `plan/09112026103202-vision-accuracy-loop/README.md` (handoff r19 appended)
- `.pytest-artifacts/agent-loop-r19-{trace,result,locators}.json`, `.pytest-artifacts/agent-loop-session.json` (r19), `.pytest-artifacts/agent-loop-session.r16.json` (renamed)
- this report and `.log`
- scratch only (scratchpad): `poll19.py`, `ops19.py`, `frames19.py`, `map19.py`, `score_r19_diag.py`, `r19runs/`, `r19-*.png`, `diag19-*.out`, `playwright-worker.log`, `claude-bridge.log`

GRAPH_UPDATE
- graph đã cập nhật: không cần — không thêm/xoá file source, không đổi import
- file mới đã đưa vào graph: không có
- hgraph check --changed: not run (no source change)
