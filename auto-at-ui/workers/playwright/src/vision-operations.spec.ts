import { createHash, randomUUID } from "node:crypto";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve, sep } from "node:path";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import type { Duplex } from "node:stream";
import { chromium, expect, test, type Browser, type Page } from "@playwright/test";
import { VisualOperationWorker, type OperationResult } from "./vision-operations.js";
import { visualHttpHandler } from "./vision-http.js";
import { digest, validateVision, type VisualWorkerIdentity } from "./vision-contract.js";
import { startVisionTarget } from "./fixtures/vision-target.js";

let target: Awaited<ReturnType<typeof startVisionTarget>>;
let external: Awaited<ReturnType<typeof startVisionTarget>>;
let worker: VisualOperationWorker, identity: VisualWorkerIdentity, root: string, browser: Browser, page: Page;
let current: string;
let closed: boolean;
test.beforeAll(async () => { target = await startVisionTarget(); external = await startVisionTarget(); });
test.afterAll(async () => { await target.close(); await external.close(); });
test.beforeEach(async () => {
  closed = false;
  root = await mkdtemp(join(tmpdir(), "auto-at-vision-operations-"));
  worker = new VisualOperationWorker(root, async (options) => { browser = await chromium.launch(options); return browser; });
  identity = { contract_version: "v4", tenant_id: "fixture-tenant", project_id: randomUUID(), session_id: randomUUID(), fencing_token: 1 };
  const opened = await worker.open({ ...identity, target_url: target.origin, allowed_origins: [target.origin],
    deadline: new Date(Date.now() + 60_000).toISOString(), max_session_seconds: 60,
    max_states: 20, max_hops: 10, max_screenshot_bytes: 1_000_000 });
  current = opened.state_fingerprint; page = browser.contexts()[0].pages()[0];
});
test.afterEach(async () => {
  if (!closed && worker.hasSession(identity.session_id)) await worker.close(identity, identity.session_id);
  const path = resolve(root);
  expect(path.startsWith(resolve(tmpdir()) + sep) && path.includes("auto-at-vision-operations-")).toBe(true);
  await rm(path, { recursive: true, force: true });
});

function command(action: object, extra: object = {}) {
  return { ...identity, operation_id: randomUUID(), purpose: "explore", action, expected_state_fingerprint: current,
    state_id: randomUUID(), proposal_id: randomUUID(), ...extra };
}
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
async function setup(checkpoint = randomUUID()) {
  const result = await run({ kind: "navigate" }, { purpose: "setup", checkpoint_id: checkpoint, checkpoint_state_id: randomUUID() });
  expect(result.operation.status, result.operation.outcome_code ?? "").toBe("completed");
  return result;
}
const click = (y: number) => ({ kind: "click", x: 100 / 1279, y: y / 719 });

for (const mutation of ["form", "presence", "control", "scroll", "url", "visual"] as const) {
  test(`checkpoint diagnostic identifies ${mutation} drift without changing restoration`, async () => {
    await page.route(target.origin + '/', route => route.fulfill({ contentType: 'text/html',
      body: '<body style="height:2000px"><button>Original</button><input type="hidden" value="private-original"><span id="passive">Before</span>' }));
    const initial = await setup();
    const lines: string[] = [], original = console.warn;
    console.warn = (line: string) => lines.push(line);
    try {
      expect((await worker.checkpoint(identity, identity.session_id, initial.checkpoint!.id)).matches_current).toBe(true);
      expect(lines).toEqual([]);
      await page.evaluate(kind => {
        if (kind === 'form') document.querySelector('input')!.value = 'private-new-value';
        if (kind === 'presence') document.querySelector('input')!.remove();
        if (kind === 'control') document.querySelector('button')!.textContent = 'private-new-label';
        if (kind === 'scroll') window.scrollTo(0, 200);
        if (kind === 'url') history.pushState({}, '', '/private-path?token=private-value');
        if (kind === 'visual') document.querySelector('#passive')!.textContent = 'private-passive-content';
      }, mutation);
      const result = await worker.checkpoint(identity, identity.session_id, initial.checkpoint!.id);
      expect(result.checkpoint).toEqual(initial.checkpoint);
      expect(result.matches_current).toBe(mutation === 'visual');
      if (mutation === 'visual') expect(lines).toEqual([]);
      else {
        expect(lines).toHaveLength(1);
        expect(JSON.parse(lines[0])).toMatchObject({event:'vision.checkpoint.mismatch',
          checkpoint_id:initial.checkpoint!.id, state_id:initial.checkpoint!.state_id,
          session_id:identity.session_id, code:'checkpoint_mismatch',
          form_values_changed:mutation === 'form' || mutation === 'presence',
          form_presence_changed:mutation === 'presence', url_changed:mutation === 'url',
          scroll_changed:mutation === 'scroll', interaction_changed:mutation === 'control' || mutation === 'scroll'});
        expect(lines.join('\n')).not.toMatch(/private-|Original|Before/);
        console.warn = () => { throw new Error('logger unavailable'); };
        expect((await worker.checkpoint(identity, identity.session_id, initial.checkpoint!.id)).matches_current).toBe(false);
      }
    } finally { console.warn = original; }
  });
}

for (let schedule = 0; schedule < 20; schedule++) {
  test(`restore dispatch barrier retains rejection and immutable checkpoint ${schedule}`, async () => {
    await page.route(target.origin + '/', route => route.fulfill({ contentType: 'text/html',
      body: '<button>Original</button><input type="hidden" value="original">' }));
    const initial = await setup();
    const prepared = await worker.prepare(command({ kind: 'wait', duration_ms: 100 }, {
      purpose: 'restore', restore_checkpoint_id: initial.checkpoint!.id,
    }));
    expect(prepared.operation.status).toBe('prepared');
    await page.evaluate(form => {
      if (form) document.querySelector('input')!.value = 'changed';
      else document.querySelector('button')!.textContent = 'Changed';
    }, schedule % 2 === 1);
    const rejected = await worker.execute(executeCommand(prepared));
    current = rejected.state_fingerprint!;
    expect(rejected.operation).toMatchObject({ status: 'rejected', outcome_code: 'state_mismatch', executed_click: null });
    expect(rejected).toMatchObject({ dispatch_started: false, failure_stage: 'before_dispatch' });
    expect(rejected.frames.map(frame => frame.role)).toEqual(['before', 'after']);
    expect((await worker.checkpoint(identity, identity.session_id, initial.checkpoint!.id)).matches_current).toBe(false);
    await page.evaluate(() => {
      document.querySelector('input')!.value = 'original';
      document.querySelector('button')!.textContent = 'Original';
    });
    const refreshed = await run({ kind: 'wait', duration_ms: 100 }, {
      purpose: 'setup', state_id: null, proposal_id: null, refresh_observation: true,
      checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID(),
    });
    expect(refreshed.operation.status).toBe('completed');
    const check = await worker.checkpoint(identity, identity.session_id, initial.checkpoint!.id);
    expect(check.checkpoint).toEqual(initial.checkpoint);
    expect(check.matches_current).toBe(true);
    const verified = await run({ kind: 'wait', duration_ms: 100 }, {
      purpose: 'restore', restore_checkpoint_id: initial.checkpoint!.id,
    });
    expect(verified.operation.status).toBe('completed');
    expect(verified.dispatch_started).toBe(true);
    expect(worker.read(identity, identity.session_id, rejected.operation.id).operation.status).toBe('rejected');
  });
}

test("button scope filters observations and rejects a link click before dispatch", async () => {
  await worker.close(identity, identity.session_id);
  identity = { ...identity, session_id: randomUUID() };
  const opened = await worker.open({ ...identity, target_url: target.origin, allowed_origins: [target.origin],
    interaction_scope: 'buttons', required_capabilities: ['button-scope-v1', 'anonymous-button-v1'],
    deadline: new Date(Date.now() + 60000).toISOString(), max_session_seconds: 60,
    max_states: 20, max_hops: 10, max_screenshot_bytes: 1000000 });
  current = opened.state_fingerprint; page = browser.contexts()[0].pages()[0];
  expect(opened.capabilities).toContain('button-scope-v1');
  expect(opened.capabilities).toContain('anonymous-button-v1');
  await page.route(target.origin + '/', route => route.fulfill({ contentType: 'text/html', body: `
    <button style="position:absolute;left:20px;top:20px;width:180px;height:40px">Save</button>
    <a href="/a" style="position:absolute;left:20px;top:80px;width:180px;height:40px">Article</a>
    <button style="position:absolute;left:20px;top:140px;width:180px;height:40px" onclick="this.dataset.clicked='yes'"></button>` }));
  await setup();
  const observed = await worker.observeDom({ ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: current });
  expect(observed.data.observation.elements.map(e => [e.role, e.name])).toEqual([['button', 'Save'], ['button', '']]);
  const rejected = await worker.prepare(command(click(100)));
  expect(rejected.operation).toMatchObject({ status: 'rejected', outcome_code: 'out_of_scope_target', executed_click: null });
  expect(page.url()).toBe(target.origin + '/');
  expect((await run(click(40))).operation.status).toBe('completed');
  const anonymous = observed.data.observation.elements.find(e => !e.name)!;
  const anonymousCommand = { dom_snapshot_id: observed.data.observation.snapshot_id,
    dom_element_id: anonymous.element_id };
  const capture = worker['capture'].bind(worker);
  worker['capture'] = async (...args: Parameters<typeof capture>) => {
    const result = await capture(...args);
    if (args[2] === 'before') await page.locator('button').nth(1).evaluate(el => (el as HTMLElement).style.left = '300px');
    return result;
  };
  const prepared = await worker.prepare(command(click(40), anonymousCommand));
  worker['capture'] = capture;
  expect(prepared.operation.status).toBe('prepared');
  await page.locator('button').nth(1).evaluate(el => (el as HTMLElement).style.left = '600px');
  const clicked = await worker.execute(executeCommand(prepared));
  current = clicked.state_fingerprint!;
  expect(clicked.operation.status).toBe('completed');
  expect(clicked.locator?.descriptor).toMatchObject({ schema_version: 'v2', strategy: 'dom_path' });
  expect(await page.locator('button').nth(1).getAttribute('data-clicked')).toBe('yes');
  const pending = await worker.prepare(command(click(40), anonymousCommand));
  expect(pending.operation.status).toBe('prepared');
  await page.locator('button').nth(1).evaluate(el => el.replaceWith(el.cloneNode(true)));
  const replaced = await worker.execute(executeCommand(pending));
  expect(replaced.operation).toMatchObject({ status: 'rejected', outcome_code: 'stale_dom_target', executed_click: null });
});

