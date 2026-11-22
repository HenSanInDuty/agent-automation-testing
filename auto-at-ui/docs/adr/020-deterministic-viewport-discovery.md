# ADR-020: Deterministic viewport discovery after model abstention

- Status: Accepted for local implementation at the user's request.
- Date: 2026-11-08
- Extends ADR-015 and ADR-019.

The Mongchiton trial completed its model call but rejected a delayed scroll-only
reply as `bridge_stale_result`. Scrolling has no bound DOM target to revalidate.
Viewport discovery therefore belongs to the controller's existing scan loop.

Exploration prompt v11 asks for actions within the current viewport and
`no_safe_action` when none is appropriate. In the deterministic scan mode, a
validated DOM abstention or legacy scroll-only reply produces no accepted action
and no target bindings. Its scroll delta is discarded. Mixed, image-stage and
completion replies retain the existing stale-response checks.

Before scanning, the worker verifies fresh evidence against the original Page,
document root, URL, scroll position, form structure/private values, visible
landmarks/dialogs/headings, tenant, session and fencing token. Context-only
revalidation remaps no targets. Private comparison material stays in worker RAM.
A changed viewport checkpoint requires an explicitly recorded read-only refresh
with fresh screenshots, state and checkpoint IDs. At most three observation
attempts can recover capture races; context changes fail immediately. Refreshes
consume the existing state, hop, operation and step budgets. No model call or
physical action is retried by this path.

The controller scrolls by 80% of the observed viewport height using the existing
prepare/execute guards. It can continue deterministic discovery after exhausting
the model-call budget, but cannot obtain another model proposal. Changed context,
unstable evidence or exhausted budgets preserve partial coverage. Pending controls
and missing evidence are never converted into successful coverage.

The private v4 transport adds context-only observation and the required
`viewport-context-v1` capability. Deploy the controller and Playwright worker
together, and rebuild the Codex bridge for prompt v11. An older worker is rejected
at open before a model call. Drain active sessions before a local rollout or
rollback; preserve historical evidence and do not replay unknown actions.

The authorized provider/model, transfer consent/redaction, rate/cost limits,
artifact retention, RBAC and tenant isolation remain unchanged. The change adds
the safe `viewport.scan_ready` progress event. Generated-test approval and the
target-neutral TestExecutionRequest/TestExecutionResult v1 remain unchanged.

Validation uses a local autoplay carousel with a lower button and delayed fake
model replies, plus Chromium checks for context drift and transport capability
checks. The dated benchmark resume record contains measured synthetic and live
results; this decision alone makes no claim of complete Mongchiton coverage.
