import { randomUUID } from "node:crypto";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium, expect, test, type Browser, type Page } from "@playwright/test";
import { equivalentState, inspectState, isPresentationOnlyAnimated, settleState } from "./vision-checkpoints.js";
import { visionLogScope } from "./vision-observability.js";
import { VisualOperationWorker } from "./vision-operations.js";
import { startVisionTarget } from "./fixtures/vision-target.js";
import { carouselHtml, leftAnimationHtml, marqueeTranslateHtml, pulsingControlHtml, spinFadeHtml, staticControlHtml, strongPulseHtml, widthAnimationHtml } from "./fixtures/settle-animated-control.js";

// QA r14 (plan 09112026103202, phase 04): adversarial boundaries of the ADR 042 settle tolerance. Local fixtures only.

async function settleWithLog(page: Page, windowMs: number, quietMs: number) {
  const lines: string[] = [], original = console.error;
  console.error = (line: string) => lines.push(line);
  try {
    const result = await visionLogScope.run({ context: {}, fields: { session_id: "qa", operation_id: "qa", stage: "operation_execute" } },
      () => settleState(page, Date.now() + windowMs, quietMs));
    return { result, log: lines.length ? JSON.parse(lines[0]) : null };
  } finally { console.error = original; }
}
const seek = (page: Page, ms: number) => page.evaluate((time) => document.getAnimations().forEach(a => { a.pause(); a.currentTime = time; }), ms);
async function pair(page: Page, mutate: () => Promise<unknown>) {
  const before = await inspectState(page, true);
  const unchanged = equivalentState(before, await inspectState(page, true));
  await mutate();
  return { unchanged, equivalent: equivalentState(before, await inspectState(page, true)) };
}
const html = (body: string, style = "") => `<!doctype html><meta charset="utf-8"><style>body{margin:0;font:14px sans-serif}${style}</style>${body}`;
const setBox = (page: Page, css: string) => page.evaluate((text) => { (document.querySelector(".widget") as HTMLElement).style.cssText += text; }, css);

test("QA-B1 centre shift of exactly 3 px is equivalent on each axis, 4 px is not", async ({ page }) => {
  for (const [axis, key] of [["x", "left"], ["y", "top"]] as const) {
    const base = key === "left" ? 600 : 300;
    await page.setContent(staticControlHtml);
    expect(await pair(page, () => setBox(page, `${key}:${base + 3}px`)), `${axis} 3px`).toEqual({ unchanged: true, equivalent: true });
    await page.setContent(staticControlHtml);
    expect(await pair(page, () => setBox(page, `${key}:${base + 4}px`)), `${axis} 4px`).toEqual({ unchanged: true, equivalent: false });
    await page.setContent(staticControlHtml);
    expect(await pair(page, () => setBox(page, `${key}:${base - 4}px`)), `${axis} -4px`).toEqual({ unchanged: true, equivalent: false });
  }
});

test("QA-B2 IoU of exactly 0.8 is equivalent, 0.787 is not (same centre)", async ({ page }) => {
  const wide = (w: number) => html(`<div class="widget"><a href="#p" aria-label="Play now"></a></div>`,
    `.widget{position:absolute;left:600px;top:300px;width:${w}px;height:72px}.widget a{position:absolute;inset:0;display:block}`);
  // 200 -> 250 keeps the centre (shift 25): IoU 0.8. 200 -> 254 (shift 27): IoU 0.787.
  await page.setContent(wide(200));
  expect(await pair(page, () => setBox(page, "left:575px;width:250px"))).toEqual({ unchanged: true, equivalent: true });
  await page.setContent(wide(200));
  expect(await pair(page, () => setBox(page, "left:573px;width:254px"))).toEqual({ unchanged: true, equivalent: false });
  // Shrinking is symmetric.
  await page.setContent(wide(250));
  expect(await pair(page, () => setBox(page, "left:625px;width:200px"))).toEqual({ unchanged: true, equivalent: true });
});

