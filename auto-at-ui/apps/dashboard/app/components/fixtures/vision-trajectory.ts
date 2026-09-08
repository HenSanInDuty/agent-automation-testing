import type { VisualTrajectory } from "../../generation-types";

/** Synthetic, redacted fixture: no screenshot bytes, URLs, text, or provider data. */
export const representativeTrajectory: VisualTrajectory = {
  session: { id: "00000000-0000-4000-8000-000000000001", state: "completed", safe_failure_reason: null },
  trajectory_available: true,
  legacy_label: null,
  states: [
    { id: "root", parent_id: null, hop: 0, sequence: 1, captured_at: "2026-09-07T00:00:00Z", frame_id: "frame-root" },
    { id: "child", parent_id: "root", hop: 1, sequence: 2, captured_at: "2026-09-07T00:00:01Z", frame_id: null },
  ],
  proposals: [],
  edges: [
    { id: "click-observed", parent_state_id: "root", proposal_id: "proposal-click", attempt: 1, action: { kind: "click", x: .4, y: .6 }, confidence: .9, status: "observed", outcome_code: null, child_state_id: "child", observed_at: "2026-09-07T00:00:01Z", duration_ms: 200, url_change: "unchanged" },
    { id: "scroll-no-change", parent_state_id: "root", proposal_id: "proposal-scroll", attempt: 1, action: { kind: "scroll", delta_y: 400 }, confidence: .7, status: "no_meaningful_change", outcome_code: null, child_state_id: null, observed_at: "2026-09-07T00:00:01Z", duration_ms: 100, url_change: "unchanged" },
    { id: "stop-terminal", parent_state_id: "root", proposal_id: "proposal-stop", attempt: 1, action: { kind: "stop" }, confidence: .5, status: "terminal", outcome_code: "model_stop", child_state_id: null, observed_at: null, duration_ms: 0, url_change: "unknown" },
    { id: "failed-capture", parent_state_id: "root", proposal_id: "proposal-failed", attempt: 1, action: { kind: "wait", duration_ms: 100 }, confidence: .4, status: "failed", outcome_code: "capture_failed", child_state_id: null, observed_at: null, duration_ms: 100, url_change: "unknown" },
  ],
};
