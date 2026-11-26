# Agent prompts

This directory is the single source of prompt text sent by control-plane agents.
Keep prompt changes reviewable, version a prompt when its behavior changes, and preserve
the existing fail-closed, advisory boundaries.

| Module | Consumer | Purpose |
| --- | --- | --- |
| `codex_exploration.py` | Local Codex bridge | `codex-dom-v11`: controller owns viewport scrolling; the model returns `stop/no_safe_action` when no matching action is visible and never chooses a scroll distance. Retains v10 button classification, distinct positions, scope, consent, bounded batches, strict JSON and advisory-only proposals. |
| `agent_loop.py` | Local Codex/Claude bridge (`codex_bridge_cli.py`) | `agent-loop-v3`: browser-agent closed loop (engine `agent_loop`). v3 (ADR-046): the agent ends with a `task_result` (status achieved / not_achieved / blocked, summary, per-expectation checks), an advisory assessment and never a test verdict; it verifies each expected effect in the next snapshot and, because the snapshot lists controls only, asks for a screenshot before judging an expectation about page text (first live run: a visible error message was reported `not_met` from the snapshot alone); the cover-the-whole-page rules apply only to whole-page tasks; a platform-stated `Target mode` line selects read-only rules (default) or owned-test-target rules (forms may be filled and submitted, task e-mail/number values are not masked). Block order for prompt caching: instructions, agent response schema, task + allowed hosts + limits, memory + last 5 steps, current snapshot (last, inside an untrusted-page-data delimiter). Multi-action steps (up to 10), 40 s per call awareness, failure rules, `version:n` refs, allowlist-aware observe-only rule, stop/need_screenshot outcomes. v2 (r11): cover the starting page first, return via navigate/back and scroll while `more below: yes` or `N control ngoài snapshot` is shown, no `complete` before that; v1 had no such rule (r10 live stopped with 9 homepage controls skipped). Independent of `codex-dom-v11`, whose text and schema are unchanged. |
| `generation.py` | `agents.generation.planner` | Governed Playwright test drafting. |
| `codex_generation.py` | Local Codex bridge | `codex-generation-v1`: text-only advisory planning using the existing generation/grounded-selection prompts; immutable tool-free instructions, schema validation and human approval. |
| `claude_bridge.py` | Local Claude bridge (`claude -p`) | `claude-bridge-system-v1`: replaces Claude Code's default coding-agent system prompt; the task prompt is the unchanged shared `codex-dom-v11` text and schema, so Codex and Claude rounds receive identical task input. |
| `vision_generation.py` | `agents.generation.vision_plan` | v1: select immutable branch/assertion references for deterministic rendering. |
| `vision.py` | `agents.vision.service`, `agents.vision.executor` | v6: explicit pixel-to-normalized arithmetic and top-strip decimal example; eight-word outcome descriptions to conserve the existing response budget. Retains screenshot bounds, scroll-first offscreen proposals and trusted locator/restore checks. |
| `triage.py` | `agents.triage.executor` | Advisory failure classification. |
| `demo.py` | `agents.demo.weather` | Local weather demonstration only. |

Callers own request/evidence serialization, provider payload construction, validation,
and authorization. Prompt modules must not access persistence, credentials, or runtime
configuration.
