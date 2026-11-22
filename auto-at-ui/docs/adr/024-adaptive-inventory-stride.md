# ADR-024: Bound baseline scrolls by viewport overlap and clipped controls

- Date: 2026-11-09.
- Status: accepted; offline fixtures validated, live qualification in progress.

Accuracy-loop iteration 02 completed 26 clicks without failed operations, then
stopped before a required restoration observation at hop 10. Its initial inventory
used seven half-viewport scrolls. With 50 states, eight baseline observations also
leave at most 42 interaction-result states, below the 45 required by this benchmark.
Caps retain their meaning; neither observations nor clicks are uncounted.

For visual-button inventories, the worker computes a geometry-only forward stride
of at most 80% of viewport height and 2000 pixels. If a classified control crosses
the lower viewport edge and can fit within a viewport, reduce the stride to at most
its current top coordinate (minimum one pixel). Thus a tall control clipped by the
lower edge is brought fully into view rather than skipped by a fixed larger step.
Do not alter website animation, layout, DOM or classifier rules. Existing binding,
occlusion, consent, policy, page-state and observation-integrity guards still apply.

`CodexBoundObservation.next_scroll_delta_y` is optional bounded private metadata;
it is outside `CodexDomObservation`, so model input, prompt and consent are unchanged.
An older worker omitting it keeps the existing half-viewport baseline behavior.
Deploy compatible controller and worker together because older strict controllers
reject new private result fields. Execution v1, public API and persistence schemas
are unchanged. Other interaction scopes keep their existing scroll behavior.

Tests cover ordinary overlap, a 220-pixel control crossing the boundary and a
700-pixel control requiring only a 50-pixel step; the latter prevents accidentally
reintroducing the former minimum 100-pixel stride. An end-to-end fixture requires
45 distinct once-only clicks on a 2900-pixel page within 50 states and 10 hops.
The independent 47-positive/14-negative presentation fixture must still pass.

## Retain bindings for a fully unchanged click result

The first optimized-stride integration run still exhausted the retained DOM
snapshot cap: six regressions passed but the 45-button fixture failed with
`dom_snapshot_limit`. Baseline stride alone did not resolve redundant DOM scans.

For same-Page visual-button clicks only, reuse the original bound observation
when the worker reports unchanged full semantics, the child and source checkpoint
semantic fingerprints match, and their interaction fingerprints match the retained
observation. Record the new logical result state and both frames as before; copy
the inventory with current attempted statuses, without allocating another DOM
snapshot. A changed result or other action still gets a fresh scan. The worker
continues comparing private form values and exact live nodes before each action.
In particular, an identical replacement must be rejected rather than inherit an
already-approved sibling proposal. This is binding reuse, not replay, automatic
success or a reduction of the state/operation accounting. Add a replacement
integration case alongside the existing worker replacement and context guards.
