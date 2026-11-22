# ADR 041: Bridge authorization receipt clock-skew tolerance

Status: accepted (offline fix, round r9; not yet verified live)

## Context

Live session `79b90323` died with `bridge_policy_revoked` 2.2 s after a model job was created. The control plane
re-signs `authorization.json` every ~2 s (atomic `os.replace`); the bridge polls `FileSpool.stop_reason(request, now)`
every 0.1 s with `now` sampled before the file is read. A receipt re-signed between the sample and the read has
`recorded_at > now`, and the rule `recorded_at <= now` classed it as revoked.

## Decision

`stop_reason` accepts `recorded_at <= now + RECEIPT_CLOCK_SKEW` (1 s, named constant in `spool.py`). Everything else is
unchanged: missing receipt, `now >= authorization_expires_at`, expiry beyond the job deadline, ttl outside (0, 10] s,
non-`queued` status and a receipt recorded more than 1 s ahead of `now` still stop the job.

## Consequences

- Closes the poll race; no change to who writes receipts (the write was already atomic).
- A receipt may be honoured up to 1 s "early" relative to the bridge clock; the lease itself is still bounded by
  expiry (ttl <= 10 s), so the effective security window is unchanged.
- Rebuild `control-plane`, `temporal-worker` and `claude-bridge` (all import `spool.py`) before the next live round.
- Rollback: remove the `- RECEIPT_CLOCK_SKEW` term.
