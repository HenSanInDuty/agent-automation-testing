# Phase 03 — Authorized replay API and deletion

## Objective

Expose replay metadata and image bytes only through session-scoped,
project-authorized API routes, and provide explicit privileged deletion.

## Scope and prerequisites

- Requires stored frames from Phase 02.
- Reuses the existing identity/session/CSRF mechanism and `Permission.READ`;
  it does not choose an authentication provider or return direct storage links.

## Exact paths

- Change `apps/control-plane/api/v1/routes/vision.py`.
- Add an application use-case module such as
  `apps/control-plane/application/vision_replay.py`.
- Change `apps/control-plane/domain/ports.py`,
  `apps/control-plane/infrastructure/persistence/repositories.py`, and
  `apps/control-plane/infrastructure/artifacts/rustfs.py` as needed.
- Change `apps/control-plane/domain/authorization.py` only if a narrowly named
  `DELETE_VISION_REPLAY` permission is needed; map it to tenant admin only and
  preserve existing role behavior.
- Add route/application tests near `tests/test_vision_routes.py`,
  `tests/test_authorization.py`, and `tests/test_artifact_retention.py`.

## Detailed behavior and data flow

1. Add `GET /api/v1/vision/explorations/{session_id}/replay-frames` returning
   ordered, metadata-only frames and safe candidate actions grouped by
   originating state. Load the session first and authorize its project with
   `READ`; return non-enumerating 404 for absent/cross-tenant/non-readable data.
2. Add `GET /api/v1/vision/explorations/{session_id}/replay-frames/{frame_id}`.
   Re-authorize each request, load only a matching non-deleted frame, verify the
   RustFS object checksum/size before responding as `image/png`, and use
   `Cache-Control: private, no-store` so a browser/proxy does not retain
   sensitive content. Audit the successful explicit frame read with IDs only.
3. Add `DELETE` for one frame and `DELETE .../replay-frames` for a session-wide
   purge. Require an authenticated non-service tenant administrator, CSRF, and
   a confirmation request body/header consistent with existing destructive API
   conventions. Do not infer deletion from a GET.
4. In the deletion use case, mark/delete in a transaction-safe intent state,
   delete verified RustFS bytes, then remove/mark metadata. Make repeated calls
   safe; if object deletion fails, retain metadata for retry and return a safe
   conflict/outcome. Append audit records for requested/completed/failed
   deletion without URIs or bytes.
5. Leave normal sessions and action history intact after replay deletion; show
   an empty/deleted replay state without altering exploration state, generated
   drafts, or run results.

## Contract/API/schema changes

- New Vision-only response schemas and routes. API JSON never includes URI,
  task intent, raw image data, typed text, prompt, or provider output.
- Permission additions, if used, are backward compatible and grant deletion to
  tenant admin only; all extant roles continue to receive `READ`-authorized
  frame viewing.

## Tests and validation

- Route tests for viewer/contributor/reviewer/project-admin/tenant-admin reads,
  service/anonymous denial, cross-tenant/session/frame enumeration denial, and
  no storage URL in list responses.
- Test corrupt/missing object returns safe failure, read is audited, and delete
  performs byte-before-metadata ordering, retries safely, and does not change
  a run/draft/verdict.
- Run focused tests then `uv run ruff check .`.

## Acceptance criteria

All existing authenticated reader roles can safely view a project replay; only
tenant admin can explicitly purge it; deleted evidence is inaccessible and has
an auditable, recoverable failure path.

## Risks and non-goals

Do not implement public signed URLs, artifact ZIP integration, or a generic
cross-resource image endpoint. Do not log the frame's URI or contents.

## Execution record

Status: completed 2026-09-06 19:32 ICT.

The session-scoped API lists metadata-only frames and their state-associated
safe actions, proxies one checksum-verified PNG with `private, no-store`, and
supports confirmed single/all-frame deletion. Reads use project `READ` for
human principals; service identities are denied this new evidence route.
Deletion is tenant-admin-only, deletes bytes before soft-deleting metadata, is
safe to repeat, and preserves metadata on storage failure for retry. All audit
events contain only safe identifiers and outcome names.

Validation: 33 focused Python tests passed; dashboard tests, typecheck, and
lint passed; `git diff --check` passed. FastAPI TestClient and Node emitted
non-failing deprecation/module-type warnings. No execution contract, verdict,
draft, or approval behavior changed.
