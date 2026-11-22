STATUS: ESCALATE

# Phase 6 - be-developer r3 - third live session: agent steps ran, ended `worker_result_mismatch`

## CONTEXT_CHECK
- conventions: `AGENTS.md`, `docs/code-standards.md` (read in r2); no `docs/api-conventions.md` in this repo.
- graphs: `vision-agent-loop`, `vision-exploration`, `codex-bridge`.
- blast radius: no source edited in r3 (docs and benchmark report only).

## Steps
1. Bridge check: container Up, `/codex-jobs/.heartbeat.json` recorded_at 14:51:06 UTC, `online: true`, `authenticated: true`, model claude-opus-5-5. No rebuild done by me.
2. Moved the r2 session file aside; one `submit`: session `685f76a7-404d-49bf-acb5-1ff6c72d66c6` (same parameters, `max_steps=20`). No fourth session.
3. Watcher: `running` then `terminal unavailable`; reason `worker_result_mismatch`; about 40 s.

## Measurements (database + logs)
| Item | Value |
| --- | --- |
| Terminal | `unavailable` / `worker_result_mismatch` (not agent_done/agent_stopped/agent_step_limit/session_timeout): AC6 not met |
| Model calls | 2 (jobs `f6a8fe39-8dea-4ce1-adbf-0518729000c2`, `7d0632c1-690b-4753-95e4-d31511263247`), both completed, outcome `agent_step`, 0 schema rejections |
| Tokens | 4657 in / 299 out; 4979 in / 506 out (1534 cached) = 9636 / 805 |
| Model time | about 9 s and 8 s per call |
| Operations | 3: setup navigate; click `1:2` completed (`url_change=changed`, stop cause `url_change`); click `2:7` failed at prepare merge |
| Step log | 2 rows (step 1 stop `url_change`, step 2 stop `worker_result_mismatch`) |
| Blocked actions by code | none; `sensitive_action_blocked` on oracle target: 0 |
| K1 (20 calls enough) | not measurable (2 calls used) |
| Codex v4 instructions (`process.py:62`) | not measured; only Claude ran |

First live proof that the phase 3 bridge parses the agent schema and returns valid `agent_step` output through the real Claude CLI.

## Root cause (outside phase 6 scope, not fixed)
`apps/control-plane/application/vision_agent_loop.py:232` sets `run.browser_parent = operation.id` after every completed operation and sends it as `parent_operation_id`
(`:217`). The worker in agent mode never extends `session.ancestry` for `purpose=explore` (`sequential`, `workers/playwright/src/vision-operations.ts:559,869-873`) and returns
`session.ancestry.at(-1)` (the root navigate) at `:502`. Op 2 passes (parent = root); op 3 sends op 2 as parent, the worker returns root, `_merge` raises
`worker_result_mismatch` (`application/vision_operations.py:136-140`). The tests' `FakeWorker` echoes the request parent, so it hides this.
Suggested fix: advance `browser_parent` only for operations the worker pushes on its ancestry (navigate; setup with `refresh_observation` or scroll), and make `FakeWorker` return
`ancestry[-1]` by the same rule (test red on old code).

## Not done
`run.py import/collect`, review, `evaluate`, `score.json`: not run, because the session is not a valid terminal and would produce an invalid score. `git diff --exit-code` metrics + oracle: exit 0.

## Docs
Updated: `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md` (r3 section and table with rounds 16/19/20/21 plus r1-r3), `docs/adr/038-vision-agent-loop-engine.md` (Consequences, third attempt),
`plan/09112026103202-vision-accuracy-loop/README.md` (r3 handoff). `docs/vision-agent-operations.md` unchanged.

## ESCALATE
- question: open a small phase to fix parent tracking in `vision_agent_loop.py` plus the `FakeWorker` parent rule, then authorize a fourth live session?
- context: evidence above; DB rows for session `685f76a7-...`; worker log "Vision operation outcome could not be proven" (failure_stage merge, op 3).
- blocked_on: AC6, scoring, K1, Codex decision.

## GRAPH_UPDATE
- graph đã cập nhật: không cần — r3 không đổi source.
- file mới đã đưa vào graph: không có.
- `hgraph check`: exit 0. `hgraph check --changed`: exit 1, only the known `auto-at-ui/` prefix `uncovered-changed` lines (`r3-hgraph-check-changed.log`).

## Cleanup
No processes of mine running. Stack left as found: control-plane, temporal-worker, playwright-worker, dashboard, claude-bridge Up; flag on via the scratchpad override. No commit.
