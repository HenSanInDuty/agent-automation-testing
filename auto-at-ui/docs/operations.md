# Operations handbook

## Service objectives and alerts

The self-hosted first release targets 99% monthly control-plane availability,
95% of queued runs starting within five minutes, and 99% of artifact deletion
jobs completing by their `retention_until` deadline. Alert on sustained API
5xx, queue delay above five minutes, failed workflow retries, artifact upload
or deletion failures, and an approval-boundary violation.

The control plane exposes the self-hosted scrape endpoint at `/metrics`. It
publishes queue delay, run duration, retry count, failure class, artifact
failure, agent latency/cost, proposal acceptance, and false-healing counters;
configure the in-network collector to scrape it and alert using the thresholds
above. The dashboard reads only the authorized `/api/v1/operations/summary`
API. Configure `CONTROL_PLANE_URL` and `DASHBOARD_TENANT_ID` on its server;
never provide database credentials to the browser.

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
