import { randomUUID } from "node:crypto";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve, sep } from "node:path";
import { chromium, expect, test, type Browser, type Page } from "@playwright/test";
import { observeDom, resolveDomTarget } from "./vision-dom.js";
import { inspectState } from "./vision-checkpoints.js";
import { validateVision, type VisualWorkerObserveDom } from "./vision-contract.js";
import { VisualOperationWorker } from "./vision-operations.js";
import { startVisionTarget } from "./fixtures/vision-target.js";

let target: Awaited<ReturnType<typeof startVisionTarget>>;
test.beforeAll(async () => { target = await startVisionTarget(); });
test.afterAll(async () => { await target.close(); });

async function request(page: Page, changes: object = {}) {
  return validateVision<VisualWorkerObserveDom>("VisualWorkerObserveDom", {
    tenant_id: "fixture", project_id: randomUUID(), session_id: randomUUID(), fencing_token: 1,
    snapshot_id: randomUUID(), expected_state_fingerprint: (await inspectState(page)).fingerprint, ...changes,
  });
}

test("observes semantic/custom controls and scoped shadow/frame bindings without values", async ({ page }) => {
  await page.goto(target.origin);
  const result = await observeDom(page, await request(page));
  const names = result.data.observation.elements.map(e => e.name);
  expect(names).toEqual(expect.arrayContaining(["Branch A", "Search", "Custom div action", "Shadow action", "Embedded action"]));
  expect(names).not.toContain("Duplicate"); expect(names).not.toContain("Offscreen action");
  expect(JSON.stringify(result.data)).not.toContain("seed");
  expect(JSON.stringify(result.data)).not.toContain("user@example.test");
  expect(result.data.observation.scrollable).toBe(true);
  expect(JSON.stringify(result.data.observation)).not.toContain("descriptor");
  expect(result.data.bindings.some(b => b.descriptor.scope.some(s => s.kind === "iframe"))).toBe(true);
});

test("omits sensitive labels, attributes, form values, disabled and covered controls", async ({ page }) => {
  await page.setContent(`<button aria-label="token fixture-credential">A</button>
    <button title="person@example.test">B</button><button data-testid="secret-fixture">C</button>
    <button>authorization fixture</button><button disabled>Disabled</button>
    <input type="password" aria-label="Sign in" value="private-password">
    <input aria-label="Search" value="private-input"><textarea aria-label="Notes">private-notes</textarea>
    <div contenteditable="true" aria-label="Editor">private-editor</div>
    <button hidden>Hidden</button><script>const fixtureSecret='private-script';</script>`);
  const result = await observeDom(page, await request(page));
  const serialized = JSON.stringify(result.data);
  for (const sensitive of ["fixture-credential", "person@example", "secret-fixture", "authorization", "private-", "Disabled", "Hidden"])
    expect(serialized).not.toContain(sensitive);
  expect(result.data.observation.elements.map(e => e.name)).toEqual(["Search", "Notes", "Editor"]);
  await page.setContent('<button style="width:100px;height:40px">Covered</button><div style="position:fixed;inset:0;background:white"></div>');
  expect((await observeDom(page, await request(page))).data.observation.elements).toHaveLength(0);
});

test("bounds element/byte counts and rejects stale or unknown bindings", async ({ page }) => {
  await page.setContent(Array.from({ length: 30 }, (_, i) => `<button>Action ${i}</button>`).join(""));
  const limited = await observeDom(page, await request(page, { max_elements: 2 }));
  expect(limited.data.observation.elements).toHaveLength(2);
  expect(limited.data.observation.truncated).toBe(true);
  const small = await observeDom(page, await request(page, { max_bytes: 1024 }));
  expect(Buffer.byteLength(JSON.stringify(small.data.observation))).toBeLessThanOrEqual(1024);
  expect(small.data.observation.truncated).toBe(true);
  await expect(resolveDomTarget(limited, page, `e_${"0".repeat(32)}`)).rejects.toThrow("unknown_dom_element");
  await page.getByRole("button", { name: "Action 0", exact: true }).evaluate(el => el.textContent = "Changed");
  await expect(resolveDomTarget(limited, page, limited.data.observation.elements[0].element_id)).rejects.toThrow("stale_dom_snapshot");
});

