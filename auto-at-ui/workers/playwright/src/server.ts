import { createServer, type IncomingMessage } from "node:http";

import { executeRequest, preflightPlaywrightTestSource } from "./execute.js";
import { executionContext, logEvent } from "./observability.js";
import { applyVisualAction, closeVisualSession, observeVisualTreeState, openVisualSession } from "./vision.js";

const port = Number(process.env.PORT ?? "7100");
const activeExecutions = new Map<string, AbortController>();
const cancelledRuns = new Set<string>();

type ProgressPayload = {
  run_id: string;
  correlation_id?: unknown;
};

function progressTenantId(request: IncomingMessage): string | undefined {
  const value = request.headers["x-auto-at-progress-tenant-id"];
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function reportProgress(payload: ProgressPayload, tenantId: string | undefined, stage: string, status: string, safeSummary: string): void {
  const url = process.env.PROGRESS_CALLBACK_URL;
  const secret = process.env.PROGRESS_CALLBACK_SECRET;
  if (!url || !secret || typeof payload.correlation_id !== "string" || typeof tenantId !== "string") return;
  void fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json", "x-worker-progress-secret": secret },
    body: JSON.stringify({ contract_version: "v1", tenant_id: tenantId, run_id: payload.run_id,
      correlation_id: payload.correlation_id, stage, status, safe_summary: safeSummary }),
  }).catch(() => undefined);
}

createServer(async (request, response) => {
  const url = request.url ?? "";
  if (!["POST", "DELETE"].includes(request.method ?? "") || !["/execute", "/preflight", "/cancel", "/visual-explorations", "/visual-explorations/tree-states", ...Array.from(url.matchAll(/^\/visual-explorations\/[^/]+(?:\/actions)?$/g), (match) => match[0])].includes(url)) { logEvent("warn", "runner.request.rejected", "Worker request route was rejected."); response.writeHead(404).end(); return; }
  if (url.startsWith("/visual-explorations")) {
    const secret = process.env.VISION_WORKER_SECRET;
    if (!secret || request.headers["x-auto-at-vision-worker-secret"] !== secret) { response.writeHead(401).end(); return; }
    const chunks: Buffer[] = []; for await (const chunk of request) chunks.push(Buffer.from(chunk));
    try {
      const payload = chunks.length === 0 ? undefined : JSON.parse(Buffer.concat(chunks).toString("utf8"));
      const sessionId = url.split("/")[2];
      const root = process.env.ARTIFACT_ROOT ?? "/artifacts";
      const result = url === "/visual-explorations/tree-states" ? await observeVisualTreeState(payload, root)
        : url === "/visual-explorations" ? await openVisualSession(payload, root)
        : url.endsWith("/actions") ? await applyVisualAction(sessionId, payload?.action, root)
        : (await closeVisualSession(sessionId, root), { session_id: sessionId, closed: true });
      response.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify(result));
    } catch { logEvent("warn", "runner.visual_request.rejected", "Visual worker request was rejected."); response.writeHead(422, { "content-type": "application/json" }).end(JSON.stringify({ detail: "Visual worker request rejected." })); }
    return;
  }
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(Buffer.from(chunk));
  try {
    const payload = JSON.parse(Buffer.concat(chunks).toString("utf8")) as ProgressPayload;
    const context = executionContext(payload);
    const tenantId = progressTenantId(request);
    if (typeof payload.run_id !== "string" || payload.run_id.length === 0) throw new Error("run_id is required");
    if (request.url === "/cancel") {
      logEvent("info", "runner.request.cancelled", "Cancellation request accepted.", context);
      cancelledRuns.add(payload.run_id);
      activeExecutions.get(payload.run_id)?.abort();
      response.writeHead(202, { "content-type": "application/json" }).end(JSON.stringify({ run_id: payload.run_id, status: "cancellation_requested" }));
      return;
    }
    if (request.url === "/preflight") {
      const result = await preflightPlaywrightTestSource(payload);
      logEvent("info", "runner.request.preflight_completed", "Preflight request completed.", context, { accepted: result.accepted });
      response.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify(result));
      return;
    }
    if (cancelledRuns.has(payload.run_id)) throw new Error("run was cancelled before execution");
    const controller = new AbortController();
    activeExecutions.set(payload.run_id, controller);
    try {
      logEvent("info", "runner.request.accepted", "Execution request accepted.", context);
      reportProgress(payload, tenantId, "validation", "running", "Worker accepted the execution request.");
      reportProgress(payload, tenantId, "browser.launch", "running", "Browser execution is starting.");
      const result = await executeRequest(
        payload,
        process.env.ARTIFACT_ROOT ?? "/artifacts",
        controller.signal,
        (stage, status, summary) => reportProgress(payload, tenantId, stage, status, summary),
      );
      reportProgress(payload, tenantId, "terminal", result.status, "Worker returned its deterministic result.");
      logEvent("info", "runner.execution.completed", "Browser execution completed.", context, { status: result.status });
      response.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify(result));
    } finally {
      activeExecutions.delete(payload.run_id);
    }
  } catch {
    logEvent("warn", "runner.request.validation_failed", "Worker request validation failed.");
    response.writeHead(422, { "content-type": "application/json" }).end(JSON.stringify({ detail: "Execution request rejected." }));
  }
}).listen(port, "0.0.0.0");
