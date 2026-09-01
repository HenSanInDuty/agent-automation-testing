# Vision agent operational runbook

## Local evaluation only

Vision exploration is disabled by default. Before a local evaluation, use an
evaluation-only Hugging Face token with the smallest practical scope and place
it only in local secret configuration as `HUGGINGFACE_API_KEY`. Never put a
token in tenant settings, reports, browser requests, logs, fixtures, or source
control. The approved local candidate is `CohereLabs/aya-vision-32b` at
`0554d66834922fc0f2e5f47a12f78464f4a98533`; verify that the deployment endpoint
resolves this exact revision before enabling a tenant policy.

The temporary-image adapter supports My Drive through
`GOOGLE_DRIVE_OAUTH_CLIENT_ID`, `GOOGLE_DRIVE_OAUTH_CLIENT_SECRET`, and
`GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN`; set `GOOGLE_DRIVE_VISION_FOLDER_ID` to a
folder owned by that OAuth user. Shared Drive service-account credentials are
also supported, but require a deployment-specific secret-file mount. Each
verified screenshot is shared by an
unlisted public link only for the model request, then deleted; neither the URL
nor image is saved in application records or logs.

For My Drive OAuth, no credential-file mount is required by the supplied local
Compose configuration.

Run the fixture-only checks before any provider call:

```bash
uv run pytest tests/test_vision_benchmark.py tests/test_vision_executor.py
```

The manifest at `benchmark/vision/v1/manifest.json` contains synthetic
fixtures only. Store aggregate metrics, fixture identifiers, model revision,
dataset version, and correlation IDs; do not store raw screenshots, prompts,
or provider output in reports.

## Consent and disablement

A tenant administrator must explicitly acknowledge raw screenshot transfer to
Hugging Face before enabling vision. The policy is tenant-scoped. To stop
future exploration immediately, disable the tenant's Vision policy in
`/agent`; this preserves prior runs and does not alter any deterministic test
result. Do not delete artifacts to enact a kill switch.

## Guardrails and incident response

Keep concurrency, steps, screenshot bytes, session duration, request rate, and
cost caps at their disabled-by-default local values until a benchmark gate is
approved. Investigate `unavailable` outcomes using the correlation ID and safe
activity/audit records. On suspected prompt injection, privacy exposure, cost
spike, or provider incident: disable the tenant policy, retain only the normal
artifact-retention evidence, review correlation-linked audit/activity events,
and roll back to the last approved immutable model revision. Do not retry by
raising limits or bypassing consent.

Retention inherits the existing artifact policy. A production retention change,
data-region choice, paid usage, or production rollout needs separate approval.
