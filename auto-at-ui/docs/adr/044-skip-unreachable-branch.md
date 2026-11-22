# ADR 044: Skip a branch whose restoration needs an unsafe replay

Status: accepted (approved by the user 2026-11-22, sprint phase 06; offline red/green; live pending)

## Context

Sprint live run 1 (iteration `6b68fe65`, session `4a1f649e`) ended `unavailable / unsafe_replay` after 32 of 47
oracle targets. The BFS queued a scan branch of state `bfb9ae9e` (hop 8). That state was reached through
same-URL clicks (tabs/characters): `url_restore_allowed=false` and no browser-history entry. Returning to it later,
the controller scrolled (op 120), the worker refused `back` before dispatch (`history_checkpoint_unavailable`,
op 121), and `restore()` raised `unsafe_replay` because the path holds non-replayable clicks. The guard was correct,
but it stopped the **whole session**. Root-level links (15 targets) stayed unvisited, although the root viewport
is still restorable by URL. Round 21 hit the same failure only after its last click, so it lost nothing. Coverage
therefore depended on the model's exploration order. Rounds 01–19 had 11 restoration terminals of this family.

## Decision

`restore()` raises `BranchUnreachable` (a `VisualOperationStopped` subclass, same code `unsafe_replay`) at the one
point where it refuses to replay a non-replayable path. That point comes before any replay primitive. For a frozen-input
(v4 accuracy) session, the BFS loop catches it for that branch only:

- retire the popped queue item and every queued item/page on the **same state id**: edges become `terminal` with
  `outcome_code="unsafe_replay"`; targets never dispatched go back to `pending` (and so still count as not covered);
- emit progress `state.branch_unreachable`; keep `stop_reason="unsafe_replay"`, so a session whose inventory stays
  incomplete still ends `unavailable / unsafe_replay`;
- if work remains, re-observe the live page read-only (`refresh_page`, a `setup` wait with new state/frame IDs)
  and continue with the next branch. Descendants are not retired in bulk: a descendant with its own restorable
  URL or history entry is still reachable, and each one is checked on its own.

Second, required change: for `visual_buttons` scope, `codex_propose` also rescans when the page's **document**
revision changed after the branch was observed. A completed `navigate` or `back` bumps `document_revisions`, and
each observation records its document revision in `observation_documents`. A first version compared every page
revision, including scrolls. It made the worker's bounded DOM-snapshot store overflow (`dom_snapshot_limit`) in
`test_page_batch_exhausts_siblings_saves_urls_and_never_repeats_home`, so it was narrowed to document changes. A restore by
navigate, replay or Back can recreate the same visible state in a **new document** with the same state
fingerprint. Proposing from the older snapshot then produced bindings that the exact-context preflight rightly
refused (`stale_dom_context`, which is terminal). The red/green fixture exposed this right after the first skip.
The rescan is a read-only `observe_dom`, so no operation is added.

Unchanged: no replay of any path with a non-replayable step and no repeated Back/click. An unknown operation outcome
still stops the session (`primitive` raises `action_outcome_unknown` before this handler). Checkpoint, exact-node,
private-form, origin and policy guards stay as they were, as do state/hop/step/call caps. The refresh counts against
`max_states`/`max_hops`. Sessions without frozen input keep the old terminal behaviour.

## Consequences

- One unreachable branch costs only its own targets, not every target after it.
- Each skip costs its restore attempts plus one read-only refresh (one state). The state cap bounds the total.
- The handoff and inventory stay honest: retired targets remain pending, `partial` still applies, and the session
  reason still says `unsafe_replay` when coverage is incomplete.
- Test: `tests/test_vision_page_batch.py::test_popup_restore_uses_returned_page_scroll_and_never_replays_effects`
  variant `history_overwritten_unreachable` (fixture `/coverage-history-overwritten-unreachable`): red before
  (session stops after the rejected Back at op 6, so "Top action" is never clicked); green after. The green run
  goes: skip, read-only refresh (op 7), root viewport restored through its replayable setup prefix (a rejected
  Back, then a `navigate` replay), and "Top action" clicked once. Sibling stays `pending` and is never clicked.
  No click is replayed, every Back is rejected before dispatch, and exactly one edge is retired.
  The 12 existing restore variants pass unchanged.
- Known limits (independent review, PASS): at the state/hop cap the post-skip refresh ends the session with
  `exploration_coverage_incomplete` instead of draining the remaining queue as `state_limit` edges; a run of
  consecutive skips raises the cursor hop by one each. Both are honest stops, not safety gaps.
- Rebuild `control-plane` and `temporal-worker` (`playwright-worker` only for the test fixture).
- Rollback: raise `VisualOperationStopped` again in `restore()` and remove the two `except BranchUnreachable` blocks.
