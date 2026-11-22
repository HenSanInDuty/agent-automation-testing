# ADR-021: Bounded DOM collection and heartbeat read timing

- Status: Accepted for local implementation.
- Date: 2026-11-08
- Extends ADR-019 and ADR-020.

Live Mongchiton sessions still encountered capture drift after controller-owned
scrolling. The read-only probe distinguishes interaction changes from URL, form
and scroll changes without logging private comparison material.

Reduce independent browser round trips: deduplicate identical locator candidates,
read visibility/enabled/editable/geometry concurrently, and collect signatures
inside bounded batches of eight grounded candidates. Preserve document order,
byte/element limits, exact-node and unique-locator checks, full before/after state
equality, context equality, and all physical prepare/execute guards. Failed
collections release their document and retained target handles. No browser action
or model call is repeated by these changes.

A separate heartbeat race can report an active bridge offline: the caller samples
time before reading the file, but an atomic replacement during I/O can contain a
later timestamp. Measure elapsed read time with a monotonic clock and evaluate
freshness at the end of the read. Keep the supplied wall-clock origin, existing
expiry threshold, future-time rejection, tenant/bridge/model binding and all
consent checks. No grace period, provider fallback or model retry is introduced.

The saved task, `Kiểm tra các nút xem có hoạt động không`, did not match the
conservative all-buttons recognizer. Add the explicit Vietnamese functionality
question suffix (with optional `xem`, `hay không` and terminal question mark).
This activates the existing `visual_buttons` path for the user's button-only
request. Full matching still rejects mixed button/link tasks, negations and
additional instructions. No keyword-based narrowing or page-text inference is
introduced. Existing button classification and target guards remain unchanged.

The corrected scope exposed the previously recorded download regression. Attribute
download initiation only to the executing click's source page or a new page in
that operation; cancel it and retain no file. Unattributed/background downloads
still poison the session. An initiated download is non-replayable and records
`download_started`, not verified file contents. Close only the new uncommitted
download tabs (empty, `:` or `about:blank` URL), retaining before/after evidence
and a checkpoint on the source page. Dialog handling remains unchanged.

A known popup can hydrate between its click capture and restoration. Before
closing it, check its saved checkpoint. On drift, record one bounded read-only
refresh on that same popup, consuming the existing state/operation budget, then
use the unchanged close prepare/execute gates. Never replace the source-page
checkpoint: it must still match independently before any sibling click. A failed
refresh or changed page identity stops restoration without a close or click.

Controller-owned viewport scrolling may be rejected during prepare if a carousel
ticks after revalidation. Permit at most three new prepare intents, refreshing
and revalidating context between them, only for `rejected/state_mismatch` or
`rejected/state_changed_during_prepare`. Executed, failed and unknown outcomes
are never repeated. Existing state, hop, operation and step limits remain active.

In-process Alembic migration must preserve existing application loggers. Set
`disable_existing_loggers=False`; otherwise a migration silences later worker
transport diagnostics and defeats their correlation/redaction checks.

Final image capture also brackets pixels with state reads. If navigation destroys
one of those reads, discard the attempt and retry evidence within the same
ten-second deadline; arbitrary errors are not retried. Log fixed capture-stage,
error-category and attempt counters, never exception text or page contents.
An executed action without a checkpoint reports its after-evidence failure rather
than the successful action's `observed` code. Preserve the executed action and
never replay it to recover evidence.

Enable Compose `init` for the Playwright worker. Repeated Chromium launches left
orphaned child processes under the npm/Node PID 1 and eventually exhausted the
unchanged 256-task container limit. Init reaps exited children; do not increase
the PID, memory, CPU or browser timeout limits to hide this accumulation.

Provider/model, prompt v11, data transfer/redaction, approval boundaries,
retention, operation budgets and TestExecutionRequest/TestExecutionResult v1 are
unchanged. Local services are drained before rollout. Synthetic checks and live
results are recorded separately in the dated stability report.
