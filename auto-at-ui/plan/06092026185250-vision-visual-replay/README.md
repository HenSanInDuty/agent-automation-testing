# Vision visual replay

## Goal

Let an authenticated member who can read a Vision exploration's project view a
durable, ordered visual replay of every captured BFS state. Each image is
rendered with the model's safe candidate actions for that state, so the viewer
can distinguish what the model observed, what it proposed, and which branch
was subsequently materialized. Screenshots remain advisory evidence and never
change a generated draft, browser verdict, or approval boundary.

## Acceptance criteria

1. Every verified PNG captured for a visual-exploration state is durably stored
   under a tenant- and exploration-scoped private RustFS key before it is sent
   to the Vision provider, with immutable metadata that links it to its state,
   checksum, byte count, and content type.
2. An authenticated principal with `Permission.READ` on the exploration's
   project can list replay frames and fetch one image through an authorized
   control-plane endpoint. The response has no public storage URL and does not
   put image bytes, URLs, task intent, typed text, prompts, or provider output
   in logs, activity events, or API JSON.
3. The dashboard displays the state graph in capture order, lets the viewer
   select a frame, and overlays only the already-safe candidate action fields
   (kind, confidence, coordinates, scroll/wait values). It clearly labels
   proposals as advisory rather than as executed test steps.
4. Evidence has no automatic expiry. A tenant administrator can explicitly
   delete a whole replay or individual frame; deletion removes verified bytes
   first, then metadata, is idempotent, and records an audit event. Deleted
   frames cannot be retrieved.
5. Tenant and project authorization is enforced for metadata, bytes, and
   deletion. Existing roles may all view because every human role already has
   `Permission.READ`; service principals and unauthenticated users never gain a
   new read path. The existing deterministic `TestExecutionRequest` /
   `TestExecutionResult` contract is unchanged.

## Request, decisions, and assumptions

| Item | Status |
| --- | --- |
| Request | Make the Vision model's exploration visually inspectable. |
| Confirmed | Store replay screenshots permanently until an explicit deletion. |
| Confirmed | Any authenticated role with access to the project may view replay evidence. |
| Confirmed | Reuse private RustFS evidence storage; do not select a new cloud or model provider. |
| Assumption | “Any role” means an authenticated tenant/project member that satisfies the existing project `READ` authorization; it does not create a public, cross-tenant, or anonymous URL. |
| Assumption | Explicit deletion uses the existing elevated evidence-deletion convention: tenant administrators may delete; ordinary readers can view but cannot remove evidence. |
| Assumption | Replay is a sequence of still PNG frames with safe action overlays, not a video, live remote browser, model chain-of-thought, prompt, typed action text, or provider response. |
| Unresolved | None for implementation planning. Production privacy/legal approval remains required before storing production screenshots indefinitely. |

## Source-scout findings

- `workers/playwright/src/vision.ts` materializes one isolated browser context
  per BFS node and writes `tree-<node_id>.png` under its artifact root. It
  returns checksum/size metadata but deliberately cleans raw files after the
  control plane consumes them.
- `apps/control-plane/application/vision_events.py` reads and verifies each PNG,
  persists only `VisualExplorationStateModel.screenshot_checksum`, sends the
  bytes transiently to the configured image-delivery adapter, and records safe
  candidate actions. There is currently no durable replay upload.
- `apps/control-plane/infrastructure/persistence/models.py` stores exploration
  sessions, states, and safe action proposals, but both state and action tables
  intentionally omit image location and state-to-action association.
- `apps/control-plane/infrastructure/artifacts/rustfs.py` already verifies
  checksums and scopes object keys by tenant. Its current artifact record is
  tied to `test_runs`, so a Vision-specific evidence record/API is required;
  an exploration can finish without a deterministic run.
- `apps/control-plane/api/v1/routes/vision.py` and
  `apps/dashboard/app/vision-dashboard.tsx` already provide session-scoped
  reads, action candidates, safe progress, and project `READ` authorization,
  but no frame endpoint or image UI.
