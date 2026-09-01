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
