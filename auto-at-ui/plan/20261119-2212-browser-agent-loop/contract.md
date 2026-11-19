# Contract (draft, Gate 1) — Browser-agent closed loop for Vision

Reference: `../../../docs/Ref/Building-Browser-Agent.pdf` (arXiv 2511.19477). Key ideas:
- Hybrid context: structured (accessibility/DOM) snapshot is primary; screenshot only when needed (sec 4.4).
- Element refs carry a snapshot version (`<version>:<ref>`); version mismatch => action fails safely (sec 5.1.1).
- Tools: click/type/hover/press_key/select_option/scroll(pan)/wait_for/navigate/navigate_back/snapshot/take_screenshot (sec 5.2).
- Bulk actions in one call when no intermediate verification is needed (sec 5.3).
- Failure adaptation: never retry identical action; analyse; try a different approach (sec 5.4).
- Only latest snapshot kept; snapshot size cap with explicit "[refs a-b trimmed]" marker; history compressed via per-step
  `evaluation_previous_goal` / `memory` / `next_goal` + rolling buffer of last K steps (sec 6).
- Prompt order for caching: static system -> session context -> history -> current snapshot (sec 7.2).
- Safety enforced by code: domain allowlist, sensitive-action block, least privilege (sec 8.4).

Clarification from user: "click every control on the page" (mongchiton `visual_buttons` benchmark) is ONE test case.
The product is a task/goal-driven agent.

## Outcome
A goal-driven, closed-loop Vision exploration engine ("agent loop") selectable per session, next to the current v4
controller-planner. Each step: worker returns a fresh versioned snapshot; model returns self-evaluation of the previous
step, memory, next goal and 1..N actions on versioned refs (or done/stop); worker executes in order, stopping the batch
when the page changes or a ref is stale; results + new snapshot feed the next step. The agent continues from the current
page (navigate/back are model tools) instead of controller restore/replay.

## Constraints
- AGENTS.md layering (api/application/domain/infrastructure/agents), prompts only in `apps/control-plane/agents/prompts/`
  with version + README, shared contracts in `packages/contracts`, Python via `uv`.
- Existing v4 engine untouched and remains default; same providers (`codex_cli`, `claude_cli` via current bridge). No new
  LLM provider/model without user approval.
- Evidence stays compatible with `benchmark/vision/accuracy/run.py collect/evaluate` (operations, before/after frames,
  locator bindings) so the independent benchmark can score the new engine; metrics/oracle unchanged.
- Budgets: max steps/calls, requests per minute, session seconds, snapshot char cap.
- Safety decided in code, never by the model.

## Non-goals (initial)
- No lightweight trimming LLM (needs provider decision) — deterministic trimming only.
- No removal/rewrite of v4; no change to metrics.py/oracle; no multi-tab workflows beyond current single-popup support;
  no real-time/canvas game control; no claim of prompt-injection immunity.

## Acceptance criteria (draft)
1. Session with engine=agent_loop runs the closed loop; each model call gets only the latest snapshot, the memory log and
   the last K steps; trace stores per-step evaluation/memory/next_goal and actions.
2. Ref from an older snapshot version is rejected with a safe error and no browser action.
3. Navigation/popup to a non-allowlisted domain is blocked or closed and recorded; sensitive actions (keywords, form
   submit, downloads) are blocked by code.
4. Bulk batch stops remaining actions after a page-changing action and returns a fresh snapshot.
5. Per-call input is bounded (snapshot cap with explicit trimmed-range marker; history compression).
6. The mongchiton click-all-controls task runs under agent_loop; `run.py collect` + `evaluate` produce `score.json`
   without metrics/oracle changes; the run never ends with `unsafe_replay` (no replay used).
7. v4 regression tests pass; default engine unchanged.
