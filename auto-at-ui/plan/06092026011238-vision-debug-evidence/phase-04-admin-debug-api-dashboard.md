# Phase 04 — Tenant-admin API and dashboard

## Objective

Offer a narrowly scoped, auditable inspection flow for tenant administrators without
leaking debug evidence into normal Vision session endpoints or UI.

## Scope and prerequisites

Depends on Phases 02–03 and existing session-cookie authentication/CSRF conventions.
Use `tenant_admin` authorization only, not the general `READ` permission.

## Changes

1. Add a specific authorization permission such as `READ_VISION_DEBUG_EVIDENCE` in
   `domain/authorization.py`, grant it only to `Role.TENANT_ADMIN`, and explicitly deny
   `is_service`. Keep project admins/viewers unable to read even their own project
   sessions.
2. Add application use cases and DTOs for metadata list and single-payload read. Each
   verifies tenant/session ownership, retention deadline, admin permission, key ID,
   decrypts in memory, and returns only the redacted canonical payload plus metadata.
   Use generic 404 for inaccessible records and a safe 410/404-style unavailable result
   for expired/undecryptable evidence without exposing why to non-admin callers.
3. Add routes beneath the existing Vision boundary, for example
   `GET /api/v1/vision/explorations/{session_id}/debug-evidence` and
   `GET /api/v1/vision/explorations/{session_id}/debug-evidence/{evidence_id}`. Require
   session auth/CSRF conventions as appropriate, set `Cache-Control: no-store`, prevent
   pagination enumeration across tenants, and append allow/deny/read-failure audit events.
4. Keep `ExplorationResponse`, `VisualActionResponse`, activity stream, and public
   Grafana dashboard payload-free. Do not add debug output to the existing list endpoint.
5. Add a tenant-admin-only section in `apps/dashboard/app/vision-dashboard.tsx` and API
   helpers/types in `generation-api.ts` / `generation-types.ts`. Load metadata only on
   explicit user action; show the redacted payload in a non-persistent view with expiry
   time and a warning not to copy sensitive content. Do not store it in local storage,
   URL, telemetry, error boundary, or client logs.
6. Make absence of debug evidence a normal state and never let dashboard role rendering
   be the authorization boundary; the server remains authoritative.

## Tests and validation

- Add HTTP tests for tenant admin success, tenant/project admin/viewer/service denial,
  cross-tenant non-enumeration, expired evidence, key failure, no-store header, and audit
  event categories.
- Extend dashboard/API tests to prove the admin call is explicit, ordinary users never
  receive a request/payload, and expiry/no-record states render safely.
- Run targeted TypeScript checks and Python route/auth tests, then `uv run pytest` and
  `npm.cmd run typecheck --prefix apps/dashboard` as applicable.

## Acceptance criteria

Only a tenant admin can retrieve redacted payload before expiry, each attempt is
auditable, and no normal Vision reader/browser list/API can obtain payload data.

## Risks and non-goals

Do not use dashboard state as a security control, add download/export, or reveal full
provider request/response envelopes. Production TLS/auth deployment remains governed by
the existing deployment decision process.

## Completion record

- Status: completed 2026-09-06T12:24:54+07:00.
- Added tenant-admin-only permission, non-enumerating no-store routes, in-memory
  decryption application use case, audit events, and an explicit non-persistent dashboard view.
- Validation: access/workflow/route tests and dashboard typecheck passed.
