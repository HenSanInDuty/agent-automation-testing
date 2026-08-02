import { apiRequest, idempotencyKey } from "./api-client.ts";
import type { Artifact, GeneratedDraft, GenerationRequest, Run } from "./generation-types";
export { ControlPlaneError } from "./api-client.ts";

export function submitGeneration(apiUrl: string, payload: { project_id: string; target_url: string; request: string }) {
  return apiRequest<GenerationRequest>(apiUrl, "/api/v1/test-generations", {
    method: "POST", headers: { "Idempotency-Key": idempotencyKey() }, body: JSON.stringify(payload),
  });
}
export function getGenerationRequest(apiUrl: string, id: string) {
  return apiRequest<GenerationRequest>(apiUrl, `/api/v1/test-generations/requests/${id}`);
}
export function getDraft(apiUrl: string, id: string) {
  return apiRequest<GeneratedDraft>(apiUrl, `/api/v1/test-generations/drafts/${id}`);
}
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
export function getRun(apiUrl: string, id: string) {
  return apiRequest<Run>(apiUrl, `/api/v1/runs/${id}`);
}
export function getArtifacts(apiUrl: string, runId: string) {
  return apiRequest<Artifact[]>(apiUrl, `/api/v1/runs/${runId}/artifacts`);
}
