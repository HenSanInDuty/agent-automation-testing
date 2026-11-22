import { createHash, randomUUID } from "node:crypto";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve, sep } from "node:path";
import { chromium, expect, test, type Browser, type Page } from "@playwright/test";
import { VisualOperationWorker, type OperationResult } from "./vision-operations.js";
import type { VisualWorkerIdentity, VisualWorkerDomObservation } from "./vision-contract.js";

// ADR-040 opt-in agent evidence: `click-context-v1` (scroll + URL on confirmed clicks) and
// `agent-dom-path-v1` (dom_path locators for controls without a name). Off must change nothing.
const PAGE = `<!doctype html><meta charset="utf-8"><style>body{margin:0}
  button,a{display:inline-block;margin:4px;padding:4px 8px}
  .tall{height:1500px}</style>
  <button id="named">Có tên</button>
  <button class="plain" onclick="this.dataset.hit='yes'"></button>
  <a class="icon" href="/next" style="width:40px;height:30px;background:#c60;padding:0"></a>
  <div class="card" onclick="this.dataset.hit='yes'" style="width:90px;height:50px;border-radius:6px;background:#06c;cursor:pointer"></div>
  <div class="tall"></div>
  <button id="below" onclick="this.dataset.hit='yes'">Phía dưới</button>`;

let server: Server, origin: string;
let worker: VisualOperationWorker, identity: VisualWorkerIdentity, root: string, browser: Browser, page: Page;
let current: string;
test.beforeAll(async () => {
  server = createServer((request, response) => {
    response.setHeader("content-type", "text/html; charset=utf-8");
    response.setHeader("cache-control", "no-store");
    response.end(request.url === "/next" ? `<!doctype html><title>next</title><p>next</p>` : PAGE);
  });
  origin = await new Promise<string>((done) => server.listen(0, "127.0.0.1",
    () => done(`http://127.0.0.1:${(server.address() as AddressInfo).port}`)));
});
test.afterAll(async () => { server.closeAllConnections(); await new Promise<void>((done) => server.close(() => done())); });
test.beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "auto-at-vision-evidence-"));
  worker = new VisualOperationWorker(root, async (options) => { browser = await chromium.launch(options); return browser; });
  identity = { contract_version: "v4", tenant_id: "fixture-tenant", project_id: randomUUID(), session_id: randomUUID(), fencing_token: 1 };
});
test.afterEach(async () => {
  if (worker.hasSession(identity.session_id)) await worker.close(identity, identity.session_id).catch(() => undefined);
  const path = resolve(root);
  expect(path.startsWith(resolve(tmpdir()) + sep) && path.includes("auto-at-vision-evidence-")).toBe(true);
  await rm(path, { recursive: true, force: true });
});

const command = (action: object, extra: object = {}) => ({ ...identity, operation_id: randomUUID(), purpose: "explore", action,
  expected_state_fingerprint: current, state_id: randomUUID(), proposal_id: randomUUID(), ...extra });
function executeCommand(prepared: OperationResult) {
  const before = prepared.frames.find((frame) => frame.role === "before")!;
  return { ...identity, operation_id: prepared.operation.id, prepared_handle: prepared.prepared_handle,
    before_persisted: true, before_frame_id: before.id, before_checksum: before.checksum };
}
async function run(action: object, extra: object = {}) {
  const prepared = await worker.prepare(command(action, extra));
  expect(prepared.operation.status, prepared.operation.outcome_code ?? "").toBe("prepared");
  const result = await worker.execute(executeCommand(prepared));
  current = result.state_fingerprint ?? current; return result;
}
async function open(capabilities: string[]) {
  const opened = await worker.open({ ...identity, target_url: origin, allowed_origins: [origin],
    deadline: new Date(Date.now() + 120_000).toISOString(), max_session_seconds: 120, max_states: 20, max_hops: 10,
    max_screenshot_bytes: 1_000_000, agent_mode: true, required_capabilities: capabilities });
  current = opened.state_fingerprint; page = browser.contexts()[0].pages()[0];
  expect((await run({ kind: "navigate" }, { purpose: "setup" })).operation.status).toBe("completed");
  return opened;
}
const observe = () => worker.observeDom({ ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: current });
const target = (observed: VisualWorkerDomObservation, element: { element_id: string }) =>
  ({ dom_snapshot_id: observed.data.observation.snapshot_id, dom_element_id: element.element_id });
const named = (observed: VisualWorkerDomObservation, name: string) => {
  const found = observed.data.observation.elements.filter((item) => item.name === name);
  expect(found).toHaveLength(1); return found[0];
};
const unnamed = (observed: VisualWorkerDomObservation) => observed.data.observation.elements.filter((item) => item.name === "");
const bindingOf = (observed: VisualWorkerDomObservation, id: string) => observed.data.bindings.find((item) => item.element_id === id)!;
const OLD_CLICK_KEYS = ["before_frame_id", "confirmed_at", "viewport_height", "viewport_width", "x", "y"];

