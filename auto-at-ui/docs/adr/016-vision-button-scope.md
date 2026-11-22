# ADR-016: Enforce explicit button exploration scope

- Status: Accepted for local implementation at the user's request.
- Date: 2026-11-01
- Extends ADR-014 and ADR-015.

Session 01d36d74-165f-4633-b0e7-741c6148aa25 stopped after four valid button clicks.
A read-only reproduction at scrollY=1152 showed carousel links and custom pointer
controls changing geometry every few seconds. Those out-of-scope interactions
invalidated the whole-page checkpoint while the model planned a button action.
Prompt scope alone also left links in the pending inventory.

Recognize a conservative set of complete English/Vietnamese all-buttons requests
from the retained user intent, never from page text. Mixed, negated, named or
unrecognized requests keep the existing general mode; keyword presence alone
does not select a scope. Require the worker's `button-scope-v1` capability before
opening a scoped session. The optional worker-open scope defaults to `all` for
existing clients. No execution request/result contract version changes.

In button mode, DOM proposals and retained inventories contain semantic buttons
only. The worker rejects link/type actions before dispatch, including coordinate
proposals. Explicit role=button, native buttons and button/submit/reset inputs
qualify; pointer styling alone does not. Popups inherit the session scope.
Inventories retain the scope and the dashboard labels it.

Checkpoint readiness compares in-scope button identities, semantics, geometry,
disabled/transparent state and hit tests. URL, scroll, modal/landmark transitions,
iframe geometry and private page-wide form state remain relevant. A moving link
that covers a button still changes its hit tests and invalidates the action.
Full semantic observations and screenshots retain out-of-scope changes for audit.
Do not freeze the site or claim its unrelated animations were tested.

An empty eligible DOM requires no model call: the existing bounded viewport loop
scrolls to find lower controls. A model-proposed downward scroll also satisfies
that source viewport's scroll request, rather than restoring and scrolling it
again. All operations retain paired evidence and the existing state/hop/call
budgets. Incomplete or failed coverage is still reported, never marked passed.

Validation covers mixed/negated intent, moving out-of-scope links, button motion,
occlusion, renaming, disabled state, hidden form changes, worker rejection of a
link click, and a synthetic page with only links above one lower button. The
provider/model, consent/redaction, cost/rate configuration and approval boundary
are unchanged. Deploy compatible controller, worker and dashboard after sessions
drain; older workers reject the required capability.

Live validation on 2026-11-01: session
`1570de51-1461-4386-890c-5727725c5b03` reached and clicked six named buttons,
including the lower character/mount tabs. It still stopped before a later scroll
with `state_changed_during_prepare`. A separate read-only inspection found an
unnamed search button and eight unnamed carousel buttons; the pagination buttons
periodically change width. These remain unsupported by the existing stable
locator contract and cannot be silently counted as completed. This is not a
successful full-site canary.

Emit `vision.dom.coverage_limited` with bounded, fixed skip-reason counts and
`vision.state.mismatch` with changed-component booleans. Never log raw labels,
locators, form values or exception text. Propagate the recorded worker outcome
code for failed scroll/click operations instead of hiding it behind the generic
`capture_or_action_failed` reason.

Session `1c7c3814-da99-4738-9b86-a72e5f3e6020` confirmed the remaining coverage
limits in Loki and completed both model calls and all 22 physical operations,
then exposed `unsafe_replay` while returning to a deferred button child. For
button-scoped exploration, prioritize pending actions on the current state and
inspect live children whose ancestry includes a non-replayable click before
leaving for siblings. Returning within the same page may first scroll back by a
bounded delta, then must match the original full checkpoint before adopting its
ancestry. This never replays a button click or relaxes private-form equality.
Model-call exhaustion stops new proposals but still allows bounded deterministic
observations to document remaining coverage; it never authorizes an unplanned click.
