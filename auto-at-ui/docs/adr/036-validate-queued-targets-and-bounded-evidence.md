# ADR 036: Validate queued targets, bound capture cost, unify restoration proof

Status: implemented and validated offline, 2026-11-18. User authorized the three
priorities in the rounds 01?19 retrospective before round 20. No live round or
service deployment is part of this implementation unit.

## Approved target continuity

Add a read-only, capability-negotiated `target-preflight-v1` endpoint to private
worker v4. It checks an approved snapshot/element against the current page and
saved checkpoint. It allocates no operation or DOM snapshot, performs no click,
scroll or navigation, and cannot return new target identities. Tenant/session/
project/fencing and response IDs are verified. Older workers fail capability
negotiation before execution; execution request/result v1 is unchanged.

Verify original live-node identity in the same document, per-node action signature
(including destination), bounds, hit target, interaction state, private forms,
page and context. Equal labels or hrefs do not collapse distinct positions.
Across a restored document, require explicit controller restoration and complete
original checkpoint equality; an unrequested same-URL reload cannot be adopted.
The action signature includes all target attributes except cosmetic class/style,
text, resolved destination and form action/method. It excludes ancestor whitespace;
full post-model revalidation signatures remain unchanged. After verified Back or
navigation, including SPA history that recreates nodes, check queued siblings
individually before rebinding them to that restored observation. Their next check
again requires exact retained nodes. This avoids carrying obsolete document
handles into later actions or granting blanket permission to adopt later reloads.
Recheck private context after the read. Emit only fixed booleans and correlation
IDs, never hrefs, text, raw errors or form values.

For a stale undispatched target with unchanged document/private context, terminate
its old proposal and queued siblings on the same page/URL with audit records.
Release only queued entries without operation IDs. Observe a new branch and ask
for a new model proposal within existing state/hop/call/deadline limits. Context
or private-form drift stops the path. Keep original checkpoint and proposal
records. The check happens before stale local restoration where the current
viewport is already the target viewport. Same-document success retains the
original snapshot/node token through prepare rather than substituting a newer
node at the same path. Worker prepare and dispatch guards remain mandatory.

This prevents stale-node/destination-copy proposals from silently inheriting a
replacement. It does not hard-code the benchmark oracle, merge video copies, or
claim an unreviewed copy is mct-47. Frozen-oracle coverage still needs live review.

## Representative sample cost

The load fixture has 575 extra DOM nodes, a deterministic large PNG surface and
one CPU/1 GiB limits, retaining the 1280x720 viewport and 500 ms sample budget.
Original capture misses the selected slide. The optional sample now uses fast
lossless PNG encoding and interaction-only readiness reads. Passive semantic
serialization is omitted only from readiness; interaction, URL, viewport,
page-wide private forms (including shadow/frame/hidden inputs), landmarks and
node limits remain identical. The required 160 ms quiet window remains.

The image is still bracketed by matching state; the post-image read uses complete
semantics, so lightweight metadata cannot become a retained checkpoint. Final
settle, page/document/target checks, popup/download handling and byte-size guards
remain unchanged. Larger fast-encoded PNGs are discarded if over budget. Tests
compare complete/fast guard behavior and decoded PNG pixels, with late mutation,
navigation and timeout fallback. No site animation or clock is modified.

## One restoration evidence matrix

Use one pure rule for refresh waits, restore verification waits and popup close:
explicit no-dispatch status, exact stage/code, known page and a matching retained
before-frame. Prepare rejection requires no after-page/frame and
`action_not_executed`; before-dispatch rejection requires matching retained after
evidence on the same page. Popup close additionally requires a distinct known
parent. Missing/legacy/unknown/dispatched evidence does not authorize recovery.

Both preparation and dispatch races during restore verification use the original
checkpoint and shared deadline. Read/close retries stay bounded; click/type/
navigation/Back are never authorized for replay by this rule. The rule matrix and
browser integration matrix include private forms, page/node drift, missing proof,
persistent changes and exhausted budgets.

Validation results and remaining scope are recorded in the canonical plan
README and `benchmark/vision/accuracy/pre-round20-validation-20261118.json`. Model, prompt, oracle and
policy limits remain unchanged; a live qualification claim is out of scope.
