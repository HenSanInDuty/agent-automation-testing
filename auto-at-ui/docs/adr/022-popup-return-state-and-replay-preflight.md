# ADR-022: Observe the returned page and preflight the entire replay path

- Status: Accepted for local implementation under the requested stability continuation.
- Date: 2026-11-09
- Extends ADR-015 and ADR-021.

The last November 8 Mongchiton session completed 19 clicks and 10 popup closes,
with after evidence for all 62 operations, then stopped at `unsafe_replay`.
The controller closed a popup but still used that popup's checkpoint URL and
scroll offset to decide how to restore its opener. Consequently it could skip
reversible scrolling on the returned page and attempt back/replay instead.
Replay also executed a safe prefix before discovering a non-replayable click
later in the path.

Keep a separate restoration observation, without changing queued branch
checkpoints or bindings. When a page switch leaves that observation on another
tab and the destination checkpoint does not match, record a bounded read-only
refresh on the active page. Use its actual URL and scroll offset to calculate
the existing reversible scroll. Retain page identity checks, exact target
checkpoint equality (including private forms), fresh locator binding and all
prepare/execute guards. Nested popup closure uses the same fresh-page rule.
Each observation consumes the existing state and operation budgets; missing
evidence, identity changes or exhausted budgets stop without a sibling click.

Before replay begins, require every operation in the entire requested path to
be replayable. If any is not, stop `unsafe_replay` before executing any prefix.
Never repeat a non-replayable click, overwrite a saved source checkpoint, or
treat new evidence as proof that an old branch was restored.

The regression uses a synthetic button that reveals controls, a button that
scrolls to the top, an upper-page popup and a pending lower-page sibling. It
checks return-page evidence, scroll restoration, exactly one click per target
and zero replay. A variant changes a private form value while opening the popup;
the pending sibling must remain unclicked and replay must not start.

The subsequent live trial passed this restoration path but reached the unchanged
DOM snapshot cap after 26 clicks and only 37 states. V3 target rebinding collected
another observation before every click even when a child-state scan already held
the same verified page state. Track each page's completed navigation, back,
same-page click, type and scroll revision. Reuse a retained observation only when
page identity, revision and state fingerprint all match, after independently
restoring the complete source checkpoint. Resolve the same unique descriptor;
the worker still checks the retained exact node, classification and actionability
at prepare and execute. Otherwise collect a new observation as before.

Do not raise or evict around the snapshot cap. A 12-button no-op fixture with a
15-state cap verifies one click per button without redundant snapshot exhaustion.
The existing navigation, replacement-node and partial-coverage regressions remain
applicable. A separate policy-reduction test verifies the returned-page refresh
cannot exceed the current state limit.

A subsequent live load captured a blank initial SPA before hydration. Its raw
session state was completed with no controls, while the conclusion correctly
retained `not_established` coverage. A read-only probe saw HTTP 200 and zero
buttons at DOMContentLoaded, then 14 buttons at approximately 1.5 seconds.
For an initial non-scrollable viewport with no buttons, allow at most two
explicit read-only refreshes within the existing state, hop, operation and step
limits. If still empty, stop `exploration_coverage_incomplete` without a model
call. A controlled hydration fixture and a permanently empty fixture cover both
outcomes. This is bounded evidence acquisition, not a physical-action retry.

History restoration has the same asynchronous rendering boundary: Back can
change the URL while the previous route's content is still painted. After one
completed Back, permit at most two bounded read-only refreshes and recheck the
original checkpoint after each. Never repeat Back, replay a click or accept the
refresh checkpoint as the source state. A controlled SPA fixture renders its
source only after the Back response; its permanently unrendered variant must
still stop `unsafe_replay` with zero replay and no pending sibling click.

A successful checkpoint read alone does not update the controller's captured
fingerprint. If the page reaches the checkpoint after the Back image was taken,
still record a refresh before the verification wait; both the checkpoint match
and captured fingerprint must agree to skip that refresh.

Provider/model, prompt v11, transfer consent/redaction, call/rate limits,
retention, tenant isolation, human approval and execution v1 remain unchanged.
Validation and separately authorized live outcomes are recorded in
`benchmark/vision/sequential/COMPLETION-20261109.md`.
