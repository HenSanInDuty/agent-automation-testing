// QA r18: full session flow under the production transform (`tsx`, esbuild keepNames), see vision-tsx-runtime.qa.spec.ts.
// open -> navigate -> observe -> prepare -> execute(click) -> close on a pulsing page (ADR-042) and a static page, then an
// injected evaluate failure through the HTTP handler, then the __name shim against a page that defines its own __name.
// Prints one JSON line. Loopback only, no model, no external network.
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { randomUUID } from "node:crypto";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium, type Browser, type Page } from "@playwright/test";
import { VisualOperationWorker, type OperationResult } from "../vision-operations.js";
import { visualHttpHandler } from "../vision-http.js";
import { pulsingControlHtml, staticControlHtml } from "./settle-animated-control.js";

const clickable = `<button type="button" id="go" onclick="document.getElementById('out').textContent='đã bấm'">Bấm thử</button><p id="out">chưa</p>`;
const pages: Record<string, string> = {
  "/pulse": pulsingControlHtml + clickable,
  "/static": staticControlHtml + clickable,
  "/own-name": `<!doctype html><meta charset="utf-8"><script>globalThis.__name = function pageOwnName(fn) { return fn; };</script>${clickable}`,
};
const server = createServer((request, response) => {
  response.setHeader("content-type", "text/html; charset=utf-8"); response.setHeader("cache-control", "no-store");
  response.end(pages[(request.url ?? "/").split("?")[0]] ?? pages["/static"]);
});
await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
const origin = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
const root = await mkdtemp(join(tmpdir(), "auto-at-vision-tsxqa-"));
let browser: Browser | undefined;
const worker = new VisualOperationWorker(root, async (options) => { browser = await chromium.launch(options); return browser; });
const out: Record<string, unknown> = {};
const logs: string[] = [];
const identity = () => ({ contract_version: "v4" as const, tenant_id: "fixture-tenant", project_id: randomUUID(), session_id: randomUUID(), fencing_token: 1 });

async function flow(path: string) {
  const id = identity();
  const opened = await worker.open({ ...id, target_url: origin + path, allowed_origins: [origin], agent_mode: true,
    deadline: new Date(Date.now() + 120_000).toISOString(), max_session_seconds: 120, max_states: 20, max_hops: 10, max_screenshot_bytes: 1_000_000 });
  let current = opened.state_fingerprint;
  const page: Page = browser!.contexts().at(-1)!.pages()[0];
  const command = (action: object, extra: object = {}) => ({ ...id, operation_id: randomUUID(), purpose: "explore", action,
    expected_state_fingerprint: current, state_id: randomUUID(), proposal_id: randomUUID(), ...extra });
  const exec = (prepared: OperationResult) => {
    const before = prepared.frames.find((frame) => frame.role === "before")!;
    return worker.execute({ ...id, operation_id: prepared.operation.id, prepared_handle: prepared.prepared_handle,
      before_persisted: true, before_frame_id: before.id, before_checksum: before.checksum });
  };
  const nav = await worker.prepare(command({ kind: "navigate" }, { purpose: "setup" }));
  const navDone = await exec(nav); current = navDone.state_fingerprint ?? current;
  const observed = await worker.observeDom({ ...id, snapshot_id: randomUUID(), expected_state_fingerprint: current });
  const names = observed.data.observation.elements.map((item) => item.name);
  const button = observed.data.observation.elements.find((item) => item.name === "Bấm thử");
  const prepared = await worker.prepare(command({ kind: "click", x: 0.5, y: 0.5 },
    { dom_snapshot_id: observed.data.observation.snapshot_id, dom_element_id: button?.element_id }));
  const result = prepared.operation.status === "prepared" ? await exec(prepared) : prepared;
  const shimType = await page.evaluate(() => typeof (globalThis as unknown as { __name?: unknown }).__name);
  const shimName = await page.evaluate(() => (globalThis as unknown as { __name?: { name: string } }).__name?.name ?? null);
  const text = await page.locator("#out").textContent();
  await worker.close(id, id.session_id);
  return { nav: navDone.operation.status, names, prepare: prepared.operation.status, execute: result.operation.status,
    outcome: result.operation.outcome_code ?? null, text, shimType, shimName, closed: page.isClosed() };
}

try {
  out.pulse = await flow("/pulse");
  out.static = await flow("/static");
  out.own_name = await flow("/own-name");

  // Injected failure inside evaluate, through the real HTTP handler (open and prepare both over HTTP).
  const launched: Browser[] = [];
  const secret = "private-page-content https://shop.example/?token=private-token";
  const realLaunch = chromium.launch.bind(chromium);
  const failing = (page: Page) => { page.evaluate = (async () => {
    throw new ReferenceError(`page.evaluate: ReferenceError: __name is not defined ${secret}`); }) as never; return page; };
  chromium.launch = (async (options?: Parameters<typeof chromium.launch>[0]) => {
    const b = await realLaunch(options); launched.push(b);
    const newContext = b.newContext.bind(b);
    b.newContext = (async (...args: Parameters<typeof b.newContext>) => {
      const context = await newContext(...args); const newPage = context.newPage.bind(context);
      context.newPage = (async () => failing(await newPage())) as never; return context; }) as never;
    return b; }) as never;
  const id = identity();
  const originalWarn = console.warn;
  const handler = visualHttpHandler(root, () => "fixture");
  const http = createServer((req, res) => { void handler(req, res); });
  await new Promise<void>((resolve) => http.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${(http.address() as AddressInfo).port}/visual-explorations`;
  const headers = { "x-auto-at-vision-worker-secret": "fixture" };
  try {
    console.warn = (line: string) => logs.push(String(line));
    const response = await fetch(base, { method: "POST", headers, body: JSON.stringify({ ...id, target_url: origin + "/static",
      allowed_origins: [origin], deadline: new Date(Date.now() + 120_000).toISOString(), max_session_seconds: 120, max_states: 20,
      max_hops: 10, max_screenshot_bytes: 1_000_000 }) });
    console.warn = originalWarn;
    out.http = { status: response.status, body: await response.json() };
    const entry = JSON.parse(logs[0] ?? "{}");
    out.log = { error_type: entry.error_type, error_name: entry.error_name, error_origin: entry.error_origin, error_digest: entry.error_digest,
      leaked: /private-|__name|shop\.example/.test(logs.join("\n")) };
  } finally {
    console.warn = originalWarn; chromium.launch = realLaunch as never;
    await Promise.all(launched.map((b) => b.close().catch(() => undefined)));
    http.closeAllConnections(); await new Promise<void>((resolve) => http.close(() => resolve()));
  }
} catch (error) {
  out.error = `${(error as Error)?.name}: ${String((error as Error)?.message).slice(0, 400)}`;
  process.exitCode = 1;
} finally {
  await browser?.close().catch(() => undefined);
  server.closeAllConnections(); server.close();
  await rm(root, { recursive: true, force: true });
}
console.log(JSON.stringify(out));
