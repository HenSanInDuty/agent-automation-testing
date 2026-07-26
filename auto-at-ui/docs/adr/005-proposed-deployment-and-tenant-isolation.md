# ADR-005: Self-hosted deployment and tenant-isolation model

- Status: Accepted
- Date: 2026-07-27

## Context

Docker Compose is a local research stack, not a production topology or tenant
boundary. The platform stores tenant-scoped transactional records in PostgreSQL
and binary artifacts in S3-compatible storage. Phase 6 requires a clear
production-like isolation model without selecting a cloud vendor prematurely.

## Decision

Adopt a logical multi-tenant SaaS model with application-enforced tenant and
project authorization, plus tenant-partitioned object storage paths. Start with
a self-hosted deployment managed by the platform team. Deploy the control
plane, Temporal workers, dashboard, PostgreSQL, telemetry collector, and object
storage adapters as separately configurable services in a private network. Only
the dashboard/API ingress and explicitly required worker egress are public.

The initial isolation controls are:

- Every business query and command receives the authenticated principal and
  checks tenant/project membership before repository access.
- PostgreSQL retains `tenant_id` on tenant-owned tables, uses composite tenant
  indexes/constraints, and will add row-level security before the first shared
  production tenant is onboarded.
- Artifact keys begin with an opaque tenant ID and project/run IDs; artifact
  download uses short-lived, authorized URLs after metadata authorization and
  checksum verification.
- Worker identities have only the queues, artifact prefixes, and API scopes
  required for assigned runs. They cannot approve proposals or query unrelated
  tenant data.
- Secrets come from the deployment runtime's secret source, never images,
  configs, database JSON, logs, contracts, or source control.
- Separate production, staging, and local environments use independent
  credentials, databases/buckets, namespaces, and telemetry destinations.

Single-tenant dedicated deployment remains a supported stronger-isolation
option for regulated customers. It uses the same `Principal` and tenant-scoped
contracts, but one deployment/database/bucket namespace per customer. No
cross-tenant analytics export is enabled by default.

Cloud-provider selection is explicitly deferred. Any future managed-service,
Kubernetes, or cloud deployment must preserve these boundaries and must not
alter the runner contract.

## Consequences

- The application can be validated against multi-tenant authorization behavior
  without coupling to a cloud provider.
- A shared deployment needs row-level security, backup restoration tests, and
  regular tenant-isolation penetration tests before onboarding external users.
- The dashboard cannot infer authorization from URL parameters or cached lists;
  every read is checked by the API.
- Infrastructure-as-code and CI integration tests must demonstrate separate
  staging and production configuration and no default credentials.

## Follow-up

Logical multi-tenancy is the default and dedicated deployments are an optional
stronger-isolation tier. Before external production use, document the concrete
self-hosted topology, region/residency requirements, and operational owner. A
cloud migration requires a separate ADR.
