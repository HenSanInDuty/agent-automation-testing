# ADR 045: Observe visual buttons that move during DOM observation

Status: accepted (scope approved by the user 2026-11-22, h-fix gate 2); direction A2 (replaces direction A, which
failed the live A/B harness at 7/30 skipped scans); offline red/green; live pending

## Context

In `visual_buttons` scope, `observeDom` sometimes skipped the video frame `a.video-frame` (mct-47) on
mongchiton.vn (`skipped_count: 1`), so the benchmark saw an incomplete inventory. The character swiper autoplays
(delay 3000 ms, speed 600 ms, slide, `loop`). The DOM walk accepts a copy that lies fully inside the viewport at T0;
grounding reads that node's box at T1, while it is still sliding, and hit-tests the box centre. Another layer is
under that point: a non-control gives `unsupported_target`, another control gives `locator_target_mismatch`. Both
end as a skip (`unsupported_target` / `unbound_target`). The existing retry for `unsupported_target` runs at once,
still mid-slide. Settle does not see the motion either, because `visual_buttons` interaction entries carry no
geometry on purpose (vision-checkpoints.ts, "All visual-button actions carry v3 live-node bindings").

Direction A (wait for the node's box to stop, then ground again only if its centre moved from the walk centre) was
red/green offline but failed live (diagnostic log of the A/B harness, 5 skipped scans analysed):

1. 4 of 5: the candidate copy slid OUT and stopped outside the viewport (centre x about -399). Grounding it again
   gives `unsupported_target`; `equivalentState` does not flag the change because the copies are interchangeable. The
   result is a silent skip, and the copy that is now on show is never listed.
2. 1 of 5: the `loop` track jumped back, so the copy stopped at the very place where the walk saw it (final centre
   901 = walk centre 901). The box had moved, but `displaced` was false, so it was not grounded again.

## Decision

Only in `vision-dom.ts` (`observeDom`, `ground()`, the batch loop). Read-only; no contract, control-plane or
`equivalentState` change.

**Wait (unchanged from A).** When scope is `visual_buttons`, the candidate has a `button_path`, and grounding (after
the existing retry) failed with `unsupported_target`, `locator_target_mismatch` or `target_outside_viewport`: poll the
descriptor's own bounding box every 50 ms until two consecutive samples agree within 0.5 px (x, y, width, height), or
1200 ms pass. Nothing is clicked or scrolled.

**A2.1 Ground again after any motion.** Once the box is still, ground again when `moving || displaced` (A: only
`displaced`). `moving` = some sample differed during the wait; `displaced` = the final centre differs from the walk
centre by more than `BOX_CENTER_TOLERANCE_PX` (3 px, unchanged). A copy that went away and came back to the same place
is therefore grounded again.

**A2.2 Walk again once when the visible set changed.** If the box moved, is still, is not fully inside the viewport
(same criterion as the DOM walk: `x >= 0`, `y >= 0`, right and bottom edges within `viewport`) and grounding still
fails, the control set the walk saw is no longer what is on show. `ground()` sets `motion.invalidated`. After the
batch loop, if the flag is set and no repeat has run yet, the retained handles are disposed, the collected elements,
bindings and signatures are cleared, and the whole DOM walk plus grounding runs one more time (the page has just
stopped; the next autoplay slide is about 2.9 s away). The second pass does not wait again and does not repeat a
third time: a failure there stays a skip, as today. The final `equivalentState(before, after)` gate and the
`contextSignature` check still run once, for the last pass, against the state taken before the first walk. A single
control that slid out for good leaves the second walk with no candidate and no skip; the changed control set then
makes the state gate reject the observation (`state_changed_during_observation`), as it did before.

**A2.3 Observability** (counts only, no label or locator): `motion_waits`, `motion_regrounded` and the new
`motion_retraversals` are on `vision.dom.coverage_limited` and on the info event `vision.dom.motion_regrounded`. The
info event is logged when a wait led to a verified binding or a second walk ran.

**A2.4 Limit.** Per observation: at most one wait (1200 ms per batch, candidates of a batch in parallel) and at most
one repeated walk. Continuous motion (never still within 1200 ms) is skipped as before and does not repeat the walk;
a node that disappears is not a stop outside the viewport and does not repeat the walk either.

**A2.5 A miss after the repeat stays a skip (phase 02).** The repeated walk replaces `skipped` and the skip reasons of
the first walk, so a candidate that motion invalidated and that the second walk could not rebind used to leave no
trace (`skipped_count` 0 with the control missing; QA phase 01 saw 1 of 80 scans). Now `ground()` marks a first-walk
candidate that set `motion.invalidated`, and the batch loop keeps its role, name, kind and normalised skip reason
(`lost`). After the last pass each `lost` entry is matched with one bound element of the same role, name and
`button_kind` (one bound element covers one entry). No twin: `skip(reason)` and `unbound_target` in `unsupported`, so
`coverage_limited` is logged with the original reason. A twin is bound: nothing is counted, so T-loop-out and
T-loop-jump keep `skipped_count` 0. Entries are only collected during the first pass; the second pass counts its own
skips as usual, so nothing is counted twice.

Twin key: the fingerprint identity of a `visual_buttons` control (`vision-checkpoints.ts:162-168`: tag, id/testid/
name/role/href/aria/title/alt attributes, labels, text) lives inside a browser callback and is not exported, and the
walk candidate does not carry the attribute list. The check therefore uses the part of that identity the candidate and
the bound element both expose: role (from tag or `role`), name (aria-label, labelled-by, title, text) and
`button_kind`. Two links with the same text and kind but different `href` count as twins.

Unchanged: `equivalentState`, settle, the contract, error codes, the Python side, batches of 8.

## Limits

- Worst case adds about 1.2 s (wait) plus one DOM walk and one grounding pass to an observation, only when a visual
  button candidate failed for one of the three reasons while its box really moved and stopped outside the viewport.
  A static page adds no wait beyond one 50 ms poll for a candidate that is already failing and counts no `motion_waits`.
- Each box read has its own timeout (250 ms, capped by the time left), so a node removed or recreated during the
  wait cannot hold a candidate, or its batch, past the ceiling; the read counts as "no box" and the old result stands.
- A slide longer than the ceiling (not seen: 600 ms) would still skip; raise the ceiling then.
- If the second walk happens to run while the next slide has already started (more than about 3 s late), it can still
  skip or be rejected by the state gate; the control plane refreshes as it does today.
- Other scopes (`all`, `buttons`) are not touched.
- Known limit, not fixed in phase 02 (pre-existing, common to every scope): a walk that runs while no copy is fully
  inside the viewport (a track stopped between slides, or a walk during a slide) has no candidate, so nothing is
  skipped and nothing is repeated; the observation lists no such control and `skipped_count` stays 0. A live scan with
  the control visible but unbound and `skipped_count` 0 is explained by this path. The same stop position reached
  after a slide that began fully visible is the `lost` case above and is counted.
- The twin key ignores `href`, so a lost link can be hidden by a different link of equal text and kind (rare: slides
  repeat the same control). Exporting the identity key from `vision-checkpoints.ts` would close it.

## Safety risk

Low. The wait and the second walk only read the page (bounding boxes, the same DOM walk, the same grounding). A
binding is still verified by `groundLocator` (exact-node, visible, enabled, inside the viewport) and by the final
state gate; dispatch-time preflight and exact-node checks are unchanged. A moving page can only turn a skip into a
bind of a verified node, or into a rejected observation. Handles held by the first pass are disposed before the
second pass in every branch; the existing `finally` still disposes everything when the observation fails.

## Tests

`workers/playwright/src/vision-dom.spec.ts`:

- Direction A tests, unchanged: slide under a non-control layer binds with `skipped_count` 0; slide under a pointer
  control (mismatch) binds; a removed node ends fast with `state_changed_during_observation`; continuous motion is
  skipped with 1 `motion_waits` (now also 1 walk and `motion_retraversals` 0), delay 1.1 s to 4 s; a static covered
  link has `motion_waits` 0 and no `motion_regrounded` event.
- Slide out of the viewport (TC-03), expectation changed for A2: exactly 2 walks, no snapshot, and the observation is
  rejected with `state_changed_during_observation` (not a skip).
- `T-loop-out` (red on A, green on A2): a swiper `loop` fixture of three slides with identical links and edge layers.
  The copy seen at rest slides out and stays outside the viewport; its twin is on show. Expect the twin bound,
  `skipped_count` 0, `motion_retraversals` 1.
- `T-loop-jump` (red on A, green on A2): the track slides and then resets, so the copy returns to the place where it
  was seen. Expect it bound again (`motion_regrounded` 1, `motion_retraversals` 0), `skipped_count` 0.

- `T-loop-lost` (red on A2, green now): same fixture, the track slides to a stop between two slides, so no copy is
  fully inside the viewport once it is still. Expect no element, `skipped_count` 1, `unbound_target` in
  `unsupported`, `coverage_limited` with `skip_reasons.unsupported_target` 1 and `motion_retraversals` 1.
- Walk during "no copy fully in the viewport" (characterisation of the known limit): the track rests between slides
  from the start. Expect no error, no element, `skipped_count` 0, no `coverage_limited` event.

Manifest source hashes for `vision-dom.ts` and its spec were regenerated (`tests/test_codex_bridge_benchmark.py`).
The live gate is the read-only A/B harness against the site (30 scans to 1152, expect 0 skips); it has not run yet.
