# Agent prompts

This directory is the single source of prompt text sent by control-plane agents.
Keep prompt changes reviewable, version a prompt when its behavior changes, and preserve
the existing fail-closed, advisory boundaries.

| Module | Consumer | Purpose |
| --- | --- | --- |
| `generation.py` | `agents.generation.planner` | Governed Playwright test drafting. |
| `vision.py` | `agents.vision.service` | Bounded visual-action exploration. |
| `triage.py` | `agents.triage.executor` | Advisory failure classification. |
| `demo.py` | `agents.demo.weather` | Local weather demonstration only. |

Callers own request/evidence serialization, provider payload construction, validation,
and authorization. Prompt modules must not access persistence, credentials, or runtime
configuration.