test("QA-D1 slow drift of 1 px per 40 ms is not settled", async ({ page }) => {
  await page.setContent(staticControlHtml);
  await page.evaluate(() => { const el = document.querySelector(".widget") as HTMLElement; let left = 600;
    setInterval(() => { left += 1; el.style.left = `${left}px`; }, 40); });
  const { result, log } = await settleWithLog(page, 2500, 800);
  expect(result.settled).toBe(false);
  expect(log).toMatchObject({ reason: "state_kept_changing" });
});

test("QA-D2 drift that stops inside 3 px of the reference still settles; drift that stops beyond 3 px resets the window", async ({ page }) => {
  await page.setContent(staticControlHtml);
  await page.evaluate(() => { const el = document.querySelector(".widget") as HTMLElement; let n = 0;
    const t = setInterval(() => { el.style.left = `${600 + ++n}px`; if (n >= 2) clearInterval(t); }, 40); });
  expect((await settleWithLog(page, 3000, 800)).result.settled).toBe(true);
  await page.setContent(staticControlHtml);
  await page.evaluate(() => { const el = document.querySelector(".widget") as HTMLElement; let n = 0;
    const t = setInterval(() => { el.style.left = `${600 + ++n}px`; if (n >= 10) clearInterval(t); }, 40); });
  const { result, log } = await settleWithLog(page, 3500, 800);
  expect(result.settled).toBe(true); // the walk ended, then 800 ms of calm: the reference was reset at the moved place
  expect(log).toBeNull();
});

test("QA-S1 two controls with the same label swapping places are a change", async ({ page }) => {
  await page.setContent(html(`<button id="a" style="position:absolute;left:50px;top:50px;width:100px;height:40px">Play</button>
    <button id="b" style="position:absolute;left:400px;top:50px;width:100px;height:40px">Play</button>`));
  expect(await pair(page, () => page.evaluate(() => { document.getElementById("a")!.style.left = "400px"; document.getElementById("b")!.style.left = "50px"; })))
    .toEqual({ unchanged: true, equivalent: false });
});

test("QA-S2 list reorder (DOM order swapped, same labels and different labels) is a change", async ({ page }) => {
  const items = (labels: string[]) => html(`<ul style="margin:0;padding:0;list-style:none">${labels.map((l, i) =>
    `<li><a href="#${l}-${i}" style="display:block;height:30px;width:200px">${l}</a></li>`).join("")}</ul>`);
  await page.setContent(items(["One", "Two", "Three"]));
  expect(await pair(page, () => page.evaluate(() => { const ul = document.querySelector("ul")!; ul.append(ul.firstElementChild!); })))
    .toEqual({ unchanged: true, equivalent: false });
  await page.setContent(html(`<ul style="margin:0;padding:0;list-style:none"><li><a href="#x" style="display:block;height:30px;width:200px">Same</a></li>
    <li><a href="#x" style="display:block;height:30px;width:200px">Same</a></li></ul><button style="position:absolute;top:200px">Go</button>`));
  // identical twins reordered is indistinguishable by construction; adding a label difference must be seen
  expect(await pair(page, () => page.evaluate(() => { document.querySelector("li:last-child a")!.textContent = "Other"; })))
    .toEqual({ unchanged: true, equivalent: false });
});

test("QA-O1 a new same-label control covering the pulsing one is a change", async ({ page }) => {
  await page.setContent(pulsingControlHtml);
  await seek(page, 0);
  expect(await pair(page, () => page.evaluate(() => document.body.insertAdjacentHTML("beforeend",
    '<a href="#play" aria-label="Play now" style="position:absolute;left:600px;top:300px;width:94px;height:72px;display:block;z-index:9"></a>'))))
    .toEqual({ unchanged: true, equivalent: false });
});

test("QA-O2 an invisible full-page overlay (opacity 0, captures pointer) over the pulse is a change", async ({ page }) => {
  await page.setContent(pulsingControlHtml);
  await seek(page, 0);
  expect(await pair(page, () => page.evaluate(() => document.body.insertAdjacentHTML("beforeend",
    '<div style="position:fixed;inset:0;opacity:0;z-index:99;background:#000"></div>'))))
    .toEqual({ unchanged: true, equivalent: false });
});

