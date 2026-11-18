# Agent prompts

This directory is the single source of prompt text sent by control-plane agents.
Keep prompt changes reviewable, version a prompt when its behavior changes, and preserve
the existing fail-closed, advisory boundaries.

| Module | Consumer | Purpose |
| --- | --- | --- |
| `codex_exploration.py` | Local Codex bridge | `codex-dom-v11`: controller owns viewport scrolling; the model returns `stop/no_safe_action` when no matching action is visible and never chooses a scroll distance. Retains v10 button classification, distinct positions, scope, consent, bounded batches, strict JSON and advisory-only proposals. |
| `generation.py` | `agents.generation.planner` | Governed Playwright test drafting. |
| `codex_generation.py` | Local Codex bridge | `codex-generation-v1`: text-only advisory planning using the existing generation/grounded-selection prompts; immutable tool-free instructions, schema validation and human approval. |
| `vision_generation.py` | `agents.generation.vision_plan` | v1: select immutable branch/assertion references for deterministic rendering. |
| `vision.py` | `agents.vision.service`, `agents.vision.executor` | v6: explicit pixel-to-normalized arithmetic and top-strip decimal example; eight-word outcome descriptions to conserve the existing response budget. Retains screenshot bounds, scroll-first offscreen proposals and trusted locator/restore checks. |
| `triage.py` | `agents.triage.executor` | Advisory failure classification. |
| `demo.py` | `agents.demo.weather` | Local weather demonstration only. |

Callers own request/evidence serialization, provider payload construction, validation,
and authorization. Prompt modules must not access persistence, credentials, or runtime
configuration.
