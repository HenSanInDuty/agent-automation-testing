import { apiRequest, idempotencyKey } from "./api-client.ts";
import type { Artifact, GeneratedDraft, GenerationRequest, Page, Proposal, ProposalDecision, Run } from "./generation-types";
export { ControlPlaneError } from "./api-client.ts";

export function submitGeneration(apiUrl: string, payload: { project_id: string; target_url: string; request: string }) {
  return apiRequest<GenerationRequest>(apiUrl, "/api/v1/test-generations", {
    method: "POST", headers: { "Idempotency-Key": idempotencyKey() }, body: JSON.stringify(payload),
  });
}
export function getGenerationRequest(apiUrl: string, id: string) {
  return apiRequest<GenerationRequest>(apiUrl, `/api/v1/test-generations/requests/${id}`);
}
export function listGenerationRequests(apiUrl: string, state?: string) { return apiRequest<Page<GenerationRequest>>(apiUrl, `/api/v1/test-generations/requests${state ? `?state=${encodeURIComponent(state)}` : ""}`); }
export function getDraft(apiUrl: string, id: string) {
  return apiRequest<GeneratedDraft>(apiUrl, `/api/v1/test-generations/drafts/${id}`);
}
export function listDrafts(apiUrl: string, state?: string) { return apiRequest<Page<GeneratedDraft>>(apiUrl, `/api/v1/test-generations/drafts${state ? `?state=${encodeURIComponent(state)}` : ""}`); }
export function decideDraft(apiUrl: string, id: string, approved: boolean, reason: string) {
  return apiRequest<GeneratedDraft>(apiUrl, `/api/v1/test-generations/drafts/${id}/decision`, {
    method: "POST", body: JSON.stringify({ approved, reason: reason || null }),
  });
}
export function setPolicy(apiUrl: string, projectId: string, allowed_origins: string[]) {
  return apiRequest<{ allowed_origins: string[] }>(apiUrl, `/api/v1/test-generations/projects/${projectId}/policy`, {
    method: "PUT", body: JSON.stringify({ allowed_origins }),
  });
}
export function getPolicy(apiUrl: string, projectId: string) {
  return apiRequest<{ allowed_origins: string[] }>(apiUrl, `/api/v1/test-generations/projects/${projectId}/policy`);
}
export function getRun(apiUrl: string, id: string) {
  return apiRequest<Run>(apiUrl, `/api/v1/runs/${id}`);
}
export function getArtifacts(apiUrl: string, runId: string) {
  return apiRequest<Artifact[]>(apiUrl, `/api/v1/runs/${runId}/artifacts`);
}
export function listProposals(apiUrl: string, decided?: boolean) { return apiRequest<Page<Proposal>>(apiUrl, `/api/v1/proposals${decided === undefined ? "" : `?decided=${decided}`}`); }
export function decideProposal(apiUrl: string, id: string, approved: boolean, reason: string) { return apiRequest<ProposalDecision>(apiUrl, `/api/v1/proposals/${id}/decision`, { method: "POST", body: JSON.stringify({ approved, reason: reason || null }) }); }