test("QA-O3 pulse and relabel at the same time is a change", async ({ page }) => {
  for (const html of [pulsingControlHtml, strongPulseHtml]) {
    await page.setContent(html);
    await seek(page, 0);
    const before = await inspectState(page, true);
    await seek(page, 600);
    await page.evaluate(() => document.querySelector("a")!.setAttribute("aria-label", "Stop now"));
    expect(equivalentState(before, await inspectState(page, true))).toBe(false);
  }
});

test("QA-M1 a marquee/swiper translate animation (infinite, links) is not exempt: not equivalent and not settled", async ({ page }) => {
  const marquee = html(`<div style="position:absolute;top:100px;left:0;width:400px;overflow:hidden"><div class="track">
    <a href="#a" style="display:inline-block;width:150px">Alpha</a><a href="#b" style="display:inline-block;width:150px">Beta</a><a href="#c" style="display:inline-block;width:150px">Gamma</a></div></div>`,
    `.track{white-space:nowrap;width:max-content;animation:m 2s linear infinite}@keyframes m{from{transform:translateX(0)}to{transform:translateX(-200px)}}`);
  await page.setContent(marquee);
  await seek(page, 0);
  const base = await inspectState(page, true);
  await seek(page, 1000);
  expect(equivalentState(base, await inspectState(page, true))).toBe(false);
  await page.setContent(marquee);
  const { result, log } = await settleWithLog(page, 2500, 800);
  expect(result.settled).toBe(false);
  expect(log).toMatchObject({ reason: "state_kept_changing" });
});

test("QA-M2 a pulsing control inside a script-driven translated wrapper is not exempt", async ({ page }) => {
  await page.setContent(html(`<div id="w" style="position:absolute;left:0;top:0;transform:translateX(0)"><div class="widget"><a href="#p" aria-label="Play now"></a></div></div>`,
    `.widget{position:absolute;left:600px;top:300px;width:94px;height:72px;animation:p 1.2s ease-in-out infinite}.widget a{position:absolute;inset:0;display:block}
     @keyframes p{0%,100%{transform:scale(1)}50%{transform:scale(1.06)}}`));
  await seek(page, 0);
  expect(await pair(page, () => page.evaluate(() => { document.getElementById("w")!.style.transform = "translateX(-40px)"; })))
    .toEqual({ unchanged: true, equivalent: false });
});

test("QA-A1 an infinite opacity animation on the control itself is exempt and settles", async ({ page }) => {
  const fade = html(`<button class="widget" style="position:absolute;left:100px;top:100px;width:120px;height:40px">Buy</button>`,
    `.widget{animation:f 1s ease-in-out infinite}@keyframes f{0%,100%{opacity:1}50%{opacity:.5}}`);
  await page.setContent(fade);
  await seek(page, 0);
  const base = await inspectState(page, true);
  await seek(page, 500);
  expect(equivalentState(base, await inspectState(page, true))).toBe(true);
  await page.setContent(fade);
  expect((await settleWithLog(page, 4000, 800)).result.settled).toBe(true);
});

test("QA-A2 an animation that stops half way settles, and the stopped state matches the quiet one", async ({ page }) => {
  await page.setContent(pulsingControlHtml);
  await page.evaluate(() => setTimeout(() => document.getAnimations().forEach(a => a.pause()), 700));
  const { result } = await settleWithLog(page, 4000, 800);
  expect(result.settled).toBe(true);
  const stopped = await inspectState(page, true);
  expect(equivalentState(result.state, stopped)).toBe(true);
  await page.evaluate(() => document.getAnimations().forEach(a => a.cancel()));
  expect(equivalentState(stopped, await inspectState(page, true))).toBe(true);
});

test("QA-N1 a page without any animation behaves as before: exact fingerprint, settles at once", async ({ page }) => {
  await page.setContent(html(`<button>One</button><a href="#x">Two</a><input aria-label="Name">`));
  const a = await inspectState(page, true), b = await inspectState(page, true);
  expect(a.fingerprint).toBe(b.fingerprint);
  expect(equivalentState(a, b)).toBe(true);
  const { result, log } = await settleWithLog(page, 3000, 400);
  expect(result.settled).toBe(true);
  expect(log).toBeNull();
  await page.evaluate(() => { document.querySelector("input")!.value = "typed"; });
  expect(equivalentState(a, await inspectState(page, true))).toBe(false);
});

