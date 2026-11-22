import type { IncomingMessage, ServerResponse } from "node:http";
import { applyVisualAction, closeVisualSession, observeVisualTreeState, openVisualSession } from "./vision.js";
import { requireVision, uuid, VisionWorkerError, type VisualOperation } from "./vision-contract.js";
import { VisualOperationWorker } from "./vision-operations.js";
import { traceContext } from "./observability.js";
import { logVisionEvent, visionErrorDetails, visionErrorType, visionLogScope } from "./vision-observability.js";

const MAX_BODY_BYTES = 64 * 1024;
export function visualHttpHandler(root: string, secret: () => string | undefined) {
  const worker = new VisualOperationWorker(root);
  return async (request: IncomingMessage, response: ServerResponse): Promise<void> => {
    const url = request.url ?? "", method = request.method;
    const started = performance.now();
    const parts = url.split("/");
    const context = {
      ...traceContext(request.headers.traceparent),
      ...(uuid(request.headers["x-correlation-id"]) ? { correlation_id: request.headers["x-correlation-id"] } : {}),
    };
    const fields: Record<string, unknown> = {
      method: ["GET", "POST", "DELETE"].includes(method ?? "") ? method : "other",
      stage: "authentication",
      ...(uuid(parts[2]) ? { session_id: parts[2] } : {}),
      ...(parts[3] === "operations" && uuid(parts[4]) ? { operation_id: parts[4] } : {}),
      ...(parts[3] === "checkpoints" && uuid(parts[4]) ? { checkpoint_id: parts[4] } : {}),
    };
    let failureCode: string | undefined;
    let errorType: string | undefined;
    let errorDetails: Record<string, string> = {};
    response.once("finish", () => {
      const rejected = response.statusCode >= 400;
      const failedOperation = ["rejected", "failed", "unknown"].includes(String(fields.operation_status));
      const operationAttempt = ["operation_prepare", "operation_execute"].includes(String(fields.stage));
      const newFailure = failedOperation && operationAttempt;
      const event = rejected ? "vision.request_rejected" : newFailure ? "vision.operation.failed" :
        failedOperation ? "vision.operation.result_read" : "vision.request_completed";
      const summary = failedOperation
        ? `Vision operation ${fields.operation_status} at ${fields.stage}: ${fields.outcome_code}.` +
          (fields.outcome_code === "settle_timeout" ? " Page did not reach a stable state before the settle deadline." : "")
        : rejected ? `Vision worker request rejected at ${fields.stage}: ${failureCode ?? "route_not_found"}.`
          : "Vision worker request completed.";
      logVisionEvent(newFailure ? "error" : rejected ? "warn" : "info", event, summary, context,
        { ...fields, status_code: response.statusCode, duration_ms: Math.round(performance.now() - started),
          ...(failureCode ? { code: failureCode, error_type: errorType, ...errorDetails } : {}) });
    });
    return visionLogScope.run({ context, fields }, async () => {
      const configuredSecret = secret();
      if (!configuredSecret || request.headers["x-auto-at-vision-worker-secret"] !== configuredSecret) {
        failureCode = "authentication_failed"; errorType = "authentication_error";
        response.writeHead(401).end(); return;
      }
      try {
        fields.stage = "request_validation";
        const chunks: Buffer[] = []; let bytes = 0;
        requireVision(Number(request.headers["content-length"] ?? 0) <= MAX_BODY_BYTES, "payload_too_large");
        for await (const chunk of request) {
          bytes += Buffer.byteLength(chunk); requireVision(bytes <= MAX_BODY_BYTES, "payload_too_large"); chunks.push(Buffer.from(chunk));
        }
        const payload = bytes ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : undefined;
        const sessionId = parts[2], operationId = parts[4];
        if (!fields.session_id && uuid(payload?.session_id ?? payload?.id)) fields.session_id = payload.session_id ?? payload.id;
        if (!fields.operation_id && uuid(payload?.operation_id)) fields.operation_id = payload.operation_id;
        fields.stage = "routing";
        const headerIdentity = {
          contract_version: "v4", tenant_id: request.headers["x-auto-at-vision-tenant-id"],
          project_id: request.headers["x-auto-at-vision-project-id"], session_id: sessionId,
          fencing_token: Number(request.headers["x-auto-at-vision-fencing-token"]),
        };
        let result: unknown;
        if (url === "/visual-explorations" && method === "POST") {
          fields.stage = "session_open";
          if (payload?.contract_version !== "v4") requireVision(uuid(payload?.id) && !worker.hasSession(payload.id.toLowerCase()), "legacy_fallback_forbidden");
          result = payload?.contract_version === "v4" ? await worker.open(payload) : await openVisualSession(payload, root);
        } else if (url === "/visual-explorations/tree-states" && method === "POST") {
          fields.stage = "tree_observation";
          requireVision(uuid(payload?.id) && !worker.hasSession(payload.id.toLowerCase()), "legacy_fallback_forbidden");
          result = await observeVisualTreeState(payload, root);
        }
        else {
          requireVision(uuid(sessionId), "invalid_session_id");
          if (parts.length === 4 && parts[3] === "origins" && method === "GET") {
            fields.stage = "origin_observation";
            result = worker.origins(headerIdentity, sessionId);
          } else if (parts.length === 5 && parts[3] === "observations" && parts[4] === "dom" && method === "POST") {
            fields.stage = "dom_observation";
            requireVision(payload?.session_id === sessionId, "scope_mismatch");
            result = await worker.observeDom(payload);
          } else if (parts.length === 5 && parts[3] === "observations" && parts[4] === "target" && method === "POST") {
            fields.stage = "target_preflight";
            requireVision(payload?.session_id === sessionId, "scope_mismatch");
            result = await worker.checkTarget(payload);
          } else if (parts.length === 4 && parts[3] === "screen" && method === "GET") {
            fields.stage = "live_screen";
            const frame = await worker.screen(headerIdentity, sessionId);
            response.writeHead(200, { "content-type": "image/png", "cache-control": "no-store" }).end(frame); return;
          } else if (parts[3] === "operations") {
            fields.stage = operationId === "prepare" ? "operation_prepare" :
              parts[5] === "execute" ? "operation_execute" : parts[5] === "ack" ? "operation_ack" :
                parts[5] === "frames" ? "operation_frame" : "operation_read";
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
            fields.stage = "checkpoint_read";
            result = await worker.checkpoint(headerIdentity, sessionId, parts[4]);
          } else if (parts.length === 3 && method === "DELETE") {
            fields.stage = "session_close";
            if (worker.hasSession(sessionId) || request.headers["x-auto-at-vision-fencing-token"] !== undefined) await worker.close(headerIdentity, sessionId);
            else await closeVisualSession(sessionId, root);
            result = { session_id: sessionId, closed: true };
          } else if (parts.length === 4 && parts[3] === "actions" && method === "POST") {
            fields.stage = "legacy_action";
            requireVision(!worker.hasSession(sessionId), "legacy_fallback_forbidden");
            result = await applyVisualAction(sessionId, payload?.action, root);
          } else { response.writeHead(404).end(); return; }
        }
        // A successful HTTP exchange can still carry a rejected browser operation.
        const operation = (result as { operation?: VisualOperation })?.operation;
        if (operation) {
          fields.operation_status = operation.status;
          fields.outcome_code = operation.outcome_code;
          fields.action_kind = operation.action_kind;
          fields.purpose = operation.purpose;
          fields.operation_sequence = operation.sequence;
          if (operation.outcome_code === "settle_timeout") fields.failure_stage = "page_settle";
        }
        response.writeHead(200, { "content-type": "application/json", "cache-control": "no-store" }).end(JSON.stringify(result));
      } catch (error) {
        const code = error instanceof VisionWorkerError ? error.code : "visual_request_rejected";
        failureCode = code;
        errorType = visionErrorType(error);
        errorDetails = visionErrorDetails(error, errorType);
        response.writeHead(code === "payload_too_large" ? 413 : 422, { "content-type": "application/json" }).end(JSON.stringify({ detail: code }));
      }
    });
  };
}