test("visual button scope executes styled links and custom buttons but rejects content links and replacements", async () => {
  await worker.close(identity, identity.session_id);
  identity = { ...identity, session_id: randomUUID() };
  const opened = await worker.open({ ...identity, target_url: target.origin, allowed_origins: [target.origin],
    interaction_scope: 'visual_buttons', required_capabilities: ['visual-button-scope-v1'],
    deadline: new Date(Date.now()+60000).toISOString(), max_session_seconds: 60,
    max_states: 20, max_hops: 10, max_screenshot_bytes: 1000000 });
  current=opened.state_fingerprint;page=browser.contexts()[0].pages()[0];
  await page.route(target.origin+'/', route=>route.fulfill({contentType:'text/html',body:`
    <a href="/a" onclick="event.preventDefault();this.dataset.clicked='yes'" style="display:block;width:180px;height:40px;background:gold;border-radius:5px">Open</a>
    <div onclick="this.dataset.clicked='yes'" style="width:80px;height:40px;background:linear-gradient(red,blue);cursor:pointer"></div>
    <a href="/a" aria-label="Article" style="display:block;width:180px;height:40px">Article</a>`}));
  await setup();
  const dom=await worker.observeDom({...identity,snapshot_id:randomUUID(),expected_state_fingerprint:current});
  expect(dom.data.observation.elements.map(e=>e.button_kind)).toEqual(['styled_link','custom']);
  for(const element of dom.data.observation.elements) {
    const result=await run(click(20),{dom_snapshot_id:dom.data.observation.snapshot_id,dom_element_id:element.element_id});
    expect(result.operation.status,result.operation.outcome_code??'').toBe('completed');
    expect(result.operation.executed_click).not.toBeNull();
  }
  expect(await page.locator('[data-clicked=yes]').count()).toBe(2);
  const outside=await worker.prepare(command(click(100)));
  expect(outside.operation.outcome_code).toBe('out_of_scope_target');
  const pending=await worker.prepare(command(click(20),{dom_snapshot_id:dom.data.observation.snapshot_id,dom_element_id:dom.data.observation.elements[0].element_id}));
  expect(pending.operation.status).toBe('prepared');
  await page.locator('a').first().evaluate(el=>el.replaceWith(el.cloneNode(true)));
  const replaced=await worker.execute(executeCommand(pending));
  expect(replaced.operation.status).toBe('rejected');
  expect(replaced.operation.executed_click).toBeNull();
});

for (const mutation of ['none', 'form', 'replacement', 'persistent'] as const) {
  test(`visual target settles after capture while preserving ${mutation} guard`, async () => {
    await worker.close(identity, identity.session_id);
    identity = { ...identity, session_id: randomUUID() };
    const opened = await worker.open({ ...identity, target_url: target.origin, allowed_origins: [target.origin],
      interaction_scope: 'visual_buttons', required_capabilities: ['visual-button-scope-v1'],
      deadline: new Date(Date.now() + 60000).toISOString(), max_session_seconds: 60,
      max_states: 20, max_hops: 10, max_screenshot_bytes: 1000000 });
    current = opened.state_fingerprint; page = browser.contexts()[0].pages()[0];
    await page.route(target.origin + '/', route => route.fulfill({ contentType: 'text/html', body: `
      <input type="hidden" value="original-private-value">
      <button style="position:absolute;left:20px;top:30px;width:8px;height:40px;padding:0;border:0"
        onclick="window.clickCount=(window.clickCount||0)+1" aria-label="Moving action"></button>` }));
    await setup();
    const observed = await worker.observeDom({ ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: current });
    const capture = worker['capture'].bind(worker);
    worker['capture'] = async (...args: Parameters<typeof capture>) => {
      const result = await capture(...args);
      if (args[2] === 'before') await page.locator('button').evaluate((el, mutation) => {
        const animation = el.animate([{ transform: 'translateX(0)' }, { transform: 'translateX(600px)' }],
          { duration: 700, fill: 'forwards', iterations: mutation === 'persistent' ? Infinity : 1 });
        animation.onfinish = () => {
          if (mutation === 'form') document.querySelector('input')!.value = 'changed-private-value';
          if (mutation === 'replacement') el.replaceWith(el.cloneNode(true));
        };
      }, mutation);
      return result;
    };
    const prepared = await worker.prepare(command(click(40), {
      dom_snapshot_id: observed.data.observation.snapshot_id,
      dom_element_id: observed.data.observation.elements[0].element_id,
    }));
    worker['capture'] = capture;
    if (mutation === 'none') {
      expect(prepared.operation.status, prepared.operation.outcome_code ?? '').toBe('prepared');
      expect(await page.evaluate(() => document.getAnimations().some(a => a.playState === 'running'))).toBe(false);
      const result = await worker.execute(executeCommand(prepared));
      expect(result.operation.status, result.operation.outcome_code ?? '').toBe('completed');
      expect(await page.evaluate(() => (window as unknown as { clickCount: number }).clickCount)).toBe(1);
    } else {
      expect(prepared.operation.status).toBe('rejected');
      expect(prepared.dispatch_started).toBe(false);
      expect(prepared.operation.executed_click).toBeNull();
      expect(await page.evaluate(() => (window as unknown as { clickCount?: number }).clickCount ?? 0)).toBe(0);
    }
  });
}

test("download button records initiation without requiring a persistent popup or retaining a file", async () => {
  await page.route(target.origin+'/', route=>route.fulfill({contentType:'text/html',body:
    '<a href="/download" target="_blank" style="display:block;width:180px;height:40px">Download</a>'}));
  await setup();
  const result=await run(click(20), { checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID() });
  expect(result.operation.status,result.operation.outcome_code??'').toBe('completed');
  expect(result.operation.outcome_code).toBe('download_started');
  expect(result.operation.executed_click).not.toBeNull();
  expect(result.operation.after_page_id).toBe(result.operation.before_page_id);
  expect(result.frames.map(frame => frame.role)).toEqual(['before', 'after']);
  expect(result.checkpoint).not.toBeNull();
  expect(result.replayable).toBe(false);
  expect(browser.contexts()[0].pages().map(p => p.url())).toEqual([target.origin + '/']);
});

test("per-step deadlines permit a session longer than its initial and step budgets", async () => {
  await worker.close(identity, identity.session_id);
  identity = { ...identity, session_id: randomUUID() };
  const began = Date.now();
  const opened = await worker.open({ ...identity, target_url: target.origin, allowed_origins: [target.origin],
    deadline: new Date(began + 2000).toISOString(), max_session_seconds: 5, step_timeout_seconds: 5,
    max_states: 20, max_hops: 10, max_screenshot_bytes: 1_000_000, required_capabilities: ["step-timeout-v1"] });
  expect(opened.capabilities).toContain("step-timeout-v1");
  current = opened.state_fingerprint; page = browser.contexts()[0].pages()[0];
  const rootState = await run({ kind: "navigate" }, { purpose: "setup", step_deadline: new Date(Date.now() + 5000).toISOString() });
  expect(rootState.operation.status).toBe("completed");
  await page.waitForTimeout(Math.max(1, began + 5200 - Date.now()));
  const next = await run(click(40), { step_deadline: new Date(Date.now() + 5000).toISOString() });
  expect(next.operation.status).toBe("completed");
  expect(next.operation.executed_click).not.toBeNull();
  expect(Date.now() - began).toBeGreaterThan(5000);
});

test("per-step prepared action expires without allowing duplicate execute to restart its timer", async () => {
  await worker.close(identity, identity.session_id);
  identity = { ...identity, session_id: randomUUID() };
  const opened = await worker.open({ ...identity, target_url: target.origin, allowed_origins: [target.origin],
    deadline: new Date(Date.now() + 5000).toISOString(), max_session_seconds: 5, step_timeout_seconds: 5,
    max_states: 20, max_hops: 10, max_screenshot_bytes: 1_000_000 });
  current = opened.state_fingerprint; page = browser.contexts()[0].pages()[0];
  await run({ kind: "navigate" }, { purpose: "setup", step_deadline: new Date(Date.now() + 5000).toISOString() });
  const missing = await worker.prepare(command(click(40)));
  expect(missing.operation.outcome_code).toBe("invalid_step_deadline");
  const prepared = await worker.prepare(command(click(40), { step_deadline: new Date(Date.now() + 1500).toISOString() }));
  expect(prepared.operation.status).toBe("prepared");
  await new Promise(resolve => setTimeout(resolve, 1700));
  const result = await worker.execute(executeCommand(prepared));
  expect(result.operation).toMatchObject({ status: "rejected", outcome_code: "step_timeout", executed_click: null });
  expect((await worker.execute(executeCommand(prepared))).operation).toEqual(result.operation);
});

