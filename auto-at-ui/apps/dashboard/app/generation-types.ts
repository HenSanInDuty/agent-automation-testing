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

export type VisionProvider = {
  id: string;
  display_name: string;
  models: { id: string; display_name: string }[];
  configured: boolean;
  supports_inline_images: boolean;
  bridge_readiness?: { configured: boolean; online: boolean; authenticated: boolean; capabilities_qualified: boolean; model_access: "unverified" | "available" | "unavailable"; failure_code: string | null; busy?: boolean } | null;
};
export type CodexInputPolicy = { input_mode: "dom_first"; dom_transfer_accepted: boolean; dom_transfer_provider: "codex_cli" | "claude_cli" | null; max_dom_elements: number; max_dom_bytes: number };
export type VisionPolicy = {
  enabled: boolean;
  provider: string;
  model: string;
  raw_screenshot_transfer_accepted: boolean;
  raw_screenshot_transfer_provider?: string | null;
  codex?: CodexInputPolicy | null;
  input_policy_fingerprint?: string | null;
  max_steps: number;
  max_screenshot_bytes: number;
  max_session_seconds: number;
  max_cost_usd: number;
  max_requests_per_minute: number;
  /** Server-owned deployment flag; the client only reads it to offer the Agent loop engine. */
  agent_loop_enabled?: boolean;
};
export type ProjectExecutionPolicy = {
  allowed_origins: string[];
  vision_max_hops: number;
  vision_max_states: number;
  /** Owner declaration that the target is a test environment they own; GET always returns it, PUT omitted/null keeps the stored value. */
  vision_owned_test_target?: boolean;
};
/** Advisory outcome of an agent-loop task session. Never a test verdict; a deterministic run decides pass/fail. */
export type VisionTaskAssessment = {
  schema_version: "v1";
  status: "achieved" | "not_achieved" | "blocked" | "inconclusive";
  summary: string;
  checks: { expectation: string; status: "met" | "not_met" | "not_checked"; evidence: string }[];
  source: "agent" | "controller";
  stop_reason: "agent_done" | "agent_stopped" | "agent_step_limit";
  facts: { actions_completed: number; actions_failed: number; actions_blocked_or_skipped: number };
  advisory: true;
};
export type VisualExploration = {
  step_timeout_seconds?: number | null;
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
  engine?: "planner" | "agent_loop";
  task_assessment?: VisionTaskAssessment | null;
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

export type VisionExplorationConclusion = {
  status: "completed" | "partial" | "cancelled" | "in_progress";
  coverage: "observed_controls_completed" | "not_established";
  interaction_scope: "buttons" | "visual_buttons" | "all" | "unknown";
  observed_controls: number | null;
  control_kinds?: Partial<Record<"native" | "styled_link" | "custom", number>>;
  completed_controls: number | null;
  remaining_controls: number | null;
  inventory_limited: boolean;
  operations_completed: number;
  operations_failed: number;
  operations_rejected: number;
  operations_unknown: number;
  operations_pending: number;
  candidates_not_attempted: number;
  business_outcome: "unverified";
};
export type VisionExplorationReport = {
  conclusion?: VisionExplorationConclusion;
  status: "completed" | "partial" | "in_progress";
  coverage: "not_established" | "observed_controls_completed";
  stop_reason: string | null;
  limits: { max_steps: number; max_hops: number; max_states: number; max_session_seconds: number; step_timeout_seconds?: number | null };
  summary: { controls_acted_on: number; actions_rejected: number; actions_failed: number; actions_unknown: number; scrolls_completed: number; candidates_not_attempted: number };
  findings: { operation_id: string; sequence: number; action_kind: string; status: string; reason_code: string | null; target: string | null; url_change: string; visual_change: string }[];
};

export type ExecutedClick = { x: number; y: number; viewport_width: number; viewport_height: number; before_frame_id: string; confirmed_at: string };
export type OperationFrame = { id: string | null; availability: "retained" | "deleted" | "missing"; reason_code: string | null; captured_at?: string };
/** Agent-loop reasoning for the step that produced an operation; present only in agent_loop sessions. */
export type VisualAgentStep = { step_index: number; evaluation_previous_goal: string; memory: string; next_goal: string; skipped_actions: { index?: number; kind?: string; ref?: string; skipped_reason?: string; stop_cause?: string }[] };
export type VisualOperation = { agent_step?: VisualAgentStep | null; executed_click?: ExecutedClick | null; id: string; sequence: number; purpose: "setup" | "explore" | "restore" | "replay"; action_kind: string; status: string; started_at: string; outcome_code: string | null; state_id: string | null; locator_id: string | null; before: OperationFrame; after: OperationFrame };
export type VisualLocator = { originating_frame_id?: string | null; id: string; operation_id: string; status: string; reason_code: string | null; verified_at: string | null; descriptor: { strategy: string; role: string | null; value: string; scope: { kind: string; selector: string }[] } | null; bounding_box: { x: number; y: number; width: number; height: number } | null };
export type VisualPageInventory = { state_id: string; checkpoint_id: string; page_url: string | null; url_fingerprint: string; interaction_scope?: "all" | "buttons" | "visual_buttons"; truncated: boolean; scrollable: boolean; skipped_count: number; controls: { key: string; button_kind?: "native" | "styled_link" | "custom" | null; role: string; name: string; status: "pending" | "queued" | "completed" | "failed" | "rejected"; proposal_id: string | null; operation_id: string | null }[] };
export type VisualTrace = { schema_version: string; session_id: string; revision: string; trace_version: string; items: VisualOperation[]; locators: VisualLocator[]; pages?: VisualPageInventory[]; next_sequence: number; has_more: boolean };
export type VisionHandoffBranch = { id: string; status: "ready" | "blocked"; reason_code: string | null; steps: { operation_id: string; locator_id: string | null; input_reference: string | null }[] };
/** Advisory agreement report for sessions of the same task (ADR-047). The API decides `eligible`; the client only shows it. */
export type AgentTaskConsistency = {
  schema_version: "v1";
  session_id: string;
  group_sessions: number;
  assessed_sessions: number;
  status_counts: Record<string, number>;
  modal_status: string | null;
  modal_count: number;
  agreement_rate: number | null;
  source_status: string | null;
  source_is_modal: boolean;
  threshold: number;
  small_sample: boolean;
  eligible: boolean;
  reasons: ("assessment_inconsistent" | "modal_not_achieved" | "source_not_modal")[];
  advisory: true;
  notice: string;
};
/** What the requester must type for a session (`GET .../test-draft/inputs`): one entry per `type` step in the order `values` expects; only lengths, never a value. `step_index` can repeat, so it is not a key. */
export type AgentTaskDraftInputs = { owned_test_target: boolean; has_type_steps: boolean; type_steps: { step_index: number; locator_name: string; text_chars: number }[] };
/** Identity and state of a draft made from an agent session. The typed values never come back in this response. */
export type AgentTaskDraftCreated = {
  request_id: string;
  draft_id: string;
  correlation_id: string;
  state: DraftState;
  title: string;
  source_hash: string;
  contains_test_values: boolean;
  owned_test_target: boolean;
  /** false: a draft for this session and trace already existed and is returned unchanged. */
  created: boolean;
};
/** What a draft made from an agent session records about its origin (a subset of `GeneratedDraft.provenance`). */
export type AgentTaskDraftProvenance = {
  agent_trace_source: { session_id: string; trace_hash: string };
  contains_test_values: boolean;
  owned_test_target: boolean;
  requested_by: string | null;
  /** Snapshot taken when the draft was created. */
  consistency: { assessed_sessions: number; group_sessions: number; agreement_rate: number | null; modal_status: string | null; threshold: number; small_sample: boolean } | null;
};
export type VisionResult = { exploration_report?: VisionExplorationReport; schema_version: string; session_id: string; project_id: string; revision: string; exploration_state: string; completion_reason: string | null; task_assessment?: VisionTaskAssessment | null; evidence_status: string; counts: Record<string, number>; branches: { id: string; status: string; reason_code: string | null }[]; handoffs: { id: string; branches: VisionHandoffBranch[] }[]; links: Record<"handoff" | "generation" | "draft" | "run" | "report", { state: string; id: string | null; href: string | null; reason_code?: string | null }>; limitations: string[] };
