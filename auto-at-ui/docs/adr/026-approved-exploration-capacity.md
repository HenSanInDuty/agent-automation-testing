# ADR 026: Explicit exploration capacity up to twenty hops

Status: user approved 2026-11-09; validation and local rollout in progress.

The accuracy loop exhausted depth at ten hops after 35 clicks. Its baseline and
independent observations also require more than fifty states to verify 45 of 47
targets. The user approved a local project policy of 100 states and 20 hops.

Expand the supported hop range from 10 to 20 consistently in the project policy
request/response, visual state provenance, private v4 worker schema, legacy v3
worker validation and dashboard input. Defaults stay 5 hops and 50 states. Apply
20/100 only to the approved local project through the normal authorized policy
API; existing sessions retain their original immutable limit snapshots.

This widens numeric validation, not the field shape or execution semantics.
The target-neutral TestExecutionRequest/TestExecutionResult v1 is unchanged.
Deploy matching API/worker/dashboard readers together because older readers can
reject values above ten. Rollback requires lowering project policy before starting
new sessions and retaining compatible readers for historical deeper trajectories.
No database migration is needed: tree/session hop columns have no <=10 constraint.

Keep provider/model, model-call/rate/cost/step-time limits, consent and approval
boundaries unchanged. Count every observation/state and enforce each requested
depth. Never combine separate runs' coverage. Checkpoint ancestry/handoff steps
remain bounded at 100; the separate 50-branch handoff limit remains explicit.

Validation includes API round trip and authorization, 10/20/21 boundaries,
twenty physical fixture actions followed by an undispatched hop-limit rejection,
and a twelve-step UI chain which stops at ten under the smaller policy and can
finish under the approved larger policy. Live qualification remains separate.
