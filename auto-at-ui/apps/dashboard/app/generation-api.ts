import type { Artifact, DashboardIdentity, GeneratedDraft, GenerationRequest, Run } from "./generation-types";

export class ControlPlaneError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function headers(identity: DashboardIdentity, extra: HeadersInit = {}): Headers {
  return new Headers({
    "Content-Type": "application/json",
    "X-Tenant-Id": identity.tenantId,
    "X-Actor-Id": identity.actorId,
    "X-Actor-Roles": identity.roles,
    ...extra,
  });
}

async function request<T>(url: string, identity: DashboardIdentity, init: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { ...init, headers: headers(identity, init.headers) });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new ControlPlaneError(response.status, body?.detail ?? "The control plane rejected this request.");
  }
  return response.json() as Promise<T>;
}

export function submitGeneration(apiUrl: string, identity: DashboardIdentity, payload: { project_id: string; target_url: string; request: string }) {
  return request<GenerationRequest>(`${apiUrl}/api/v1/test-generations`, identity, {
    method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify(payload),
  });
}
export function getGenerationRequest(apiUrl: string, identity: DashboardIdentity, id: string) {
  return request<GenerationRequest>(`${apiUrl}/api/v1/test-generations/requests/${id}`, identity);
}
export function getDraft(apiUrl: string, identity: DashboardIdentity, id: string) {
  return request<GeneratedDraft>(`${apiUrl}/api/v1/test-generations/drafts/${id}`, identity);
}
export function decideDraft(apiUrl: string, identity: DashboardIdentity, id: string, approved: boolean, reason: string) {
  return request<GeneratedDraft>(`${apiUrl}/api/v1/test-generations/drafts/${id}/decision`, identity, {
    method: "POST", body: JSON.stringify({ approved, reason: reason || null }),
  });
}
export function setPolicy(apiUrl: string, identity: DashboardIdentity, projectId: string, allowed_origins: string[]) {
  return request<{ allowed_origins: string[] }>(`${apiUrl}/api/v1/test-generations/projects/${projectId}/policy`, identity, {
    method: "PUT", body: JSON.stringify({ allowed_origins }),
  });
}
export function getRun(apiUrl: string, identity: DashboardIdentity, id: string) {
  return request<Run>(`${apiUrl}/api/v1/runs/${id}`, identity);
}
export function getArtifacts(apiUrl: string, identity: DashboardIdentity, runId: string) {
  return request<Artifact[]>(`${apiUrl}/api/v1/runs/${runId}/artifacts`, identity);
}
