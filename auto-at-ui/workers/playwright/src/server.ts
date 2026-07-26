import { createServer } from "node:http";

import { executeRequest } from "./execute.js";

const port = Number(process.env.PORT ?? "7100");
const activeExecutions = new Map<string, AbortController>();
const cancelledRuns = new Set<string>();

createServer(async (request, response) => {
  if (request.method !== "POST" || !["/execute", "/cancel"].includes(request.url ?? "")) { response.writeHead(404).end(); return; }
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(Buffer.from(chunk));
  try {
    const payload = JSON.parse(Buffer.concat(chunks).toString("utf8")) as { run_id?: unknown };
    if (typeof payload.run_id !== "string" || payload.run_id.length === 0) throw new Error("run_id is required");
    if (request.url === "/cancel") {
      cancelledRuns.add(payload.run_id);
      activeExecutions.get(payload.run_id)?.abort();
      response.writeHead(202, { "content-type": "application/json" }).end(JSON.stringify({ run_id: payload.run_id, status: "cancellation_requested" }));
      return;
    }
    if (cancelledRuns.has(payload.run_id)) throw new Error("run was cancelled before execution");
    const controller = new AbortController();
    activeExecutions.set(payload.run_id, controller);
    try {
      const result = await executeRequest(payload, process.env.ARTIFACT_ROOT ?? "/artifacts", controller.signal);
      response.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify(result));
    } finally {
      activeExecutions.delete(payload.run_id);
    }
  } catch (error) {
    response.writeHead(422, { "content-type": "application/json" }).end(JSON.stringify({ detail: error instanceof Error ? error.message : String(error) }));
  }
}).listen(port, "0.0.0.0");
