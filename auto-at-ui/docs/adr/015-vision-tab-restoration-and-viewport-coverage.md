# ADR-015: Restore browser tabs and report bounded viewport coverage

- Status: Accepted for local implementation at the user's request.
- Date: 2026-11-01
- Extends ADR-012 and ADR-014.

Session ff335592-16ca-41df-b56c-0709f61972eb recorded five header clicks,
eight stale DOM rejections and no scrolls. A read-only refresh on the Support
popup replaced the last operation used to infer popup ancestry. Restoration
then navigated inside that popup, while DOM bindings still belonged to the
original tab. The three-call budget ended with a misleading completed result.

Track active page IDs and popup parents from completed browser operations,
independently of screenshot refreshes. Close descendant popups before restoring
a different branch. A restored/replayed page may be a new browser Page: collect
a fresh DOM snapshot when its page ID or fingerprint differs, then bind only an
exact, unique match of the already proposed descriptor on the same verified
checkpoint. Never weaken the worker's same-page or actionability checks, reuse
an old element ID across pages, or repeat an uncertain physical action.

A DOM observation may become stale after collection but before the first model
reservation. If planning returns `bridge_stale_result` with no calls used and an
unchanged call budget, allow at most two explicit read-only refresh operations.
Each records fresh frames, a checkpoint and DOM binding, consumes state/hop
capacity, and rechecks policy before planning. Never retry a stale response after
a call reservation, reuse a discarded proposal, or repeat a physical action.
Persistent drift still fails closed. Regression cases cover one pre-call drift,
persistent pre-call drift, and a stale response after model reservation.

After executing a batch, prioritize the next viewport of its source page before
planning child pages. Record an ordinary scroll operation, new before/after
evidence and checkpoint, then inventory and plan the newly visible controls.
Scroll by 80 percent of viewport height, within existing state/hop/operation
limits, only while another model call is available. The observation's existing
scrollable flag means there is vertical content below the current viewport.
Stop on no movement; nested scroll containers and unbindable controls remain
explicit coverage limitations. Existing URL/descriptor deduplication excludes
previously queued/attempted header targets on the same page.

Known pending, rejected, skipped, truncated or unvisited viewport coverage ends
as unavailable with exploration_call_limit or exploration_coverage_incomplete.
The UI labels these results Partial exploration. Retain evidence and the handoff,
but do not auto-submit generation from an incomplete exploration. No new state
enum, schema migration or historical outcome rewrite is needed.

Provider/model, centralized prompts, three-call default, cost/rate limits, consent,
tenant fencing, retention and approval boundaries remain unchanged. No live model
calls are needed for validation. Execution request/result contracts remain v1.
Validate with isolated PostgreSQL and a synthetic browser: refreshed popup then
sibling click on the original tab, reopened popup with fresh bindings, lower-page
content after scrolling, and retained partial evidence when the call budget ends.
Deploy controller, worker and dashboard together after active sessions finish.
