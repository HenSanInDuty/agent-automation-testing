# ADR-039: Credit `agent_loop` clicks through strict role-locator binding in the accuracy harness

Status: implemented and validated offline, 2026-11-21. Harness-only change; the oracle
(`oracle-mongchiton-1280-v1.json`, hash `9242b33d...`), `metrics.py`, the 95% thresholds, the
C/A/P/R definitions and the evidence requirements are unchanged. No live session, deployment or
model call was part of it.

## Context

The first valid `agent_loop` session (AGENT-LOOP-01 r6, iteration `1c56623e...`) scored C 0/47 and
A 0/12 although 5 of its 12 clicks matched oracle targets and were reviewed correct by hand. The
harness only bound a click to the oracle when the evidence locator's `dom_path` equalled the oracle
`reference_path`. The agent loop grounds elements with the `role` strategy (role + accessible name),
so the exported `path` was `null` and every credited assessment failed with
`assessment binding does not match oracle`. This was a measurement gap, not a model result.

## Decision

1. `collect` also exports a `grounding.json` sidecar (`vision-accuracy-grounding-v1`, allowlisted):
   for every `role` locator its role, accessible name, normalized box, the operation's viewport and
   confirmed click point. `evidence.json` keeps its schema, so retained runs are byte-identical.
   `run.py ground` adds the sidecar to evidence collected earlier from the same stored trace and
   refuses it if the trace revision, session or locator set differ.
2. A credited operation binds to an oracle target by exactly one of:
   - **Path locator (unchanged):** `path == reference_path`. Any locator with a path uses only this rule.
   - **Role locator (new, stricter):** the operation is on the session's root tab (the page of the
     first completed setup navigate; popups and new tabs earn nothing); the locator viewport equals
     the oracle viewport; the oracle candidates with the same role (`a` -> link, `button` -> button),
     the same normalized name (accent, case and spacing insensitive, non-empty) and box IoU >= 0.8
     are exactly one; that candidate is the reviewer's `target_id`; and the executed click point is
     inside the oracle `reference_box`. Zero or several candidates, other tags and unnamed controls
     earn nothing. Each oracle target can be credited by at most one role-bound operation.
3. Detection and inventory are not derived. `agent_loop` persists no DOM snapshot or page inventory
   (`visual_exploration_states.page_inventory` is NULL, `/result` has `pages=[]`, step logs keep only
   refs). The harness therefore keeps `inventory_complete=false` and no identified IDs for such runs.

## Why this does not make the old measurement easier

- The path rule is untouched; role binding is reachable only when `path is null`, which was an
  unconditional failure before. A test re-scores every retained run with `score.json` and checks each
  credited assessment still passes the path rule and reproduces the stored score exactly.
- Credit still needs the same independent, content-addressed outcome review, frame checksums and
  `metrics.score` rules. Binding is an extra necessary gate, never a replacement.
- Role binding is conservative: below-the-fold targets (no scroll offset is exported), unnamed icon
  controls and non-link/button tags cannot be bound and stay uncredited; unverifiable cases count
  as attempts in accuracy.

## Consequences and open limits

- Under today's evidence the credit ceiling of role binding is 16/47 (positives inside the first
  viewport, named, link/button); 31 are below the fold and 15 (icon-only or `div`) are unnameable, so
  at most 32/47 even with scroll evidence. C > 95% and inventory completeness need evidence the
  control plane does not export (scroll offset and page URL fingerprint per operation, an inventory
  per observation, or `dom_path` locators for unnamed controls). Those are contract/control-plane
  changes and need a separate user decision.
- The page URL of a click is not exported either, so a header link clicked on another page of the same
  site binds like the homepage one (same label, role and place). Retained frames and the outcome
  review still decide whether the observed outcome matches the declared destination.
