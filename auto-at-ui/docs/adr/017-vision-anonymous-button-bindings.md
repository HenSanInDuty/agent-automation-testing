# ADR-017: Live bindings for anonymous buttons

- Status: Local implementation for the user's all-buttons exploration request.
- Date: 2026-11-01
- Extends ADR-016; execution request/result contracts remain v1.

The target has native buttons with no accessible name or stable identifying
attribute. Omitting them prevents completing an all-buttons request. Add an
explicit v2 `dom_path` locator descriptor for main-document native buttons only.
Its grammar contains tag names and bounded `nth-of-type` indices, never arbitrary
CSS, executable selectors, page text or sensitive attributes. Stable locators keep
their existing v1 grammar and length bound. The controller requires the new
`anonymous-button-v1` worker capability for button-scoped sessions.

Only worker DOM observation may create this fallback, after ordinary unique
locators fail and only for unnamed native buttons. Duplicate named buttons remain
ambiguous. Retain the original element handle with the snapshot. Resolving a
proposal checks that the path still identifies that same connected node; replacing
a node at the same path cannot inherit the proposal. The controller never rebinds
an ephemeral proposal to a new snapshot. The worker repeats node identity checks
after capture and before dispatch, and clicks the original element handle without
force. It does not resolve the path anew at the moment of clicking. Context closure
releases the handles; the existing snapshot and element limits bound retention.

For otherwise anonymous main-document buttons in explicit button scope, readiness
uses their structural identity and center hit test instead of animated bounds
and corner samples. Round pagination dots changing to pills have different corner
hit masks even though their click point stays unobstructed. Fresh bounds and hit
targets are checked at dispatch and Playwright waits for the retained node's
actionability. Actual click-event evidence is required instead of the geometric
fallback. Named-control geometry, URL, viewport scroll, enabled/disabled state,
accessible names, transparency, occlusion, landmarks and private form changes
retain their existing checks. Reparenting an anonymous button changes its path.
Full visual semantics and before/after frames remain available for audit.

An ephemeral locator is not a durable test selector. Handoff branches containing
one are explicitly blocked with `ephemeral_locator`; a successful advisory click
does not automatically approve or execute a generated test. Keep the selected
provider/model, consent, redaction, call/cost budgets and existing approval boundary.
There is no new model prompt or transfer of DOM paths to the model's observation.

Validation covers grammar rejection, same-path node replacement, relocation before
dispatch, named-control movement, scope rejection for links and blocked handoff.
Live validation completed on 2026-11-01 in session
`d802f4a3-eb24-4e53-9b96-f12b6763128e`: all 15 distinct button targets
(six named, nine anonymous) completed, with 78 completed operations, three
completed model jobs, 48 states and maximum observed hop seven. No skipped or
truncated inventories were recorded. The session finished `completed` without a
failure reason; Loki returned no operation-failure, state-mismatch or limited-
coverage events for this session. This verifies advisory exploration of this
target, not a functional test verdict or the full standard live canary. See
`benchmark/vision/codex/mongchiton-regression-20261101.json` for the run summary.

The original project depth of five stopped branches after reaching the carousel,
even when every observed target had been clicked. Session
`fb96528b-2502-496a-93f7-461cc61b4f86` recorded 60 completed operations and all 15
button targets completed, but correctly retained incomplete coverage. Increase
this local project's `vision_max_hops` from 5 to 10 with an audit entry; retain
50 states and 20 model calls. Old sessions and their limit snapshots are immutable.

An anonymous target's point is resolved again after DOM collection, after the
before-frame capture and before dispatch. These are read-only identity/bounds
checks, not physical-action retries. A page transition during capture must not
cause the worker to test the previous pixel against an adjacent carousel button.
Pixels may naturally move between frames; successful anonymous clicks require
the actual browser click event on the retained node, never inferred coordinates.
