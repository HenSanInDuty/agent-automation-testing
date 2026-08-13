import { apiRequest, idempotencyKey } from "./api-client.ts";

export type Project = { id: string; name: string; default_target: string };
export type TestCase = { id: string; project_id: string; target_type: string; revision: string; specification: Record<string, unknown> };
export type Artifact = { id: string; kind: string; uri: string; checksum: string; size: number; content_type: string | null };
export type Run = { id: string; correlation_id: string; status: string; revision: string; project_id: string; test_case_id: string; target_type: string | null; target_url: string | null; artifact_policy: { trace_on_failure: boolean; video_on_failure: boolean; screenshot_on_failure: boolean; retain_days: number } | null; terminal_summary: string | null; created_at: string | null };
export type RunPage = { items: Run[]; total: number; limit: number; offset: number };
export type Activity = { id: string; source: string; stage: string; status: string; safe_summary: string; occurred_at: string };
export type RunReportObservation = { text: string; evidence_references: string[] };
export type RunReportFailure = { stage: string; location: string; message: string; evidence_references: string[] };
export type RunReport = { report_version: number; schema_version: string; prompt_version: string; deterministic_status: string; status: "completed" | "unavailable"; payload: { deterministic_status: string; headline: string; what_ran: string; observations: RunReportObservation[]; failure: RunReportFailure | null; unverified_or_skipped: string[]; limitations: string[] } | null; unavailable_reason: string | null; provenance: { provider: string | null; model: string | null; redaction_policy_version: string | null; input_hash: string }; created_at: string };

export const projects = (apiUrl: string, query = "") => apiRequest<Project[]>(apiUrl, `/api/v1/projects${query ? `?q=${encodeURIComponent(query)}` : ""}`);
export const createProject = (apiUrl: string, payload: { name: string; default_target: string }) => apiRequest<Project>(apiUrl, "/api/v1/projects", { method: "POST", body: JSON.stringify(payload) });
export const testCases = (apiUrl: string, projectId: string, query = "") => apiRequest<TestCase[]>(apiUrl, `/api/v1/projects/${projectId}/tests${query ? `?q=${encodeURIComponent(query)}` : ""}`);
export const createRun = (apiUrl: string, payload: { project_id: string; test_case_id: string; target_type: string; target_url?: string; runner_config: Record<string, unknown>; artifact_policy: Run["artifact_policy"] }) => apiRequest<Run>(apiUrl, "/api/v1/runs", { method: "POST", headers: { "Idempotency-Key": idempotencyKey() }, body: JSON.stringify(payload) });
export const runs = (apiUrl: string, query = "") => apiRequest<RunPage>(apiUrl, `/api/v1/runs${query ? `?${query}` : ""}`);
export const run = (apiUrl: string, id: string) => apiRequest<Run>(apiUrl, `/api/v1/runs/${id}`);
export const artifacts = (apiUrl: string, id: string) => apiRequest<Artifact[]>(apiUrl, `/api/v1/runs/${id}/artifacts`);
export const runReport = (apiUrl: string, id: string) => apiRequest<RunReport>(apiUrl, `/api/v1/runs/${id}/report`);
export const cancelRun = (apiUrl: string, id: string) => apiRequest<Run>(apiUrl, `/api/v1/runs/${id}/cancel`, { method: "POST", headers: { "Idempotency-Key": idempotencyKey() } });
export const activities = (apiUrl: string, id: string, byCorrelation = false) => apiRequest<Activity[]>(apiUrl, `/api/v1/activities?${byCorrelation ? "correlation_id" : "run_id"}=${encodeURIComponent(id)}`);
