STATUS: ESCALATE

# Phase 6 - be-developer r1 - live run refused by the worker; regression green; docs written

## CONTEXT_CHECK
- conventions: `AGENTS.md` and `docs/code-standards.md` (index) read verbatim; `docs/api-conventions.md` does not exist (repo has no such file).
- graphs: `vision-agent-loop`, `playwright-vision-worker` consulted; `hgraph brief` found no graph covering docs/benchmark paths (docs are not indexed).
- blast radius: 0 dependents (docs, benchmark report and handoff only; no source file edited).

## Impact inventory
- Database: no schema change. `uv run alembic upgrade head` on the local stack only: `a4c6e8f01234 -> b7c9d1e3f5a7` (phase 1 migration, additive), exit 0 (`alembic-upgrade.log`). Needed `CODEX_BRIDGE_ENABLED=false` in the process env because `.env` has the bridge enabled without an executable.
- Files created: `docs/adr/038-vision-agent-loop-engine.md`, `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md`, untracked helper `.pytest-artifacts/agent_loop_round.py` (`check`, `submit`), logs under `reports/phase-06/`.
- Files edited: `docs/vision-agent-operations.md` (new section "Agent loop engine"), `plan/09112026103202-vision-accuracy-loop/README.md` (handoff).
- No code, test, `.env`, compose file, metrics or oracle edited. `git checkout -- benchmark/vision/visual-buttons/flow-result.json` undid a pytest side effect (99 to 96 operations).

## 1. Regression (AC7), baseline = phase 0
| Check | Result | Log |
|---|---|---|
| `uv run ruff check .` | All checks passed | `ruff-check.log` |
| pytest G1 `test_[a-m]*` | 603 passed, 1 failed, 32 skipped | `pytest-G1.log` |
| pytest G2 `test_[n-z]*` non-vision (+ watch_vision_session) | 164 passed, 1 skipped | `pytest-G2.log` |
| pytest vision `[a-l]` | 521 passed | `pytest-G3a.log` |
| pytest vision `[m-r]` without page_batch | 332 passed | `pytest-G3b1-rest.log` |
| pytest vision `[s-z]` | 70 passed | `pytest-G3b2.log` |
| `test_vision_page_batch.py` (81 tests, 5 commands) | 27+27+8+7 passed; 12 clean dots then a 535 s timeout (ids 55-66, not re-run by name) | `pytest-page-batch-1..5.log` |
| Total pytest | 1771 passed, 1 failed, 33 skipped | |
| worker `tsc --noEmit` | exit 0 | `worker-typecheck.log` |
| worker locators + history + dom | 56 passed | `worker-vision-small.log` |
| worker `vision-agent-mode.spec` + `.qa.spec` | 40 passed, 1 failed (`QA-W08`, `action_outcome_unknown`); alone x2: 2 passed (timing-sensitive under load) | `worker-agent-mode.log`, `worker-qa-w08-rerun.log` |
| worker `vision-operations.spec` | 99 passed (6.6 min) | `worker-vision-operations.log` |
| worker `npm run lint` | 22 errors in 6 files not touched by this plan (same count phase 2 QA recorded) | `worker-lint.log` |
| dashboard test / typecheck / lint | 49 passed / exit 0 / exit 0 | `dashboard-*.log` |
| v4 identity hashes | `572143fe...` and `cc45b116...` equal to phase 0 | rerun of `v4_identity.py` |
| `git diff --exit-code -- metrics.py oracle` | exit 0 | |

The only failing pytest is the baseline failure `test_codex_bridge_benchmark.py::test_offline_manifest_provenance_and_explicit_live_boundary` (manifest hash; baseline actual `3b1c1ca08a19...`, now `e01f38efddfc...` because hashed sources changed; same assertion line). The 12 additional skips are the new Linux-container tests `test_agent_loop_bridge*.py`; they are not exercised on this host (Linux container only).
Order note: I deployed and created the session before running the regression (time limit); code is the same, no source changed in between.

## 2-3. Deploy, flag, checksums
- Build + `up -d` of control-plane, temporal-worker, playwright-worker, dashboard from the working tree (build logs `deploy-build-*.log`; started 20:21 by the coordinator after my build). `VISION_AGENT_LOOP_ENABLED=true` verified inside control-plane and temporal-worker; set through a scratchpad compose override because `docker-compose.yml` does not forward the variable and `.env` must not be edited.
- Checksums: `.pytest-artifacts/agent_loop_round.py check` compares every `*.py` (apps/control-plane, packages/contracts/src) and every `*.ts` (workers/playwright/src) byte-for-byte: 163 / 163 / 48 files, 0 mismatches (`deployed-checksums.json`). First attempt reported false mismatches (my helper normalised CRLF; containers keep CRLF); fixed to raw bytes.
- Tenant policy: `claude_cli / claude-opus-5-5`, max_steps 20, step timeout 120 s, fingerprint `5408692c...` (same as round 21), `agent_loop_enabled: true`.