test("QA-P0 root cause of QA-P1: Playwright refuses a plain click on an infinitely pulsing control (not stable)", async ({ page }) => {
  await page.setContent(pulsingControlHtml);
  await expect(page.locator(".widget a").click({ timeout: 1500 })).rejects.toThrow(/not stable|Timeout/);
  await page.locator(".widget a").click({ timeout: 1500, force: true });
});

// prepare -> execute while the target itself pulses: the click must reach the exact node.
test.describe("prepare then dispatch on a pulsing target", () => {
  let target: Awaited<ReturnType<typeof startVisionTarget>>, worker: VisualOperationWorker, root: string, browser: Browser;
  test.beforeAll(async () => { target = await startVisionTarget(); });
  test.afterAll(async () => { await target.close(); });
  // QA-P1 (r14b): dispatch clicks a target under an eligible infinite pulse with `force` (ADR 042).
  test("QA-P1 click lands on the pulsing node after the page kept animating between prepare and execute", async () => {
    root = await mkdtemp(join(tmpdir(), "auto-at-vision-qa-r14-"));
    worker = new VisualOperationWorker(root, async (options) => { browser = await chromium.launch(options); return browser; });
    const identity = { contract_version: "v4", tenant_id: "fixture-tenant", project_id: randomUUID(), session_id: randomUUID(), fencing_token: 1 } as const;
    try {
      const opened = await worker.open({ ...identity, target_url: target.origin, allowed_origins: [target.origin],
        deadline: new Date(Date.now() + 60_000).toISOString(), max_session_seconds: 60, max_states: 20, max_hops: 10, max_screenshot_bytes: 1_000_000 });
      let current = opened.state_fingerprint;
      const page = browser.contexts()[0].pages()[0];
      await page.route(target.origin + "/", route => route.fulfill({ contentType: "text/html", body: pulsingControlHtml.replace('<a href="#play"',
        `<a href="#play" onclick="event.preventDefault();this.dataset.clicked=(Number(this.dataset.clicked||0)+1);this.setAttribute('aria-label','Played')"`) }));
      const command = (action: object, extra: object = {}) => ({ ...identity, operation_id: randomUUID(), purpose: "explore", action,
        expected_state_fingerprint: current, state_id: randomUUID(), proposal_id: randomUUID(), ...extra });
      const exec = (p: Awaited<ReturnType<typeof worker.prepare>>) => { const before = p.frames.find(f => f.role === "before")!;
        return { ...identity, operation_id: p.operation.id, prepared_handle: p.prepared_handle, before_persisted: true, before_frame_id: before.id, before_checksum: before.checksum }; };
      // navigate as setup, as the operations spec does
      const nav =await worker.prepare(command({ kind: "navigate" }, { purpose: "setup", checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID() }));
      expect(nav.operation.status, nav.operation.outcome_code ?? "").toBe("prepared");
      const done = await worker.execute(exec(nav));
      expect(done.operation.status, done.operation.outcome_code ?? "").toBe("completed");
      current = done.state_fingerprint ?? current;
      const prepared = await worker.prepare(command({ kind: "click", x: 647 / 1279, y: 336 / 719 }));
      expect(prepared.operation.status, prepared.operation.outcome_code ?? "").toBe("prepared");
      await page.waitForTimeout(700); // the pulse moves on between prepare and execute
      const result = await worker.execute(exec(prepared));
      expect(result.operation.status, result.operation.outcome_code ?? "").toBe("completed");
      expect(await page.locator(".widget a").getAttribute("data-clicked")).toBe("1");
    } finally {
      if (worker.hasSession(identity.session_id)) await worker.close(identity, identity.session_id);
      await rm(root, { recursive: true, force: true });
    }
  });
});

