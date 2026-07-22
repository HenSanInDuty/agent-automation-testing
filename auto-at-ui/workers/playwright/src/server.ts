import { createServer } from "node:http";

import { executeRequest } from "./execute.js";

const port = Number(process.env.PORT ?? "7100");
createServer(async (request, response) => {
  if (request.method !== "POST" || request.url !== "/execute") { response.writeHead(404).end(); return; }
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(Buffer.from(chunk));
  try {
    const result = await executeRequest(JSON.parse(Buffer.concat(chunks).toString("utf8")));
    response.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify(result));
  } catch (error) {
    response.writeHead(422, { "content-type": "application/json" }).end(JSON.stringify({ detail: error instanceof Error ? error.message : String(error) }));
  }
}).listen(port, "0.0.0.0");
