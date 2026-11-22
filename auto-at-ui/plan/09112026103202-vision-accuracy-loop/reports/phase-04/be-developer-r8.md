STATUS: ESCALATE

CONTEXT_CHECK
- conventions: AGENTS.md, docs/code-standards.md (via hgraph brief), docs/vision-agent-operations.md (agent loop + ADR-040 flags), benchmark/vision/accuracy/README.md, docs/adr/040-agent-loop-accuracy-evidence-flags.md, AGENT-LOOP-01-20261120.md (r1-r6a), plan README handoffs r6/r7/r8. docs/api-conventions.md not read (no API change in this live round).
- graphs: vision-agent-loop and vision-accuracy-harness not opened in full (no file added or changed by this round); hgraph brief for benchmark/vision/accuracy reported "no graph covers the folder" (the path is a folder, not an indexed file).
- blast radius: not applicable (no source file touched).

# Agent loop round 01 r9 (internal label "r8 live") - A1+A3 live session

## Summary

The single approved live agent_loop session ran for 40 s and ended `unavailable` / `bridge_policy_revoked`: the Claude bridge itself stopped model job 2, 2.2 s after it started.
It is not a valid agent terminal (AC6 not met), so it was not imported into `runs/` and has no official score. It is still the first live proof that A1 (click context) and A3 (inventory) work.
No source, oracle, `metrics.py`, policy, prompt or verdict was changed. No second session was created.

## Session

| Item | Value |
| --- | --- |
| Session id | `79b90323-e05f-474e-9ca7-6f66993995f2` (correlation `2b33b62c-ff00-4544-9d4c-135c15a37b1f`) |
| Params | project `8f2d5531...`, target mongchiton.vn, same task/policy as r1-r6, `max_steps=20`, step timeout 120 s, fingerprint `5408692c...` |
| Engine / model | `agent_loop` / `claude_cli` `claude-opus-5-5` |
| Flags | loop, A1, A3 on (control-plane and temporal-worker env checked); A2 off |
| Terminal | state `unavailable`, reason `bridge_policy_revoked` (not in {agent_done, agent_stopped, agent_step_limit, session_timeout}) |
| Wall time | about 40 s (09:04:11 to 09:04:46 UTC) |
| Bridge jobs | 2: job 1 completed (4,655 in / 289 out, cached 0, about 9 s); job 2 failed `bridge_policy_revoked`, no usage, 0 schema rejections |
| Operations | 2: seq 1 setup navigate (completed); seq 2 explore click `1:2` SU KIEN (completed, `url_change=changed`, batch stopped by `url_change`) |
| Step log | 1 row. Blocked actions by code: 0. `sensitive_action_blocked`: 0. `vision.state.mismatch` in worker log: 0 |

## Step 1 - preconditions (evidence)