- `apps/control-plane/domain/authorization.py` grants `READ` to viewer,
  contributor, reviewer, project_admin, tenant_admin, and service roles;
  tenant admin has the existing management privilege. `docs/adr/006-...`
  sets a 30-day default artifact retention, so permanent Vision replay needs an
  explicit ADR update rather than silently inheriting that expiry.
- The already-completed `plan/06092026152909-vision-advisory-progress-stream/`
  defines the safe session timeline. This plan builds on it and must preserve
  its no-screenshot-in-activity-feed constraint.

## Constraints

- Keep layer direction: contracts/domain ports define data and permissions;
  application orchestrates verification, persistence, deletion, and audits;
  infrastructure owns RustFS/SQLAlchemy; API owns HTTP; dashboard remains a
  thin authenticated client.
- The approved local Vision provider/model, raw-screenshot consent gate,
  request/cost/rate/state/time caps, origin policy, and temporary provider
  image delivery remain unchanged. Capturing a replay must not make an extra
  model call.
- Screenshot bytes are sensitive. Object keys and data remain tenant-scoped;
  never expose a RustFS URI, temporary image URL, prompt, intent, typed text,
  provider response, or raw bytes in structured logs, timelines, audit detail,
  or response metadata.
- This is separate from `TestExecutionRequest` / `TestExecutionResult` and
  must not alter a test verdict, run artifact semantics, or human approval.
- “Permanent” means no scheduled lifecycle expiry for this new evidence class,
  not immunity from a lawful/user-authorized deletion request or storage loss.

## Phases

| Phase | Objective | Status | Dependencies | Validation |
| --- | --- | --- | --- | --- |
| [01](phase-01-governed-replay-evidence.md) | Define governed replay evidence, permanent-retention policy, and schema. | completed — 2026-09-06 19:03 ICT | None | 11 focused contract/evidence/schema tests passed; Alembic head verified |
| [02](phase-02-capture-and-store-frames.md) | Verify and persist every worker-captured PNG through private RustFS. | completed — 2026-09-06 19:11 ICT | Phase 01 | Vision processor, worker, storage tests |
| [03](phase-03-authorized-replay-api-and-deletion.md) | Add session-scoped list/image/delete endpoints with audit and RBAC. | completed — 2026-09-06 19:32 ICT | Phases 01–02 | Route/RBAC/deletion tests |
| [04](phase-04-visual-replay-dashboard.md) | Render a safe state-frame viewer and action overlays in the dashboard. | completed — 2026-09-06 19:41 ICT | Phase 03 | Dashboard unit/type/build checks |
| [05](phase-05-operational-rollout-and-regression.md) | Document retention, deletion, migration, and end-to-end operational checks. | completed — 2026-09-06 19:52 ICT | Phases 01–04 | Focused and baseline checks |

## Risks and rollout

- **Indefinite sensitive data:** amend ADR-006 and operational documentation to
  make this intentional, display the persistence/deletion behavior in the UI,
  and require production privacy/legal approval before production data is
  enabled. Keep local rollout behind existing tenant Vision consent.
- **Authorization bypass:** proxy image bytes through an authorized API route;
  never return storage URIs, public links, or presigned URLs. Test tenant,
  project, role, and deleted-record cases.
- **At-least-once processing:** give state-frame insertion a unique
  `(session_id, state_id)` constraint and use deterministic storage keys so a
  redelivered outbox event neither creates duplicate DB rows nor overwrites a
  checksum mismatch.
- **Partial failure:** upload/verify bytes before adding metadata. If metadata
  fails after upload, record safe failure/audit information and leave an
  operator-detectable orphan for a bounded reconciliation command; never mark
  exploration passed because replay storage failed.
- **Object volume/cost:** frame count remains bounded by existing state/hop and
  screenshot-byte caps. Show count/size in metadata and use aggregate,
  non-sensitive observability fields only.

## Execution progress