// r14b: observe -> prepare -> execute on a pulsing control, and the limits of the dispatch `force`.
const clickable = (html: string) => html.replace('<a href="#play"',
  `<a href="#play" onclick="event.preventDefault();this.dataset.clicked=(Number(this.dataset.clicked||0)+1)"`);
test("force is only decided for presentation-only infinite animations", async ({ page }) => {
  const forced = async (html: string) => { await page.setContent(html); return isPresentationOnlyAnimated(
    (await page.locator(".widget a").first().elementHandle())!); };
  expect(await forced(pulsingControlHtml)).toBe(true);
  expect(await forced(strongPulseHtml)).toBe(true);
  expect(await forced(spinFadeHtml)).toBe(true);
  expect(await forced(staticControlHtml)).toBe(false);
  expect(await forced(marqueeTranslateHtml)).toBe(false);
  expect(await forced(leftAnimationHtml)).toBe(false);
  expect(await forced(widthAnimationHtml)).toBe(false);
  // eligible animation, but another control covers the click point: no force
  await page.setContent(strongPulseHtml.replace("</style>",
    "</style><div style='position:fixed;left:560px;top:270px;width:200px;height:150px;z-index:9'></div>"));
  const link = (await page.locator(".widget a").elementHandle())!;
  expect(await isPresentationOnlyAnimated(link)).toBe(false);
  expect(await isPresentationOnlyAnimated(link, { x: 100, y: 100 })).toBe(false);
  await page.setContent(carouselHtml);
  expect(await isPresentationOnlyAnimated((await page.locator("a[href='#s1']").elementHandle())!)).toBe(false);
});

