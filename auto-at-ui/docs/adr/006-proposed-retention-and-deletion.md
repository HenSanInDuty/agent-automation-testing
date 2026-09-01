# ADR-006: Proposed artifact, log, and audit retention and deletion policy

- Status: Accepted
- Date: 2026-07-27

## Context

Artifacts and logs can contain test data, browser evidence, URLs, and redacted
agent inputs. Local RustFS retention is not a production policy. The platform
must retain enough evidence for reproducibility and auditability while limiting
data exposure and supporting deletion requests.

## Proposed decision

Classify and retain data by purpose. Retention is calculated at creation time,
stored as `retention_until`, applied by scheduled deletion jobs, and reflected
in object-storage lifecycle rules. Redaction occurs before logs or agent inputs
are persisted; raw secrets and unredacted production PII must never be stored.

| Data class | Default retention | Deletion behavior |
| --- | --- | --- |
| Run artifacts (screenshots, video, traces, reports) | 30 days | Delete object and metadata after expiry; record a minimal deletion audit event. |
| Operational logs and telemetry | 30 days | Expire from the observability backend; do not copy raw artifact payloads into logs. |
| Redacted agent evidence and proposal inputs | 90 days | Delete payloads and derived embeddings; retain only non-sensitive reproducibility hashes. |
| Run/result metadata and proposal decisions | 1 year | Delete or anonymize at expiry unless a documented legal hold applies. |
| Immutable audit events | 1 year online, then 6 additional years in restricted archive | Erase/anonymize personal fields at expiry while retaining integrity hash chains and deletion records. |
| Benchmark manifests and anonymized aggregate metrics | 3 years | Delete source links and tenant identifiers at expiry; retain only approved anonymized research data. |

A tenant administrator may request early deletion for a project or run. The
system authorizes the request, places the target in `deletion_pending`, deletes
application records, artifacts, embeddings, and search indexes within 30 days,
and records a completion audit event. Backups are encrypted and expire within
35 days; erased data is not restored except for an approved disaster-recovery
event, after which the deletion queue is replayed. Legal holds suspend deletion
only for specifically identified data and are auditable.

Retention extension is disabled by default. A project administrator may set a
shorter value; a tenant administrator may request a documented longer value
subject to privacy/legal approval. Access to archived audit data is restricted
to named operational and compliance principals.

## Consequences

- Artifact metadata and logs need retention fields, deletion state, correlation
  IDs, and failure metrics so failed deletions alert the operational owner.
- Backup/recovery procedures must prove that tenant isolation, retention, and
  deletion requests survive restoration.
- Dashboard views must show evidence expiry and deletion status, but cannot
  bypass authorization or alter retention without API authorization.
- The periods are a product proposal, not a jurisdiction-specific legal claim;
  legal/privacy approval is required before production data is processed.

## Follow-up

The default periods, 30-day deletion completion target, and 35-day backup
expiry are approved. Name the operational and compliance owners in the
operations runbook; amend this ADR if contractual, regional, or legal
requirements differ.
