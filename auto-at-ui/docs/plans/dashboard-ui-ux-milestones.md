# Dashboard UI/UX milestones

Status: **M6 complete** (2026-08-10) — authenticated Compose acceptance,
quality-gate coverage, and dashboard operator guidance are validated.

This plan is the implementation order for the dashboard experience. A later
milestone does not start until its predecessor meets its validation criteria.

## Source reconnaissance

- `apps/dashboard/app/generation-dashboard.tsx` is the only current page; it
  sends development identity headers from browser state and has no design
  system, routing, or authenticated session.
- `apps/control-plane/api/v1/dependencies/authorization.py` deliberately only
  adapts local development headers. `domain/authorization.py` already defines
  the target roles and permission matrix, so a real principal adapter can
  retain the domain policy.
- `infrastructure/persistence/models.py` has project, test, run, artifact,
  proposal, audit, and outbox tables, but no user, membership, session, or
  activity-event persistence.
- `api/v1/routes/runs.py` immediately dispatches a Web UI run when local
  dispatch is enabled. Durable dispatch is already available in
  `infrastructure/workflows/temporal.py`; this must become the normal UI path
  before a live pipeline can be reliable.
- `workers/playwright/src/execute.ts` retains final step history and evidence,
  but its HTTP response is terminal-only. It needs progress callbacks/events
  for a live Browser Agent todo.

## M0 — Stable Web UI execution — done

- [x] Add `artifact-init` Compose service that owns `execution-artifacts` as
  the worker's unprivileged `pwuser` (UID/GID 1001).
- [x] Make control-plane, Playwright worker, and Temporal worker wait for the
  init service before mounting the shared artifact volume.
- [x] Rebuild Compose and pass `tests/test_playwright_worker_compose.py`.

Exit criterion: a passing and a failing browser test both persist evidence.
Validated: 2026-08-02, 2/2 Compose worker tests passed.

## M1 — App shell and design system — done

- [x] Add a dashboard CSS foundation imported by `app/layout.tsx`: neutral
  tokens, spacing, typography, focus rings, elevation, responsive breakpoints,
  and motion-reduction support.
- [x] Define semantic status tokens: neutral chrome uses black/gray/white;
  green is passed, red failed/errored, amber queued/running, and gray
  skipped/cancelled. Do not use status colors as decoration.
- [x] Replace the single-page layout with authenticated app shell components:
  desktop sidebar, mobile drawer, top bar, tenant label, current-user menu,
  and content breadcrumb/title slot.
- [x] Add route/page shells for Overview, Runs, Projects & Tests, Agent
  workspace, Reviews, and Admin. Until their data APIs arrive, render explicit
  empty/coming-next states rather than fake values.
- [x] Create reusable `StatusBadge`, `PageHeader`, `DataTable`, `EmptyState`,
  `LoadingState`, `ErrorState`, `ConfirmDialog`, and `CodeBlock` components.
- [x] Migrate the existing generation screen into the Agent workspace while
  retaining its current polling and approval behavior.
- [x] Add dashboard unit tests for status semantics, responsive navigation
  state, keyboard focus, and error/empty/loading rendering.

Exit criterion: dashboard has a responsive neutral app shell, no manually
editable identity panel, and existing generation behavior remains available.
Validated: 2026-08-02 — dashboard tests (7), typecheck, lint, and production
build passed.

## M2 — Authentication and account administration — done

- [x] Add an Alembic revision and persistence models for `users`,
  `tenant_memberships`, and hashed opaque `sessions`; index all tenant and
  session lookup paths and enforce unique email/membership constraints.
- [x] Add a password service using Argon2id, with password complexity policy,
  constant-time verification, session-token hashing, expiry, and revocation.
  Never log, persist, or return a password except the one-time temporary value
  in the provisioning response.
- [x] Add application/domain ports and use cases for bootstrap admin, login,
  logout, current principal, force password change, create user, list users,
  change role, and disable user. Keep role decisions in
  `domain/authorization.py`.
- [x] Add CLI command to create the first tenant admin with a temporary
  password; make it idempotent only for an explicitly named existing account.
