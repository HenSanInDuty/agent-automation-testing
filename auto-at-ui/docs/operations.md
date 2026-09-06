# Local observability

Fluent Bit reads first-party container stdout, parses JSON records, redacts sensitive-shaped fields again, and forwards to Loki. Grafana is local-only at `http://localhost:3001`; product users have no Grafana or Loki authorization path.

Use the **Auto-AT / Run Investigation** dashboard and enter a correlation or run ID in its single search field. The dashboard searches the redacted JSON log record without turning either ID into a Loki label. Loki keeps local data for 30 days. Fluent Bit has a finite filesystem buffer and bounded retries: a collector or Loki failure is observable but cannot alter a deterministic run verdict.

For production, choose Grafana authentication/RBAC, alert routing, TLS, and a durable Loki topology before exposing any endpoint.

## Artifact retention and legacy migration

The Temporal worker deletes expired RustFS evidence in small retryable batches. It deletes verified bytes first and tenant-scoped metadata second; a provider failure leaves metadata for a later retry. RustFS object deletion is idempotent. Do not use this local worker as proof of a production retention, legal-hold, backup, or recovery policy.

`scripts/migrate_minio_to_rustfs.py` is read-only by default and inventories a legacy MinIO bucket. Copy mode requires `--copy --confirm-copy COPY_LEGACY_MINIO`, streams each object, and verifies destination size and SHA-256 metadata. It never deletes or modifies the source. Obtain separate operator approval after reconciliation before retiring a legacy volume or bucket.

## Vision debug-evidence operations

The `vision_debug_evidence` migration must be applied before capture is enabled.
Configure the separate deployment-secret variables `VISION_DEBUG_EVIDENCE_ENCRYPTION_KEY`
and `VISION_DEBUG_EVIDENCE_KEY_ID`; do not add their values to Compose, Grafana, or
application configuration records. During a bounded key rotation only, configure
`VISION_DEBUG_EVIDENCE_PREVIOUS_ENCRYPTION_KEY` and
`VISION_DEBUG_EVIDENCE_PREVIOUS_KEY_ID` to read records under the retired key. Capture
and administration access remain disabled or unavailable if the current key or ID is
absent. The cleanup worker reports only safe deleted, failed, and overdue counts and
deletes records at the fixed seven-day deadline without decrypting.

Grafana/Loki must retain only safe aggregate diagnostic codes and operational counts.
Never build a log query, label, dashboard panel, or alert annotation from encrypted
payloads, plaintext diagnostics, prompts, screenshots, URLs, tenant content, or IDs.
See `docs/vision-agent-operations.md` for rotation, incident, canary, and smoke-test
procedures.

## Vision visual replay operations

Apply the `visual_replay_frames` migration before deploying capture code. Verify
the private RustFS policy allows only the tenant-scoped
`tenants/<tenant>/vision-explorations/<session>/states/` prefix, then exercise a
synthetic PNG capture, authorized read, and tenant-admin deletion. Do not
backfill old sessions: their worker copies were intentionally cleaned up.

Replay bytes have no automatic expiry. A deletion first removes the verified
private object and only then marks its metadata deleted; a storage failure keeps
metadata for an authorized retry. Monitor aggregate capture, verified-read,
delete-requested, delete-completed, delete-failed, orphan, retained-count, and
retained-byte metrics only. Do not put a screenshot, storage key, URL, prompt,
typed text, provider output, tenant ID, session ID, or correlation ID into logs,
tickets, alert labels, or dashboards. Production use remains subject to the
documented privacy/legal approval gate.
