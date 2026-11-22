STATUS: FAIL

CONTEXT_CHECK
- conventions: AGENTS.md, docs/code-standards.md (hgraph brief), be-developer-r12.md (harness commands), AGENT-LOOP-01-20261120.md r12/r13 sections. ADR-042, r13/r14/r14b/r15-shelve and the README handoffs were NOT re-read in full (the run ended before any worker or model step; they were not needed for the result). docs/api-conventions.md not read: no API change.
- graphs: hgraph brief for benchmark/vision/accuracy: no graph covers the folder. No source touched.
- blast radius: not applicable (no source change)

# Agent loop round 01 r16 - live A1+A3, prompt v2, ADR-042: session never opened

## Summary
The one approved live session ended `unavailable` / `visual_exploration_unavailable` at **session_open** (worker HTTP 422 `visual_request_rejected`, `error_type=unexpected_error`, 3,787 ms), before any worker operation and any bridge call. Zero operations, zero calls, nothing to score, nothing imported into `runs/`. ADR-042 and prompt v2 were therefore NOT exercised by this round. The approved session is consumed; no second session was created.

## Session
| Item | Value |
| --- | --- |
| Session | `82e22289-b52a-4fd3-b74f-633a31147214`, correlation `8cf2d7c9-ca0b-4c0b-ae46-b80778d83b75` |
| Terminal | `unavailable`, `safe_failure_reason=visual_exploration_unavailable` (invalid terminal; not `agent_done`/`agent_stopped`/`agent_step_limit`/`session_timeout`) |
| Time | submit 13:09:10 UTC, session_open rejected 13:09:15.535 UTC, state `unavailable` seen 13:09:19 |
| Counts (result) | proposed 0, operations 0, completed 0, failed 0, frames 0; trace `pages=[] items=[] states=[]`, `evidence_status=not_started` |
| Bridge jobs / calls | 0 jobs, calls 0 of cap 20 (the `claude-bridge` log has no job line); `bridge_policy_revoked` 0 |
| Flags | loop, A1, A3 on; A2 off (as prepared) |

## Steps and real outputs (abridged)
1. 20:07 `GET /vision/providers`: `claude_cli` `online=false` on the first call right after the stack came up, then `online=true, authenticated=true, capabilities_qualified=true, busy=false` on three consecutive checks (bridge heartbeat lag after recreate; one later poll showed `online=false` again for a moment, then true before submit). Bridge authenticated throughout; submit happened while `online=true`.
2. `agent_loop_round.py check`: `mismatches: []`, compared control-plane 163, temporal-worker 163, claude-bridge 163, playwright-worker 52 (20:07).
3. `mv agent-loop-session.json agent-loop-session.r12.json`; one `submit`: `202`, session `82e22289...`, `max_steps=20`, `max_hops=20`, `max_session_seconds=120`, `step_timeout_seconds=120`. Poll: first read already `unavailable visual_exploration_unavailable`.
4. Dumps (read-only API): `.pytest-artifacts/agent-loop-r16-{trace,result,locators}.json` (257 / 1,827 / 144 bytes, all empty of evidence).
5. Logs (all four services, last 5-10 min):
   - temporal-worker 13:09:15.535 `HTTP Request: POST http://playwright-worker:7100/visual-explorations "422"`, `vision.worker.rejected` stage `visual-explorations` code `visual_requ...`; then GET `/origins` 422 `session_unavailable` and DELETE 422 `session_unavailable` (cleanup of a session that never opened); `workflow.outbox.published`.
   - playwright-worker 13:09:15.535 `vision.request_rejected ... session_open: visual_request_rejected`, `status_code=422`, `duration_ms=3787`, `error_type=unexpected_error`; followed by the two `session_unavailable` entries. No `vision.state.mismatch`, no `settle_*` events.
   - claude-bridge: no job. control-plane: 202 on submit, then GET polls only.
6. Not imported, not collected, not scored: no `run.py import/collect/detect/evaluate` was run (nothing to import: 0 operations, 0 frames). `runs/` untouched (git status shows only the pre-existing untracked 1c56623e and 396af7e4).

