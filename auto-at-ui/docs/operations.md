# Operations handbook

## Service objectives and alerts

The self-hosted first release targets 99% monthly control-plane availability,
95% of queued runs starting within five minutes, and 99% of artifact deletion
jobs completing by their `retention_until` deadline. Alert on sustained API
5xx, queue delay above five minutes, failed workflow retries, artifact upload
or deletion failures, and an approval-boundary violation.

The control plane exposes the self-hosted scrape endpoint at `/metrics`. It
publishes queue delay, run duration, retry count, failure class, artifact
failure, agent latency/cost, proposal acceptance, and false-healing counters.
For generated tests, additionally track request state totals/age, planner
policy failures, pending-review age, approval/rejection totals, and time from
approval to deterministic terminal result. Configure the in-network collector
to scrape it and alert on a generation request stuck in `queued`/`generating`,
an unusual policy-failure rate, or a pending review that exceeds its agreed
service target.

The dashboard reads and changes data only through the authorized control-plane
API. Its public API URL is `NEXT_PUBLIC_CONTROL_PLANE_URL`; browser identity
headers exist only for the local development adapter and must never substitute
for production OIDC. Never provide database credentials, provider keys, or
unredacted requests to the browser.

## Generated-test acceptance scenario

With the local Compose stack running and migrations applied, use the
`Governed test generation` folder in
`docs/hoppscotch/auto-at-phase-1.postman_collection.json` in this order:
set the project policy, submit, poll to `completed`, inspect the draft, then
approve. The Temporal worker dispatches exactly one v1 run; inspect its linked
run ID and artifacts through the existing run endpoints. This scenario requires
the already-configured generation model gateway and a non-secret credential in
the local environment. It must be run against an allowed public target only.
Use a contributor, project administrator, or tenant administrator for approval;
a reviewer-only or service role must be rejected. Repeating a different final
decision must return the immutable-decision conflict and must not create a
second run.

## Incident and recovery

On an alert, identify the `correlation_id` in API logs, workflow history,
worker logs, artifact metadata, and audit events. Do not alter a deterministic
verdict or approve a proposal as a recovery action. Restore encrypted backups
only to an isolated environment, validate tenant isolation and deletion queues,
then replay the deletion queue before reopening access. Backups expire after
35 days under ADR-006.

## Deployment and ownership

Deploy the dashboard, API, workers, PostgreSQL, Temporal, telemetry collector,
and object storage as a self-hosted private-network stack. Use separate local,
staging, and production credentials and stores. The platform operations owner
owns availability, backups, and alerts; the compliance owner owns retention,
legal holds, and deletion review. Names must be recorded before external
production access.

## Release gate

CI must pass Python lint/test/type checking (errors in production source), dashboard and worker type checks,
worker contract tests, Compose validation, secret scan, dependency review, and
lockfile reproducibility. A failed contract, redaction, or approval-boundary
test blocks release.