- `agent_loop_round.py check`: `compared {control-plane 163, temporal-worker 163, claude-bridge 163, playwright-worker 49}`, `mismatches: []`.
- Bridge: container up; `GET /api/v1/vision/providers` `claude_cli.bridge_readiness = {configured: true, online: true, authenticated: true, capabilities_qualified: true, busy: false}`. (The `online:false` in the bridge container's startup line is a startup status print, the control-plane readiness read was true.)
- `GET /api/v1/vision/policy`: `agent_loop_enabled=true`, `max_steps=20`, `max_session_seconds=120`, fingerprint `5408692c...`.
- `mv .pytest-artifacts/agent-loop-session.json .pytest-artifacts/agent-loop-session.r6.json`, then exactly one `uv run python .pytest-artifacts/agent_loop_round.py submit`: `202 ... "id":"79b90323-...","state":"queued"`.

## Why the session ended (finding, not fixed)

`bridge_policy_revoked` came from the bridge (claude-bridge log, `Claude rejection {"job_id":"94fa2b90-...","phase":"stream","code":"bridge_policy_revoked","schema_rejections":0}` at 09:04:46.18). The control-plane logged no `codex.handoff.failed`; the DB job row is `failed` with the same safe reason.

- `apps/control-plane/infrastructure/codex_bridge/spool.py:371-400` (`FileSpool.stop_reason`) returns `bridge_policy_revoked` if `authorization.json` is missing or `recorded_at <= now < authorization_expires_at <= deadline` or the ttl rule fails.
- `apps/control-plane/application/codex_bridge.py:72`: the bridge calls `stop_reason(req, datetime.now(UTC))` every 0.1 s during streaming; `now` is evaluated before the file is read.
- `apps/control-plane/infrastructure/vision/codex_batch.py:126-130`: the control plane rewrites `authorization.json` every 2 s (`spool.py:339`: `recorded_at=datetime.now(UTC)`; the write is atomic `os.replace`).
- Hypothesis: a receipt written between the bridge's `now` and its read has `recorded_at > now` and is classed as revoked. Evidence for it: the failure came 2.2 s after job creation (first re-authorization after the initial one); r5 (11 jobs) and r6 (20 jobs) never hit it, so the window is thin. Not proven: the spool folder of the job is already gone, so a missing/expired receipt cannot be excluded.
- Not caused by A1/A3: neither flag changes the bridge or the authorization path; job 2 was a normal DOM job (the DOM sent was the su-kien page).
- Proposed fix (not applied, source out of scope): take `now` after reading the receipt (or allow small clock skew) in `stop_reason`, and add a test that rewrites the receipt while `stop_reason` is polling; rebuild control-plane, temporal-worker, claude-bridge.

## A1 and A3 findings (first live data)

- **A1 negotiated and worked.** Session opened without `worker DOM capability unavailable`. The click operation `d65a15cf-ce10-48aa-91bd-c038e813b6de` carries `executed_click`: `x=0.4386, y=0.0422, viewport 1280x720, scroll_x=0, scroll_y=0, url_fingerprint=a21c4cf7e5975779dd3a0dd2a618726df7dab4587ee0547fbcd9f242b0c11687`, equal to `sha256("https://mongchiton.vn/")` (oracle `source_url`).
  The setup navigate carries `executed_click: null` (as designed).
- **A3 worked.** `/result` `pages` (2 states): `https://mongchiton.vn/` 7 controls (TRANG CHU, SU KIEN, CAM NANG, DIEU KHOAN, CONG DONG, HO TRO, TREN WINDOW), `scrollable=true`, `truncated=false`, `skipped_count=9` (`multiple_matches`);
  `https://mongchiton.vn/su-kien` 11 controls (6 header links, tab buttons Tin Tuc / Su Kien / Cam Nang, 2 event links), `scrollable=true`, `truncated=false`, `skipped_count=2` (`no_grounded_locator`). Real inventory size is tiny versus the 100-control cap, no truncation.
  The model memory in step 1 says "9 controls are below the visible area" (the 9 skipped). Runtime conclusion unchanged: `partial`, `observed_controls=18`, `completed_controls=0`, `inventory_limited=true`.
- Click review (independent, frame bytes read through the harness): the SU KIEN header link (role locator, box x=0.381 y=0.015 w=0.113 h=0.051, equals oracle mct-02) opened `/su-kien` (SU KIEN title, nav item highlighted, tabs Tin Tuc / Su Kien / Cam Nang visible). Correct.

## Official scores vs diagnostic

Official harness score: **none**. The session is not a valid terminal, so it was not imported into `benchmark/vision/accuracy/runs/` (same rule as r3-r5), and `runs/` was not touched (`git status` shows only the pre-existing r6 folder as untracked).

Diagnostic run (not a benchmark score): `run.py import/collect/detect` plus a scratchpad script calling `Loop.evaluate` with one reviewed click (mct-02 correct) for every `--sources` value, in a scratch directory
(`...\scratchpad\r9runs\c5d666f0-a73d-4810-9042-d24ca6f972ec`, script `...\scratchpad\score_r9_diag.py`). Its only purpose is to prove the harness consumes the new evidence.

| `--sources` | C | A | P | R | inventory_complete | passed |
| --- | --- | --- | --- | --- | --- | --- |
| all | 1/47 | 1/1 | 7/7 | 7/47 | false | false |
| none | 1/47 | 1/1 | 0/0 (n/a) | 0/47 | false | false |
| click_context | 1/47 | 1/1 | 0/0 (n/a) | 0/47 | false | false |
| inventory | 1/47 | 1/1 | 7/7 | 7/47 | false | false |
| click_context,inventory | 1/47 | 1/1 | 7/7 | 7/47 | false | false |

- Detection `identified_ids`: mct-01 to mct-06 and mct-11, `unexpected_paths` 0 (oracle page only; the su-kien page is not counted). Incomplete because the page is scrollable and 9 controls were skipped.
- `grounding.json` `contexts` is present with the one click; click credit is identical with and without it (the target is in the first viewport, role rule binds it as in r6a). A1 would matter only for below-the-fold clicks, none reached.

## Comparison with r6 (C 5/47, A 5/12, detection R 0/47)

Not comparable: r6 ran 20 model steps and 12 attempted clicks; r9 ran 1 click. No claim that C, A, P or R improved. The only substantive change is that detection can now be derived (7 identified, P 7/7, R 7/47, incomplete) where r6 had `pages=[]` and R 0/47.
Not measured in r9: whether `click-context-v1` helps credit below-the-fold targets, the homepage `state_mismatch` drift after scroll (no state_mismatch occurred, so the `vision.state.mismatch` diagnostic still has nothing to say about which element drifts), K1, 20-call sufficiency, behaviour of the agent with A2. `partial`/runtime verdict untouched.

## Risks

- The remaining live-session approval is used (one session); the next valid score needs a user decision.
- The `stop_reason` race, if confirmed, can hit any live run (agent_loop and planner); frequency looks low (1 of about 33 jobs across r5, r6, r9) but a 20-step session has about 100 re-authorizations.
- This report cites a root cause as a hypothesis; confirming it needs the spool folder or a unit test, both out of scope here.
- Writes outside the listed scope: `.pytest-artifacts/agent-loop-r9-{trace,result,locators}.json` (read-only API dumps in the untracked scratch folder already used by every round) and the scratchpad harness directory. No repo source file changed.

## Commands (condensed output)

- `uv run python .pytest-artifacts/agent_loop_round.py check`: `mismatches: []` (163/163/163/49).
- `submit`: `202 {"id":"79b90323-e05f-474e-9ca7-6f66993995f2","state":"queued",...}`.
- poll: `0 ('running', None)`, `40 ('unavailable', None)`; `safe_failure_reason=bridge_policy_revoked`.
- `psql codex_bridge_jobs`: seq 1 dom completed (4655/289); seq 2 dom failed `bridge_policy_revoked` (09:04:43.98 to 09:04:46.45).
- `run.py --directory <scratch> import --original 79b90323-... --oracle benchmark/vision/accuracy/oracle-mongchiton-1280-v1.json --policy .pytest-artifacts/accuracy-local-policy-claude.json`: `{"iteration_id": "c5d666f0-...", "state": "unavailable"}`; `collect`: diagnosis `model_or_provider / bridge_policy_revoked`; `detect`: `{"identified": 7, "unexpected": 0, "inventory_complete": false}`.
- `git diff --quiet -- metrics.py oracle-mongchiton-1280-v1.json`: exit 0 (unchanged).
- `docker ps`: control-plane (healthy), temporal-worker, claude-bridge, playwright-worker, dashboard, rustfs, temporal, temporal-postgres, postgres, redis all up. No process or container opened by this round remains; the stack was left running as instructed.

## Recommendations (proposals only)

1. Small phase: fix and test the `stop_reason` receipt race, rebuild the three Python services, then one more live session with A1+A3 (needs the user's approval of a new session). Reuse the same flags to keep the comparison with r6 valid.
2. Do not run A2 yet. A2 changes what the model can click and cannot be re-scored after the fact; it only makes sense compared against a valid A1+A3 terminal. Run it after a valid session exists, as the one A1+A2+A3 run ADR-040 describes.
3. Then, with a valid terminal: `import`, `collect`, `detect --sources inventory`, independent reviews of every completed click, `evaluate --sources all|none|click_context,inventory --label ...`; keep only what scores better.

## Files changed

- `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md` (appended section r9)
- `plan/09112026103202-vision-accuracy-loop/README.md` (appended handoff "Agent loop round 01 r9 handoff - 2026-11-21")
- this report and its `.log`

GRAPH_UPDATE
- graph đã cập nhật: không cần, không thêm/xoá file trong repo, không đổi quan hệ import
- file mới đã đưa vào graph: không có
- hgraph check --changed: output tail "uncovered-changed" for pre-existing files (e.g. tests/test_vision_handoff_repository.py, +8 more), the same git-root prefix tooling issue already recorded in r7/r8 handoffs; not caused by this round.

ESCALATE
- decision needed: approve a fix of the `FileSpool.stop_reason` receipt race (control-plane code) and a new live session with the same A1+A3 flags; the one approved session is consumed without a valid terminal.
