STATUS: DONE

CONTEXT_CHECK
- conventions: AGENTS.md, docs/code-standards.md (hgraph brief), be-developer-r10.md, be-developer-r11.md, benchmark/vision/accuracy/README.md, AGENT-LOOP-01-20261120.md, plan README handoffs. docs/api-conventions.md not read: no API change.
- graphs: hgraph brief for benchmark/vision/accuracy reported no graph covering the folder. No source file added or changed.
- blast radius: not applicable (no source change)

# Agent loop round 01 r12 - live A1+A3, prompt agent-loop-v2

## Summary
One live agent_loop session ended `unavailable` / `settle_timeout` after about 1 min 33 s: a worker page-readiness outcome, not an agent terminal (`agent_done` / `agent_stopped`). Per the instructions it was NOT imported into `runs/`; only a diagnostic in a scratch directory. No official score. Prompt v2 clearly changed the behaviour (scroll, all clicks on the oracle page); the worker settle rule stopped the run, not the model.

## Session
| Item | Value |
| --- | --- |
| Session | `e0de6697-ed86-4418-8d8d-f3bc4922e36a`, correlation `196104d1-0504-4681-97bf-7d23dd6b5099` |
| Terminal | `unavailable`, `safe_failure_reason=settle_timeout` (diagnosis category `capture_or_readiness`, ops aeb15992 explore scroll and 46367803 setup wait), invalid terminal |
| Time | 10:37:38 to 10:39:11 UTC |
| Bridge jobs | 5, all `completed`, 0 failed, 0 `bridge_policy_revoked`, 0 `Claude rejection` (bridge, control-plane, temporal-worker, playwright-worker logs) |
| Tokens | 27,976 in / 2,598 out, cached 6,136 (4 x 1,534) |
| Calls | 5 of 20 |
| Operations | 9: setup navigate 1 ok, scroll 2 (1 ok, 1 failed settle_timeout), click 5 ok, setup wait 1 rejected settle_timeout |
| Flags | loop, A1, A3 on; A2 off (as prepared by the coordinator) |

## Steps
1. `GET /vision/providers`: `claude_cli` `online=true, authenticated=true, capabilities_qualified=true, busy=false`.
2. `agent_loop_round.py check`: `mismatches: []` (163/163/163/49). `PROMPT_VERSION = "agent-loop-v2"` in claude-bridge container (`agent_loop.py:21`). `mv agent-loop-session.json agent-loop-session.r10.json`; one `submit`: `202`, session `e0de6697...`. No second session. Polled to terminal with a 10 s loop.
3. Prompt version: the job table has no prompt column and the bridge log does not print it. Evidence is indirect: bridge `PROMPT_BUILDERS` (codex_bridge_cli.py:21-24) contains only the current builders and raises `unsupported bridge prompt version` otherwise; `agent_loop.py:115` refuses a request whose version is not v2; all 5 jobs completed. Prompt v1 is not in the container.
4. Invalid terminal: `run.py import` with `--directory` pointing at the scratchpad (`r12runs`), iteration `bbdac7f0-ec45-4286-8102-b6ffe600dd11`; `collect` -> diagnosis `capture_or_readiness / settle_timeout` x2, `missing_evidence_operations` [46367803...], `physical_retry_authorized=false`; `detect --sources all` -> `{"identified": 14, "unexpected": 21, "inventory_complete": false}`; scoring through scratch `score_r12_diag.py` (strict and lenient review sets, five `--sources` combinations each). Nothing was written to `benchmark/vision/accuracy/runs/` (`git status` shows only the pre-existing untracked 1c56623e and 396af7e4). Oracle, `metrics.py`, thresholds, policy, prompt untouched.

## Behaviour (prompt v2 versus r10)
- Returned to the starting page: not applicable, the model never left the homepage (every click and the scroll have `url_fingerprint a21c4cf7...` = oracle page). In r10 it left after click 1.
- Scroll: first action after navigate was `scroll` (seq 2, completed, `scroll_y=600`); then 5 clicks at `scroll=(0,600)`; a second `scroll` (seq 8) failed `settle_timeout`. Total scroll ops 2 (1 completed).
- Final homepage inventory: `scrollable=true`, `skipped_count=12` (4 states, all homepage: 21, 14, 14, 14 controls, `truncated=false`). The model did not get to a `complete` decision; the worker ended the session.
- `state_mismatch`: 1 (worker `vision.state.mismatch`, `dom_observation`, 10:39:01.127, `observe_start`), between the two settle failures: `interaction_count 18 -> 18`, added 0, removed 0, `interaction_geometry_only=1`, no changed tags, `url_changed=false`, `scroll_changed=false`, forms unchanged, `state_age_ms=216`. Drift = a single interactive control whose geometry changed (element not identified in the log). Gate not changed.
- `settle_timeout` x2: op 8 `state_kept_changing`, 53 state changes in 10 s, 2 visible DOM/layout changes, 0 URL, longest stable 236 ms (needs 800); op 9 51 changes, 0 visible, longest stable 266 ms. The page keeps changing after scroll and tab clicks (animated widgets, hypothesis not isolated).
- `bridge_policy_revoked`: 0.