test("DOM replay matches the submitted action and reuses verified coordinates", async () => {
  const rootState = await setup();
  const snapshotId = randomUUID();
  const observation = await worker.observeDom({ ...identity, snapshot_id: snapshotId, expected_state_fingerprint: current });
  const element = observation.data.observation.elements.find(e => e.name === "Branch A")!;
  const proposed = { kind: "click", x: 0.99, y: 0.01 };
  const first = await run(proposed, { dom_snapshot_id: snapshotId, dom_element_id: element.element_id });
  expect(first.operation.status).toBe("completed");
  expect(first.replayable).toBe(true);
  const home = await run({ kind: "navigate" }, { purpose: "replay", replay_operation_id: rootState.operation.id });
  expect(home.operation.status).toBe("completed");
  const bad = await worker.prepare(command({ ...proposed, x: 0.8 }, {
    purpose: "replay", replay_operation_id: first.operation.id, expected_locator: first.locator!.descriptor,
  }));
  expect(bad.operation.outcome_code).toBe("replay_mismatch");
  const replay = await run(proposed, {
    purpose: "replay", replay_operation_id: first.operation.id, expected_locator: first.locator!.descriptor,
  });
  expect(replay.operation.status).toBe("completed");
  expect(page.url()).toBe(target.origin + "/a");
  expect(replay.operation.executed_click).not.toBeNull();
});

