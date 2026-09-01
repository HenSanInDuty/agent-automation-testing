# Local observability

Fluent Bit reads first-party container stdout, parses JSON records, redacts sensitive-shaped fields again, and forwards to Loki. Grafana is local-only at `http://localhost:3001`; product users have no Grafana or Loki authorization path.

Use the **Auto-AT / Run Investigation** dashboard and enter a correlation or run ID. Those values are JSON fields, never Loki labels. Loki keeps local data for 30 days. Fluent Bit has a finite filesystem buffer and bounded retries: a collector or Loki failure is observable but cannot alter a deterministic run verdict.

For production, choose Grafana authentication/RBAC, alert routing, TLS, and a durable Loki topology before exposing any endpoint.

## Artifact retention and legacy migration

The Temporal worker deletes expired RustFS evidence in small retryable batches. It deletes verified bytes first and tenant-scoped metadata second; a provider failure leaves metadata for a later retry. RustFS object deletion is idempotent. Do not use this local worker as proof of a production retention, legal-hold, backup, or recovery policy.

`scripts/migrate_minio_to_rustfs.py` is read-only by default and inventories a legacy MinIO bucket. Copy mode requires `--copy --confirm-copy COPY_LEGACY_MINIO`, streams each object, and verifies destination size and SHA-256 metadata. It never deletes or modifies the source. Obtain separate operator approval after reconciliation before retiring a legacy volume or bucket.
