# Phase 05 — Operations, key lifecycle, and rollout

## Objective

Make the debug-evidence mechanism observable and supportable in production without
making sensitive diagnostic content observable outside its privileged read path.

## Scope and prerequisites

Depends on Phases 01–04. This phase documents deployment integration but does not select
a cloud, secret manager, IdP, or managed Temporal service.

## Changes

1. Update `.env.example`, `docs/vision-agent-operations.md`, and `docs/operations.md`
   with variable names only, mandatory production secret injection, seven-day retention,
   dedicated-key separation, current/previous key rotation procedure, revocation/
   incident response, and no-store/admin-only access.
2. Define safe structured logs/metrics: capture attempts by diagnostic code, encryption/
   redaction failures, admin read allowed/denied totals, expiry deleted/failed/overdue
   totals, and cleanup duration. Exclude payload, ciphertext, prompt, screenshot, URL,
   exception message, tenant content, and high-cardinality IDs from labels.
3. Extend Grafana's local dashboard only with safe aggregate operational panels or link
   instructions; preserve current correlation search and never query/display debug
   payloads from Loki.
4. Add a migration/deployment checklist: apply Alembic before enabling capture, verify
   required key/configuration, run synthetic redaction + unauthorized-access smoke tests,
   verify expiry queue, then enable a canary tenant. Include rollback: disable debug
   capture/read endpoint, retain existing records until scheduled deletion, and do not
   delete/rotate blindly during an incident.
5. Specify SLO-facing signals: cleanup lag below 24 hours, zero plaintext payload log
   detections, and alerts for decryption/key mismatch or persistent cleanup failure.

## Tests and validation

- Run the full focused Vision/auth/retention suite, `uv run ruff check .`, dashboard
  typecheck/tests, `docker compose config --quiet`, and an authenticated local smoke
  test using synthetic redacted model output.
- Verify Grafana contains only safe event code/counts and a deliberate secret-shaped
  fixture is absent from logs and activity/API responses.
- Verify key rotation can read old record with the explicitly configured previous key,
  cannot capture with a missing current key, and can delete either record.

## Acceptance criteria

Operators can enable, audit, rotate, expire, and disable the feature using documented,
safe procedures. No production secret/provider choice is embedded in source or plan.

## Risks and non-goals

This is not a production launch approval. Data-region, privacy/legal review, alert
routing, backups, legal holds, and ownership must be finalized by the deployment team
before real production data is enabled.

## Completion record

- Status: completed 2026-09-06T12:24:54+07:00.
- Updated Vision and operations runbooks for key lifecycle, incident handling, canary
  rollout, cleanup SLO signals, and safe observability boundaries. Completion
  reconciliation added URL redaction and per-attempt expiry audits.
- Validation: Ruff, dashboard typecheck, Compose configuration, and diff check passed.
  The full pytest suite stalled at `tests/test_catalog_routes.py` after 18%; focused
  Vision/auth suites passed and this is intentionally not represented as full-suite success.