Phase 01 completed at 2026-09-06 19:03 ICT. Added the metadata-only,
versioned `VisualReplayFrame` contract and a separate private replay-frame
domain record, with no execution-contract change. The forward-only
`f7a8b9c0d1e2` migration creates `visual_replay_frames`, adds nullable
`originating_state_id` to action proposals without historical backfill, and
follows the existing progress-stream migration head. SQL persistence supports
idempotent same-state insertion, tenant/session ordered reads, and soft-delete
metadata marking; conflicting duplicate evidence fails closed.

Changed paths: `packages/contracts/src/auto_at/contracts/vision.py`,
`apps/control-plane/domain/entities.py`, `apps/control-plane/domain/ports.py`,
`apps/control-plane/infrastructure/persistence/models.py`,
`apps/control-plane/infrastructure/persistence/repositories.py`,
`migrations/versions/f7a8b9c0d1e2_add_visual_replay_frames.py`,
`docs/adr/006-proposed-retention-and-deletion.md`,
`docs/vision-agent-operations.md`, `tests/test_vision_contracts.py`, and
`tests/test_persistence_schema.py`.

Validation passed: focused Ruff check; `uv run pytest tests/test_vision_contracts.py
tests/test_vision_evidence.py tests/test_persistence_schema.py` (11 passed);
`uv run alembic heads` (single `f7a8b9c0d1e2` head); and `git diff --check`.
The repository already contained uncommitted Vision progress-stream and
dashboard work; it was preserved. No retention job, screenshot upload, route,
dashboard, test verdict, or `TestExecutionRequest` / `TestExecutionResult`
change was made. Phase 02 is now active.

Phase 02 completed at 2026-09-06 19:11 ICT. The Vision processor creates a
deterministic tenant/session/state key, validates the PNG before storing it,
and writes/head-verifies private RustFS bytes before saving state/frame metadata
or invoking temporary provider delivery. The RustFS adapter treats a matching
retry as idempotent and fails closed before a checksum-mismatched retry can
overwrite existing evidence. Storage is injected through the Vision replay port,
preserving application-to-infrastructure direction; the Temporal worker remains
the composition root. New proposals link to their originating state and retain
only safe action fields. No worker or target-neutral execution contract changed.

Changed paths: `apps/control-plane/application/vision_events.py`,
`apps/control-plane/domain/ports.py`,
`apps/control-plane/infrastructure/artifacts/rustfs.py`,
`tests/test_vision_event_processor.py`, and `tests/test_rustfs_artifacts.py`.

Validation passed: `uv run pytest --basetemp .pytest-replay-phase-02
tests/test_vision_event_processor.py tests/test_vision_evidence.py
tests/test_rustfs_artifacts.py tests/test_vision_contracts.py
tests/test_persistence_schema.py` (19 passed); focused Ruff; Playwright worker
`corepack pnpm --dir workers/playwright typecheck`; and `git diff --check`.
`corepack pnpm --dir workers/playwright test -- --list` was not counted as a
passing validation because Playwright reported no discoverable tests. Phase 03
is active.

Phase 03 completed at 2026-09-06 19:32 ICT. Implemented the Vision-only replay list, verified
image-read, and explicit deletion routes plus the application use case and
RustFS read/delete methods. Reads require project `READ`, return only safe
metadata or `image/png` with `Cache-Control: private, no-store`, and append an
ID-only audit event. Deletion requires a non-service tenant administrator and
an explicit confirmation body; it deletes bytes before soft-deleting metadata
and preserves metadata when byte deletion fails. The dashboard now consumes the
authorized list and blob endpoints, revokes object URLs on selection changes,
and labels overlays as model proposals. Focused route/event/storage tests,
Ruff, dashboard typecheck, and dashboard lint passed. Service principals are
explicitly excluded from this new human-facing evidence path even though their
generic role retains `READ` elsewhere. Focused replay tests now cover all human
reader roles, service/cross-tenant denial, byte-before-metadata deletion
ordering, idempotent retries, and failed byte deletion retaining metadata. The
dashboard obtains the authenticated role from the existing `/auth/me` response
and shows destructive replay controls only to tenant administrators; server-side
authorization remains authoritative.

