STATUS: ESCALATE

# Phase 6 - be-developer r2 - deadline bug fixed; live session failed again on a stale claude-bridge image

## CONTEXT_CHECK
- conventions: `AGENTS.md` and `docs/code-standards.md` read; `docs/api-conventions.md` does not exist in this repo.
- graphs: `vision-agent-loop`, `vision-exploration`, `codex-bridge` (per `hgraph brief apps/control-plane/application/vision_agent_loop.py`).
- blast radius: 5 dependents (vision_publisher, temporal_worker, 3 tests), 16 dependencies.

## Impact inventory
- Database: no change.
- Files edited: `apps/control-plane/application/vision_agent_loop.py` (open deadline), `tests/test_vision_agent_loop.py` (fake worker rules + 2 tests), `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md`, `docs/adr/038-vision-agent-loop-engine.md`, `plan/09112026103202-vision-accuracy-loop/README.md`. New: `reports/phase-06/live-session-r2-evidence.log`, `r2-*` logs. `docs/vision-agent-operations.md` not changed (nothing new in runbook behaviour; the bridge-image lesson is in the ADR and handoff).
- No contract, worker, `.env`, metrics or oracle change. No commit.

## 1. Fix
`vision_agent_loop.py` (after `opened = True`): in step mode the worker is opened with `deadline = self.now() + step_timeout_seconds`
(<= worker rule `now + max_session_seconds`, `vision-operations.ts:140`); the session deadline stays in `ExecuteVisualOperation`, `CodexCallBudget`
and `check_policy`. Non-step mode keeps `deadline` (= started + min(record, runtime max_session_seconds), already within the rule).
Renewal as v4: each prepare sends `step_deadline = now + step_timeout` (`vision_operations.py:246-252`; worker accepts it at `vision-operations.ts:513-517`);
the worker's idle lease covers observe + model time between steps (`idleLease`, `:104-109`). Other worker-bound fields audited:
prepare `step_deadline` (<= now + step_timeout, ok), observe_dom has no deadline, `max_session_seconds` = step timeout (ok). No other violation found.

## 2. Tests
- `FakeWorker.open` now rejects unless `now < deadline <= now + max_session_seconds` (`invalid_deadline`); `FakeWorker.prepare` enforces the step-deadline rule
  (present and within `step_timeout_seconds` in step mode, absent otherwise).
- New: `test_the_worker_is_opened_within_its_max_session_seconds_in_step_mode` (red on old code: confirmed by reverting `deadline=open_deadline` to `deadline=deadline`
  -> `1 failed, 1 passed`; green on new) and `..._without_step_mode`.
- Real output: `tests/test_vision_agent_loop.py` 53 passed (125.99 s); `tests/test_vision_agent_loop_qa.py tests/test_vision_live_persistence.py` 160 passed (191 s);
  `uv run ruff check .` All checks passed (after one E501 fix in the test, re-run clean).
- Note: `test_twenty_calls_of_ten_actions...` takes about 54 s against its 60 s session limit; it failed once under load during my first run and passed alone and in the full file (not changed by me; flag as timing-sensitive).

## 3. Deploy
`docker compose -f docker-compose.yml -f docker-compose.codex.yml -f <scratchpad>/agent-loop-override.yml` with `CLAUDE_BRIDGE_TOKEN_DIR` (a path, not a secret) set, `build` then `up -d --no-deps control-plane temporal-worker`
(`r2-deploy-build.log`, `r2-deploy-up.log`). `VISION_AGENT_LOOP_ENABLED=true` in both. `agent_loop_round.py check`: 163 / 163 / 48 files, 0 mismatches (`r2-deployed-checksums.json`).
Gap: this check does not cover the `claude-bridge` container (see 4).

## 4. Live session (the single approved one): `84fc0fa8-8c5a-48fc-9ab6-4a4e1faa8525`
- Worker open: 200 OK (r1: 422 invalid_deadline). Setup navigate prepare/execute/ack and `observations/dom`: 200 OK.
- First bridge job `76fb53f2-68a5-4d1e-8c87-fedd20333628`: `codex.handoff.failed`, phase `policy_check`, failure `bridge_offline`. Container `auto-at-ui-claude-bridge-1` died at 14:47:31 UTC, exit 1, last line `{"failure_code":"bridge_io_error"}`.
- Terminal: state `unavailable`, reason `bridge_offline`; 1 operation, 1 job (cancelled), 0 agent steps, 0 tokens. AC6 not met.
- Root cause: the bridge image `auto-at-claude-bridge:2.1.328` predates the phase 3 bridge changes (sha256 of `claude_process.py`, `spool.py`, `process.py`, `codex_bridge_cli.py` differ from the tree; no agent job schema support). Details in `live-session-r2-evidence.log`.
- Classification: deployment gap (service not rebuilt), outside "rebuild only control-plane and temporal-worker" instruction. I did not rebuild the bridge (not authorized) and did not run a second session. The claude-bridge container is currently EXITED.

## 5. Not done (blocked by 4)
`run.py import/collect/evaluate`, score.json, independent review, call/token/time/blocked-action counts, 20-call sufficiency (K1), Codex v4-instructions decision (`process.py:62`): all unmeasured. Metrics and oracle: `git diff --exit-code` exit 0.

## 6. Docs
Updated `AGENT-LOOP-01-20261120.md` (r2 section, comparison table with rounds 16/19/20/21, r1 and r2 both not scored), ADR-038 Consequences (second attempt, bridge-image lesson), plan 09112026 README handoff.

## ESCALATE
- question: authorize (a) rebuilding and recreating only `claude-bridge` from the tree (`CLAUDE_BRIDGE_TOKEN_DIR=C:/Users/hen/.auto-at/claude-bridge-secrets docker compose -f docker-compose.yml -f docker-compose.codex.yml build claude-bridge`, then `up -d --no-deps claude-bridge`, with a byte comparison of its source against the tree and a token-expiry check), and (b) one more live session?
- context: `reports/phase-06/live-session-r2-evidence.log`; image built 2026-11-19 14:14 vs phase 3 files.
- blocked_on: AC6, scoring, K1, Codex instruction decision.

## GRAPH_UPDATE
- graph đã cập nhật: không cần — không thêm/xoá file source, không đổi quan hệ import.
- file mới đã đưa vào graph: không có.
- `hgraph check`: exit 0 (`5 graph, 454 file source / Không có vấn đề`).
- `hgraph check --changed`: exit 1, only `uncovered-changed` lines, all with the known `auto-at-ui/` prefix (git root is the parent dir); no line without the prefix. Log `r2-hgraph-check-changed.log`.

## Cleanup
No background processes of mine. Stack: control-plane, temporal-worker, playwright-worker, dashboard running; claude-bridge exited (left as found after the crash).
