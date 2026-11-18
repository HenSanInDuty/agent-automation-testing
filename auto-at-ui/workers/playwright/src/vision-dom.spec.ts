import { randomUUID } from "node:crypto";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve, sep } from "node:path";
import { chromium, expect, test, type Browser, type Page } from "@playwright/test";
import { observeDom, resolveDomTarget } from "./vision-dom.js";
import { inspectState, setInteractionScope, settleState } from "./vision-checkpoints.js";
import { validateVision, type VisualWorkerObserveDom } from "./vision-contract.js";
import { VisualOperationWorker } from "./vision-operations.js";
import { startVisionTarget } from "./fixtures/vision-target.js";
import { revalidateDom } from "./vision-revalidation.js";

let target: Awaited<ReturnType<typeof startVisionTarget>>;
test.beforeAll(async () => { target = await startVisionTarget(); });
test.afterAll(async () => { await target.close(); });

test("settle retries a destroyed navigation context but preserves the deadline and other errors", async ({ page }) => {
  await page.goto(target.origin);
  const evaluate = page.evaluate.bind(page);
  let calls = 0;
  page.evaluate = (async (...args: Parameters<Page["evaluate"]>) => {
    if (++calls === 1 || calls === 3) throw new Error("Execution context was destroyed, most likely because of a navigation");
    return evaluate(...args);
  }) as Page["evaluate"];
  const began = Date.now();
  expect((await settleState(page, began + 3000, 240)).settled).toBe(true);
  expect(Date.now() - began).toBeGreaterThanOrEqual(400);
  page.evaluate = (async () => { throw new Error("Execution context was destroyed"); }) as Page["evaluate"];
  const deadline = Date.now() + 250;
  await expect(settleState(page, deadline)).rejects.toThrow("Execution context was destroyed");
  expect(Date.now()).toBeLessThan(deadline + 500);
  page.evaluate = (async () => { throw new Error("state_structure_limit"); }) as Page["evaluate"];
  await expect(settleState(page, Date.now() + 3000)).rejects.toThrow("state_structure_limit");
  page.evaluate = evaluate;
});

async function request(page: Page, changes: object = {}) {
  return validateVision<VisualWorkerObserveDom>("VisualWorkerObserveDom", {
    tenant_id: "fixture", project_id: randomUUID(), session_id: randomUUID(), fencing_token: 1,
    snapshot_id: randomUUID(), expected_state_fingerprint: (await inspectState(page)).fingerprint, ...changes,
  });
}

for (const boundary of [{ top: 900, height: 40, delta: 576 },
  { top: 550, height: 220, delta: 550 }, { top: 50, height: 700, delta: 50 }]) {
  test(`visual scan stride preserves clipped button at ${boundary.top}/${boundary.height}`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto(target.origin);
    await page.setContent(`<body style="margin:0;height:2900px"><button style="position:absolute;left:20px;top:${boundary.top}px;height:${boundary.height}px;width:120px">Boundary action</button></body>`);
    setInteractionScope(page, "visual_buttons");
    const observed = await observeDom(page, await request(page));
    const delta = (observed.data as { next_scroll_delta_y?: number }).next_scroll_delta_y;
    expect(delta).toBe(boundary.delta);
    expect(JSON.stringify(observed.data.observation)).not.toContain("next_scroll_delta_y");
    await page.evaluate(delta => scrollBy(0, delta!), delta);
    const next = await observeDom(page, await request(page));
    expect(next.data.observation.elements.map(e => e.name)).toContain("Boundary action");
  });
}

