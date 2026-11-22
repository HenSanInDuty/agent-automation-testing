# ADR 029: Bounded reads during heartbeat replacement

Status: implemented; isolated validation passed, 2026-11-09.

Live iteration 09 completed 25 clicks and 69 operations without browser failure.
The seventh model job was cancelled after the producer reported `bridge_offline`.
The Temporal worker's allowlisted diagnostic recorded `FileNotFoundError`, errno
2, during heartbeat file reading (2 ms). The bridge process remained running and
had not restarted. The spool writes heartbeats with temporary-file `os.replace`;
the shared-mount read can observe the name as absent during replacement.

Retry only missing-heartbeat file validation/open reads, up to three attempts
with 10 ms between them. Recheck the plain-file invariant and read the current
file on each attempt. Root-directory, permission, malformed content, identity,
readiness, future timestamp and stale timestamp failures remain failures. No
cached readiness, stale grace period, changed authorization TTL or replay of a
cancelled model job is introduced. Freshness is checked at the end of the read,
including elapsed retry time, as before. Missing files after the bounded reads
still report offline.

Two red cases reproduce lstat/open replacement races. The matrix covers both
stages for transient/persistent missing files, permission denial, stale/future
timestamps, foreign tenant, malformed JSON and offline readiness. Host bridge
service/spool/process suite: 56 passed, 16 Linux-only skips (9.47s); Linux run
must execute those platform-specific cases before deployment.
Final Linux run `bb078006005f`: 72 passed, zero skips/failures/errors (11.561s).
