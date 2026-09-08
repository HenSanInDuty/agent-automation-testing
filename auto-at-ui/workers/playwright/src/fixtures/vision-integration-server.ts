import { createServer } from "node:http";
import { mkdir, mkdtemp, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { chromium } from "@playwright/test";
import { executeRequest, preflightPlaywrightTestSource } from "../execute.js";
import type { AddressInfo } from "node:net";
import { visualHttpHandler } from "../vision-http.js";
import { startVisionTarget } from "./vision-target.js";

const target = await startVisionTarget();
const root = await mkdtemp(join(tmpdir(), "vision-integration-"));
// The unchanged Linux runner resolves its cache under HOME. This owned fixture
// junction lets its child use the installed pinned browser on Windows too.
if (process.platform === "win32") {
  const cache = dirname(dirname(dirname(chromium.executablePath())));
  await mkdir(join(root, ".cache"));
  await symlink(cache, join(root, ".cache", "ms-playwright"), "junction");
  process.env.HOME = root;
}
const handler = visualHttpHandler(root, () => "integration-fixture-only");
const server = createServer(async (request, response) => {
  if (request.method === "GET" && request.url === "/fixture-visits") {
    response.writeHead(200, { "content-type": "application/json" })
      .end(JSON.stringify(Object.fromEntries(target.visits)));
    return;
  }
  if (request.url?.startsWith("/visual-explorations")) {
    await handler(request, response);
    return;
  }
  if (request.method !== "POST" || !["/preflight", "/execute"].includes(request.url ?? "")) {
    response.writeHead(404).end();
    return;
  }
  try {
    const chunks: Buffer[] = [];
    let size = 0;
    for await (const chunk of request) {
      const bytes = Buffer.from(chunk);
      size += bytes.length;
      if (size > 500_000) throw new Error("fixture request size");
      chunks.push(bytes);
    }
    const payload: unknown = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    const result = request.url === "/preflight"
      ? await preflightPlaywrightTestSource(payload)
      : await executeRequest(payload, root);
    response.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify(result));
  } catch {
    response.writeHead(422).end();
  }
});
await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
process.stdout.write(JSON.stringify({ target: target.origin,
  worker: `http://127.0.0.1:${(server.address() as AddressInfo).port}`, root }) + "\n");
