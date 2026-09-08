export type RequestState = "queued" | "generating" | "completed" | "failed";
export type DraftState = "pending_review" | "approved" | "rejected";

export type GenerationRequest = {
  id: string;
  project_id: string;
  correlation_id: string;
  target_url: string;
  redacted_request: string;
  request_hash: string;
  state: RequestState;
  failure_reason: string | null;
  draft_id: string | null;
};

export type GeneratedDraft = {
  id: string;
  planning_request_id: string;
  correlation_id: string;
  state: DraftState;
  title: string;
  playwright_test_source: string;
  source_hash: string;
  assumptions: string[];
  stop_conditions: string[];
  provenance: Record<string, unknown>;
  linked_test_case_id: string | null;
  linked_run_id: string | null;
  preflight_repair_request_id: string | null;
  preflight_message: string | null;
};

export type ProposalDecision = { proposal_id: string; proposal_version: number; approved: boolean; decided_by: string; reason: string | null };
export type Proposal = { id: string; run_id: string; correlation_id: string; kind: string; proposal_version: number; summary: string; payload: Record<string, unknown>; decision: ProposalDecision | null };
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

export type Run = { id: string; correlation_id: string; status: string; revision: string };
export type Artifact = { id: string; kind: string; uri: string; checksum: string; size: number; content_type: string | null };

export type VisionPolicy = {
  enabled: boolean;
  provider: string;
  model: string;
  raw_screenshot_transfer_accepted: boolean;
  max_steps: number;
  max_screenshot_bytes: number;
  max_session_seconds: number;
  max_cost_usd: number;
  max_requests_per_minute: number;
};
export type ProjectExecutionPolicy = {
  allowed_origins: string[];
  vision_max_hops: number;
  vision_max_states: number;
};
export type VisualExploration = {
  trace_version?: "legacy" | "v4";
  id: string;
  project_id: string;
  correlation_id: string;
  state: "queued" | "running" | "completed" | "unavailable" | "cancelled";
  policy_version: string;
  provider: string;
  model: string;
  max_steps: number;
  max_hops: number;
  max_states: number;
  max_screenshot_bytes: number;
  max_session_seconds: number;
  safe_failure_reason: string | null;
};
export type VisualAction = {
  sequence: number;
  action: { kind: "click" | "type" | "scroll" | "wait" | "stop"; confidence?: number; x?: number; y?: number; delta_y?: number; duration_ms?: number };
  evidence_checksum: string | null;
};
export type VisualReplayFrame = {
  id: string;
  state_id: string;
  sequence: number;
  checksum: string;
  size: number;
  content_type: "image/png";
  captured_at: string;
  actions: VisualAction[];
};
export type VisualReplayFrames = { items: VisualReplayFrame[] };
export type VisualTrajectoryState = { id: string; parent_id: string | null; hop: number; sequence: number | null; captured_at: string; frame_id: string | null };
export type VisualTrajectoryEdge = { id: string; parent_state_id: string; proposal_id: string; attempt: number; action: VisualAction["action"]; confidence: number; status: string; outcome_code: string | null; child_state_id: string | null; observed_at: string | null; duration_ms: number; url_change: string };
export type VisualTrajectory = { session: { id: string; state: string; safe_failure_reason: string | null }; trajectory_available: boolean; legacy_label: string | null; states: VisualTrajectoryState[]; proposals: { id: string; state_id: string | null; sequence: number; action: VisualAction["action"]; confidence: number | null }[]; edges: VisualTrajectoryEdge[] };
export type VisionProgressActivity = {
  id: string;
  run_id: string | null;
  correlation_id: string;
  source: "vision";
  stage: string;
  status: string;
  safe_summary: string;
  metadata: Record<string, string | number | boolean>;
  occurred_at: string;
};
export type VisionDebugEvidence = {
  id: string;
  diagnostic_code: string;
  provider: string;
  model: string;
  prompt_version: string;
  captured_at: string;
  retention_until: string;
};
export type VisionDebugEvidencePayload = VisionDebugEvidence & { payload: string };

export type OperationFrame = { id: string | null; availability: "retained" | "deleted" | "missing"; reason_code: string | null; captured_at?: string };
export type VisualOperation = { id: string; sequence: number; purpose: "setup" | "explore" | "restore" | "replay"; action_kind: string; status: string; started_at: string; outcome_code: string | null; state_id: string | null; locator_id: string | null; before: OperationFrame; after: OperationFrame };
export type VisualLocator = { id: string; operation_id: string; status: string; reason_code: string | null; verified_at: string | null; descriptor: { strategy: string; role: string | null; value: string; scope: { kind: string; selector: string }[] } | null; bounding_box: { x: number; y: number; width: number; height: number } | null };
export type VisualTrace = { schema_version: string; session_id: string; revision: string; trace_version: string; items: VisualOperation[]; locators: VisualLocator[]; next_sequence: number; has_more: boolean };
export type VisionHandoffBranch = { id: string; status: "ready" | "blocked"; reason_code: string | null; steps: { operation_id: string; locator_id: string | null; input_reference: string | null }[] };
export type VisionResult = { schema_version: string; session_id: string; project_id: string; revision: string; exploration_state: string; completion_reason: string | null; evidence_status: string; counts: Record<string, number>; branches: { id: string; status: string; reason_code: string | null }[]; handoffs: { id: string; branches: VisionHandoffBranch[] }[]; links: Record<"handoff" | "generation" | "draft" | "run" | "report", { state: string; id: string | null; href: string | null; reason_code?: string | null }>; limitations: string[] };