## Diagnosis of the open failure (read-only; cause NOT established)
- `VisionOperations.open` (`workers/playwright/src/vision-operations.ts:139-229`) validates, launches Chromium, creates the context (`reducedMotion: "reduce"`), a blank page, calls `inspectState(page)`. It does not navigate (navigation is the later setup op). A `VisionWorkerError` would log `contract_rejection`, a Playwright timeout `timeout`; this one logged `unexpected_error`, i.e. a plain error whose message is deliberately not logged (`vision-observability.ts:13-24`), so the real message is unrecoverable from logs.
- Environment looked healthy: worker container up 13:05:10 UTC (4 min before), `OOMKilled=false`, restarts 0, 1 GiB limit, 282 MiB used after, `/tmp` tmpfs 1% used, `shm=64 MiB`. The target resolves and answers `200` from the container (`fetch https://mongchiton.vn`, `getent hosts` -> 103.206.217.155).
- Tree code is not obviously broken: `npx playwright test src/vision-agent-mode.spec.ts src/vision-settle-animation.spec.ts` locally: `45 passed (2.9m)` (these specs call `open`). The running container's 52 worker files are byte-identical to the tree (check above). So a deterministic bug in the open path is unlikely, but a first-use Chromium launch problem inside the read-only container (launch took the whole 3.8 s) is a hypothesis only. I could not reproduce it: `docker cp` into the container fails (`container rootfs is marked read-only`), and an in-container probe would have needed extra permissions/files; I did not push further (no source or container change allowed). I did not create a second session to retry.

## Requested monitoring items (all unanswered by this run)
| Item | Result |
| --- | --- |
| `settle_timeout` / `state_kept_changing`, ADR-042 effective live | not exercised (no navigate/scroll/click ran) |
| scroll count | 0 |
| `state_mismatch` | 0 (no observation ran) |
| force click used / hit the intended node | not exercised |
| calls / cap 20 | 0 / 20 |
| `bridge_policy_revoked` | 0 |
| return to start page, final `skipped_count` | not applicable |
| safety invariant (click hitting another control) | no click happened; the r14 debt (overlaying control) is still untested live |
| mct-30/31 rule | not applied (no clicks) |

## Comparison (r6 / r10 / r12 / r16)
| Run | C | A | P | R | Clicks | Scroll | Calls | Terminal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| r6 | 5/47 official (no page check) | 5/12 | n/a | 0/47 | 12 (8 ok) | 2 | 20 | `agent_stopped` valid |
| r10 | 1/47 official | 1/10 | 7/7 | 7/47 | 10 (1 on oracle page) | 0 | 14 | `agent_done` valid |
| r12 | 3/47 strict, 5/47 lenient (diagnostic only) | 3/5, 5/5 | 14/35 | 14/47 | 5 | 2 (1 failed) | 5 | `settle_timeout` invalid |
| r16 | n/a | n/a | n/a | n/a | 0 | 0 | 0 | `visual_exploration_unavailable` at session_open, invalid |
Official: only r6 and r10 have valid-terminal scores. r16 has no number; no improvement or regression is claimed for prompt v2 or ADR-042.

## Findings
- A new failure class: worker `session_open` rejected with an unlabelled `unexpected_error` (cause unknown) right after a stack recreate. It cost the single approved session without testing the ADR-042 fix.
- The `unexpected_error` category hides the cause; a worker log of the error class/name (not message, per the secrecy rule) would make this diagnosable without a retry. This is a proposal only (source untouched).
- Provider readiness flaps right after the bridge is recreated (`online=false` for roughly the first minute, and once more later); the harness should poll until stable before submit.

## Risks
- The one approved session is consumed with no score; ADR-042 live effect is still unverified. A rerun needs a new user approval.
- If the open failure is a cold-start Chromium issue in the recreated worker, it can recur; if it is deterministic in the container, a rerun would burn another session.
- Oracle `9242b33d...`, `metrics.py`, thresholds, policy, prompt: not touched.

## Stack
control-plane, temporal-worker, claude-bridge, playwright-worker (up since 13:05 UTC, not restarted), dashboard, rustfs, temporal, temporal-postgres, postgres, redis up. Nothing rebuilt or stopped; no temporary process or container left (local `playwright test` finished; no chrome process remaining). Bridge token valid to about 22:10.

## Recommendations (proposals only)
1. Before another live session, run a no-LLM check of the worker open path in the recreated container (for example one cheap `POST /visual-explorations` open+close via the internal route by an authorised operator, or a worker-side log of `error.name` for `unexpected_error`), and require the provider `online=true` for 60 s before submit.
2. After that, one new approved live session A1+A3 to finally test ADR-042 and prompt v2 together; keep A2 off.
3. If it recurs, rebuild/recreate playwright-worker once and retry open before spending a session.

## Files changed
- `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md` (section r16 appended)
- `plan/09112026103202-vision-accuracy-loop/README.md` (handoff r16 appended)
- `.pytest-artifacts/agent-loop-r16-{trace,result,locators}.json`, `.pytest-artifacts/agent-loop-session.json` (r16), `.pytest-artifacts/agent-loop-session.r12.json` (renamed r12 session)
- this report and `.log`
- scratch only (scratchpad): `prov16.py`, `poll16.py`, `zz-probe16.ts`, `open-probe16.ts`

GRAPH_UPDATE
- graph đã cập nhật: không cần — không thêm/xoá file source, không đổi import
- file mới đã đưa vào graph: không có
- hgraph check --changed: not run (no source change)