test.describe("observe, prepare, execute on the pulse fixture (r14b)", () => {
  let target: Awaited<ReturnType<typeof startVisionTarget>>, worker: VisualOperationWorker, root: string, browser: Browser;
  test.beforeAll(async () => { target = await startVisionTarget(); });
  test.afterAll(async () => { await target.close(); });
  type Worker = VisualOperationWorker; type Observed = Awaited<ReturnType<Worker["observeDom"]>>; type Prepared = Awaited<ReturnType<Worker["prepare"]>>;
  type Api = { page: Page; expected: () => string; observeWith: (expected: string) => Promise<Observed>; proposeWith: (o: Observed, expected: string) => Promise<Prepared>; observe: () => Promise<Observed>; propose: (o: Observed) => Promise<Prepared>; execute: (p: Prepared) => Promise<Prepared> };
  async function session(html: string, run: (api: Api) => Promise<void>, navigates = true) {
    root = await mkdtemp(join(tmpdir(), "auto-at-vision-qa-r14b-"));
    worker = new VisualOperationWorker(root, async (options) => { browser = await chromium.launch(options); return browser; });
    const identity = { contract_version: "v4", tenant_id: "fixture-tenant", project_id: randomUUID(), session_id: randomUUID(), fencing_token: 1 } as const;
    try {
      const opened = await worker.open({ ...identity, agent_mode: true, target_url: target.origin, allowed_origins: [target.origin],
        deadline: new Date(Date.now() + 90_000).toISOString(), max_session_seconds: 90, max_states: 20, max_hops: 10, max_screenshot_bytes: 1_000_000 });
      let current = opened.state_fingerprint;
      const page = browser.contexts()[0].pages()[0];
      await page.route(target.origin + "/", route => route.fulfill({ contentType: "text/html", body: html }));
      const command = (action: object, extra: object = {}) => ({ ...identity, operation_id: randomUUID(), purpose: "explore", action,
        expected_state_fingerprint: current, state_id: randomUUID(), proposal_id: randomUUID(), ...extra });
      const execute = async (p: Awaited<ReturnType<typeof worker.prepare>>) => { const before = p.frames.find(f => f.role === "before")!;
        const r = await worker.execute({ ...identity, operation_id: p.operation.id, prepared_handle: p.prepared_handle,
          before_persisted: true, before_frame_id: before.id, before_checksum: before.checksum }); current = r.state_fingerprint ?? current; return r; };
      const nav = await worker.prepare(command({ kind: "navigate" }, { purpose: "setup", checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID() }));
      expect(nav.operation.status, nav.operation.outcome_code ?? "").toBe("prepared");
      const navigated = await execute(nav);
      if (navigates) expect(navigated.operation.status).toBe("completed"); // a marquee never settles: setup itself fails there
      const proposeAs = (observed: Observed, expected: string) => { const el = observed.data.observation.elements.find((item: { name: string }) => item.name === "Play now");
        return worker.prepare(command({ kind: "click", x: 0.5, y: 0.5 }, { expected_state_fingerprint: expected,
          dom_snapshot_id: observed.data.observation.snapshot_id, dom_element_id: el!.element_id })); };
      await run({ page, execute, expected: () => current, proposeWith: proposeAs,
        observeWith: (expected) => worker.observeDom({ ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: expected }),
        observe: () => worker.observeDom({ ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: current }),
        propose: (observed) => { const el = observed.data.observation.elements.find((item: { name: string }) => item.name === "Play now");
          return worker.prepare(command({ kind: "click", x: 0.5, y: 0.5 }, { dom_snapshot_id: observed.data.observation.snapshot_id, dom_element_id: el!.element_id })); } });
    } finally {
      if (worker.hasSession(identity.session_id)) await worker.close(identity, identity.session_id);
      await rm(root, { recursive: true, force: true });
    }
  }

  test("a strong pulse never ends in state_mismatch across observe, prepare and a forced click", async () => {
    test.setTimeout(60_000);
    await session(clickable(strongPulseHtml), async ({ page, observe, propose, execute }) => {
      for (let round = 1; round <= 3; round++) {
        const observed = await observe();
        await page.waitForTimeout(450); // the pulse keeps moving between observe and prepare
        const prepared = await propose(observed);
        expect(prepared.operation.status, prepared.operation.outcome_code ?? "").toBe("prepared");
        await page.waitForTimeout(450);
        const done = await execute(prepared);
        expect(done.operation.status, done.operation.outcome_code ?? "").toBe("completed");
        expect(await page.locator(".widget a").getAttribute("data-clicked")).toBe(String(round));
      }
    });
  });

  test("a pulse target covered by another control is never forced: the link itself is not clicked", async () => {
    // DOM mode grounds the click by coordinates (existing behaviour), so the visible cover is what receives it;
    // the pulsing link underneath must not be clicked through it by `force`.
    const covered = clickable(strongPulseHtml).replace("</style>",
      "</style><div id=cover onclick=\"document.body.dataset.cover='1'\" style=\"position:fixed;left:560px;top:270px;width:200px;height:150px;z-index:9;cursor:pointer\"></div>");
    await session(covered, async ({ page, observe, propose, execute }) => {
      const observed = await observe();
      const prepared = await propose(observed);
      if (prepared.operation.status === "prepared") await execute(prepared);
      expect(await page.locator(".widget a").getAttribute("data-clicked")).toBeNull();
    });
  });

  test("a marquee translate target is not eligible and is never clicked by force", async () => {
    await session(clickable(marqueeTranslateHtml), async ({ page, observe, propose, execute }) => {
      const observed = await observe().catch(() => null);
      const prepared = observed ? await propose(observed).catch(() => null) : null;
      const done = prepared?.operation.status === "prepared" ? await execute(prepared) : prepared;
      expect(done?.operation.status ?? "absent").not.toBe("completed");
      expect(await page.locator(".widget a").getAttribute("data-clicked")).toBeNull();
    }, false);
  });

  // r14b QA r2: the baseline is the held state; a slow drift must not be absorbed round after round.
  test("pulse drifting 1 px per round is tolerated up to 3 px of the held state, then caught (no baseline creep)", async () => {
    test.setTimeout(60_000);
    await session(clickable(strongPulseHtml), async ({ page, observe, observeWith, expected }) => {
      const first = await observe();
      const held = first.data.observation.state_fingerprint;
      const rejected: number[] = [];
      for (let shift = 1; shift <= 6; shift++) {
        await page.evaluate((px) => { (document.querySelector(".widget") as HTMLElement).style.left = `${600 + px}px`; }, shift);
        await page.waitForTimeout(300);
        const outcome: Observed | Error = await observe().then(o => o, (error: unknown) => error as Error);
        if (outcome instanceof Error) rejected.push(shift);
        else expect(outcome.data.observation.state_fingerprint, `shift ${shift}`).toBe(held); // identity stays the held hash
      }
      expect(rejected[0], `rejected at shifts ${rejected}`).toBeLessThanOrEqual(4);
      expect(rejected).toEqual([rejected[0], ...[5, 6].filter(n => n > rejected[0])]); // once beyond tolerance it stays rejected
      expect(expected()).toBe(held);
      // prepare on a stale (pre-drift) snapshot is rejected as well; a fresh observe at the drifted spot cannot re-baseline it
      await expect(observeWith(held)).rejects.toThrow();
    });
  });

  test("a pulse whose control moves 1 px between rounds: prepare is rejected once the cumulative shift exceeds tolerance", async () => {
    test.setTimeout(60_000);
    await session(clickable(strongPulseHtml), async ({ page, observe, propose }) => {
      const observed = await observe();
      await page.evaluate(() => { (document.querySelector(".widget") as HTMLElement).style.left = "601px"; });
      const ok = await propose(observed);
      expect(ok.operation.status, ok.operation.outcome_code ?? "").toBe("prepared"); // 1 px: inside tolerance
      await page.evaluate(() => { (document.querySelector(".widget") as HTMLElement).style.left = "610px"; });
      const observed2 = await observe().then(o => o, (error: unknown) => error);
      expect(observed2 instanceof Error, "10 px shift must not be absorbed").toBe(true);
    });
  });

  test("an expected fingerprint that is not the held one is still a state_mismatch (observe and prepare)", async () => {
    await session(clickable(strongPulseHtml), async ({ observe, observeWith, proposeWith, expected }) => {
      const flip = (hash: string) => hash.slice(0, -1) + (hash.endsWith("0") ? "1" : "0"); // same shape, different hash
      await expect(observeWith(flip(expected()))).rejects.toThrow(/state_mismatch/);
      const observed = await observe();
      const wrong = await proposeWith(observed, flip(expected())).then(p => p, (error: unknown) => error);
      const text = wrong instanceof Error ? wrong.message : `${(wrong as { operation: { status: string; outcome_code?: string } }).operation.status}:${(wrong as { operation: { outcome_code?: string } }).operation.outcome_code}`;
      expect(text).toMatch(/state_mismatch/);
      const good = await proposeWith(observed, expected());
      expect(good.operation.status).toBe("prepared");
    });
  });
});