for (const change of ["carousel", "move", "replace", "rename", "href", "disabled", "covered",
  "form", "modal", "heading", "scroll", "navigation", "scope", "ancestor"] as const) {
  test(`delayed DOM reply revalidates exact targets: ${change}`, async ({ page }) => {
    await page.goto(target.origin);
    await page.setContent('<main><h1>Shop</h1><section id="products"><a href="/a" id="chosen" style="position:absolute;left:20px;top:100px;width:100px;height:40px">Open item</a></section>' +
      '<div id="carousel" style="cursor:pointer;position:absolute;left:400px;top:100px;width:100px;height:60px">Slide</div>' +
      '<input aria-label="Quantity" value="private-test-value"><div style="height:2000px"></div></main>');
    const req = await request(page), original = await observeDom(page, req);
    const id = original.data.observation.elements.find(e => e.name === "Open item")!.element_id;
    await page.evaluate(change => {
      const chosen = document.querySelector<HTMLAnchorElement>('#chosen')!;
      const carousel = document.querySelector<HTMLElement>('#carousel')!;
      carousel.style.left = '450px';
      if (change === 'move') chosen.style.left = '180px';
      if (change === 'replace') chosen.replaceWith(chosen.cloneNode(true));
      if (change === 'rename') chosen.textContent = 'Delete item';
      if (change === 'href') chosen.href = '/b';
      if (change === 'disabled') chosen.setAttribute('aria-disabled', 'true');
      if (change === 'covered') document.body.insertAdjacentHTML('beforeend', '<div style="position:fixed;inset:0;background:white;z-index:100"></div>');
      if (change === 'form') document.querySelector('input')!.value = 'changed-private-value';
      if (change === 'modal') document.body.insertAdjacentHTML('beforeend', '<div role="dialog" style="position:absolute;left:700px;top:100px;width:100px;height:100px">Confirm</div>');
      if (change === 'heading') document.querySelector('h1')!.textContent = 'Delete account';
      if (change === 'scroll') scrollTo(0, 20);
      if (change === 'navigation') history.pushState({}, '', '/changed');
      if (change === 'ancestor') document.querySelector('section')!.setAttribute('data-item', 'different');
    }, change);
    const fresh = await observeDom(page, await request(page, { ...req, snapshot_id: randomUUID(),
      expected_state_fingerprint: (await inspectState(page)).fingerprint,
      ...(change === 'scope' ? { fencing_token: 2 } : {}) }));
    expect(fresh.state.fingerprint).not.toBe(original.state.fingerprint);
    if (change === 'carousel' || change === 'move') {
      await revalidateDom(original, fresh, [id]);
      const rebound = await resolveDomTarget(fresh, page, id);
      expect(fresh.data.observation.snapshot_id).not.toBe(original.data.observation.snapshot_id);
      if (change === 'move') expect(rebound.binding.bounds.x).toBeGreaterThan(0.1);
      await page.mouse.click(rebound.x * (page.viewportSize()!.width - 1),
        rebound.y * (page.viewportSize()!.height - 1));
      await expect(page).toHaveURL(target.origin + '/a');
    } else {
      await expect(revalidateDom(original, fresh, [id])).rejects.toThrow(/stale_dom_(context|target)/);
      expect(page.url()).toBe(target.origin + (change === 'navigation' ? '/changed' : '/'));
    }
    expect(JSON.stringify(fresh.data)).not.toContain('private-value');
  });
}