test("form changes and mutation during collection invalidate a snapshot", async ({ page }) => {
  await page.setContent('<input aria-label="Search" value="seed"><button>Action</button>');
  const snapshot = await observeDom(page, await request(page));
  await page.getByRole("textbox").fill("changed-private");
  await expect(resolveDomTarget(snapshot, page, snapshot.data.observation.elements[0].element_id)).rejects.toThrow("stale_dom_snapshot");
  const req = await request(page);
  const original = page.evaluate.bind(page);
  let reads = 0;
  page.evaluate = (async (...args: any[]) => {
    const result = await (original as any)(...args);
    if (++reads === 2) await original(() => document.body.append(document.createElement("button")));
    return result;
  }) as typeof page.evaluate;
  await expect(observeDom(page, req)).rejects.toThrow("state_changed_during_observation");
});

test("reports unsupported coverage and binds IDs only within their own snapshot", async ({ page }) => {
  const other = await startVisionTarget();
  try {
    await page.goto(target.origin);
    await page.locator("#embedded").evaluate((el, origin) => (el as HTMLIFrameElement).src = `${origin}/frame`, other.origin);
    await page.frameLocator("#embedded").getByRole("button").waitFor();
    await page.evaluate(() => {
      const canvas = document.createElement("canvas"); canvas.style.cssText = "position:fixed;left:800px;top:10px";
      document.body.append(canvas);
    });
    const first = await observeDom(page, await request(page));
    expect(first.data.observation.unsupported).toEqual(expect.arrayContaining(["iframe", "canvas", "closed_shadow"]));
    const second = await observeDom(page, await request(page));
    await expect(resolveDomTarget(second, page, first.data.observation.elements[0].element_id)).rejects.toThrow("unknown_dom_element");
  } finally { await other.close(); }
});

test("worker binds DOM proposals freshly, rejects scope/fence/staleness and retains confirmed clicks", async () => {
  const root = await mkdtemp(join(tmpdir(), "auto-at-dom-test-"));
  let browser: Browser | undefined;
  const worker = new VisualOperationWorker(root, async options => { browser = await chromium.launch(options); return browser; });
  const identity = { contract_version: "v4", tenant_id: "fixture", project_id: randomUUID(), session_id: randomUUID(), fencing_token: 1 };
  try {
    const opened = await worker.open({ ...identity, target_url: target.origin, allowed_origins: [target.origin],
      deadline: new Date(Date.now() + 60000).toISOString(), max_session_seconds: 60,
      max_states: 20, max_hops: 10, max_screenshot_bytes: 1_000_000, required_capabilities: ["dom-observation-v1"] });
    expect(opened.capabilities).toContain("dom-observation-v1");
    const execute = async (prepared: Awaited<ReturnType<typeof worker.prepare>>) => worker.execute({ ...identity,
      operation_id: prepared.operation.id, prepared_handle: prepared.prepared_handle, before_persisted: true,
      before_frame_id: prepared.frames[0].id, before_checksum: prepared.frames[0].checksum });
    const setup = await worker.prepare({ ...identity, operation_id: randomUUID(), purpose: "setup",
      action: { kind: "navigate" }, expected_state_fingerprint: opened.state_fingerprint });
    const navigated = await execute(setup);
    const req = { ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: navigated.state_fingerprint };
    await expect(worker.observeDom({ ...req, tenant_id: "other" })).rejects.toThrow("scope_mismatch");
    await expect(worker.observeDom({ ...req, fencing_token: 2 })).rejects.toThrow("stale_fencing_token");
    const obs = await worker.observeDom(req);
    const element = obs.data.observation.elements.find(e => e.name === "Custom div action")!;
    const command = { ...identity, operation_id: randomUUID(), purpose: "explore", state_id: randomUUID(), proposal_id: randomUUID(),
      action: { kind: "click", x: 0.99, y: 0.01 }, expected_state_fingerprint: navigated.state_fingerprint,
      dom_snapshot_id: req.snapshot_id, dom_element_id: element.element_id };
    const prepared = await worker.prepare(command);
    expect(prepared.operation.status).toBe("prepared");
    await expect(worker.observeDom({ ...req, snapshot_id: randomUUID() })).rejects.toThrow("operation_pending");
    const result = await execute(prepared);
    expect(result.operation.status).toBe("completed");
    expect(result.operation.executed_click).not.toBeNull();
    const page = browser!.contexts()[0].pages()[0];
    expect(await page.getByText("Custom div action").getAttribute("data-clicked")).toBe("yes");
    const stale = await worker.prepare({ ...command, operation_id: randomUUID(), expected_state_fingerprint: result.state_fingerprint });
    expect(stale.operation.status).toBe("rejected"); expect(stale.operation.executed_click).toBeNull();
  } finally {
    await worker.close(identity, identity.session_id);
    expect(resolve(root).startsWith(resolve(tmpdir()) + sep) && root.includes("auto-at-dom-test-")).toBe(true);
    await rm(root, { recursive: true, force: true });
  }
});