test("live screen works during an operation, respects scope and does not create actions", async () => {
  await setup();
  await expect(worker.screen({ ...identity, tenant_id: "other" }, identity.session_id)).rejects.toThrow("scope_mismatch");
  await expect(worker.screen({ ...identity, fencing_token: 2 }, identity.session_id)).rejects.toThrow("stale_fencing_token");
  const prepared = await worker.prepare(command({ kind: "wait", duration_ms: 1000 }));
  const running = worker.execute(executeCommand(prepared));
  const images = await Promise.all([worker.screen(identity, identity.session_id), worker.screen(identity, identity.session_id)]);
  expect(images[0].subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
  expect(images[0]).toEqual(images[1]);
  const result = await running;
  expect(result.operation.sequence).toBe(2);
  expect(result.operation.status).toBe("completed");
  await worker.close(identity, identity.session_id);
  closed = true;
  await expect(worker.screen(identity, identity.session_id)).rejects.toThrow("session_unavailable");
});

test("read-only refresh retains old evidence and cannot authorize a stale click", async () => {
  const first = await setup();
  await page.getByRole('button', { name: 'Toggle modal', exact: true }).evaluate(el => { el.textContent = 'Updated modal'; });
  await expect(worker.observeDom({ ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: current })).rejects.toThrow('state_mismatch');
  const invalid = await worker.prepare(command(click(340), { refresh_observation: true }));
  expect(invalid.operation.status).toBe('rejected');
  const refreshed = await run({ kind: 'wait', duration_ms: 100 }, {
    purpose: 'setup', state_id: first.checkpoint!.state_id, proposal_id: null,
    refresh_observation: true, checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID(),
  });
  expect(refreshed.operation.status).toBe('completed');
  expect(refreshed.operation.executed_click).toBeNull();
  expect(refreshed.checkpoint!.id).not.toBe(first.checkpoint!.id);
  expect((await worker.checkpoint(identity, identity.session_id, first.checkpoint!.id)).matches_current).toBe(false);
  const observed = await worker.observeDom({ ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: current });
  expect(observed.data.observation.elements.some(e => e.name === 'Updated modal')).toBe(true);
});

test("read-only refresh waits for delayed controls beyond three seconds", async () => {
  const first = await setup();
  await page.evaluate(() => {
    const button = document.querySelector('button')!;
    const timer = setInterval(() => { button.disabled = !button.disabled; }, 100);
    setTimeout(() => { clearInterval(timer); button.disabled = false; }, 3300);
  });
  const refreshed = await run({ kind: 'wait', duration_ms: 100 }, {
    purpose: 'setup', proposal_id: null, refresh_observation: true,
    checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID(),
  });
  expect(refreshed.operation.status).toBe('completed');
  expect(refreshed.operation.executed_click).toBeNull();
  expect(refreshed.checkpoint!.id).not.toBe(first.checkpoint!.id);
  expect((await worker.checkpoint(identity, identity.session_id, refreshed.checkpoint!.id)).matches_current).toBe(true);
});

test("read-only refresh never accepts continuously changing controls", async () => {
  await setup();
  await page.evaluate(() => {
    const button = document.querySelector('button')!;
    setInterval(() => { button.disabled = !button.disabled; }, 100);
  });
  const refreshed = await worker.prepare(command({ kind: 'wait', duration_ms: 100 }, {
    purpose: 'setup', proposal_id: null, refresh_observation: true,
    checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID(),
  }));
  expect(refreshed.operation.status).toBe('rejected');
  expect(refreshed.operation.outcome_code).toBe('settle_timeout');
  expect(refreshed.operation.executed_click).toBeNull();
  expect(refreshed.checkpoint).toBeNull();
});

test("a delayed DOM reply gets new checkpoint evidence and cannot adopt a replacement target", async () => {
  await setup();
  const initial = await worker.observeDom({ ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: current });
  const element = initial.data.observation.elements.find(e => e.name === 'Branch A')!;
  await page.evaluate(() => document.body.insertAdjacentHTML('beforeend',
    '<div style="position:fixed;left:1000px;top:50px;width:30px;height:30px;cursor:pointer">Slide</div>'));
  await run({ kind: 'wait', duration_ms: 100 }, { purpose: 'setup', proposal_id: null, refresh_observation: true,
    checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID() });
  const fresh = await worker.observeDom({ ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: current,
    revalidate_snapshot_id: initial.data.observation.snapshot_id, revalidate_element_ids: [element.element_id] });
  expect(fresh.data.observation.snapshot_id).not.toBe(initial.data.observation.snapshot_id);
  expect(fresh.data.observation.elements.some(e => e.element_id === element.element_id)).toBe(true);
  await page.getByRole('link', { name: 'Branch A', exact: true }).evaluate(el => el.replaceWith(el.cloneNode(true)));
  const rejected = await worker.prepare(command(click(20), { dom_snapshot_id: fresh.data.observation.snapshot_id,
    dom_element_id: element.element_id }));
  expect(rejected.operation.status).toBe('rejected');
  expect(rejected.operation.outcome_code).toBe('stale_dom_target');
  expect(rejected.operation.executed_click).toBeNull();
});

test("screen capture does not wait for an unresolved font load", async () => {
  await setup();
  await page.evaluate(() => {
    Object.defineProperty(document.fonts, "ready", { get: () => new Promise(() => {}) });
  });
  const prepared = await worker.prepare(command(click(340)));
  expect(prepared.operation.status).toBe("prepared");
  expect((await worker.screen(identity, identity.session_id)).length).toBeGreaterThan(100);
});

test("read-only refresh capture race retains before evidence and proves no dispatch", async () => {
  const initial = await setup();
  const context = page.context(), original = context.newCDPSession.bind(context);
  let injected = false;
  context.newCDPSession = async (target) => {
    const client = await original(target), send = client.send.bind(client);
    client.send = async (method, params) => {
      const result = await send(method, params);
      if (method === "Page.captureScreenshot" && !injected) {
        injected = true;
        await page.evaluate(() => {
          const input = document.createElement("input"); input.type = "hidden";
          input.value = "synthetic-refresh-private"; document.body.append(input);
        });
      }
      return result;
    };
    return client;
  };
  const rejected = await worker.prepare(command({ kind: "wait", duration_ms: 100 }, {
    purpose: "setup", proposal_id: null, refresh_observation: true,
    checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID(),
  }));
  expect(rejected.operation).toMatchObject({ status: "rejected", outcome_code: "state_changed_during_prepare",
    before_page_id: initial.operation.after_page_id, after_unavailable_reason: "action_not_executed" });
  expect(rejected.dispatch_started).toBe(false);
  expect(rejected.failure_stage).toBe("prepare");
  expect(rejected.frames.map(frame => frame.role)).toEqual(["before"]);
  expect(rejected.checkpoint).toBeNull();
  expect(JSON.stringify(rejected)).not.toContain("synthetic-refresh-private");
});

test("checkpoint and final image include hydration that finishes during capture", async () => {
  const context = page.context(), original = context.newCDPSession.bind(context);
  let captures = 0;
  context.newCDPSession = async (target) => {
    const client = await original(target), send = client.send.bind(client);
    client.send = async (method, params) => {
      const result = await send(method, params);
      if (method === "Page.captureScreenshot" && page.url() !== "about:blank" && captures++ === 0) {
        await page.evaluate(() => {
          const input = document.createElement("input");
          input.type = "hidden"; input.value = "synthetic-capture-value";
          document.body.append(input);
          const heading = document.createElement("h1");
          heading.textContent = "Hydration finished"; document.body.append(heading);
        });
      }
      return result;
    };
    return client;
  };
  const result = await setup();
  expect(captures).toBe(2);
  expect(result.frames.map(frame => frame.role)).toEqual(["before", "after"]);
  expect((await worker.checkpoint(identity, identity.session_id, result.checkpoint!.id)).matches_current).toBe(true);
  expect(JSON.stringify(result)).not.toContain("synthetic-capture-value");
  expect((await run(click(100))).operation.status).toBe("completed");
});

for (const navigationReset of [true, false]) test(`after capture read recovery is navigation-only: ${navigationReset}`, async () => {
  await setup();
  const context = page.context(), original = context.newCDPSession.bind(context);
  const evaluate = page.evaluate.bind(page);
  let captures = 0, interruptRead = false;
  page.evaluate = (async (...args: Parameters<typeof page.evaluate>) => {
    if (interruptRead) {
      interruptRead = false;
      throw new Error(navigationReset ? 'Execution context was destroyed, most likely because of a navigation' : 'synthetic read failure');
    }
    return evaluate(...args);
  }) as typeof page.evaluate;
  context.newCDPSession = async (target) => {
    const client = await original(target), send = client.send.bind(client);
    client.send = async (method, params) => {
      const result = await send(method, params);
      if (method === 'Page.captureScreenshot' && ++captures === 2) interruptRead = true;
      return result;
    };
    return client;
  };
  const result = await run(click(340), { checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID() });
  expect(result.operation.status).toBe('completed');
  expect(await page.getByRole('button', { name: 'Icon action', exact: true }).getAttribute('data-count')).toBe('1');
  expect(captures).toBe(navigationReset ? 3 : 2);
  expect(result.frames.map(frame => frame.role)).toEqual(navigationReset ? ['before', 'after'] : ['before']);
  if (navigationReset) {
    expect(result.checkpoint).not.toBeNull();
    expect((await worker.checkpoint(identity, identity.session_id, result.checkpoint!.id)).matches_current).toBe(true);
  } else {
    expect(result.checkpoint).toBeNull();
    expect(result.operation.after_unavailable_reason).toBe('capture_failed');
  }
});

test("restoration rechecks form state against the final image", async () => {
  const rootState = await setup();
  await run(click(40));
  const context = page.context(), original = context.newCDPSession.bind(context);
  let changed = false;
  context.newCDPSession = async (target) => {
    const client = await original(target), send = client.send.bind(client);
    client.send = async (method, params) => {
      const result = await send(method, params);
      if (method === "Page.captureScreenshot" && new URL(page.url()).pathname === "/" && !changed) {
        changed = true;
        await page.getByRole("textbox").evaluate(el => { (el as HTMLInputElement).value = "changed-during-capture"; });
      }
      return result;
    };
    return client;
  };
  const result = await run({ kind: "back" }, { purpose: "restore", restore_checkpoint_id: rootState.checkpoint!.id });
  expect(result.operation).toMatchObject({ status: "failed", outcome_code: "state_restore_failed" });
  expect(result.frames).toHaveLength(2);
  expect(result.replayable).toBe(false);
  expect((await worker.prepare(command(click(100)))).operation.status).toBe("rejected");
});

test("restoration without an after image cannot authorize a sibling click", async () => {
  const rootState = await setup();
  await run(click(40));
  const context = page.context(), original = context.newCDPSession.bind(context);
  context.newCDPSession = async (target) => {
    if (new URL(page.url()).pathname === "/") throw new Error("fixture after capture unavailable");
    return original(target);
  };
  const result = await run({ kind: "back" }, { purpose: "restore", restore_checkpoint_id: rootState.checkpoint!.id });
  expect(result.operation).toMatchObject({ status: "failed", outcome_code: "state_restore_failed", after_unavailable_reason: "capture_failed" });
  expect(result.replayable).toBe(false);
  expect((await worker.prepare(command(click(100)))).operation.status).toBe("rejected");
});
function ledger(result: OperationResult, kind: string, sequence: number) {
  expect(result.operation).toMatchObject({ action_kind: kind, sequence, status: "completed" });
  expect(result.frames.map((f) => f.role)).toEqual(["before", "after"]);
  expect(() => validateVision("VisualOperation", result.operation)).not.toThrow();
}

test("blank setup → A → verified back → B preserves chronology and real frames", async () => {
  const rootState = await setup(); ledger(rootState, "navigate", 1);
  expect(rootState.operation.url_change).toBe("changed");
  const a = await run(click(40)); ledger(a, "click", 2);
  expect(a.operation.url_change).toBe("changed"); expect(a.locator?.descriptor?.value).toBe("Branch A");
  expect(a.replayable).toBe(true);
  const back = await run({ kind: "back" }, { purpose: "restore", restore_checkpoint_id: rootState.checkpoint!.id });
  ledger(back, "back", 3);
  expect((await worker.checkpoint(identity, identity.session_id, rootState.checkpoint!.id)).matches_current).toBe(true);
  const b = await run(click(100)); ledger(b, "click", 4);
  expect(b.locator?.descriptor?.value).toBe("Branch B");
  expect(b.operation.parent_operation_id).toBe(rootState.operation.id);
  for (const result of [rootState, a, back, b]) for (const frame of result.frames) {
    const bytes = await worker.frame(identity, identity.session_id, result.operation.id, frame.id);
    expect(digest(bytes)).toBe(frame.checksum);
  }
});
test("prepare requires durable before ACK; duplicate execute performs only one click", async () => {
  await setup(); const payload = command(click(340));
  const prepared = await worker.prepare(payload);
  expect(await worker.prepare(payload)).toEqual(prepared);
  expect(await page.getByRole("button", { name: "Icon action" }).getAttribute("data-count")).toBeNull();
  await expect(worker.execute({ ...executeCommand(prepared), before_persisted: false })).rejects.toThrow();
  await expect(worker.execute({ ...executeCommand(prepared), before_checksum: "a".repeat(64) })).rejects.toThrow("before_ack_mismatch");
  await expect(worker.prepare({ ...payload, action: click(100) })).rejects.toThrow("operation_payload_conflict");
  const result = await worker.execute(executeCommand(prepared)); ledger(result, "click", 2);
  expect(result.operation.executed_click?.before_frame_id).toBe(prepared.operation.actual_before_frame_id);
  expect(await worker.execute(executeCommand(prepared))).toEqual(result);
  expect(worker.read(identity, identity.session_id, result.operation.id)).toEqual(result);
  expect(await page.getByRole("button", { name: "Icon action" }).getAttribute("data-count")).toBe("1");
  await expect(worker.acknowledge({ ...identity, operation_id: result.operation.id, persisted_frame_ids: [] })).rejects.toThrow("frame_ack_mismatch");
  await worker.acknowledge({ ...identity, operation_id: result.operation.id, persisted_frame_ids: result.frames.map((f) => f.id) });
  await expect(worker.frame(identity, identity.session_id, result.operation.id, result.frames[0].id)).rejects.toThrow("frame_unavailable");
  expect(worker.read(identity, identity.session_id, result.operation.id).acknowledged).toBe(true);
});

test("synthetic div/span buttons and a scrolled offscreen control execute with paired frames", async () => {
  await setup();
  for (const [name, y, sequence] of [["Custom div action", 580, 2], ["Custom span action", 640, 3]] as const) {
    const result = await run(click(y)); ledger(result, "click", sequence);
    expect(result.locator?.descriptor).toMatchObject({ strategy: "role", role: "button", value: name });
    expect(await page.getByRole("button", { name }).getAttribute("data-clicked")).toBe("yes");
  }
  await expect(page.getByRole("button", { name: "Offscreen action" })).not.toBeInViewport();
  const scrolled = await run({ kind: "scroll", delta_y: 1000 }); ledger(scrolled, "scroll", 4);
  const control = page.getByRole("button", { name: "Offscreen action" });
  await expect(control).toBeInViewport();
  const box = (await control.boundingBox())!;
  const clicked = await run({ kind: "click", x: (box.x + box.width / 2) / 1279, y: (box.y + box.height / 2) / 719 });
  ledger(clicked, "click", 5);
  expect(await control.getAttribute("data-clicked")).toBe("yes");
  for (const frame of clicked.frames) expect(digest(await worker.frame(identity, identity.session_id, clicked.operation.id, frame.id))).toBe(frame.checksum);
});
test("hydration replacing an identical DOM target rejects stale prepared locator", async () => {
  await setup(); const prepared = await worker.prepare(command(click(340)));
  await page.getByRole("button", { name: "Icon action" }).evaluate((el) => el.replaceWith(el.cloneNode(true)));
  const result = await worker.execute(executeCommand(prepared));
  expect(result.operation).toMatchObject({ status: "rejected", outcome_code: "stale_locator" });
  expect(result.operation.executed_click).toBeNull();
  expect(result.frames.map((f) => f.role)).toEqual(["before", "after"]);
  expect(await page.getByRole("button", { name: "Icon action" }).getAttribute("data-count")).toBeNull();
});
test("same URL modal has semantic/visual change; no-op remains an observation", async () => {
  await setup(); const modal = await run(click(160));
  expect(modal.operation).toMatchObject({ status: "completed", url_change: "unchanged", visual_change: "changed", outcome_code: "observed" });
  expect(modal.semantic_change).toBe("changed");
  const noop = await run(click(400));
  expect(noop.operation).toMatchObject({ status: "completed", url_change: "unchanged", outcome_code: "observed" });
  expect(noop.semantic_change).toBe("unchanged");
});
test("declared new-tab link waits for a delayed response before finalizing its click", async () => {
  await page.context().route(target.origin + '/', route => route.fulfill({ contentType: 'text/html',
    body: '<a href="/slow-popup" target="_blank" style="position:absolute;left:20px;top:80px;width:200px;height:40px">Delayed tab</a>' }));
  await page.context().route(target.origin + '/slow-popup', async route => {
    await new Promise(resolve => setTimeout(resolve, 1200));
    await route.fulfill({ contentType: 'text/html', body: '<button>Popup control</button>' });
  });
  await setup();
  const result = await run(click(100), { checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID() });
  expect(result.operation.status).toBe('completed');
  expect(result.operation.after_page_id).not.toBe(result.operation.before_page_id);
  const observed = await worker.observeDom({ ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: current });
  expect(observed.data.observation.elements.map(e => e.name)).toEqual(['Popup control']);
  expect((await run({ kind: 'close_popup' }, { purpose: 'restore' })).operation.status).toBe('completed');
});

test("popup close records popup before and original parent after with invariant check", async () => {
  const rootState = await setup(); const popup = await run(click(220)); ledger(popup, "click", 2);
  expect(popup.operation.before_page_id).not.toBe(popup.operation.after_page_id);
  const closed = await run({ kind: "close_popup" }, { purpose: "restore", restore_checkpoint_id: rootState.checkpoint!.id });
  ledger(closed, "close_popup", 3);
  expect(closed.operation.before_page_id).toBe(popup.operation.after_page_id);
  expect(closed.operation.after_page_id).toBe(rootState.operation.after_page_id);
});
test("input appends and its value is omitted from transport and checkpoints", async () => {
  await setup(); const result = await run({ kind: "type", x: 100 / 1279, y: 280 / 719, text: "private-fixture-value" },
    { checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID() });
  ledger(result, "type", 2);
  expect(await page.getByRole("textbox").inputValue()).toBe("seedprivate-fixture-value");
  expect(JSON.stringify(result)).not.toContain("private-fixture-value");
  expect(result.replayable).toBe(false);
  await worker.acknowledge({ ...identity, operation_id: result.operation.id, persisted_frame_ids: result.frames.map((f) => f.id) });
});
test("each replay primitive is traced; unsafe and unknown operations cannot replay", async () => {
  const rootState = await setup(); const modal = await run(click(160));
  const rejected = await worker.prepare(command(click(160), { purpose: "replay", replay_operation_id: modal.operation.id, expected_locator: modal.locator!.descriptor }));
  expect(rejected.operation).toMatchObject({ status: "rejected", outcome_code: "unsafe_replay" });
  const replay = await run({ kind: "navigate" }, { purpose: "replay", replay_operation_id: rootState.operation.id,
    restore_checkpoint_id: rootState.checkpoint!.id });
  ledger(replay, "navigate", 4);
  expect(replay.operation.purpose).toBe("replay");
});
test("failed restoration prevents a dependent sibling from executing", async () => {
  const rootState = await setup();
  const failed = await run({ kind: "scroll", delta_y: 300 }, { purpose: "restore", restore_checkpoint_id: rootState.checkpoint!.id });
  expect(failed.operation).toMatchObject({ status: "failed", outcome_code: "state_restore_failed" });
  const sibling = await worker.prepare(command(click(100)));
  expect(sibling.operation).toMatchObject({ status: "rejected", outcome_code: "state_restore_failed" });
});
for (const popup of [false, true]) test(`external ${popup ? "popup" : "navigation"} continues and records only its origin`, async () => {
  await page.route(`${target.origin}/`, async (route) => {
    const response = await route.fetch();
    const html = (await response.text()).replace('href="http://localhost:1/denied" target="_blank"',
      `href="${external.origin}/a?token=synthetic-private#fragment" ${popup ? 'target="_blank"' : ""}`);
    await route.fulfill({ response, body: html });
  });
  await setup();
  const result = await run(click(460));
  expect(result.operation.status).toBe("completed");
  const observed = worker.origins(identity, identity.session_id) as { items: { origin: string; request_kind: string }[] };
  expect(observed.items).toContainEqual(expect.objectContaining({ origin: external.origin, request_kind: popup ? "popup" : "navigation" }));
  expect(JSON.stringify(observed)).not.toContain("synthetic-private");
  expect(JSON.stringify(observed)).not.toContain("fragment");
  expect(() => worker.origins({ ...identity, tenant_id: "other" }, identity.session_id)).toThrow("scope_mismatch");
  const next = await run({ kind: "wait", duration_ms: 100 });
  expect(next.operation.status).toBe("completed");
});

test("external subresources are loaded and deduplicated without poisoning the session", async () => {
  await setup();
  await page.evaluate(async (origin) => {
    await fetch(`${origin}/resource?token=private-one`, { mode: "no-cors" });
    await fetch(`${origin}/resource?token=private-two`, { mode: "no-cors" });
  }, external.origin);
  const result = await run({ kind: "wait", duration_ms: 100 });
  expect(result.operation.status).toBe("completed");
  const observed = worker.origins(identity, identity.session_id) as { items: unknown[] };
  expect(observed.items).toHaveLength(1);
  expect(observed.items[0]).toMatchObject({ origin: external.origin, request_kind: "resource" });
  expect(external.visits.get("/resource?token=private-one")).toBe(1);
  expect(JSON.stringify(observed)).not.toContain("private-one");
});

test("external WebSocket connects and records its origin without query values", async () => {
  const sockets = new Set<Duplex>();
  const server = createServer();
  server.on("upgrade", (request, socket) => {
    sockets.add(socket);
    const accept = createHash("sha1").update(request.headers["sec-websocket-key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest("base64");
    socket.write(`HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ${accept}\r\n\r\n`);
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  try {
    await setup();
    await page.evaluate((url) => new Promise<void>((resolve, reject) => {
      const socket = new WebSocket(url);
      socket.onopen = () => { socket.close(); resolve(); };
      socket.onerror = () => reject(new Error("fixture websocket failed"));
    }), origin.replace("http:", "ws:") + "/socket?token=private-fixture");
    const observations = worker.origins(identity, identity.session_id) as { items: unknown[] };
    expect(observations.items).toContainEqual(expect.objectContaining({ origin, request_kind: "websocket" }));
    expect(JSON.stringify(observations)).not.toContain("private-fixture");
    expect((await run({ kind: "wait", duration_ms: 100 })).operation.status).toBe("completed");
  } finally {
    for (const socket of sockets) socket.destroy();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});
test("before capture failure rejects without action and after failure retains actual action", async () => {
  await setup(); const context = page.context(); const original = context.newCDPSession.bind(context);
  context.newCDPSession = async () => { throw new Error("fixture capture unavailable"); };
  const rejected = await worker.prepare(command(click(340)));
  expect(rejected.operation).toMatchObject({ status: "rejected", before_unavailable_reason: "capture_failed" });
  context.newCDPSession = original;
  const prepared = await worker.prepare(command(click(340)));
  context.newCDPSession = async () => { throw new Error("fixture capture unavailable"); };
  const result = await worker.execute(executeCommand(prepared));
  expect(result.operation).toMatchObject({ status: "completed", after_unavailable_reason: "capture_failed" });
  expect(result.frames).toHaveLength(1);
  expect(await page.getByRole("button", { name: "Icon action" }).getAttribute("data-count")).toBe("1");
  context.newCDPSession = original;
});
test("browser loss during an action yields unknown and duplicate execute cannot retry", async () => {
  await setup(); const prepared = await worker.prepare(command({ kind: "wait", duration_ms: 1000 }));
  const timer = setTimeout(() => { void browser.close(); }, 100);
  const result = await worker.execute(executeCommand(prepared)); clearTimeout(timer);
  expect(result.operation.status).toBe("unknown");
  expect(result.operation.after_unavailable_reason).not.toBeNull();
  expect(await worker.execute(executeCommand(prepared))).toEqual(result);
});
test("session scope, fencing and serialization are enforced", async () => {
  const setupResult = await setup();
  expect(() => worker.read({ ...identity, tenant_id: "other" }, identity.session_id, setupResult.operation.id)).toThrow("scope_mismatch");
  expect(() => worker.read({ ...identity, project_id: randomUUID() }, identity.session_id, setupResult.operation.id)).toThrow("scope_mismatch");
  expect(() => worker.read({ ...identity, fencing_token: 2 }, identity.session_id, setupResult.operation.id)).toThrow("stale_fencing_token");
  const prepared = await worker.prepare(command({ kind: "wait", duration_ms: 300 }));
  await expect(worker.prepare(command(click(100)))).rejects.toThrow("operation_pending");
  const executing = worker.execute(executeCommand(prepared));
  await expect(worker.execute(executeCommand(prepared))).rejects.toThrow("session_busy");
  await executing;
  await expect(worker.open({ ...identity, session_id: "../escape" })).rejects.toThrow();
  await expect(worker.prepare(command({ kind: "stop" }))).rejects.toThrow();
});

test("unsupported dialog has an explicit recorded outcome", async () => {
  await setup();
  const control = page.getByRole("button", { name: "Dialog", exact: true });
  const box = (await control.boundingBox())!;
  const result = await run({ kind: "click", x: (box.x + box.width / 2) / 1279, y: (box.y + box.height / 2) / 719 });
  expect(result.operation).toMatchObject({ status: "failed", outcome_code: "dialog_unsupported" });
  expect(result.frames.map((f) => f.role)).toEqual(["before", "after"]);
});

test("same-page download is attributed to its click and cannot be replayed", async () => {
  await setup();
  const control = page.getByRole('link', { name: 'Download fixture' });
  const box = (await control.boundingBox())!;
  const download = page.waitForEvent('download');
  const result = await run({ kind: 'click', x: (box.x + box.width / 2) / 1279, y: (box.y + box.height / 2) / 719 });
  expect(result.operation).toMatchObject({ status: 'completed', outcome_code: 'download_started' });
  expect(result.operation.executed_click).not.toBeNull();
  expect(result.replayable).toBe(false);
  expect(await (await download).failure()).not.toBeNull();
});

test("download outside a dispatched click remains unsupported", async () => {
  await setup();
  const download = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Download fixture' }).click();
  expect(await (await download).failure()).not.toBeNull();
  const next = await worker.prepare(command(click(20)));
  expect(next.operation).toMatchObject({ status: 'rejected', outcome_code: 'download_unsupported' });
  expect(next.operation.executed_click).toBeNull();
});

for (const popup of [false, true]) for (const redirect of [false, true]) test(`download destination audit binds hashes to the actual click (popup=${popup}, redirect=${redirect})`, async () => {
  const destination = target.origin + '/download?private_fixture=do-not-export';
  const source = redirect ? target.origin + '/download-redirect' : destination;
  await page.route(target.origin + '/', route => route.fulfill({ contentType: 'text/html', body:
    `<a href="${source}" ${popup ? 'target="_blank"' : ''} style="display:block;width:180px;height:40px">Download</a>` }));
  await setup();
  const lines: string[] = [], original = console.log;
  console.log = (...args) => { lines.push(String(args[0])); };
  let result: OperationResult;
  try { result = await run(click(20)); } finally { console.log = original; }
  expect(result.operation).toMatchObject({ status: 'completed', outcome_code: 'download_started' });
  const records = lines.map(line => JSON.parse(line)).filter(row => row.event === 'vision.download.destinations');
  expect(records).toHaveLength(1);
  expect(records[0]).toMatchObject({ session_id: identity.session_id, operation_id: result.operation.id,
    destination_hashes: [digest(destination)], truncated: false, status: 'completed' });
  expect(records[0].navigation_chain).toEqual(redirect ? [
    { url_sha256: digest(source), redirected_from_sha256: null },
    { url_sha256: digest(destination), redirected_from_sha256: digest(source) },
  ] : [{ url_sha256: digest(destination), redirected_from_sha256: null }]);
  expect(JSON.stringify(records)).not.toContain('do-not-export');
  expect(JSON.stringify(records)).not.toContain(target.origin);
  expect(result.replayable).toBe(false);
});

test("download audit logging failure cannot change its execution verdict", async () => {
  await page.route(target.origin + '/', route => route.fulfill({ contentType: 'text/html', body:
    '<a href="/download" style="display:block;width:180px;height:40px">Download</a>' }));
  await setup();
  const original = console.log;
  console.log = () => { throw new Error('fixture logging failure'); };
  try {
    const result = await run(click(20));
    expect(result.operation).toMatchObject({ status: 'completed', outcome_code: 'download_started' });
  } finally { console.log = original; }
});

test("a background download during a wait cannot inherit click attribution", async () => {
  await setup();
  const download = page.waitForEvent('download');
  await page.evaluate(() => setTimeout(() => {
    document.querySelector<HTMLAnchorElement>('a[href="/download"]')!.click();
  }, 700));
  const result = await run({ kind: 'wait', duration_ms: 1200 });
  expect(await (await download).failure()).not.toBeNull();
  expect(result.operation).toMatchObject({ status: 'failed', outcome_code: 'download_unsupported' });
  expect(result.operation.executed_click).toBeNull();
});

test("setup waits for explicitly busy hydration and records the settled checkpoint", async () => {
  await page.route(target.origin + "/", (route) => route.fulfill({ contentType: "text/html", body: `
    <button aria-label="Loading" aria-busy="true">Loading</button><script>
      const button = document.querySelector('button');
      let count = 0;
      const timer = setInterval(() => button.setAttribute('data-changing', String(++count)), 20);
      setTimeout(() => {
        clearInterval(timer);
        button.textContent = 'Ready'; button.setAttribute('aria-label', 'Ready'); button.removeAttribute('aria-busy');
      }, 2500);
    </script>` }));
  const result = await setup();
  ledger(result, "navigate", 1);
  expect(await page.getByRole("button", { name: "Ready" }).count()).toBe(1);
  expect(result.duration_ms).toBeGreaterThanOrEqual(2500);
  expect(result.duration_ms).toBeLessThan(10_000);
  expect((await worker.checkpoint(identity, identity.session_id, result.checkpoint!.id)).matches_current).toBe(true);
});

test("setup still fails when navigation never settles and retains both frames", async () => {
  await page.route(target.origin + "/", (route) => route.fulfill({ contentType: "text/html", body: `
    <button>Loading</button><script>
      let count = 0;
      setInterval(() => document.querySelector('button').setAttribute('aria-label', 'Loading ' + ++count), 20);
    </script>` }));
  const result = await run({ kind: "navigate" }, {
    purpose: "setup", checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID(),
  });
  expect(result.operation).toMatchObject({ status: "failed", outcome_code: "settle_timeout" });
  expect(result.frames.map((frame) => frame.role)).toEqual(["before", "after"]);
  expect(result.checkpoint).toBeNull();
  expect(result.replayable).toBe(false);
  expect(result.duration_ms).toBeLessThan(13_000);
});

test("a link navigation gets time to hydrate its destination before the next checkpoint", async () => {
  await page.route(target.origin + "/a", route => route.fulfill({ contentType: "text/html", body: `
    <button aria-label="Loading" aria-busy="true">Loading</button><script>
      const button = document.querySelector('button');
      let count = 0;
      const timer = setInterval(() => button.setAttribute('data-changing', String(++count)), 20);
      setTimeout(() => {
        clearInterval(timer); button.textContent = 'Ready'; button.setAttribute('aria-label', 'Ready'); button.removeAttribute('aria-busy');
      }, 2500);
    </script>` }));
  await setup();
  const result = await run(click(40), { checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID() });
  expect(result.operation).toMatchObject({ status: "completed", url_change: "changed" });
  expect(await page.getByRole("button", { name: "Ready" }).count()).toBe(1);
  expect(result.duration_ms).toBeGreaterThanOrEqual(2500);
  expect(result.duration_ms).toBeLessThan(13_000);
  expect((await worker.checkpoint(identity, identity.session_id, result.checkpoint!.id)).matches_current).toBe(true);
});

test("scroll replay waits for lazy content and slow DOM reads before verifying its checkpoint", async () => {
  await page.route(target.origin + '/', route => route.fulfill({ contentType: 'text/html', body: `
    <style>body{margin:0;height:1500px}main{height:1500px}</style>
    <main><button style="position:absolute;left:40px;top:900px" onclick="this.dataset.clicked='yes'">Lower content</button></main>
    <script>let timer; addEventListener('scroll', () => {
      if (!scrollY) return; const main=document.querySelector('main');main.setAttribute('aria-busy','true');
      clearTimeout(timer);timer=setTimeout(()=>main.removeAttribute('aria-busy'),2200);
    });</script>` }));
  const rootState = await setup();
  const evaluate = page.evaluate.bind(page), wheel = page.mouse.wheel.bind(page.mouse);
  let slow = false, wheelCalls = 0;
  page.mouse.wheel = async (...args) => { slow = true; wheelCalls++; return wheel(...args); };
  page.evaluate = (async (...args: Parameters<Page['evaluate']>) => {
    if (slow) await new Promise(resolve => setTimeout(resolve, 600));
    return evaluate(...args);
  }) as Page['evaluate'];
  const action = { kind: 'scroll', delta_y: 576 };
  try {
    const first = await run(action, { checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID() });
    expect(first.operation.status).toBe('completed');
    expect(first.duration_ms).toBeGreaterThan(1500);
    expect(first.checkpoint?.scroll_y).toBe(576);
    slow = false;
    expect((await run({ kind: 'navigate' }, { purpose: 'restore', restore_checkpoint_id: rootState.checkpoint!.id })).operation.status).toBe('completed');
    const replay = await run(action, { purpose: 'replay', replay_operation_id: first.operation.id,
      restore_checkpoint_id: first.checkpoint!.id });
    expect(replay.operation.status).toBe('completed');
    expect(replay.frames.map(frame => frame.role)).toEqual(['before', 'after']);
    expect((await worker.checkpoint(identity, identity.session_id, first.checkpoint!.id)).matches_current).toBe(true);
    expect(wheelCalls).toBe(2);
    slow = false;
    const observation = await worker.observeDom({ ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: current });
    const lower = observation.data.observation.elements.find(element => element.name === 'Lower content')!;
    const clicked = await run({ kind: 'click', x: 0.5, y: 0.5 }, {
      dom_snapshot_id: observation.data.observation.snapshot_id, dom_element_id: lower.element_id,
    });
    expect(clicked.operation.status).toBe('completed');
    expect(await page.getByRole('button').getAttribute('data-clicked')).toBe('yes');
  } finally { page.evaluate = evaluate; page.mouse.wheel = wheel; }
});

test("scroll still fails on continuously changing controls and retains diagnostic frames", async () => {
  await setup();
  await page.evaluate(() => addEventListener('scroll', () => {
    let tick = 0; const button = document.querySelector('#hydrate')!;
    button.setAttribute('style', 'position:fixed;top:20px;left:600px');
    setInterval(() => button.setAttribute('aria-label', 'Changing ' + ++tick), 20);
  }, { once: true }));
  const result = await run({ kind: 'scroll', delta_y: 576 }, {
    checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID(),
  });
  expect(result.operation).toMatchObject({ status: 'failed', outcome_code: 'settle_timeout' });
  expect(result.checkpoint).toBeNull();
  expect(result.replayable).toBe(false);
  expect(result.frames.map(frame => frame.role)).toEqual(['before', 'after']);
  expect(result.duration_ms).toBeLessThan(13_000);
});

test("scroll readiness respects a shorter step deadline and duplicate execution cannot scroll again", async () => {
  await worker.close(identity, identity.session_id);
  identity = { ...identity, session_id: randomUUID() };
  const opened = await worker.open({ ...identity, target_url: target.origin, allowed_origins: [target.origin],
    deadline: new Date(Date.now() + 5000).toISOString(), max_session_seconds: 5, step_timeout_seconds: 5,
    max_states: 20, max_hops: 10, max_screenshot_bytes: 1_000_000 });
  current = opened.state_fingerprint; page = browser.contexts()[0].pages()[0];
  await run({ kind: 'navigate' }, { purpose: 'setup', step_deadline: new Date(Date.now() + 5000).toISOString() });
  await page.evaluate(() => addEventListener('scroll', () => {
    document.body.setAttribute('aria-busy', 'true');
  }, { once: true }));
  const wheel = page.mouse.wheel.bind(page.mouse);
  let wheelCalls = 0;
  page.mouse.wheel = async (...args) => { wheelCalls++; return wheel(...args); };
  const started = Date.now();
  const prepared = await worker.prepare(command({ kind: 'scroll', delta_y: 576 }, {
    step_deadline: new Date(started + 2000).toISOString(), checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID(),
  }));
  expect(prepared.operation.status).toBe('prepared');
  const result = await worker.execute(executeCommand(prepared));
  expect(result.operation.status).not.toBe('completed');
  expect(result.checkpoint).toBeNull();
  expect(result.replayable).toBe(false);
  expect(Date.now() - started).toBeLessThan(5000);
  expect((await worker.execute(executeCommand(prepared))).operation).toEqual(result.operation);
  expect(wheelCalls).toBe(1);
});

test("settle timeout is bounded and retains after evidence", async () => {
  await setup();
  await page.getByRole("button", { name: "No operation" }).evaluate((el) => {
    el.addEventListener("click", () => { let count = 0; setInterval(() => el.setAttribute("aria-label", 'Changing ' + ++count), 20); });
  });
  const result = await run(click(400));
  expect(result.operation).toMatchObject({ status: "failed", outcome_code: "settle_timeout" });
  expect(result.operation.executed_click?.before_frame_id).toBe(result.operation.actual_before_frame_id);
  expect(result.frames).toHaveLength(2);
  expect(result.duration_ms).toBeLessThan(5000);
});

test("confirmed click coordinates match browser input with borders, scrolling and popup", async () => {
  await setup();
  await page.evaluate(() => {
    document.addEventListener("click", (event) => {
      (window as unknown as { fixtureClick: { x: number; y: number } }).fixtureClick = { x: event.clientX, y: event.clientY };
    }, true);
  });
  const verify = async (result: OperationResult, source = page) => {
    const actual = await source.evaluate(() => (window as unknown as { fixtureClick: { x: number; y: number } }).fixtureClick);
    const recorded = result.operation.executed_click!;
    expect(recorded).not.toBeNull();
    expect(Math.abs(recorded.x * (recorded.viewport_width - 1) - actual.x)).toBeLessThan(1);
    expect(Math.abs(recorded.y * (recorded.viewport_height - 1) - actual.y)).toBeLessThan(1);
    expect(recorded.before_frame_id).toBe(result.operation.actual_before_frame_id);
    expect(recorded.before_frame_id).not.toBe(result.operation.actual_after_frame_id);
  };
  await verify(await run(click(340)));
  await run({ kind: "scroll", delta_y: 1000 });
  const box = (await page.getByRole("button", { name: "Offscreen action" }).boundingBox())!;
  await verify(await run({ kind: "click", x: (box.x + 40) / 1279, y: (box.y + 20) / 719 }));
  await run({ kind: "scroll", delta_y: -1000 });
  const popup = await run(click(220));
  await verify(popup);
  expect(popup.operation.before_page_id).not.toBe(popup.operation.after_page_id);
});

test("click metadata is absent when Playwright click itself fails", async () => {
  await setup();
  const prepared = await worker.prepare(command(click(340)));
  // Force the browser to disappear after the dispatch intent; never retry it.
  const timer = setTimeout(() => { void browser.close(); }, 1);
  const result = await worker.execute(executeCommand(prepared));
  clearTimeout(timer);
  expect(["rejected", "unknown"]).toContain(result.operation.status);
  expect(result.operation.executed_click).toBeNull();
  expect(await worker.execute(executeCommand(prepared))).toEqual(result);
});

test("checkpoint reads compare the live page including form values", async () => {
  const rootState = await setup();
  await page.getByRole("textbox").fill("runtime-only-fixture");
  const checkpoint = await worker.checkpoint(identity, identity.session_id, rootState.checkpoint!.id);
  expect(checkpoint.matches_current).toBe(false);
  expect(JSON.stringify(checkpoint)).not.toContain("runtime-only-fixture");
  const rejected = await worker.prepare(command(click(100)));
  expect(rejected.operation).toMatchObject({ status: "rejected", outcome_code: "state_mismatch" });
});

test("offscreen animation survives model latency and restores for another button after operation 3", async () => {
  await page.route(target.origin + "/", async (route) => {
    await route.fulfill({ response: await route.fetch({ url: target.origin + "/?animated=1" }) });
  });
  const rootState = await setup();
  const before = await page.locator("#carousel").textContent();
  await page.waitForTimeout(500);
  expect(await page.locator("#carousel").textContent()).not.toBe(before);
  expect((await worker.checkpoint(identity, identity.session_id, rootState.checkpoint!.id)).matches_current).toBe(true);
  ledger(await run(click(40)), "click", 2);
  ledger(await run({ kind: "back" }, { purpose: "restore", restore_checkpoint_id: rootState.checkpoint!.id }), "back", 3);
  await page.waitForTimeout(200);
  const next = await run(click(100));
  ledger(next, "click", 4);
  expect(next.locator?.descriptor?.value).toBe("Branch B");
});

test("reduced-motion exploration settles pulsing link ancestors and keeps DOM bindings through model latency", async () => {
  await page.route(target.origin + "/", async route => {
    const response = await route.fetch();
    await route.fulfill({ response, body: (await response.text()).replace("</body>", `
      <style>@keyframes pulse { from { transform: scale(0.8) } to { transform: scale(1.2) } }
      #pulse { position:absolute;left:800px;top:50px;width:150px;height:50px;animation:pulse 0.2s infinite alternate }
      @media (prefers-reduced-motion: reduce) { #pulse { animation:none } }</style>
      <div id="pulse"><a href="/b" style="display:block;width:150px;height:50px">Pulsing link</a></div></body>`) });
  });
  const rootState = await setup();
  ledger(rootState, "navigate", 1);
  expect(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(true);
  expect(await page.locator('#pulse').evaluate(el => getComputedStyle(el).animationName)).toBe('none');
  const observed = await worker.observeDom({ ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: current });
  const link = observed.data.observation.elements.find(el => el.name === 'Pulsing link')!;
  expect(link).toBeDefined();
  await page.waitForTimeout(600);
  ledger(await run({ kind: 'click', x: 0.5, y: 0.5 }, {
    dom_snapshot_id: observed.data.observation.snapshot_id, dom_element_id: link.element_id,
  }), 'click', 2);
  expect(page.url()).toBe(target.origin + '/b');
});

test("visible passive animation survives capture, DOM model latency, click and checkpoint restoration", async () => {
  await page.route(target.origin + "/", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, body: (await response.text()).replace("</body>", `
      <div id="clock" style="position:absolute;left:800px;top:20px;width:200px">Tick</div>
      <div id="passive-banner" style="position:absolute;left:800px;top:100px;width:150px;height:80px;background:red">Slide</div>
      <script>let tick = 0; setInterval(() => {
        document.querySelector('#clock').textContent = 'Tick ' + ++tick;
        document.querySelector('#passive-banner').style.transform = 'translateX(' + tick % 30 + 'px)';
        document.querySelector('#hydrate').setAttribute('data-render-counter', String(tick));
      }, 20);</script></body>`) });
  });
  const rootState = await setup();
  ledger(rootState, "navigate", 1);
  const observed = await worker.observeDom({ ...identity, snapshot_id: randomUUID(),
    expected_state_fingerprint: current, max_elements: 100, max_bytes: 48_000 });
  const branch = observed.data.observation.elements.find(el => el.name === "Branch A")!;
  const clock = await page.locator('#clock').textContent();
  await page.waitForTimeout(350);
  expect(await page.locator('#clock').textContent()).not.toBe(clock);
  expect((await worker.checkpoint(identity, identity.session_id, rootState.checkpoint!.id)).matches_current).toBe(true);
  ledger(await run({ kind: "click", x: 0.5, y: 0.5 }, {
    dom_snapshot_id: observed.data.observation.snapshot_id, dom_element_id: branch.element_id,
  }), "click", 2);
  expect(page.url()).toBe(target.origin + '/a');
  ledger(await run({ kind: "back" }, { purpose: "restore", restore_checkpoint_id: rootState.checkpoint!.id }), "back", 3);
  await page.waitForTimeout(250);
  // Candidate batches reuse bindings after a verified restore to their checkpoint.
  const nextBranch = observed.data.observation.elements.find(el => el.name === "Branch B")!;
  ledger(await run({ kind: "click", x: 0.5, y: 0.5 }, {
    dom_snapshot_id: observed.data.observation.snapshot_id, dom_element_id: nextBranch.element_id,
  }), "click", 4);
  expect(page.url()).toBe(target.origin + '/b');
});

for (const drift of ["move", "cover", "disable"] as const) {
  test(`target ${drift} after prepare prevents every physical click`, async () => {
    await setup();
    await page.getByRole('button', { name: 'No operation', exact: true }).evaluate(el => {
      el.addEventListener('click', () => { el.setAttribute('data-physical-click', 'yes'); });
    });
    const prepared = await worker.prepare(command(click(400)));
    expect(prepared.operation.status).toBe('prepared');
    await page.getByRole('button', { name: 'No operation', exact: true }).evaluate((el, change) => {
      if (change === 'move') (el as HTMLElement).style.transform = 'translateX(100px)';
      if (change === 'disable') (el as HTMLButtonElement).disabled = true;
      if (change === 'cover') {
        const overlay = document.createElement('div');
        overlay.style.cssText = 'position:fixed;inset:0;z-index:10000;background:white';
        document.body.append(overlay);
      }
    }, drift);
    const result = await worker.execute(executeCommand(prepared));
    expect(result.operation).toMatchObject({ status: 'rejected', outcome_code: 'state_mismatch', executed_click: null });
    expect(await page.getByRole('button', { name: 'No operation', exact: true }).getAttribute('data-physical-click')).toBeNull();
    expect(await worker.execute(executeCommand(prepared))).toEqual(result);
  });
}

for (const change of ["move", "overlay", "offscreen_form", "iframe", "accessible_name"] as const) {
  test(`checkpoint still rejects ${change} drift before clicking`, async () => {
    const visitsBefore = target.visits.get("/b") ?? 0;
    if (change === "accessible_name" || change === "offscreen_form") {
      await page.route(target.origin + "/", async (route) => {
        const response = await route.fetch();
        await route.fulfill({ response, body: (await response.text()).replace("</body>",
          (change === "accessible_name"
            ? '<span id="hidden-label" hidden>Original name</span><button aria-labelledby="hidden-label">Named</button>'
            : '<input id="offscreen-form" style="position:absolute;top:1600px" value="seed">') + '</body>') });
      });
    }
    const rootState = await setup();
    if (change === "move") await page.getByRole("link", { name: "Branch B", exact: true }).evaluate((el) => {
      (el as HTMLElement).style.transform = "translateX(200px)";
    });
    else if (change === "overlay") await page.evaluate(() => {
      const overlay = document.createElement("div");
      overlay.style.cssText = "position:fixed;inset:0;z-index:1000;background:white";
      document.body.append(overlay);
    });
    else if (change === "offscreen_form") await page.locator("#offscreen-form").evaluate((el) => {
      (el as HTMLInputElement).value = "private-offscreen-value";
    });
    else if (change === "iframe") await page.frameLocator("#embedded").getByRole("button").evaluate((el) => { el.textContent = "Changed"; });
    else await page.locator("#hidden-label").evaluate((el) => { el.textContent = "Different name"; });
    const checkpoint = await worker.checkpoint(identity, identity.session_id, rootState.checkpoint!.id);
    expect(checkpoint.matches_current).toBe(false);
    const result = await worker.prepare(command(click(100)));
    expect(result.operation).toMatchObject({ status: "rejected", outcome_code: "state_mismatch" });
    expect(target.visits.get("/b") ?? 0).toBe(visitsBefore);
    expect(JSON.stringify(result)).not.toContain("private-offscreen-value");
  });
}

test("explicit twenty-hop session dispatches twenty actions and blocks the next", async () => {
  test.setTimeout(90_000);
  await worker.close(identity, identity.session_id);
  identity = { ...identity, session_id: randomUUID() };
  const opened = await worker.open({ ...identity, target_url: target.origin, allowed_origins: [target.origin],
    deadline: new Date(Date.now() + 60_000).toISOString(), max_session_seconds: 60,
    max_states: 100, max_hops: 20, max_screenshot_bytes: 1_000_000 });
  current = opened.state_fingerprint;
  page = browser.contexts()[0].pages()[0];
  await page.route(target.origin + '/', route => route.fulfill({ contentType: 'text/html',
    body: '<button style="position:absolute;left:20px;top:20px;width:200px;height:60px" onclick="this.dataset.count=String(Number(this.dataset.count||0)+1)">Count</button>' }));
  await setup();
  for (let i = 0; i < 20; i++) {
    const action = await run(click(40));
    expect(action.operation.status).toBe("completed");
  }
  const rejected = await worker.prepare(command(click(40)));
  expect(rejected.operation).toMatchObject({ status: "rejected", outcome_code: "hop_limit" });
  expect(rejected.dispatch_started).toBe(false);
  expect(await page.locator('button').getAttribute('data-count')).toBe('20');
});

test("state/hop and derived operation caps reject before another browser action", async () => {
  await worker.close(identity, identity.session_id);
  identity = { ...identity, session_id: randomUUID() };
  const opened = await worker.open({ ...identity, target_url: target.origin, allowed_origins: [target.origin],
    deadline: new Date(Date.now() + 60_000).toISOString(), max_session_seconds: 60,
    max_states: 1, max_hops: 1, max_screenshot_bytes: 1_000_000 });
  current = opened.state_fingerprint; await setup();
  expect(opened.operation_budget).toBe(6);
  const blocked = await worker.prepare(command(click(100)));
  expect(blocked.operation).toMatchObject({ status: "rejected", outcome_code: "state_limit" });
  for (let i = 0; i < 4; i++) await worker.prepare(command(click(100)));
  await expect(worker.prepare(command(click(100)))).rejects.toThrow("operation_budget_exhausted");
  await worker.close(identity, identity.session_id);
  identity = { ...identity, session_id: randomUUID() };
  const next = await worker.open({ ...identity, target_url: target.origin, allowed_origins: [target.origin],
    deadline: new Date(Date.now() + 60_000).toISOString(), max_session_seconds: 60,
    max_states: 3, max_hops: 1, max_screenshot_bytes: 1_000_000 });
  current = next.state_fingerprint; await setup(); await run(click(400));
  const hop = await worker.prepare(command(click(100)));
  expect(hop.operation).toMatchObject({ status: "rejected", outcome_code: "hop_limit" });
});
test("deadline expires idle browser, preserves records and makes checkpoints unavailable", async () => {
  const setupResult = await setup();
  await worker.close(identity, identity.session_id);
  identity = { ...identity, session_id: randomUUID() };
  const opened = await worker.open({ ...identity, target_url: target.origin, allowed_origins: [target.origin],
    deadline: new Date(Date.now() + 1200).toISOString(), max_session_seconds: 2,
    max_states: 1, max_hops: 1, max_screenshot_bytes: 1024 });
  current = opened.state_fingerprint;
  const result = await worker.prepare(command({ kind: "navigate" }, { purpose: "setup" }));
  expect(result.operation).toMatchObject({ status: "rejected", outcome_code: "screenshot_byte_limit" });
  await new Promise((resolve) => setTimeout(resolve, 1250));
  expect(worker.read(identity, identity.session_id, result.operation.id).operation.status).toBe("rejected");
  await expect(worker.checkpoint(identity, identity.session_id, setupResult.checkpoint!.id)).rejects.toThrow("checkpoint_unavailable");
  await expect(worker.prepare(command(click(100)))).rejects.toThrow("session_timeout");
});
test("HTTP endpoints require secret, scoped identity, bounded body and matching path IDs", async () => {
  const handler = visualHttpHandler(root, () => "fixture-worker-secret");
  const server = createServer((req, res) => { void handler(req, res); });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const url = `http://127.0.0.1:${(server.address() as AddressInfo).port}/visual-explorations`;
  const headers = { "x-auto-at-vision-worker-secret": "fixture-worker-secret", "content-type": "application/json" };
  const scopeHeaders = { ...headers, "x-auto-at-vision-tenant-id": identity.tenant_id,
    "x-auto-at-vision-project-id": identity.project_id, "x-auto-at-vision-fencing-token": "1" };
  try {
    expect((await fetch(url, { method: "POST", body: "{}" })).status).toBe(401);
    expect((await fetch(url, { method: "POST", headers, body: "x".repeat(65537) })).status).toBe(413);
    const open = await fetch(url, { method: "POST", headers, body: JSON.stringify({ ...identity,
      target_url: target.origin, allowed_origins: [target.origin], deadline: new Date(Date.now() + 60_000).toISOString(),
      max_session_seconds: 60, max_states: 2, max_hops: 1, max_screenshot_bytes: 1_000_000 }) });
    expect(open.status).toBe(200); const opened = await open.json();
    expect((await fetch(`${url}/${identity.session_id}/origins`, { headers })).status).toBe(422);
    const origins = await fetch(`${url}/${identity.session_id}/origins`, { headers: scopeHeaders });
    expect(origins.status).toBe(200);
    expect(await origins.json()).toMatchObject({ ...identity, items: [], truncated: false });
    const prepare = await fetch(`${url}/${identity.session_id}/operations/prepare`, { method: "POST", headers,
      body: JSON.stringify(command({ kind: "navigate" }, { purpose: "setup", expected_state_fingerprint: opened.state_fingerprint })) });
    expect(prepare.status).toBe(200); const prepared = await prepare.json() as OperationResult;
    const opUrl = `${url}/${identity.session_id}/operations/${prepared.operation.id}`;
    expect((await fetch(opUrl, { headers })).status).toBe(422);
    expect((await fetch(opUrl, { headers: scopeHeaders })).status).toBe(200);
    expect((await fetch(`${opUrl}/frames/${prepared.frames[0].id}`, { headers: scopeHeaders })).status).toBe(200);
    expect((await fetch(`${opUrl}/execute`, { method: "POST", headers, body: JSON.stringify({ ...executeCommand(prepared), operation_id: randomUUID() }) })).status).toBe(422);
    expect((await fetch(`${url}/${identity.session_id}/actions`, { method: "POST", headers, body: '{"action":{"kind":"stop"}}' })).status).toBe(422);
    expect((await fetch(`${opUrl}/execute`, { method: "POST", headers, body: JSON.stringify(executeCommand(prepared)) })).status).toBe(200);
    expect((await fetch(`${url}/${identity.session_id}`, { method: "DELETE", headers: scopeHeaders })).status).toBe(200);
  } finally { server.closeAllConnections(); await new Promise<void>((resolve) => server.close(() => resolve())); }
});
