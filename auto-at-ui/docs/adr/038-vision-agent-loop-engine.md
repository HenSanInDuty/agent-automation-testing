# ADR-038: Closed-loop browser agent engine for Vision (`engine=agent_loop`)

Status: accepted for implementation (user approval of plan scope and decisions K1-K5, 2026-11-19/20);
live validation **not yet achieved** (see Consequences). Date: 2026-11-20.

## Context

The Vision planner (v4) asks the model for a batch of candidates over one DOM inventory, then the
control plane executes them and restores or replays pages between hops. It cannot follow a task
that depends on what the previous click did: the model never sees the result of an action before
proposing the next, and every popup or navigation costs a restore that can end in `unsafe_replay`.
The accuracy rounds (01-21) show that the restore path, not the model, is the recurring terminal.

The goal is a second engine in which the model observes, acts, observes again and decides, while
the existing worker, operation ledger, evidence, benchmark and v4 planner stay as they are.

## Decision

- Add an engine selector per session: `planner` (default, unchanged) or `agent_loop`. The column
  `exploration_engine` is stored on the session and kept on reload (K5). The flag
  `VISION_AGENT_LOOP_ENABLED` (default false) gates it on the server; the policy read response exposes
  `agent_loop_enabled` for the dashboard.
- Each step: the worker returns a fresh snapshot whose refs are `version:n`; the model returns
  `evaluation_previous_goal`, `memory`, `next_goal` and 1 to 10 actions, or done/stop/need_screenshot.
  The control plane validates refs and safety in code, runs each action through the existing
  `ExecuteVisualOperation` (before/after frames), stops the batch when the page changes, writes a step
  log (`visual_agent_steps`) and loops. No restore or replay: the agent continues from the current page,
  and `back` / `navigate` (to the target only) are model actions.
- Safety is enforced twice in code (`domain/vision_agent_safety.py`, then the worker in agent mode), with a
  single keyword list passed down through `VisualWorkerOpen`. The prompt is advice, not a control.
- Context per call is bounded: newest snapshot (cap `vision_agent_snapshot_chars`), memory, last five steps.
- Budget stays at 20 model calls per session, counting every bridge call (K1). Provider stays
  `codex_cli` or `claude_cli`.
- K2: action kinds already in the contract only (click, type, scroll, wait, back, close_popup, navigate).
- K3: the project `allowed_origins` is an observe-only allowlist; off-allowlist pages can be opened and read,
  and only `close_popup` / `back` act there. Sub-resources are not blocked.
  The only action allowed on an off-allowlist page besides `back`/`close_popup` is the read-only observation refresh (setup `wait` with `refresh_observation`), which resyncs the worker's page state after a redirect and has no side effect.
- K4: in agent mode a dialog or download caused by an action is recorded, cancelled and reported to the
  model; `action_outcome_unknown` still locks the session as in v4.
- K5: the step log lives as long as the session intent (`intent_retention_until`).
- v4 behavior, its schema hash (`codex-dom-v11`) and `metrics.py` / the oracle do not change; every relaxation of a
  worker guard sits behind `agent_mode`.

## Alternatives rejected

- **Extend the planner to loop.** Keeps restore and replay, which is the failure being avoided, and would
  change v4 behavior and its identity hashes.
- **Replace v4.** Loses the engine that produced the benchmark history; rollback becomes impossible.
- **Let the model drive the browser directly (hover, key presses, arbitrary URLs, select).** Widens the unsafe
  action surface; deferred (non-goals).
- **Keep a live CLI session between steps.** Couples correctness to process lifetime; each call stays stateless.
- **Cheaper model that trims the snapshot, or a worker-side snapshot-range endpoint.** Extra moving parts before
  the base loop is proven; deferred.
- **`ariaSnapshot()` as the ref scheme.** Refs must be tied to the worker's own element map to be checkable.
- **Per-session allowlist column.** Project allowlist is enough for the first version.
- **Raise the 20-call ceiling now.** Needs evidence from a live run first (K1).

## Consequences and technical debt

- Two engines share primitives that are copied rather than extracted: the bridge exchange / retry loop,
  operation lifecycle handling and result classification exist in both the planner and the agent loop.
  Extracting them is a separate refactor after the loop is validated.
- Snapshot truncation means a page with more controls than fit may be only partly visible to the model;
  the prompt reports "N controls outside the snapshot" but cannot list them.
- Detection numbers from the benchmark are not comparable with v4: the agent loop does not produce a full-page
  inventory.
- Re-baselining form state for a `type A` then `type B` batch is limited to value changes; richer form
  handling is open.
- The worker keeps at most 200 checkpoints; a very long session could hit `state_limit`.
- Prompt injection from page text is mitigated by code-enforced blocks, not eliminated.
- **The engine has not completed a live session yet.** The first live attempt (2026-11-20) was refused by the worker
  at session open (`invalid_deadline`) before any model call: the control plane opened the worker session with the
  whole-session deadline while sending the per-step `max_session_seconds`. Unit tests used a fake worker that does not
  apply that rule. The open request must use a deadline within one step, as v4 does, and the processor needs a test
  against the worker's rule. Until a live run reaches a terminal agent reason, the accuracy of this engine, whether
  20 calls cover the click-everything task, and whether Codex needs its own agent instructions (it still sends the v4
  instructions, `infrastructure/codex_bridge/process.py`) are all unmeasured.
- **Second live attempt (r2, 2026-11-20).** The open deadline is fixed (open with `now + step_timeout`, per-step
  `step_deadline` as v4) and a worker-rule test guards it; the worker then accepted the session and the setup navigate ran.
  The attempt still produced no agent step: the `claude-bridge` container was running an image built before the phase 3
  bridge changes and exited on the first agent job (`bridge_io_error`). The engine therefore remains live-unvalidated.
  Lesson: the deploy checksum check must include the `claude-bridge` image, not only control-plane, temporal-worker and
  the Playwright worker.
- **Third live attempt (r3).** With the bridge rebuilt the loop ran two real model steps (Claude returned valid `agent_step` output, 9636 input /
  805 output tokens, about 8 s per call) and one completed click, then stopped with `worker_result_mismatch`: the loop advances its
  `parent_operation_id` after every completed operation while the worker in agent mode keeps the root navigate as parent for explore operations.
  The unit-test fake worker echoes the parent, so the mismatch was not covered. Still no scored session; the fake worker should apply the
  parent rule as well.
- **Fourth live attempt (r4).** Parent tracking was fixed (the loop advances `parent_operation_id` only for the operations the worker pushes onto its ancestry) and a dry run
  against the real worker with a scripted model reached `agent_done`. The live session then ran six real model steps and four clicks before the 30 s session lease lapsed in two steps
  whose actions were all blocked (no operation renews it). The loop now renews the lease every step and before every model call. Lesson: the fake worker, then a dry run, must also cover
  quiet stretches (no operation for longer than the lease). Still no session with a valid terminal reason, so accuracy, K1 and the Codex-instruction question stay open.

## Related

- Plan: `plan/20261119-2212-browser-agent-loop/plan.md`; graph `docs/graphs/vision-agent-loop.md`.
- Operations: `docs/vision-agent-operations.md` section "Agent loop engine".
- Round record: `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md`.
- Builds on ADR-037 (Claude bridge) and the v4 trace/evidence ADRs 033-036.
