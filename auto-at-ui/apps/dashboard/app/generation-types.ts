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
};

export type Run = { id: string; correlation_id: string; status: string; revision: string };
export type Artifact = { id: string; kind: string; uri: string; checksum: string; size: number; content_type: string | null };