for (const change of ['carousel', 'form', 'modal', 'heading', 'scroll', 'url', 'reload', 'fence'] as const) {
  test(`viewport context revalidation: ${change}`, async ({ page }) => {
    await page.goto(target.origin + '/scan-carousel');
    const req = await request(page), previous = await observeDom(page, req);
    if (change === 'reload') await page.reload();
    else await page.evaluate(kind => {
      if (kind === 'carousel') document.querySelector<HTMLElement>('#carousel')!.style.left = '450px';
      if (kind === 'form') document.querySelector('input')!.value = 'changed-private-value';
      if (kind === 'modal') document.body.insertAdjacentHTML('beforeend', '<dialog open>Confirm</dialog>');
      if (kind === 'heading') document.querySelector('h1')!.textContent = 'Different task';
      if (kind === 'scroll') scrollTo(0, 50);
      if (kind === 'url') history.pushState({}, '', '/different');
    }, change);
    const fresh = await observeDom(page, await request(page, { ...req, snapshot_id: randomUUID(),
      expected_state_fingerprint: (await inspectState(page)).fingerprint,
      ...(change === 'fence' ? { fencing_token: 2 } : {}) }));
    if (change === 'carousel') {
      await revalidateDom(previous, fresh, []);
      expect(fresh.data.observation.elements.map(e => e.element_id))
        .not.toEqual(previous.data.observation.elements.map(e => e.element_id));
    } else await expect(revalidateDom(previous, fresh, [])).rejects.toThrow('stale_dom_context');
    expect(JSON.stringify(fresh.data)).not.toContain('private-value');
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
  await page.setContent('<div style="opacity:0;pointer-events:none"><button>Invisible until scrolling</button></div>');
  const hidden = await observeDom(page, await request(page));
  expect(hidden.data.observation.elements).toHaveLength(0);
  expect(hidden.data.observation.skipped_count).toBe(0);
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

test("anonymous buttons bind live nodes only and never adopt replacement nodes at the same path", async ({ page }) => {
  await page.setContent('<button style="position:absolute;left:10px;top:100px;width:50px;height:30px"></button>' +
    '<button style="position:absolute;left:100px;top:100px;width:50px;height:30px"></button>' +
    '<button>Duplicate</button><button>Duplicate</button>');
  expect((await observeDom(page, await request(page))).data.observation.elements).toHaveLength(0);
  setInteractionScope(page, 'buttons');
  const snapshot = await observeDom(page, await request(page));
  expect(snapshot.data.observation.elements).toHaveLength(2);
  expect(snapshot.data.bindings.every(b => b.descriptor.schema_version === 'v2' && b.descriptor.strategy === 'dom_path')).toBe(true);
  const first = snapshot.data.observation.elements[0].element_id;
  expect((await resolveDomTarget(snapshot, page, first)).binding.descriptor.value).toContain('button:nth-of-type(1)');
  const oldX = (await resolveDomTarget(snapshot, page, first)).x;
  await page.locator('button').first().evaluate(el => (el as HTMLElement).style.left = '250px');
  expect((await resolveDomTarget(snapshot, page, first)).x).toBeGreaterThan(oldX);
  await page.locator('button').first().evaluate(el => el.replaceWith(el.cloneNode(true)));
  await expect(resolveDomTarget(snapshot, page, first)).rejects.toThrow('stale_dom_target');
});

test("anonymous paths support nested layouts without extending stable locator limits", async ({ page }) => {
  await page.setContent('<div>'.repeat(15) + '<button style="width:50px;height:30px"></button>' + '</div>'.repeat(15));
  setInteractionScope(page, 'buttons');
  const snapshot = await observeDom(page, await request(page));
  expect(snapshot.data.observation.elements).toHaveLength(1);
  expect(snapshot.data.bindings[0].descriptor.value.length).toBeGreaterThan(240);
  expect(snapshot.data.bindings[0].descriptor.schema_version).toBe('v2');
});

test("anonymous inventory resolves a fresh point after movement during DOM collection", async ({ page }) => {
  await page.setContent('<button style="position:absolute;left:10px;top:100px;width:50px;height:30px"></button>');
  setInteractionScope(page, 'buttons');
  const req = await request(page);
  const evaluate = page.evaluate.bind(page);
  page.evaluate = (async (...args: Parameters<Page['evaluate']>) => {
    const result = await evaluate(...args);
    if (result && typeof result === 'object' && 'candidates' in result) {
      await evaluate(() => document.querySelector('button')!.style.left = '400px');
    }
    return result;
  }) as Page['evaluate'];
  const snapshot = await observeDom(page, req);
  expect(snapshot.data.observation.elements).toHaveLength(1);
  expect(snapshot.data.observation.skipped_count).toBe(0);
  expect(snapshot.data.bindings[0].bounds.x).toBeCloseTo(400 / page.viewportSize()!.width);
});

test("viewport scanning exposes lower controls and stops requesting scroll at the bottom", async ({ page }) => {
  await page.goto(target.origin + '/coverage-scroll');
  const first = await observeDom(page, await request(page));
  expect(first.data.observation.scrollable).toBe(true);
  expect(first.data.observation.elements.map(e => e.name)).toEqual(['Header']);
  await page.evaluate(() => scrollTo(0, document.documentElement.scrollHeight));
  const last = await observeDom(page, await request(page));
  expect(last.data.observation.scrollable).toBe(false);
  expect(last.data.observation.elements.map(e => e.name)).toEqual(['Lower content']);
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

test("failed DOM collection releases grounded targets and the document handle", async ({ page }) => {
  await page.setContent('<button>Action</button>');
  const req = await request(page);
  const handles: import('@playwright/test').JSHandle[] = [];
  const disposed = new Set<import('@playwright/test').JSHandle>();
  const track = <T extends import('@playwright/test').JSHandle>(handle: T): T => {
    handles.push(handle);
    const dispose = handle.dispose.bind(handle);
    handle.dispose = async () => { await dispose(); disposed.add(handle); };
    return handle;
  };
  const locate = page.locator.bind(page);
  page.locator = ((...args: Parameters<typeof page.locator>) => {
    const locator = locate(...args);
    if (args[0] === 'html') {
      const elementHandle = locator.elementHandle.bind(locator);
      locator.elementHandle = async (...args) => {
        const handle = await elementHandle(...args); return handle ? track(handle) : handle;
      };
    }
    return locator;
  }) as typeof page.locator;
  const frame = page.mainFrame(), evaluateHandle = frame.evaluateHandle.bind(frame);
  frame.evaluateHandle = (async (...args: any[]) => {
    return track(await (evaluateHandle as any)(...args));
  }) as typeof frame.evaluateHandle;
  const original = page.evaluate.bind(page);
  let reads = 0;
  page.evaluate = (async (...args: any[]) => {
    const value = await (original as any)(...args);
    if (++reads === 2) await original(() => { document.querySelector('button')!.textContent = 'Changed'; });
    return value;
  }) as typeof page.evaluate;
  await expect(observeDom(page, req)).rejects.toThrow('state_changed_during_observation');
  expect(handles.length).toBeGreaterThanOrEqual(2);
  expect(handles.every(handle => disposed.has(handle))).toBe(true);
  expect(await original(() => document.querySelector('button')!.textContent)).toBe('Changed');
});

test("navigation quiet window includes delayed controls without accepting stale targets", async ({ page }) => {
  await page.setContent('<button>Home</button>');
  await page.evaluate(() => { setTimeout(() => {
    const button = document.createElement('button'); button.textContent = 'News'; document.body.append(button);
  }, 300); });
  const settled = await settleState(page, Date.now() + 3000, 800);
  expect(settled.settled).toBe(true);
  const snapshot = await observeDom(page, await request(page, { expected_state_fingerprint: settled.state.fingerprint }));
  expect(snapshot.data.observation.elements.map(e => e.name)).toEqual(['Home', 'News']);
  await page.getByRole('button', { name: 'News', exact: true }).evaluate(el => { el.textContent = 'Changed'; });
  await expect(resolveDomTarget(snapshot, page, snapshot.data.observation.elements[1].element_id)).rejects.toThrow('stale_dom_snapshot');
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
