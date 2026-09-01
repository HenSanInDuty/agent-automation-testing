# ADR-008: Temporary image delivery for vision inference

- Status: Accepted for local evaluation
- Date: 2026-08-31

## Context

The selected Hugging Face vision route accepts remotely retrievable image URLs,
but rejects in-memory data URIs. Raw screenshots must never be included in
database records, activity feeds, logs, browser responses, or durable proposal
payloads.

## Decision

Use Google Drive My Drive OAuth for local evaluation. The adapter uploads the
verified PNG to the configured Drive folder, assigns non-discoverable
`anyone:reader` access, and supplies Drive's `webContentLink` only in memory to
the model adapter. A retained-file verification fetched that link from the
local container as `image/png` without authentication.

The user selected persistent Drive files: deletion after delivery defaults to
disabled (`GOOGLE_DRIVE_VISION_DELETE_AFTER_DELIVERY=false`). The application
must not persist, log, render, or include the link in audit/activity/proposal
payloads. Supabase Storage is not used by this flow.

## Consequences

- Google Drive My Drive OAuth credentials are supplied only at runtime. Each
  retained file remains accessible to anyone with its unlisted link until its
  permission is revoked or it is deleted; Drive has no TTL-enforced signed URL.
- `VISION_TEMPORARY_URL_TTL_SECONDS` is not a security expiry when Drive file
  retention is enabled. The user must govern later cleanup and retention.
- The capability remains disabled until the adapter, cleanup tests, tenant
  policy, and endpoint-backed benchmark pass.
- This is local-evaluation infrastructure only; production region, retention,
  and service terms require separate approval.
