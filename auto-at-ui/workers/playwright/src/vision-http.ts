import type { IncomingMessage, ServerResponse } from "node:http";
import { applyVisualAction, closeVisualSession, observeVisualTreeState, openVisualSession } from "./vision.js";
import { requireVision, uuid, VisionWorkerError } from "./vision-contract.js";
import { VisualOperationWorker } from "./vision-operations.js";

const MAX_BODY_BYTES = 64 * 1024;
export function visualHttpHandler(root: string, secret: () => string | undefined) {
  const worker = new VisualOperationWorker(root);
  return async (request: IncomingMessage, response: ServerResponse): Promise<void> => {
    const url = request.url ?? "", method = request.method;
    const configuredSecret = secret();
    if (!configuredSecret || request.headers["x-auto-at-vision-worker-secret"] !== configuredSecret) { response.writeHead(401).end(); return; }
    try {
      const chunks: Buffer[] = []; let bytes = 0;
      requireVision(Number(request.headers["content-length"] ?? 0) <= MAX_BODY_BYTES, "payload_too_large");
      for await (const chunk of request) {
        bytes += Buffer.byteLength(chunk); requireVision(bytes <= MAX_BODY_BYTES, "payload_too_large"); chunks.push(Buffer.from(chunk));
      }
      const payload = bytes ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : undefined;
      const parts = url.split("/");
      const sessionId = parts[2], operationId = parts[4];
      const headerIdentity = {
        contract_version: "v4", tenant_id: request.headers["x-auto-at-vision-tenant-id"],
        project_id: request.headers["x-auto-at-vision-project-id"], session_id: sessionId,
        fencing_token: Number(request.headers["x-auto-at-vision-fencing-token"]),
      };
      let result: unknown;
      if (url === "/visual-explorations" && method === "POST") {
        if (payload?.contract_version !== "v4") requireVision(uuid(payload?.id) && !worker.hasSession(payload.id.toLowerCase()), "legacy_fallback_forbidden");
        result = payload?.contract_version === "v4" ? await worker.open(payload) : await openVisualSession(payload, root);
      } else if (url === "/visual-explorations/tree-states" && method === "POST") {
        requireVision(uuid(payload?.id) && !worker.hasSession(payload.id.toLowerCase()), "legacy_fallback_forbidden");
        result = await observeVisualTreeState(payload, root);
      }
      else {
        requireVision(uuid(sessionId), "invalid_session_id");
        if (parts[3] === "operations") {
          if (method === "POST") requireVision(payload?.session_id === sessionId, "scope_mismatch");
          if (parts.length === 5 && operationId === "prepare" && method === "POST") result = await worker.prepare(payload);
          else {
            requireVision(uuid(operationId), "invalid_operation_id");
            if (method === "POST") requireVision(payload?.operation_id === operationId, "scope_mismatch");
            if (parts.length === 6 && parts[5] === "execute" && method === "POST") result = await worker.execute(payload);
            else if (parts.length === 6 && parts[5] === "ack" && method === "POST") result = await worker.acknowledge(payload);
            else if (parts.length === 5 && method === "GET") result = worker.read(headerIdentity, sessionId, operationId);
            else if (parts.length === 7 && parts[5] === "frames" && uuid(parts[6]) && method === "GET") {
              const frame = await worker.frame(headerIdentity, sessionId, operationId, parts[6]);
              response.writeHead(200, { "content-type": "image/png", "cache-control": "no-store" }).end(frame); return;
            } else { response.writeHead(404).end(); return; }
          }
        } else if (parts.length === 5 && parts[3] === "checkpoints" && uuid(parts[4]) && method === "GET") {
          result = await worker.checkpoint(headerIdentity, sessionId, parts[4]);
        } else if (parts.length === 3 && method === "DELETE") {
          if (worker.hasSession(sessionId) || request.headers["x-auto-at-vision-fencing-token"] !== undefined) await worker.close(headerIdentity, sessionId);
          else await closeVisualSession(sessionId, root);
          result = { session_id: sessionId, closed: true };
        } else if (parts.length === 4 && parts[3] === "actions" && method === "POST") {
          requireVision(!worker.hasSession(sessionId), "legacy_fallback_forbidden");
          result = await applyVisualAction(sessionId, payload?.action, root);
        } else { response.writeHead(404).end(); return; }
      }
      response.writeHead(200, { "content-type": "application/json", "cache-control": "no-store" }).end(JSON.stringify(result));
    } catch (error) {
      const code = error instanceof VisionWorkerError ? error.code : "visual_request_rejected";
      response.writeHead(code === "payload_too_large" ? 413 : 422, { "content-type": "application/json" }).end(JSON.stringify({ detail: code }));
    }
  };
}