- [x] Replace header-based `current_principal` for non-local use with a
  session-cookie adapter. Configure CORS credentials, allowed dashboard
  origins, `HttpOnly`, `Secure` outside local, `SameSite=Lax`, and CSRF token
  validation on POST/PUT/DELETE.
- [x] Add `/api/v1/auth/login`, `/logout`, `/me`, and `/change-password` plus
  tenant-admin user-management endpoints. Update OpenAPI response schemas and
  avoid user enumeration in authentication errors.
- [x] Build Login, forced-password-change, and Admin > Users screens. Admin
  receives and must acknowledge a temporary password once; the UI never
  displays it again after navigation or reload.
- [x] Add tests for invalid credentials/rate limit, session expiry/logout,
  CSRF, forced password change, disabled users, role enforcement, audit
  events, and tenant isolation.

Exit criterion: a bootstrapped tenant admin can sign in, provision a
contributor, and the contributor can sign in without sending identity headers.

## M3 — Project, test, and run workflow — complete

- [x] Add authorized project and test-case list/detail/create endpoints backed
  by the existing `ProjectModel` and `TestCaseModel`; preserve current
  target-neutral execution contracts and tenant/project authorization.
- [x] Add paginated/filterable run listing with project, status, time range,
  target, revision, correlation ID, and terminal summary. Do not expose raw
  runner configuration unless it is redacted.
- [x] Refactor the dashboard API client to derive tenant/actor from session and
  centralize API errors, idempotency keys, artifact download, and request
  cancellation.
- [x] Build Projects & Tests pages with searchable project picker and test-case
  picker. Add an administrator policy editor only for authorized project roles.
- [x] Build a run creation flow: choose project, test, target URL/config,
  review immutable revision and artifact policy, submit once, then navigate to
  the created run. User-facing forms must never request a UUID.
- [x] Build Runs list and Run detail with status, request summary, artifact
  list/download, correlation ID, revision, terminal result, and cancel action
  when state permits.
- [x] Add API and dashboard tests for cross-tenant invisibility, idempotent
  create/cancel, filters, artifact integrity failure, and empty project/test
  states.

Exit criterion: an authorized contributor creates, finds, cancels where valid,
and investigates a deterministic run entirely from the dashboard.

Validated 2026-08-02: `uv run pytest` (93 passed), `uv run ruff check .`, dashboard
typecheck/lint/test (7 passed), production build, and `git diff --check` all passed.
The implementation adds the catalog and run route boundaries, tenant-scoped
persistence queries, immutable request capture, the `created_at` migration, and
dashboard project/test selection plus run list/detail/evidence views. M4 remains next.

## M4 — Live pipeline and Browser Agent todo — complete

Started 2026-08-02 22:52:08 +07:00. Scope: additive, target-neutral activity
history; durable UI dispatch; authenticated worker progress; and safe run/agent
timeline presentation. Existing v1 request/result verdict semantics remain
unchanged.

Validated 2026-08-10 22:34:35 +07:00: `uv run ruff check .`, `uv run pytest
--basetemp D:\\tmp\\auto-at-m4-final` (97 passed), dashboard `typecheck`, `lint`,
`test` (7 passed), and production `build`, Playwright worker `typecheck`, and
`git diff --check` all passed. The dashboard test command emits existing Node
module-type warnings; the production build emits existing multi-lockfile and
Next ESLint-plugin warnings. Neither affected the result.

Completion summary: the current checkout's existing M4 backend supplies the
append-only, redacted activity history, durable dispatch, authenticated worker
progress, and SSE endpoint. This completion adds the SSE-connected timeline
with a visible polling fallback to Run detail and Agent workspace, plus
stream-resume and forged-callback coverage. Changed paths for this completion:
`apps/dashboard/app/components/activity-timeline.tsx`,
`apps/dashboard/app/runs/[id]/page.tsx`,
`apps/dashboard/app/generation-dashboard.tsx`, `tests/test_activity.py`, and
`tests/test_worker_progress.py`. No deviations or deferred M4 items.

- [x] Add an append-only `activity_events` table and migration with tenant,
  run nullable/required-by-source, correlation ID, source, stage, status,
  safe summary, redacted metadata, and timestamp. Add indexes for run and
  correlation timeline queries.
