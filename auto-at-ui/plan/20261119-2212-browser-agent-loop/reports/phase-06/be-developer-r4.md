STATUS: ESCALATE

# Phase 6 - be-developer r4 - parent fix, real-worker dry run green, live 4 reached six model steps then a lease lapse

## CONTEXT_CHECK
- conventions: `AGENTS.md`, `docs/code-standards.md` (read r2); no `docs/api-conventions.md` in this repo.
- graphs: `vision-agent-loop`, `vision-exploration`, `codex-bridge`.
- blast radius: 5 dependents of `application/vision_agent_loop.py` (vision_publisher, temporal_worker, 3 tests).

## Impact inventory
- Database: no change. Contract/worker: no change.
- Edited: `apps/control-plane/application/vision_agent_loop.py` (parent tracking; lease renewal), `tests/test_vision_agent_loop.py` (FakeWorker rules + 2 tests), `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md`, `docs/adr/038-vision-agent-loop-engine.md`, `plan/09112026103202-vision-accuracy-loop/README.md`.
- Untracked helpers: `.pytest-artifacts/agent_loop_dry_run.py`, `.pytest-artifacts/agent_loop_round.py` (check now also covers claude-bridge). Evidence: `reports/phase-06/r4-*`, `live-session-r4-evidence.log`.

## 1. Parent tracking fix
`run_operation` advances `run.browser_parent` only when `purpose != "explore"` (worker agent mode never extends ancestry for explore: `vision-operations.ts:502,559,869-873`).
`FakeWorker` now: returns `ancestry[-1]` as parent (navigate -> null) and updates ancestry like the worker; rejects `state_mismatch` (expected fingerprint), `stale_dom_snapshot`, `origin_blocked` (off-origin page: only back/close_popup), `invalid_observation_refresh`, `invalid_navigation_purpose`, `invalid_restore_purpose`, `sensitive_action_blocked` (type with a line break); kept `invalid_deadline` and step-deadline rules; budget formula was already there.
New test `test_every_explore_operation_reports_the_worker_parent_not_the_previous_operation`: red on old code (`worker_result_mismatch`, same as live r3), green on new.

## 2. Tests
`uv run ruff check .`: All checks passed. `test_vision_agent_loop.py` + `test_vision_agent_loop_qa.py`: 188 passed (final run, after both fixes). `test_vision_live_persistence.py`: 27 passed. `twenty_calls` test 57 s (limit 60 s, timing sensitive, unchanged).

## 3. Deploy and checksums
control-plane + temporal-worker rebuilt and recreated twice (`r4-deploy-*.log`, `r4b-deploy-*.log`), flag on via the scratchpad override. `agent_loop_round.py check` (now incl. claude-bridge): 163 / 163 / 163 / 48; control-plane, temporal-worker, playwright-worker 0 mismatches; claude-bridge differs only in `application/vision_agent_loop.py` (the bridge does not import it; the bridge files from phase 3 are equal, as the coordinator verified).

## 4. Dry run (no model)
In-process processor + real playwright-worker container (through a temporary TCP forwarder container, removed; none left) + scripted model on https://mongchiton.vn, disposable database.
- Run 2 (`r4-dry-run-2.json`): `agent_done`, 7 calls, 8 operations: click, scroll x2, click that changed the URL (batch stopped), `back`, `navigate` to target, wait; blocked `sensitive_action_blocked` and `stale_ref`; parents consistent.
- Run 3 (`r4-dry-run-3.json`, after the lease fix, with 3 blocked-only steps over 36 s): `agent_done`, 10 calls, 94 s.
- Run 1 exposed only a harness issue (screenshot cap 1 MB in the test seed; set to 5 MB like live).

## 5. Live session 4 (the one approved): `9e21e389-8145-4870-824e-8a38013ea86e`
- Final: `unavailable` / `worker_state_unavailable` (not agent_done/stopped/step_limit/timeout); about 97 s. AC6 not met.
- 7 bridge jobs: 6 completed (tokens in/out 30,672 / 2,495; per call 4657/283, 4975/509, 5107/379, 5214/331, 5287/494, 5432/499), #7 cancelled. Model time 6-9 s/call.
- Operations: setup navigate + 4 explore clicks (3 completed with `url_change`, 4th `settle_timeout`, `url_change=changed`). Steps: 3 stopped by `url_change`, one 4-action batch cut after its first click.
- Blocked actions by code: `origin_blocked` x5 (steps 5-6, page had left the allowed origin; model proposed wait/clicks, not back/navigate); `sensitive_action_blocked` 0 (none on an oracle target).
- Cause (fixed in scope after the run): `vision_agent_loop.py` renewed the 30 s lease only through operations; steps 5-6 ran none, so call 7 hit `stale or expired visual session lease` (`repositories.py:964`, logged as `bridge_malformed_output`), `finish` failed too, the outbox event was redelivered and the evidence-only recovery wrote `worker_state_unavailable`. Fix: `uow.renew` at the top of each step and before each model call; test `test_the_lease_is_renewed_every_step_even_when_no_action_reaches_the_worker` red on old (0 renewals), green on new. Evidence: `live-session-r4-evidence.log`.

## 6. Not done
`run.py import/collect`, review, `evaluate`, `score.json`, C/A, K1 (only 6 of 20 calls used, ended by an infrastructure fault), Codex v4-instructions decision: not run; the session is not a valid terminal and must not be scored. Metrics and oracle `git diff --exit-code`: exit 0.

## Observation (not fixed, outside code scope)
After the 4th click left the allowed origin, the model proposed blocked clicks/waits instead of `back`/`navigate`; a prompt hint for off-origin pages may help (prompt change needs its own phase/version bump).

## ESCALATE
- question: authorize a fifth live session now that the lease fix is deployed (and decide whether to add an off-origin hint to the agent prompt first)?
- context: sessions used: r1 open deadline, r2 stale bridge image, r3 parent mismatch, r4 lease lapse; each failure was a distinct code/deploy defect, each fixed with a test. Evidence above.
- blocked_on: AC6, scoring, K1, Codex decision.

## GRAPH_UPDATE
- graph đã cập nhật: không cần — không thêm/xoá file source, không đổi import.
- file mới đã đưa vào graph: không có.
- `hgraph check`: exit 0. `hgraph check --changed`: exit 1, only `uncovered-changed` file lines with the known `auto-at-ui/` prefix (git root is the parent folder); no unprefixed file line (`r4-hgraph-check-changed.log`).

## Cleanup
Forwarder container `agent-dry-run-proxy` removed (`docker ps -a --filter name=dry-run` empty); disposable databases dropped by the script. Stack left Up: control-plane, temporal-worker (with the fix and flag), playwright-worker, dashboard, claude-bridge. No commit.
