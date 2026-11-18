# ADR-013: Vision time limits apply to steps

- Status: Accepted for local implementation
- Date: 2026-10-25
- Supersedes the session-duration limit in ADR-010/012 for new v4 explorations.

The user requested a time limit for each step, not for the entire exploration.
New v4 sessions snapshot `step_timeout_seconds` (120 by default). There is no
elapsed-session deadline. Model-call counts, rate/cost limits, state/depth limits,
tenant isolation, consent checks, explicit cancellation and draft approval remain
unchanged. TestExecutionRequest/TestExecutionResult remain at v1. No prompt or
provider/model changes are required.

A browser step has one deadline shared by preparation, before evidence,
execution, after evidence and acknowledgement. A duplicate request cannot extend
it or execute an uncertain action again. Standalone reads and each planning batch
have fresh budgets; retries and rate waiting within a planning batch share that
batch's deadline. Codex jobs still receive finite expiry and authorization leases.
The HTTP adapter no longer shortens a configured step with a fixed 30-second
read timeout. Connection establishment remains bounded separately.

The private v4 transport adds optional `step_timeout_seconds` on open and
`step_deadline` on prepare, guarded by required capability `step-timeout-v1`.
The worker rejects missing, expired or oversized step deadlines in this mode.
Its deadline timer stays fixed between prepare and execute. Idle browsers are
reclaimed after controller inactivity (twice the step limit plus ten seconds,
at least thirty seconds); completed controller work renews this lease. Dashboard
preview polling cannot keep an orphan browser alive. This inactivity cleanup is
not a limit on the cumulative duration of an active exploration.

The existing policy key `max_session_seconds` remains as a compatibility wire
name and supplies the new step timeout. A nullable database column records the
new meaning explicitly. NULL preserves historical session limits and legacy
readers. New API/report responses expose `step_timeout_seconds`, and the dashboard
labels new reports as seconds per step and historical reports as per session.
Old traces and terminal outcomes are not rewritten; Reload creates a new session
with the new timing policy.

Deploy the compatible controller, worker and dashboard images together after
the additive migration. Existing active sessions must finish before replacing
the browser worker. Rollback retains the migration and requires compatible
readers; it must not silently send step-mode jobs to a legacy worker.

Focused validation covers an exploration whose start predates the old session
limit, browser work continuing beyond the initial deadline, a prepared action
expiring without execution, shared step timeout and uncertain-action handling,
legacy timing, HTTP submission snapshots, report labels and contract generation.