- [x] Define a target-neutral activity contract and application port; validate
  allowed sources/stages/statuses and reject secret-bearing metadata before
  persistence.
- [x] Emit activities from create/cancel/run dispatch, Temporal retry and
  completion, generation claim/model/validation/completion/failure, and triage
  request/proposal/failure. Mirror security-relevant events to audit events;
  activity records are observability, not authorization evidence.
- [x] Change normal UI run dispatch to the durable Temporal path so create-run
  returns queued promptly. Preserve idempotency and terminal verdict semantics.
- [x] Extend the Playwright worker execution API with a versioned internal
  progress callback: validation, browser launch, navigation, each configured
  step, evidence collection, terminal result. Authenticate callbacks with a
  per-environment secret and bind every callback to existing run and
  correlation IDs.
- [x] Store browser step plans as read-only todo entries before dispatch;
  transition entries only from trusted worker events. Generated source mode
  uses coarse safe stages rather than attempting to parse arbitrary source into
  user-facing actions.
- [x] Add authorized history endpoint plus SSE stream scoped to run or
  correlation ID. Send keepalives, resume with `Last-Event-ID`, and provide a
  polling fallback for reverse proxies that do not support SSE.
- [x] Build pipeline/timeline/todo UI on Run detail and Agent workspace:
  ordered timestamps, source labels, reconnect state, safe error summaries,
  and no raw model prompt, secret, or untrusted HTML rendering.
- [x] Test redaction, event ordering/idempotency, SSE authorization/reconnect,
  Temporal queued-to-terminal lifecycle, worker callback forgery rejection,
  and browser todo pass/fail/cancel transitions.

Exit criterion: a user sees what control-plane, agent, and browser worker are
doing during a run without exposing secret or changing the verdict authority.

## M5 — Agent workspace and governed review — complete

M4 completed 2026-08-10 and unlocked its activity history, correlation timeline,
and Browser Agent progress dependencies. This is the next planned milestone.

Started 2026-08-10 +07:00. Scope: tenant- and project-authorized generation and
proposal review APIs, plus evidence-backed Agent workspace and Reviews queue UI.

Validated 2026-08-10: `uv run ruff check .`, `uv run pytest --basetemp D:\\tmp\\auto-at-m5-final`
(97 passed), dashboard `typecheck`, `test` (8 passed),
`lint`, production `build`, and `git diff --check` all passed. Dashboard tests
continue to emit the existing Node module-type warning; the production build
continues to emit existing multi-lockfile and Next ESLint-plugin warnings.

Completion summary: added tenant- and project-filtered paginated request, draft,
and proposal/approval listing routes. The Agent workspace now shows the safe
correlation-scoped activity timeline before a deterministic run exists. Reviews
now renders pending generated drafts and proposal evidence, links to the linked
run/correlation context, and submits immutable decisions through the control
plane before reloading persisted state. React text and `CodeBlock` retain hostile
model payloads as inert text. Changed paths: `apps/control-plane/api/v1/routes/generation.py`,
`apps/control-plane/api/v1/routes/proposals.py`,
`apps/control-plane/infrastructure/persistence/repositories.py`,
`apps/dashboard/app/components/activity-timeline.tsx`,
`apps/dashboard/app/run-api.ts`, `apps/dashboard/app/generation-api.ts`,
`apps/dashboard/app/generation-api.test.ts`, `apps/dashboard/app/generation-types.ts`,
`apps/dashboard/app/generation-dashboard.tsx`, `apps/dashboard/app/reviews/page.tsx`,
and `apps/dashboard/app/reviews/reviews-dashboard.tsx`. No deviations or deferred
M5 items. M6 is next.

- [x] Add read endpoints and list/filter APIs for generation requests, drafts,
  reviewable proposals, and approvals, all scoped through the existing project
  authorization check.
- [x] Extend Agent workspace to show the live generation timeline, request
  fingerprint/redacted request, safe failure, draft source, assumptions, stop
  conditions, provenance, linked test case, and linked run.
- [x] Build Reviews queue with clear pending/approved/rejected state; include
  proposal evidence and deterministic run context before an approver decides.
