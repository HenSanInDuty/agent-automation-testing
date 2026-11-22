# ADR-014: Vision readiness follows interaction state

- Status: Accepted for local implementation at the user's request.
- Date: 2026-11-01

The v4 worker previously required all visible DOM text, attributes and geometry
to remain unchanged. Clocks, passive carousel images and framework counters could
therefore cause `settle_timeout`, or invalidate a screenshot/DOM observation before
the model's selected action was even checked.

Separate full visual semantics from interaction readiness. Keep full semantic
observations for before/after change reporting. The opaque state fingerprint uses
a versioned `interaction-v1` preimage containing URL, scroll, form presence and
interaction state. Form values remain private in memory and are still compared.
Controls retain their accessible identity, semantic attributes, destination,
enabled/editable state, viewport geometry, transparency and sampled hit testing.
Iframe geometry/occlusion and visible dialog/landmark presence remain relevant.
Passive text, passive image motion and unrelated framework attributes no longer
require a quiet window. Known semantic `data-state`/`data-status` are retained.

The same comparison protects settling, capture, DOM observation, pending actions
and checkpoint restoration. Changing only the settle timeout would move the same
failure to a later phase. Visible `aria-busy=true` still prevents readiness until
it clears. Navigation and scrolling (including replay) allow up to 10 seconds
for readiness and require an 800 ms quiet window; local actions retain a 1.5 second
budget and 160 ms quiet window. Scrolling can reveal lazy content, so the former
local-action budget could expire after only two slow DOM observations. All waits
remain capped by the original operation deadline. An observation that finishes
after that deadline cannot certify readiness. Continuously changing controls
still fail with diagnostic frames and cannot create a checkpoint.
DOM bindings can be reused after a verified checkpoint restore, preserving queued
candidate batches. Each use still checks current interaction state and resolves
the live target; duplicate execution IDs return their immutable recorded outcome.
Moving controls, changing link destinations or names, overlays and form changes
remain conservative invalidations; this is not a blanket exemption for every
carousel. The worker still resolves a unique live target, verifies its DOM
identity again before execution, and uses Playwright actionability checks without
`force`. This does not certify arbitrary noninteractive text as unchanged.

Advisory v4 browser contexts request `prefers-reduced-motion: reduce`. A real-target
regression on mongchiton.vn exposed perpetual `play-now-pulse` transforms on two
link ancestors, which correctly kept invalidating live control geometry. The site
already supplies a reduced-motion CSS variant that disables those pulses. Use that
accessible variant consistently across navigation, screenshots, DOM observations
and actions; do not inject CSS, freeze timers or ignore moving controls.
Sites that ignore the preference remain subject to the same checks.
This changes the exploration browser environment, not deterministic runner
configuration; animation behavior under normal motion needs a separate test.

No prompt, provider, approval boundary, retry behavior, artifact retention, or
deterministic test assertion changes. `TestExecutionRequest` and
`TestExecutionResult` remain v1. The v4 wire schema and opaque fingerprint format
are unchanged. Existing persisted outcomes are immutable. Because fingerprints
are held by live browser sessions, finish active sessions before replacing the
worker and use new sessions after deployment or rollback.

Validation includes visible passive animation through setup, screenshot capture,
DOM observation, model latency, a verified click and back/checkpoint restoration;
negative cases cover movement, overlays, disabled/renamed targets, link changes,
hidden form changes, transparent ancestors and iframe occlusion. Existing browser
action, evidence, lease/fencing, duplicate-execution and replay tests still apply.
