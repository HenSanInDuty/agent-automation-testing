# ADR-004: Proposed identity and role-based authorization boundary

- Status: Accepted
- Date: 2026-07-27

## Context

Local development has one trusted developer and accepts `X-Tenant-Id` only as a
development boundary. It is not authenticated identity and must not be used in
a production-like deployment. Phase 6 needs an identity-independent `Actor` /
`Principal` interface so authorization is applied by application use cases,
not dashboard visibility or route-local headers.

## Proposed decision

Introduce a provider-neutral authentication adapter which verifies an external
identity token and constructs an immutable `Principal` containing:

- a stable subject identifier;
- authenticated tenant memberships;
- project-scoped role grants; and
- a request correlation ID.

The application receives an `Actor` derived from that principal and authorizes
every query and command against the requested tenant and project. The client
does not supply a tenant identifier as an authority claim. `X-Tenant-Id` stays
available only under an explicit local-development setting and is rejected in
production-like environments.

Use the following least-privilege roles for the first release:

| Role | Permissions |
| --- | --- |
| `viewer` | Read projects, tests, runs, artifacts, proposals, and audit history within granted projects. |
| `contributor` | `viewer` permissions plus create/cancel runs and create draft test definitions. |
| `reviewer` | `viewer` permissions plus approve or reject proposals for granted projects. |
| `project_admin` | Manage project membership/configuration and all `contributor`/`reviewer` actions. |
| `tenant_admin` | Manage tenant membership and projects; cannot alter immutable audit events. |
| `service` | A non-human, narrowly scoped workload identity; cannot approve or reject proposals. |

Approval requires the `reviewer`, `project_admin`, or `tenant_admin` role for
the proposal's exact tenant and project. A proposal author, agent, worker, and
service principal can never approve it. Authorization failures return a
non-enumerating `404` for inaccessible tenant/project resources, while audit
records retain the denied action category without storing secrets.

The initial production adapter should be OpenID Connect (OIDC) discovery and
JWT validation behind the port. Selecting a specific identity provider is
explicitly deferred to deployment planning; it must not change domain models or
application authorization policy.

## Consequences

- Phase 6 can test authorization entirely with fake principals and later add a
  provider adapter without changing routes or application use cases.
- Existing tenant-scoped repository calls remain necessary but no longer rely
  on a user-controlled header for authorization.
- Role grants, membership changes, approval decisions, and denied approval
  attempts become auditable events with correlation IDs.
- Dashboard pages consume protected API query endpoints only; they have no
  direct database access or browser-side authorization rules.

## Follow-up

The role matrix and OIDC-based provider-neutral boundary are approved. Select
the production identity provider and nominate its ownership team in the
deployment runbook before external production access is enabled.