## 4. The single live session - failed before any model call
- Session `552a906a-9044-4440-b4b0-fbaea0eabcc3` (project `8f2d5531-...`, target `https://mongchiton.vn`, task text of the original round session "Kiem tra cac nut xem co hoat dong khong", recovered by decrypting it in the control-plane container). Created once; no second session.
- Result: terminal after 0.94 s, state `unavailable`, reason `visual_exploration_unavailable`, 0 operations, 0 step-log rows, 0 bridge jobs (`codex_bridge_jobs` count 0).
- Root cause (evidence `live-session-failure-evidence.log`): the worker rejected `POST /visual-explorations` with `invalid_deadline` (HTTP 422). The worker requires `deadline <= now + max_session_seconds` (`workers/playwright/src/vision-operations.ts:140`). The agent loop computes `deadline = started + min(3600, step_timeout x max_calls)` = 2400 s (`apps/control-plane/application/vision_agent_loop.py:296-301`) and sends `max_session_seconds = step_timeout_seconds` = 120 (`:351-353`). v4 opens with `now + step_timeout` (`vision_trace_events.py:86-91`) and renews per step.
- Classification: a defect in phase 4 code (fake worker in unit tests does not apply the rule), not a bridge/token/stack failure. Fix is outside the files phase 6 may touch, so I did not change code and did not retry. AC6 is **not met**.
- Because no agent step ran: no `run.py import/collect/evaluate`, no `score.json`, no C/A, no token, blocked-action or call-count data, no 20-call sufficiency (K1) answer, no live job parse of the agent schema (phase 3 bridge check is still unverified live).

## 5. Benchmark identity
`git diff --exit-code -- benchmark/vision/accuracy/metrics.py benchmark/vision/accuracy/oracle-mongchiton-1280-v1.json` exit 0. Oracle hash `9242b33d...` unchanged.

## 6-7. Documents
- Round report `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md`: states "not scored", cause, comparison table (rounds 16/19/20/21 plus this round), regression numbers.
- `docs/adr/038-vision-agent-loop-engine.md`: decisions, rejected alternatives, technical debt (duplicated primitives, K1-K5), no figures; Consequences records that the engine has no completed live session.
- `docs/vision-agent-operations.md`: new section (flag on both services, compose override note, engine choice, 20-call budget, block codes, terminal reasons, diagnosing a session that ends in seconds, rollback). Block code names checked against `domain/vision_agent_safety.py` (`action_kind_blocked`, `origin_blocked`, `ineligible_target`, `sensitive_action_blocked`, `invalid_ref`, `stale_ref`).
- Handoff appended to `plan/09112026103202-vision-accuracy-loop/README.md`.

## 8. Codex with fixed v4 instructions (`process.py:62`)
Not measured: no agent job ran. Needs the live round first.

NEEDS_USER_INPUT
- question: open a small phase to fix the worker-open deadline in `application/vision_agent_loop.py` (open with `now + step_timeout`, keep the session deadline in the loop; add a test where the fake worker applies `deadline <= now + max_session_seconds`) and then authorize one new live round? The same phase could carry the Codex-instruction decision after that round.
- context: `vision_agent_loop.py:296-301,351-353` vs `vision-operations.ts:140`; evidence in `reports/phase-06/live-session-failure-evidence.log`.
- blocked_on: AC6, benchmark scoring, ADR-038 validation, Codex decision, 20-call coverage.

## GRAPH_UPDATE
- graph đã cập nhật: không cần — không thêm/xoá file source, không đổi quan hệ import (chỉ docs, báo cáo, helper untracked).
- file mới đã đưa vào graph: không có (docs/benchmark/`.pytest-artifacts` không được hgraph lập chỉ mục).
- `hgraph check`: `hgraph check — 5 graph, 454 file source / ✔ Không có vấn đề.` (exit 0).
- `hgraph check --changed`: exit 1 chỉ với 31 dòng `uncovered-changed` có tiền tố `auto-at-ui/` (git gốc là thư mục cha `agent-at/`, lỗi đường dẫn đã ghi ở phase 1-4; cùng các file đã thuộc graph khi tra không tiền tố). Output: `hgraph-check.log`. Không có dòng nào thiếu tiền tố.

## Cleanup
Stack local (control-plane, temporal-worker, playwright-worker, dashboard, claude-bridge) giữ nguyên chạy; control-plane và temporal-worker còn `VISION_AGENT_LOOP_ENABLED=true` qua override ở scratchpad (không trong `.env`; recreate bằng compose không có override sẽ tắt cờ). Không có tiến trình nền của tôi (một REPL python nhầm đã kill). Không commit, không sửa `.env`.