test("without the capabilities unnamed controls stay invisible to the agent and named ones keep role locators", async () => {
  await open([]);
  const observed = await observe();
  expect(unnamed(observed)).toHaveLength(0);
  expect(bindingOf(observed, named(observed, "Có tên").element_id).descriptor.strategy).toBe("role");
});

test("agent-dom-path-v1 binds unnamed buttons, links and custom controls by dom_path and they can be clicked", async () => {
  await open(["agent-dom-path-v1"]);
  const observed = await observe();
  const blank = unnamed(observed);
  expect(blank.map((item) => item.role).sort()).toEqual(["button", "generic", "link"]);
  for (const element of blank) {
    const descriptor = bindingOf(observed, element.element_id).descriptor;
    expect(descriptor.strategy).toBe("dom_path");
    expect(descriptor.value).toMatch(/^html > body:nth-of-type\(1\) > (?:[a-z]+:nth-of-type\(\d+\) > )*[a-z]+:nth-of-type\(\d+\)$/);
    expect(descriptor.schema_version).toBe(descriptor.value.endsWith("> button:nth-of-type(2)") ? "v2" : "v3");
  }
  const button = blank.find((item) => item.role === "button")!;
  expect(bindingOf(observed, button.element_id).descriptor.schema_version).toBe("v2");
  // Named controls are exactly as before.
  expect(bindingOf(observed, named(observed, "Có tên").element_id).descriptor.strategy).toBe("role");
  const clicked = await run({ kind: "click", x: 0.5, y: 0.5 }, target(observed, button));
  expect(clicked.operation.status, clicked.operation.outcome_code ?? "").toBe("completed");
  expect(clicked.locator?.descriptor?.strategy).toBe("dom_path");
  expect(await page.locator(".plain").getAttribute("data-hit")).toBe("yes");
  const after = await observe();
  const card = unnamed(after).find((item) => item.role === "generic")!;
  const second = await run({ kind: "click", x: 0.5, y: 0.5 }, target(after, card));
  expect(second.operation.status, second.operation.outcome_code ?? "").toBe("completed");
  expect(await page.locator(".card").getAttribute("data-hit")).toBe("yes");
});

test("a client-supplied dom_path locator never replaces the observed binding", async () => {
  await open([]);
  const observed = await observe();
  const prepared = await worker.prepare(command({ kind: "click", x: 0.5, y: 0.5 }, {
    ...target(observed, named(observed, "Có tên")), purpose: "explore",
    expected_locator: { schema_version: "v2", strategy: "dom_path", scope: [], exact: true,
      value: "html > body:nth-of-type(1) > button:nth-of-type(2)" } }));
  expect(prepared.operation).toMatchObject({ status: "rejected", outcome_code: "dom_descriptor_mismatch" });
});

test("click-context-v1 reports the scroll offset and URL fingerprint of a confirmed click", async () => {
  await open(["click-context-v1"]);
  expect((await run({ kind: "scroll", delta_y: 1000 })).operation.status).toBe("completed");
  const observed = await observe();
  const result = await run({ kind: "click", x: 0.5, y: 0.5 }, target(observed, named(observed, "Phía dưới")));
  expect(result.operation.status, result.operation.outcome_code ?? "").toBe("completed");
  const click = result.operation.executed_click!;
  expect(click.scroll_x).toBe(0);
  expect(click.scroll_y).toBeGreaterThan(0);
  expect(click.scroll_y).toBe(await page.evaluate(() => Math.round(scrollY)));
  expect(click.url_fingerprint).toBe(createHash("sha256").update(page.url()).digest("hex"));
});

test("without click-context-v1 a confirmed click carries no scroll or URL facts", async () => {
  await open([]);
  const observed = await observe();
  const result = await run({ kind: "click", x: 0.5, y: 0.5 }, target(observed, named(observed, "Có tên")));
  expect(result.operation.status).toBe("completed");
  // The transport schema fills absent optional fields with null; the control plane never keeps them.
  const click = result.operation.executed_click as Record<string, unknown>;
  expect(OLD_CLICK_KEYS.every((key) => click[key] !== null && click[key] !== undefined)).toBe(true);
  for (const key of ["scroll_x", "scroll_y", "url_fingerprint"]) expect(click[key] ?? null).toBeNull();
});

test("the capabilities are advertised, and are inert outside agent mode", async () => {
  const opened = await worker.open({ ...identity, target_url: origin, allowed_origins: [origin],
    deadline: new Date(Date.now() + 120_000).toISOString(), max_session_seconds: 120, max_states: 20, max_hops: 10,
    max_screenshot_bytes: 1_000_000, required_capabilities: ["click-context-v1", "agent-dom-path-v1"] });
  expect(opened.capabilities).toEqual(expect.arrayContaining(["click-context-v1", "agent-dom-path-v1"]));
  current = opened.state_fingerprint; page = browser.contexts()[0].pages()[0];
  expect((await run({ kind: "navigate" }, { purpose: "setup" })).operation.status).toBe("completed");
  const observed = await observe();
  expect(unnamed(observed)).toHaveLength(0);
});
