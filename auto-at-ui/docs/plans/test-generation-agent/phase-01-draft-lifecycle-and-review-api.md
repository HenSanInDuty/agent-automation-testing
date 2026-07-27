# Phase 1 — request, draft lifecycle, and review API

**Status:** complete  
**Prerequisite:** Phase 0 complete  
**Exit:** An authorized user can submit a redacted natural-language request,
inspect its resulting draft, and make one immutable decision. Approval atomically
creates one test case and one queued v1 run.

## Lifecycle and authority

A generation request moves `queued` → `generating` → `completed` or `failed`.
On completion it creates one draft in `pending_review`; a draft moves only to
`approved` or `rejected`. Only `pending_review` drafts can be decided, and a
final decision is immutable. The planner may move only request-generation
states; it cannot approve, create a test case, create a run, or dispatch work.

- Contributors, project administrators, and tenant administrators may submit
  and approve for projects they are authorized to access.
- Viewers are read-only. Reviewer-only and service identities cannot approve.
- Project and tenant administrators alone may manage the project origin policy.

## Checklist

- [x] Add migrations and tenant-scoped repositories for generation requests,
  drafts, immutable decisions, and project execution policies.
- [x] Accept a target URL and natural-language request. Redact it before any
  persistence, calculate the request hash server-side, reject credentials, and
  enforce the project origin policy before publishing generation work.
- [x] Add endpoints to submit and query requests/drafts, inspect only redacted
  content, and approve or reject a pending-review draft. Add an administrator-only
  project-policy endpoint.
- [x] Enforce the lifecycle and exact role rules above at the application
  boundary; routes contain no persistence or dispatch logic.
- [x] On approval, verify the stored source hash, create a versioned test case,
  v1 deterministic run, audit events, and an idempotent dispatch outbox event
  in one transaction.
- [x] Make submission and decisions idempotent. A matching retry returns its
  existing linked records; a conflicting final decision is rejected without
  resource leakage or duplicate test cases/runs.

## Completion demonstration

A contributor submits a request for an allowed URL and observes `queued`, then
`completed` with a `pending_review` draft. Approval creates one linked test case and queued v1 run. Rejection,
a duplicate approval, a reviewer-only actor, or a cross-tenant actor cannot
create a run.

## Validation

Domain/application lifecycle and idempotency tests, HTTP authorization and
redaction tests, plus migration and tenant-isolation tests.
