STATUS: DONE

CONTEXT_CHECK
- conventions: AGENTS.md, docs/code-standards.md (via hgraph brief), be-developer-r8.md, be-developer-r9.md, plan README handoffs r8/r9/r10-fix, benchmark/vision/accuracy/README.md, AGENT-LOOP-01-20261120.md (r6, r9). docs/api-conventions.md not read: no API change.
- graphs: not opened in full; hgraph brief for benchmark/vision/accuracy reported no graph covering the folder (folder, not an indexed file). No source file added or changed.
- blast radius: not applicable (no source change)

# Agent loop round 01 r10 - live A1+A3 with ADR-041

## Summary
One live agent_loop session, ended `agent_done`: a valid terminal, imported (iteration `396af7e4-11f9-4983-adea-180d37c768db`) and scored for five `--sources` combinations. ADR-041 worked live (0 `bridge_policy_revoked` in 14 jobs).
Official C 1/47, A 1/10, R 7/47 (with inventory). Gates not met. This is not an improvement over r6: the like-for-like r6 label/box number would be 5/47, but A1 shows 4 of those 5 clicks were made on non-oracle pages.

## Session
| Item | Value |
| --- | --- |
| Session | `22187cc7-4247-426b-83ec-446de3682f5c`, correlation `7ede4ae0-4102-487b-aa63-57cbb071ec25` |
| Iteration | `396af7e4-11f9-4983-adea-180d37c768db` (import, not qualification-eligible) |
| Terminal | state `unavailable`, `safe_failure_reason=agent_done` (model stop `complete`) = valid terminal |
| Time | about 3 min 19 s (09:27:55 to 09:31:14 UTC) |
| Bridge jobs | 14, all `completed`, 0 failed, 0 `bridge_policy_revoked`, 0 `Claude rejection` |
| Tokens | 72,096 in / 5,136 out, cached 24,233 (4,291 + 13 x 1,534) |
| Operations | 16, all completed: setup navigate 1, setup wait 1, click 10, back 1, close_popup 3 |
| Flags | loop, A1, A3 on (env checked in control-plane and temporal-worker); A2 off |

## Steps 1-2 preconditions
- `agent_loop_round.py check`: `mismatches: []`, compared control-plane 163, temporal-worker 163, claude-bridge 163, playwright-worker 49.
- `GET /vision/providers` claude_cli `bridge_readiness = {online: true, authenticated: true, capabilities_qualified: true, busy: false}`; policy `agent_loop`, `max_steps=20`. (The bridge container startup line still prints `online:false`, a startup print.)
- `mv agent-loop-session.json agent-loop-session.r9.json`, one `submit`: `202`, session `22187cc7...`, state `queued`. No second session.

## Step 3 ADR-041
Bridge log (since 30 min): `bridge_policy_revoked` 0, `Claude rejection` 0, control-plane / worker 0. DB `codex_bridge_jobs`: 14 rows `completed`, `safe_reason` null. In r9 job 2 died 2.2 s after creation; here jobs 2-14 (about 5-8 s each, 2-4 re-authorizations each) all survived. Live evidence consistent with the fix; it cannot prove the race is the only cause, but the failure that killed r9 did not recur in about 70 re-authorizations.

## Step 4 harness
`run.py import` -> `{"iteration_id": "396af7e4...", "state": "unavailable"}`; `collect` -> diagnosis `categories: [], reason: agent_done`; `detect` -> `{"identified": 7, "unexpected": 0, "inventory_complete": false}`; `evaluate` per `--sources all|none|click_context|inventory|click_context,inventory --label r10_<x>` through scratch script `score_r10.py` (calls `Loop.record_review`, `Loop.detect`, `Loop.evaluate`; official mode, one review: seq 2 -> mct-02).
Written: `runs/396af7e4.../{assessments,detection,detection.derived,detection.facts,score}.r10_*.json`, `review-eca7ec5a...json`; default artifacts (no label) are not created. Oracle `9242b33d...`, `metrics.py` (git diff clean), policy, prompt untouched.

## Official score
| `--sources` | C | A | P | R | inventory_complete | unsafe | passed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all | 1/47 = 2.13% | 1/10 = 10% | 7/7 | 7/47 | false | 0 | false |
| none | 1/47 | 1/10 | 0/0 (n/a) | 0/47 | false | 0 | false |
| click_context | 1/47 | 1/10 | 0/0 (n/a) | 0/47 | false | 0 | false |
| inventory | 1/47 | 1/10 | 7/7 | 7/47 | false | 0 | false |
| click_context,inventory | 1/47 | 1/10 | 7/7 | 7/47 | false | 0 | false |

Detection identified mct-01 to 06 and 11 (oracle page only), unexpected 0; incomplete (homepage `scrollable`, `skipped_count=9`).

## Manual review vs oracle (frames read through the harness, bytes verified)
Operation table (grounding + context): seq 2 link SU KIEN, page homepage (fp `a21c4cf7`); seq 3 button Tin Tuc on /su-kien; 4 Cam Nang on /tin-tuc; 5 Su Kien on /cam-nang; 6 Su Kien on /su-kien (url unchanged); 7 link DIEU KHOAN on /su-kien; 10 CONG DONG on /su-kien; 12 HO TRO on /su-kien; 15 CAM NANG on /su-kien; 16 TRANG CHU on /cam-nang. All scroll (0,0).
- seq 2: SU KIEN (box 0.381, 0.015, 0.113 x 0.051 = mct-02) opened /su-kien (title, highlighted nav, tabs). Correct, credited mct-02.
- seq 7 (Tepaylink Terms), 10 (Facebook group behind login dialog, not logged in), 12 (Tepaylink support center), 16 (homepage): functional, same label and box as mct-04, 05, 06, 01 but clicked on /su-kien or /cam-nang, so they are not those oracle controls; no credit (reviewer decision, recorded). Seq 15 CAM NANG nav (mct-03) likewise off-page.
- A1 value measured: diagnostic scratch run (`score_r10.py ... naive`, copy under the scratchpad, not in `runs/`, **not official**): tying the 4 off-page clicks to mct-04/05/06/01 gives `--sources none` C 5/47, A 5/10 (harness accepts, cannot tell the page), `--sources click_context` refused `assessment binding does not match oracle (off_page_url)`. So A1 turns a false 5/47 (the r6 style) into the honest 1/47.

