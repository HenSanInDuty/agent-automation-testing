# ADR-023: Observe again after a proven undispatched restore verification

- Status: accepted; offline regression validated under the accuracy-loop plan, live qualification pending.
- Date: 2026-11-09.
- Extends ADR-019, ADR-020 and ADR-022.

The November 9 live session stopped at operation 81. Its restore wait prepared
successfully, then changed interaction state before dispatch. A controlled
fixture reproduces this boundary using a server barrier after prepare; the old
controller stops even when the original checkpoint returns before it receives
the rejected result. This differs from a completed action with an unknown outcome.

The private v4 operation result gains nullable `dispatch_started` and
`failure_stage` evidence. Missing fields from old workers mean unknown, never
permission to retry. A before-dispatch failure requires `dispatch_started=false`
and `status=rejected`. The worker sets started before performing an action;
the controller does not infer this proof from free-form logs. Execution v1,
public operation status and persisted historical results are unchanged.

For a DOM-backed restoration verification **wait** rejected with state_mismatch
before dispatch and retained after evidence, permit up to two read-only refreshes.
Each produces a distinct recorded operation and fresh observation. Verify the
complete original checkpoint after each refresh, including private form values;
only a match allows another read-only verification wait. Preserve the rejected
operation and do not replace its verdict or original source checkpoint. Permanent
drift stops; old workers without proof stop. No click/type/scroll/Back is retried.

The entire recovery has the original rejected step's deadline as an upper bound.
Policy checks, state/hop/operation caps, page identity, exact-node gates, frame
commits and acknowledgements still apply. A reduced state policy can stop before
any refresh. Unknown execution and failed post-dispatch restoration are not
eligible. Restore recovery can improve benchmark coverage while the runtime
conclusion correctly remains partial because its historical rejection persists.

Deploy the compatible controller and worker together after draining active
sessions; old strict controllers can reject additional private result fields.
Rollback both images together. No DB migration, provider/model, prompt, consent,
retention, authentication or material budget change is introduced.

Validation includes a red reproduction, temporary/permanent/form/policy/legacy
controller variants and twenty prepare/dispatch barriers alternating visible
interaction and private-form changes. Broader regressions and live qualification
are tracked in `plan/09112026103202-vision-accuracy-loop/README.md`.

## November 9 iteration 01: close of a hydrating child

Live operation 64 in session 79a9170d was a rejected `close_popup`, with retained
blank-before/rendered-after frames and explicit before-dispatch proof. The wait
recovery deliberately did not apply. A server barrier reproduces that exact race.

Extend recovery to closing a known child only: the rejected operation must have
identical before/after Page IDs equal to the active child, and its parent must
remain in the recorded popup ancestry. Within the failed close's original deadline,
permit at most two fresh read-only observations followed by new close operations
on that same child/parent. Each close uses normal prepare/dispatch state guards.
The child may have hydrated permanently; this does not certify the opener as
restored. After closing, the original opener checkpoint still must pass the full
existing verification. Never reopen a popup, replay a click, repeat a dispatched
close, or recover unknown/Page-change/legacy-proof cases. State/hop/revocation
limits continue to apply. Rejected operations remain rejected in the audit trail.

## November 9 iteration 04: hydration during a read-only refresh prepare

The fourth live run retained 10 completed clicks and rejected setup wait 31:
form presence/values changed at prepare_end while the popup hydrated. No click
was rejected or replayed. Its before frame remains retained; the nonexistent
after frame is explicitly unavailable. Diagnostic supplement and trace are kept.

The worker now marks prepare rejections with explicit no-dispatch/prepare proof.
Only read-only setup refreshes with that proof, a state-drift reason, and the same
known Page may get up to two new observation operations. Keep the first attempt's
deadline across retries, retain every rejection, and enforce state/hop limits.
Fresh observation is permitted to describe a changed form; it never certifies an
older restoration checkpoint or authorizes replay. Existing target revalidation
and original-checkpoint comparisons remain mandatory. Missing legacy proof,
different Pages, dispatched/unknown outcomes and persistent drift fail closed.

## November 9 iteration 08: hydration after refresh preparation

YouTube popup operation 41 completed; read-only refresh 42 was rejected before
dispatch when private form presence/values changed. Extend the same bounded
refresh loop to explicit `before_dispatch`/`dispatch_started=false` results only
when the after frame exists and both Page IDs match the known source. No other
prepare/dispatch failure becomes retryable. Keep the original deadline ceiling,
three-attempt maximum and all state/hop checks. This refresh does not validate
an original restoration checkpoint: the existing independent check still must
pass before any queued action can run. All rejections remain in the trajectory.

The deterministic close-child barrier triggers another hydration between refresh
prepare and execute. The old controller fails after one rejected refresh. Tests
also cover persistent drift, absent legacy proof, unknown outcome, changed Page,
missing after frame, and tightened state/hop budgets.
Final matrix `c8f146d7641b`: 24 passed (217.683s), zero failures/skips/errors.
