# ADR 030: Preserve visible targets when scheduling independent proposals

Status: implemented; isolated validation passed, 2026-11-09.

Iteration 10 reached the Mounts tab before four character selectors from the
same visible panel. The before/after frames show those character controls being
replaced by mount controls. Four later clicks were correctly rejected as stale;
restoring the original local UI also required an unavailable history entry.
Rebinding those old proposals or repeating the tab click would weaken safety.

The existing v11 prompt explicitly requests distinct independent actions. For a
frozen visual-button batch containing only validated clicks with v3 DOM-path
bindings from the current observation, schedule styled links first, then deeper
DOM paths before shallower paths. Stable ties retain the model order. This lets
known destinations be visited before a local tab can change their href, and
panel children before a shallower tab switch can hide them. It is a scheduling
heuristic, not proof of reversibility or general dependency inference.

Do not invent an action, promote an unproposed target, change a binding or relax
worker validation. Mixed actions, older bindings, other scopes and observations
that do not match retain their original order. Proposals, operations and bridge
responses remain auditable. No prompt text/version or execution contract changes.
Every original-checkpoint/live-node guard remains mandatory at dispatch.

A fixture with hidden form state, two parent tabs, two nested child controls and
a navigation link reproduces lost coverage in the original order. The corrected
schedule must visit the destination, click each child exactly once, then switch
tabs, without replay or discarded failures. Broader navigation, mutation,
identical-replacement, dataset and popup restoration regressions are required.
Final matrix `738e59068388`: 19 passed, zero failures/skips/errors (490.04s
pytest runtime), including the 45- and 47-button fixtures. Ruff and worker
typecheck passed. The panel fixture verifies all five approved clicks from one
model batch, navigation first and child controls before the tab switch.