test("force is not decided for transition, translate or Element.animate targets", async ({ page }) => {
  const eligible = async () => isPresentationOnlyAnimated((await page.locator(".widget a").first().elementHandle())!);
  await page.setContent(strongPulseHtml);
  expect(await eligible()).toBe(true);
  // Element.animate (script-driven, infinite scale): not a CSS animation, so never exempt
  await page.setContent(staticControlHtml);
  await page.evaluate(() => document.querySelector(".widget")!.animate([{ transform: "scale(1)" }, { transform: "scale(1.5)" }], { duration: 1200, iterations: Infinity, direction: "alternate" }));
  expect(await eligible()).toBe(false);
  // Element.animate on a translate
  await page.setContent(staticControlHtml);
  await page.evaluate(() => document.querySelector(".widget")!.animate([{ transform: "translateX(0)" }, { transform: "translateX(40px)" }], { duration: 1200, iterations: Infinity }));
  expect(await eligible()).toBe(false);
  // CSS transition in flight (finite) leaves a non-identity transform on an ancestor
  await page.setContent(staticControlHtml.replace("</style>", ".widget{transition:transform 5s linear}.go .widget{transform:translateX(80px)}</style>"));
  await page.evaluate(() => { document.body.getBoundingClientRect(); document.body.classList.add("go"); });
  await page.waitForTimeout(200);
  expect(await eligible()).toBe(false);
  // eligible pulse inside a translated static wrapper
  await page.setContent(strongPulseHtml.replace('<div class="widget">', '<div style="transform:translateX(10px)"><div class="widget">') + "</div>");
  expect(await eligible()).toBe(false);
});
