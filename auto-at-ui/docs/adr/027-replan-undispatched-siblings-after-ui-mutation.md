# ADR 027: Replan undispatched siblings after local UI mutation

Status: implemented; isolated regressions passed, 2026-11-09.

Live loop 06 stopped after selecting the Events news tab at 37 clicks, 52 states
and hop 15. The new 100-state/20-hop policy was not exhausted. Siblings remained
queued against the prior checkpoint. The new child inventory filtered out those
queued controls, so no fresh proposals were generated; later restoration of the
old selected-tab state correctly failed. Retrying Back cannot recover a local
UI transition that created no history entry.

For frozen visual-button exploration only, a completed, non-replayable click that
changes the interaction-state fingerprint on the same Page, URL and scroll position terminates
still-undispatched sibling proposals on the same observed Page and URL. Retain each
old edge with terminal `stale_dom_context`; never rewrite its parent/proposal.
Release only target entries whose queued proposal ID still matches and which
have no operation ID. Inventory returns those targets to pending; completed,
failed and rejected attempts remain untouched.

Scan the actual live child and obtain fresh model proposals under existing call,
state, hop and deadline limits. Do not migrate old handles, bypass original state
verification, replay the mutation, or count proposals as physical attempts. If
the budget cannot supply a new proposal, retain a truthful partial outcome.

Keep existing bindings for unchanged interaction state: an identical-node
replacement must still fail old live-node verification. Do not broaden this to
unobserved hidden-form mutations, cross-page navigation or unknown dispatch.
Prompt, execution v1, private transport shape and policy caps remain unchanged.

Scroll-changing clicks keep the original restoration path and its guards. A
viewport shift changes the interaction fingerprint without proving a local UI
mutation; invalidating those proposals bypassed the intended popup-return
restoration scenario in three regression cases. Require equal scroll coordinates.

Regression coverage includes two stateful tabs, a fixed hidden form preventing
direct URL restoration, exhausted model-call budget, identical replacement,
unchanged batches, deeper UI chains and existing restoration guards.

Loop 07 exposed a second instance across viewports: the source branch for a
queued target at y=1152 predated the local mutation at y=576. Releasing only the
exact source branch left the target filtered out of the new child inventory.
The cross-viewport fixture failed with `unsafe_replay` before this extension.
Release matching queued entries across observed branches of the same Page/URL;
do not release entries from another tab, URL, dispatched operation or attempted
target. Existing other viewport checkpoints remain immutable and restoration
must still verify them; fresh child inventory may supply new proposals.

Cross-viewport matrix `69ac3d7f2cda`: 15 old regression cases passed; the new case
performed all four intended clicks with fresh proposals, but truthfully retained
`exploration_coverage_incomplete` for its superseded, unscanned top viewport.
Its assertion now checks that conservative conclusion plus all exact-once
clicks, no failed/unknown operations, no replay/Back and terminal old-proposal
audit. Final focused run `41f4d1039001`: one passed (15.177s). No production
conclusion rule was relaxed to satisfy this fixture.

Final isolated matrix `d41a656cf309`: 15 passed, zero failures/skips/errors,
224.246 seconds. Ruff, worker typecheck and generated-contract check passed.
