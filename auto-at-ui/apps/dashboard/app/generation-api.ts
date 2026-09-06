import { apiRequest, ControlPlaneError, idempotencyKey } from "./api-client.ts";
import type { Artifact, GeneratedDraft, GenerationRequest, Page, ProjectExecutionPolicy, Proposal, ProposalDecision, Run, VisualAction, VisualExploration, VisualReplayFrames, VisionDebugEvidence, VisionDebugEvidencePayload, VisionPolicy, VisionProgressActivity } from "./generation-types";
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
export function setPolicy(apiUrl: string, projectId: string, policy: ProjectExecutionPolicy) {
  return apiRequest<ProjectExecutionPolicy>(apiUrl, `/api/v1/test-generations/projects/${projectId}/policy`, {
    method: "PUT", body: JSON.stringify(policy),
  });
}
export function getPolicy(apiUrl: string, projectId: string) {
  return apiRequest<ProjectExecutionPolicy>(apiUrl, `/api/v1/test-generations/projects/${projectId}/policy`);
}
export function getRun(apiUrl: string, id: string) {
  return apiRequest<Run>(apiUrl, `/api/v1/runs/${id}`);
}
export function getArtifacts(apiUrl: string, runId: string) {
  return apiRequest<Artifact[]>(apiUrl, `/api/v1/runs/${runId}/artifacts`);
}
export function listProposals(apiUrl: string, decided?: boolean, runId?: string) {
  const query = new URLSearchParams();
  if (decided !== undefined) query.set("decided", String(decided));
  if (runId) query.set("run_id", runId);
  return apiRequest<Page<Proposal>>(apiUrl, `/api/v1/proposals${query.size ? `?${query}` : ""}`);
}
export function decideProposal(apiUrl: string, id: string, approved: boolean, reason: string) { return apiRequest<ProposalDecision>(apiUrl, `/api/v1/proposals/${id}/decision`, { method: "POST", body: JSON.stringify({ approved, reason: reason || null }) }); }
export function getVisionPolicy(apiUrl: string) { return apiRequest<VisionPolicy>(apiUrl, "/api/v1/vision/policy"); }
export function setVisionPolicy(apiUrl: string, policy: VisionPolicy) { return apiRequest<VisionPolicy>(apiUrl, "/api/v1/vision/policy", { method: "PUT", body: JSON.stringify(policy) }); }
export function submitVisualExploration(apiUrl: string, payload: { project_id: string; target_url: string; task_intent: string; use_vision: true }) {
  return apiRequest<VisualExploration>(apiUrl, "/api/v1/vision/explorations", { method: "POST", headers: { "Idempotency-Key": idempotencyKey() }, body: JSON.stringify(payload) });
}
export function listVisualExplorations(apiUrl: string, projectId: string) { return apiRequest<{ items: VisualExploration[]; total: number }>(apiUrl, `/api/v1/vision/explorations?project_id=${encodeURIComponent(projectId)}`); }
export function getVisualExploration(apiUrl: string, id: string) { return apiRequest<VisualExploration>(apiUrl, `/api/v1/vision/explorations/${id}`); }
export function listVisualActions(apiUrl: string, id: string) { return apiRequest<VisualAction[]>(apiUrl, `/api/v1/vision/explorations/${id}/actions`); }
export function listVisualReplayFrames(apiUrl: string, id: string) { return apiRequest<VisualReplayFrames>(apiUrl, `/api/v1/vision/explorations/${id}/replay-frames`); }
export async function getVisualReplayFrameBlob(apiUrl: string, sessionId: string, frameId: string) {
  const response = await fetch(`${apiUrl}/api/v1/vision/explorations/${encodeURIComponent(sessionId)}/replay-frames/${encodeURIComponent(frameId)}`, { credentials: "include", headers: { Accept: "image/png" } });
  if (!response.ok) throw new ControlPlaneError(response.status, "Replay frame is unavailable.");
  return response.blob();
}
export function deleteVisualReplayFrame(apiUrl: string, sessionId: string, frameId: string) { return apiRequest<void>(apiUrl, `/api/v1/vision/explorations/${sessionId}/replay-frames/${frameId}`, { method: "DELETE", body: JSON.stringify({ confirm: true }) }); }
export function deleteVisualReplayFrames(apiUrl: string, sessionId: string) { return apiRequest<void>(apiUrl, `/api/v1/vision/explorations/${sessionId}/replay-frames`, { method: "DELETE", body: JSON.stringify({ confirm: true }) }); }
export function listVisionProgress(apiUrl: string, id: string) { return apiRequest<VisionProgressActivity[]>(apiUrl, `/api/v1/vision/explorations/${id}/activities`); }
export function visionProgressStreamUrl(apiUrl: string, id: string) { return `${apiUrl}/api/v1/vision/explorations/${encodeURIComponent(id)}/activities/stream`; }
export function listVisionDebugEvidence(apiUrl: string, id: string) { return apiRequest<VisionDebugEvidence[]>(apiUrl, `/api/v1/vision/explorations/${id}/debug-evidence`); }
export function getVisionDebugEvidence(apiUrl: string, sessionId: string, evidenceId: string) { return apiRequest<VisionDebugEvidencePayload>(apiUrl, `/api/v1/vision/explorations/${sessionId}/debug-evidence/${evidenceId}`); }
