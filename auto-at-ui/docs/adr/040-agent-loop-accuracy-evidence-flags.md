# ADR-040: Opt-in agent evidence for the accuracy benchmark (click context, dom_path, inventory)

Status: implemented and validated offline, 2026-11-21; not deployed, no live session. User approved the three
items on 2026-11-21 (plan README, "Agent loop round 01 r7 handoff"), each behind its own flag, default off. The
oracle (`oracle-mongchiton-1280-v1.json`, hash `9242b33d...`), `metrics.py`, the 95% thresholds, the C/A/P/R
definitions, the agent prompt, the safety gate (`state_mismatch`), policy and caps are unchanged. Execution
contract v1 is untouched; the private worker contract v4 gains optional, additive fields only.

## Context

ADR-039 made `agent_loop` clicks creditable by role-locator binding and listed what the harness still cannot
see: the scroll offset and page URL of a click (31 of 47 oracle targets are below the first viewport), a locator
for controls without a name (15 targets), and any page inventory (`pages=[]`, so detection is 0/47 and the
inventory is incomplete). The three are evidence the control plane did not export; they are not model results.

## Decision

Three independent flags, all read only by the processor (`temporal-worker`), all default `false`. With a flag off
the worker request, worker behaviour, persisted rows, `/trace`, `/result` and harness output are unchanged.

| Item | Flag (`Settings` / env) | Worker capability | Effect when on |
|---|---|---|---|
| A1 click context | `vision_agent_click_context_enabled` / `VISION_AGENT_CLICK_CONTEXT_ENABLED` | `click-context-v1` | every confirmed click (`operations[].executed_click`) also carries `scroll_x`, `scroll_y` and `url_fingerprint` |
| A2 dom_path locators | `vision_agent_dom_path_enabled` / `VISION_AGENT_DOM_PATH_ENABLED` | `agent-dom-path-v1` | a main-document control without an accessible name (button, link, custom div/span) gets a `dom_path` locator and can be clicked |
| A3 inventory | `vision_agent_inventory_enabled` / `VISION_AGENT_INVENTORY_ENABLED` | none (control plane only) | each DOM observation is merged into the page inventory of the current state (`/result` `pages`) |

1. **A1.** `VisualExecutedClick` gains three optional fields. A serializer drops absent keys, so stored payloads, the
   `/trace` dump and the trace revision hash of every existing session are byte-identical (re-grounding retained
   iterations keeps working). The worker fills them from the state it verified equal to the observation at dispatch
   (that fingerprint covers scroll and URL), so they describe the click itself. The transport schema fills missing
   optional fields with `null` on the worker wire only; the control plane never keeps them.
2. **A2.** The worker session records the capability. In agent mode with it, an unnamed candidate gets
   `schema_version: v2` (button) or `v3` (link, div, span, input) `dom_path` descriptor and the click rule that
   demanded button scopes also accepts agent sessions. Named controls keep role/label/css locators; unnamed
   visual-only candidates (div/span matched by `visualButtonSemantics`) are listed only when unnamed. The state
   fingerprint is untouched, because it keys controls by geometry in scope `all`. The model now sees these controls
   as `button ""`; it has no way to tell them apart except by order, which is a prompt matter and is not changed here.
3. **A3.** The existing planner machinery is reused: `domain/vision_coverage.inventory` builds the page inventory and
   `uow.page_inventory` stores it in `visual_exploration_states.page_inventory` (a JSON column, **no migration**).
   The agent does not create a state per scroll, so `merge_inventory` accumulates the union per state (capped at the
   contract's 100 controls, then `truncated`). A write failure never stops the agent; the next observation retries.
4. **Harness.** `collect` and `ground` export what exists, both additive sidecars: `grounding.json` gains a
   `contexts` key only when a click carries a valid context, `inventory.json` exists only when `/result` has pages.
   Binding (`binding_error`) with a context: the click must be on the oracle page (`url_fingerprint` equals
   `sha256(source_url)`, the fingerprint the planner runs recorded for it), for the path rule and the role rule. The
   role rule may additionally place an in-flow control at the click's scroll offset; a fixed one still matches at
   offset 0; a candidate matching at both offsets for different targets is ambiguous and earns nothing.
   `run.py detect` derives detection from the inventory of the oracle page only: identified by `dom_path` descriptor
   key (same hash as the control plane), else by role plus normalized name when exactly one oracle example has them
   (several: left out of both sides); every other control on that page is unexpected; completeness needs an
   unscrollable, untruncated page with nothing skipped. Detection is never derived from clicks.
5. **Benchmarking a combination.** `run.py ground|detect|evaluate` take `--sources all|none|click_context,inventory`
   and `--label <name>` (artifacts `score.<label>.json` etc., the retained default artifacts are never touched), so a
   session captured with all flags is re-scored as if only some sources existed. A2 is not selectable after the fact:
   it decides which locator a live click used, so comparing it needs sessions run with that flag on and off.

## Why this does not make the measurement easier

- Every new check is an additional gate or a new source of facts: URL gate (new, only with context), scroll offset
  (can only add a candidate, uniqueness still required), ambiguity across offsets removes credit. No rule is loosened
  for data that lacks the new facts; partial or invalid context is treated as absent.
- Path locators from A2 use the unchanged historical rule `path == reference_path`; the role rule keeps its limits.
- The credit still requires the independent, content-addressed outcome review, frame checksums and `metrics.score`.
- Detection precision counts every unmatched control of the oracle page as unexpected, so a wider inventory
  (A2 shows unnamed controls the oracle does not list) lowers precision instead of hiding it.

## Consequences, costs and open limits

- A2 changes what the model sees and can click; A1 and A3 do not change agent behaviour. Whether A2 improves A, C
  or only exposes more wrong clicks is a live question; the flag exists to compare. `docs/vision-agent-operations.md`
  lists the run order.
- A3 enriches `/result` `pages` for agent sessions, so `conclusion.observed_controls` and `remaining_controls` change
  with the flag on (status stays `partial`: controls are `pending`; per-control status is not written).
- A2/A3 inventory merges are bounded at 100 controls per state; a long page truncates and reports it.
- Not verified live: capability negotiation against the rebuilt worker container, real-site dom_path stability
  under the carousel (`stable` wait for v3 paths), real inventory size and the agent's behaviour with unnamed controls.
- The three flags need `temporal-worker` and, for A1/A2, a rebuilt `playwright-worker` (a session that requires a
  capability the running worker lacks fails at open with `worker DOM capability unavailable`, it does not silently
  fall back). `control-plane` needs no flag: it serves whatever was stored.
- Rollback: set the flag to `false` and recreate `temporal-worker`; rows already written stay valid (optional keys).
