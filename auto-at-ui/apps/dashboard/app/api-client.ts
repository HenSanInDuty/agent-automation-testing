export class ControlPlaneError extends Error {
  readonly status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

function csrfToken(): string {
  if (typeof document === "undefined") return "";
  return document.cookie.split("; ").find((cookie) => cookie.startsWith("auto_at_csrf="))?.split("=")[1] ?? "";
}

export function idempotencyKey(): string { return crypto.randomUUID(); }

export async function apiRequest<T>(apiUrl: string, path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (init.method && !["GET", "HEAD"].includes(init.method)) headers.set("X-CSRF-Token", csrfToken());
  const response = await fetch(`${apiUrl}${path}`, { ...init, headers, credentials: "include" });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new ControlPlaneError(response.status, body?.detail ?? "The control plane rejected this request.");
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

export function artifactDownloadUrl(apiUrl: string, runId: string, artifactId: string): string {
  return `${apiUrl}/api/v1/runs/${runId}/artifacts/${artifactId}`;
}