Changed paths in this completion: `apps/control-plane/application/vision_replay.py`,
`apps/dashboard/app/vision-dashboard.tsx`, `tests/test_vision_replay.py`, and
`tests/test_dashboard_route_contracts.py`.

Validation passed: `uv run pytest --basetemp .pytest-replay-phase-03
tests/test_vision_replay.py tests/test_vision_routes.py
tests/test_dashboard_route_contracts.py tests/test_rustfs_artifacts.py` (33
passed); dashboard test/typecheck/lint; and `git diff --check`. A FastAPI
TestClient deprecation warning and Node module-type warnings were emitted, but
no validation failure occurred. Phase 04 is active.

Phase 04 completed at 2026-09-06 19:41 ICT. The dashboard uses only the
session-scoped replay API to order retained frames, retrieve one credentialed
PNG blob on selection, revoke its object URL on frame/session changes and
unmount, and display responsive coordinate overlays calculated from the image's
intrinsic dimensions. Frame selectors identify capture sequence, checksum
prefix, retained status, and capture time. The UI labels every marker as a
model proposal, shows safe non-coordinate action data separately, gives a
privacy/retention disclosure, and confines confirmed deletion controls to the
tenant-admin role; server-side RBAC remains authoritative. Deleted or historic
sessions render the no-retained-frame state. No storage URL, raw image JSON,
action text, prompt, or provider result is introduced.

Changed paths in this phase: `apps/dashboard/app/vision-dashboard.tsx`,
`apps/dashboard/app/generation-api.ts`, `apps/dashboard/app/generation-types.ts`,
`apps/dashboard/app/components/vision-replay-model.ts`,
`apps/dashboard/app/components/vision-replay-model.test.ts`, and
`apps/dashboard/app/globals.css`.

Validation passed: `corepack pnpm --dir apps/dashboard test` (19 passed),
`corepack pnpm --dir apps/dashboard typecheck`,
`corepack pnpm --dir apps/dashboard lint`, `corepack pnpm --dir apps/dashboard
build`, and `git diff --check`. Next.js reported an existing workspace-root
lockfile warning; Node reported module-type warnings. Neither was a failure.
Phase 05 completed at 2026-09-06 19:52 ICT. ADR-006, the Vision runbook,
operations runbook, and API examples now state the replay-specific private
storage classification, no-expiry-until-tenant-admin-deletion policy,
byte-before-metadata deletion recovery, no-backfill deployment order, and the
production privacy/legal gate. They also prohibit sensitive screenshots,
storage keys, URLs, prompts, typed text, provider output, and identifiers from
operational logs, tickets, metrics labels, and dashboards. The existing
synthetic capture, storage, read/RBAC, and deletion tests cover the evidence
lifecycle without affecting a generated draft or deterministic verdict.

Final validation passed: `uv run ruff check .`; `uv run pytest -q` (229
passed); `corepack pnpm --dir apps/dashboard test` (20 passed), typecheck,
lint, and production build; `corepack pnpm --dir workers/playwright typecheck`;
and `corepack pnpm --dir workers/playwright exec playwright test
src/contract.spec.ts` (14 passed, 1 image-only test skipped). A disposable
`replay_validation_20260906` PostgreSQL database migrated through
`f7a8b9c0d1e2` successfully and was then removed. `git diff --check` passed.
The package's unconfigured default Playwright test discovery reports no tests,
so the explicit repository contract spec was used. Next.js workspace-root,
Node module-type, and FORCE_COLOR/NO_COLOR warnings were non-failing. No
execution contract, verdict, draft, approval boundary, retention scheduler, or
production configuration was changed. Overall plan status: completed.

## Out of scope

- Public sharing, anonymous links, direct RustFS console access, export ZIPs,
  video capture, live remote-browser control, OCR, model reasoning, prompts,
  typed action text, or provider payloads.
- A new Vision provider/model, new cloud storage/provider, altered consent,
  altered cost/rate limits, or changes to deterministic execution/approvals.
- Retroactively reconstructing frames for past sessions: their raw worker files
  were intentionally removed and only checksums survive.