## Inventory (A3) real
`/result` `pages` = 14 states (about 30 KB): homepage 7 controls (skipped 9 `multiple_matches`), /su-kien, /tin-tuc, /cam-nang 11 each (skipped 2), Facebook 5 (skipped 17, not scrollable), id.tpl.vn/rules 3, support.tpl.vn 1 (skipped 3). `truncated=false` everywhere (cap 100). DB `visual_exploration_states.page_inventory` about 1.8-2.8 KB each.

## Step 5 state_mismatch
1 event (worker, 09:30:30.129, `dom_observation`, `failure_stage=observe_start`): after click seq 12 (HO TRO) opened support.tpl.vn, `interaction_count 56 -> 57`, `interaction_content_added=1`, `interaction_changed_tags {IMG:1}`, geometry-only 0, `state_age_ms=345`, `url_changed=false`, `scroll_changed=false`, forms unchanged. Recovered: seq 13 setup `wait` (refresh) then seq 14 `close_popup`. Drift element = an `IMG` added to an external page (lazy image), fingerprint scope `all`. The r6 homepage-after-scroll drift did not occur (the model never scrolled), so that question stays open. Gate unchanged.

## Comparison
| Run | Steps / clicks | Terminal | C | A | R | Note |
| --- | --- | --- | --- | --- | --- | --- |
| r6 | 20 / 12 (8 ok, 4 rejected) | agent_stopped | 5/47 (ADR-039, no page check) | 5/12 | 0/47 | 6 homepage `state_mismatch`, 107,235 in tokens |
| r9 | 2 jobs / 1 click | bridge_policy_revoked | 1/47 diagnostic | 1/1 | 7/47 diagnostic | not valid |
| r10 | 14 / 10 (all ok) | agent_done | 1/47 (page-checked) | 1/10 | 7/47 | 72,096 in tokens, 1 mismatch recovered |
Not like for like. No improvement claimed: C and A fell because the evidence is stricter and the agent mostly clicked off-page; R rose only due to A3 inventory. K1 not met (14 calls, 1 target). runtime verdict `partial`/`inventory_limited` unchanged.

## Findings
- Agent behaviour, not the harness, is now the cap: after the first click it stayed on /su-kien, /tin-tuc, /cam-nang, tested shared header links there, never scrolled, and stopped `complete` with 9 below-fold homepage controls skipped in its own inventory; 46 of 47 oracle targets untouched (31 are below the fold, 15 unnamed).
- A1 works and is decisive for honest scoring; A3 gives detection (P 7/7, R 7/47) but cannot reach complete inventory unless the agent scrolls (the observation lists skipped controls).
- Possible cause of the early stop (hypothesis): prompt has no rule to return to the homepage or to scroll when `skipped` > 0; not verified in prompt text in this round (prompt untouched).

## Risks
- The single approved live session is consumed; the next valid score needs a new user decision.
- Writes outside plain scope: scratch directory scripts/frames/diagnostic copy under the session scratchpad, `.pytest-artifacts/agent-loop-r10-*.json` and `agent-loop-session.r9.json` rename. Untracked `runs/396af7e4.../` and the earlier `runs/1c56623e.../` are in the working tree, no commit.
- r10 official artifacts include 5 labelled evaluations only; no default `score.json` (labels carry the result).

## Stack
control-plane, temporal-worker, claude-bridge, playwright-worker, dashboard, rustfs, temporal, temporal-postgres, postgres, redis all up. No temporary process, container or session left. Bridge token refreshed 16:02 (about 5 h left). Not rebuilt, not stopped.

## Recommendations (proposals only)
1. Prompt/policy change (needs approval and prompt version bump): keep the agent on the oracle page set, return to the homepage after each external page, scroll when `scrollable` and `skipped_count>0`, and do not stop while the oracle page has skipped controls. Then one live session with A1+A3 (same flags) to measure the effect against r10 (1/47, R 7/47).
2. A2 (`VISION_AGENT_DOM_PATH_ENABLED`): only after (1) or together as the single A1+A2+A3 run; it addresses only the 15 unnamed targets and needs the agent to reach them. Not run here.
3. Optional separate round: investigate homepage `state_mismatch` after scroll once the agent scrolls (needs `vision.state.mismatch` data from a scrolling run).

## Files changed
- `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md` (section r10 appended)
- `plan/09112026103202-vision-accuracy-loop/README.md` (handoff r10 live appended)
- `benchmark/vision/accuracy/runs/396af7e4-11f9-4983-adea-180d37c768db/` (harness output)
- `.pytest-artifacts/agent-loop-r10-{trace,result,locators}.json` (read-only dumps)
- this report and `.log`

GRAPH_UPDATE
- graph đã cập nhật: không cần — không thêm/xoá file source, không đổi import
- file mới đã đưa vào graph: không có
- hgraph check --changed: not run (no source change; known git-root prefix tooling issue recorded in r7/r8)