- [x] Keep approval/rejection final and immutable; confirmation UI states its
  effect, captures optional reason, disables after response, and renders the
  persisted decision rather than optimistic local authority.
- [x] Link every draft/proposal to run detail and correlation timeline; surface
  provider/model only from redacted provenance already sanctioned by backend.
- [x] Test role-specific visibility and decision rights, service/reviewer
  restrictions, immutable duplicate decisions, and safe rendering of hostile
  model output.

Exit criterion: users can understand agent work and make a governed decision
with the evidence and audit context required by the platform boundaries.

## M6 — Quality gate — complete

Started 2026-08-10 +07:00. Scope: close contract, dashboard accessibility, and
local acceptance coverage gaps; then validate the documented authenticated
workflow and refresh its operator guidance. Existing M5 changes are preserved.

- [x] Add route contract tests for all new auth, administration, catalog, run,
  activity, and review APIs; include unauthenticated, forbidden, tenant-cross,
  malformed, and idempotent cases.
- [x] Add dashboard tests for accessibility labels, keyboard navigation, role
  gating, responsive shell, status colors/text, SSE fallback, and protected
  artifact links.
- [x] Add Compose end-to-end acceptance: bootstrap admin → login → provision
  contributor → login → create/select project/test → create run → live
  pipeline/todo → evidence → failure triage → governed generation review.
- [x] Run Python `uv run ruff check .` and `uv run pytest`; run dashboard
  `lint`, `typecheck`, `test`, and production `build`; run Compose worker
  checks with a fresh artifact volume.
- [x] Update README and API examples: bootstrap command, first login, account
  provisioning, normal UI run flow, local troubleshooting, and known security
  boundaries.

Exit criterion: all checks pass and a user can complete the core workflow
without sending identity headers or entering UUIDs.

Validation 2026-08-10 23:55 +07:00: `uv run ruff check .`, `uv run pytest
--basetemp D:\\tmp\\auto-at-m6-final-acceptance` (106 passed), dashboard `lint`,
`typecheck`, `test` (10 passed), and production `build` all passed; `git diff
--check` passed. The Playwright worker `typecheck` and the two Compose worker
evidence tests passed after recreating only the `auto-at-ui_execution-artifacts`
volume. The dashboard tests and build retain the existing Node module-type,
multiple-lockfile, and Next ESLint-plugin warnings; none affected results.

Completion summary: added unauthenticated/malformed dashboard API route-family
contracts; extracted and tested timeline ordering, accessible connection labels,
and SSE-to-polling fallback behavior; added cookie-session API examples plus
dashboard troubleshooting/security-boundary guidance; and added a Compose-backed
acceptance test that bootstraps an admin through the CLI, uses cookie session and
CSRF authentication to provision and sign in a contributor, creates/selects a
project and test, validates passed/failed runs, timeline, and evidence, and
performs a governed generated-draft decision. Deterministic fixture records
represent agent output so this validation does not depend on an external model
gateway; the review decision itself uses the public API. The test also uncovered
and fixed PostgreSQL foreign-key ordering in account bootstrap/provisioning.
Changed paths for M6:
`tests/test_dashboard_route_contracts.py`,
`tests/test_playwright_worker_compose.py`,
`apps/control-plane/application/authentication.py`,
`apps/dashboard/app/components/activity-timeline.tsx`,
`apps/dashboard/app/components/activity-timeline-model.ts`,
`apps/dashboard/app/components/activity-timeline-model.test.ts`, `README.md`,
and `docs/api-examples.md`. No deviations or deferred M6 items.

## Implementation rules

- Work M1–M6 in order. Mark a milestone done only after every listed task and
  its exit criterion are complete; update this document in the same change.
- Keep `main.py` as application assembly, environment reads in `config.py`,
  HTTP in `api/`, use cases in `application/`, pure policy in `domain/`, and
  adapters in `infrastructure/`.
- Preserve target-neutral `TestExecutionRequest` / `TestExecutionResult` v1;
  activity and session interfaces are additive and must not alter runner
  verdict semantics.
- Do not select a cloud, model, OIDC provider, email provider, or production
  retention policy without user direction.

Exit criterion: all checks pass and a user can complete the core workflow
without sending identity headers or entering UUIDs.