## Frame review (diagnostic)
Each click's viewport box + scroll 600 equals an oracle box: seq 3 Su Kien -> mct-19 (799, 831), seq 4 Cam Nang -> mct-20 (947, 831), seq 5 NHAN VAT -> mct-30 (491, 1273), seq 6 THU CUOI -> mct-31 (643, 1273), seq 7 Tin Tuc -> mct-18 (650, 831). Frames read through `Loop.frame` (checksums verified): seq 3, 4, 7 the tab becomes active and its list is visible (correct). Seq 5: NHAN VAT already active, after frame equals before (checksum d1a58d3a both). Seq 6: THU CUOI active, NHAN VAT inactive. For 5 and 6 the matching panel is below the viewport, so "matching content is visible" is not shown: strict reading does not credit them, lenient reading does. Oracle rule: already-active selection permitted.

## Diagnostic score (not official, invalid terminal, scratch dir)
| reading | `--sources` | C | A | P | R |
| --- | --- | --- | --- | --- | --- |
| strict | all | 3/47 = 6.38% | 3/5 = 60% | 14/35 | 14/47 |
| strict | none | refused `no_oracle_match` | - | - | - |
| strict | click_context | 3/47 | 3/5 | 0/0 | 0/47 |
| strict | inventory | refused `no_oracle_match` | - | 14/35 | 14/47 |
| strict | click_context,inventory | 3/47 | 3/5 | 14/35 | 14/47 |
| lenient | all | 5/47 = 10.64% | 5/5 | 14/35 | 14/47 |
| lenient | none, inventory | refused `no_oracle_match` | - | - | - |
| lenient | click_context | 5/47 | 5/5 | 0/0 | 0/47 |
| lenient | click_context,inventory | 5/47 | 5/5 | 14/35 | 14/47 |
passed=false, unsafe 0, inventory incomplete (scrollable, skipped 12). Detection identified: mct-01 to 06, 11, 18, 19, 20, 30, 31, 37, 43; unexpected 21 (inventory controls with no oracle match, e.g. article links), so P 14/35.
A1 value: without scroll offset the scrolled clicks cannot bind (`no_oracle_match`).

## Comparison
| Run | C | A | P | R | Clicks | Scroll | Calls | Terminal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| r6 | 5/47 (ADR-039, no page check) | 5/12 | n/a | 0/47 | 12 (8 ok) | 2 | 20 | `agent_stopped` valid |
| r9 | 1/47 diag | 1/1 | 7/7 diag | 7/47 diag | 1 | 0 | 2 | `bridge_policy_revoked` invalid |
| r10 | 1/47 official | 1/10 | 7/7 | 7/47 | 10 (1 on oracle page) | 0 | 14 | `agent_done` valid |
| r12 | 3/47 strict, 5/47 lenient (diag) | 3/5, 5/5 | 14/35 | 14/47 | 5 (all on oracle page) | 2 (1 failed) | 5 | `settle_timeout` invalid |
Official versus estimate: only r6 (5/47 without page check) and r10 (1/47) are official valid-terminal numbers; r9 and r12 are diagnostics. No improvement is claimed: r12 has no valid terminal. The only claim the data supports is behavioural (v2 scrolls and stays on the oracle page).

## Findings
- Prompt v2 works as designed on the two behaviours asked for: scroll early, stay on the oracle page. 5 calls produced 5 distinct oracle targets (r10: 14 calls, 1 target).
- New blocker: the worker settle rule (`state_kept_changing`) on the homepage after scroll/tab clicks ended the session at 5 of 20 calls; the recovery wait also timed out because the page never has an 800 ms quiet window. Same class as r6 homepage drift, now the primary cap.
- A1 is required for any below-the-fold credit; A3 inventory shows 14 identified but also 21 unmatched controls (precision 40%).
- 12 controls still skipped on the homepage; every scrolled viewport reports 12 skipped (the model-visible "skipped" count stays high wherever it scrolls).

## Risks
- The single approved session is consumed; a valid terminal needs a new decision.
- `settle_timeout` may recur on any homepage run; retrying without a worker/policy decision would reproduce it. Loosening settle must not be done silently (gate).
- Strict versus lenient review differ (3 vs 5); a reviewer rule on "matching content visible" for tabs whose panel is below the frame needs a decision before a valid run is scored.
- Writes beyond the plain scope: scratch scripts/frames/`r12runs` under the session scratchpad; `agent-loop-session.r10.json` rename; `.pytest-artifacts/agent-loop-r12-*.json` dumps. No source change; the `runs/` directory untouched by this round.

## Stack
control-plane, temporal-worker, claude-bridge, playwright-worker, dashboard, rustfs, temporal, temporal-postgres, postgres, redis up (not rebuilt, not stopped). No temporary process or container left. Bridge token valid to about 22:00.

## Recommendations (proposals only)
1. Decide how to handle homepage `settle_timeout` after scroll/click (worker rule: ignore geometry-only/animation changes below a threshold, or a bounded retry with a longer quiet window for the recovery wait) without weakening the stability gate; needs a user/ADR decision and rebuild of playwright-worker, then one new live A1+A3 session.
2. A2 (`VISION_AGENT_DOM_PATH_ENABLED`) after (1): targets the 15 unnamed controls; run as a separate session so A1+A3 effect stays comparable.
3. Decide the tab-outcome rule (content below the frame) for scoring.

## Files changed
- `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md` (section r12 appended)
- `plan/09112026103202-vision-accuracy-loop/README.md` (handoff r12 appended)
- `.pytest-artifacts/agent-loop-r12-{trace,result,locators}.json`, `.pytest-artifacts/agent-loop-session.json` (r12), `.pytest-artifacts/agent-loop-session.r10.json`
- this report and `.log`

GRAPH_UPDATE
- graph đã cập nhật: không cần — không thêm/xoá file source, không đổi import
- file mới đã đưa vào graph: không có
- hgraph check --changed: not run (no source change)
