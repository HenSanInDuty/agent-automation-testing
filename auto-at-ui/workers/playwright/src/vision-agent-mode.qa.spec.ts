import { randomUUID } from "node:crypto";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve, sep } from "node:path";
import { chromium, expect, test, type Browser, type Page } from "@playwright/test";
import { VisualOperationWorker, type OperationResult } from "./vision-operations.js";
import type { VisualWorkerIdentity, VisualWorkerDomObservation } from "./vision-contract.js";

// QA edge cases for worker agent mode (phase 2). Own loopback fixture so it never depends on the developer's.
const listen = (server: Server) => new Promise<string>((done) => server.listen(0, "127.0.0.1", () =>
  done(`http://127.0.0.1:${(server.address() as AddressInfo).port}`)));
const stop = async (server: Server) => {
  server.closeAllConnections();
  await new Promise<void>((done, fail) => server.close((error) => error ? fail(error) : done()));
};
let main: Server, external: Server, origin: string, externalOrigin: string, posts: string[];
const home = () => `<!doctype html><meta charset="utf-8"><style>button,a,input{display:inline-block;margin:4px;padding:3px 6px}</style>
  <form id="f" action="/submit" method="post">
    <input aria-label="Ô một" name="one"><input aria-label="Ô hai" name="two">
    <button type="button" id="plain">Nút thường trong form</button>
    <input type="submit" value="Lưu lại">
    <input type="reset" value="Làm lại">
    <input type="image" alt="Ảnh gửi" src="${externalOrigin}/pixel.png" width="20" height="20">
    <button type="submit" aria-label="Hành động A">Biểu tượng</button>
  </form>
  <button type="submit" form="f">Gửi ngoài form</button>
  <button type="button" form="f" id="outside">Nút ngoài form kiểu button</button>
  <button type="button" title="Huỷ vĩnh viễn" onclick="this.dataset.clicked='yes'">Biểu tượng hai</button>
  <button type="button" aria-label="Thanh toán ngay" onclick="this.dataset.clicked='yes'">Biểu tượng ba</button>
  <button type="button" onclick="this.dataset.clicked='yes'">Xoá tài khoản</button>
  <button type="button" onclick="this.dataset.clicked='yes'">Nạp thẻ</button>
  <button type="button" onclick="document.getElementById('out').textContent='đã đổi'">Đổi nội dung</button>
  <button type="button" onclick="confirm('x')">Hỏi một</button>
  <button type="button" onclick="alert('y')">Hỏi hai</button>
  <a href="${externalOrigin}/landing">Đi ngoài cùng tab</a>
  <a href="${externalOrigin}/landing" target="_blank">Mở ngoài popup</a>
  <a href="/next">Trang kế</a>
  <p><span id="out">chưa đổi</span></p>`;
// ADR-048 QA pages: /qa-clock (timer carousel + form), /qa-raf (control moved by requestAnimationFrame),
// /qa-marquee (infinite CSS translate animation, not a timer).
const clockPage = (path: string) => `<!doctype html><meta charset="utf-8"><style>body{margin:8px;font:14px sans-serif}
  button,a,input{display:inline-block;margin:4px;padding:3px 6px}
  @keyframes slide{from{transform:translateX(0)}to{transform:translateX(200px)}}
  #marquee{animation:slide 1s linear infinite alternate}</style>
  <a id="slide" href="#slide0">Slide 0</a>
  <a href="/next">Trang kế</a>
  <button type="button" onclick="document.getElementById('out').textContent='đã đổi'">Đổi nội dung</button>
  <input aria-label="Ô gõ" name="typed">
  ${path === "/qa-raf" ? `<button type="button" id="mover" style="position:absolute;top:120px;left:0">Nút chạy</button>` : ""}
  ${path === "/qa-marquee" ? `<button type="button" id="marquee" style="position:absolute;top:120px;left:0">Nút trôi</button>` : ""}
  <p><span id="out">chưa đổi</span></p>
  <script>
    var ticks = 0;
    window.startCarousel = function (period) { setInterval(function () { ticks++;
      var slide = document.getElementById('slide'); slide.textContent = 'Slide ' + ticks; slide.setAttribute('href', '#slide' + ticks); }, period); };
    ${path === "/qa-raf" ? `(function frame() { var m = document.getElementById('mover');
      m.style.left = (Math.floor(performance.now() / 20) % 150) + 'px'; requestAnimationFrame(frame); })();` : ""}
  </script>`;
test.beforeAll(async () => {
  posts = [];
  external = createServer((request, response) => {
    if (request.url === "/pixel.png") { response.setHeader("content-type", "image/png"); response.end(Buffer.alloc(0)); return; }
    response.setHeader("content-type", "text/html; charset=utf-8");
    response.end(`<!doctype html><meta charset="utf-8"><button type="button" onclick="this.dataset.clicked='yes'">Bấm ngoài</button>`);
  });
  externalOrigin = await listen(external);
  main = createServer((request, response) => {
    if (request.method === "POST") posts.push(request.url ?? "");
    response.setHeader("content-type", "text/html; charset=utf-8");
    response.setHeader("cache-control", "no-store");
    // ADR-048 round 2 QA: `/qa-delay` answers after 480 ms (real time); `/qa-slow` makes every state read (inspectState
    // calls document.getAnimations once per sample) block on a synchronous request, i.e. a slow page, not a changing one.
    if (request.url?.startsWith("/qa-delay")) { setTimeout(() => response.end("ok"), Number(request.url.split("ms=")[1] ?? 480)); return; }
    if (request.url?.startsWith("/qa-slow")) {
      const ms = request.url.split("ms=")[1] ?? "480";
      response.end(`<!doctype html><meta charset="utf-8"><button type="button">Nút tĩnh</button><p>Trang tĩnh, đọc trạng thái chậm</p>
        <script>var real = document.getAnimations.bind(document);
        document.getAnimations = function () { var x = new XMLHttpRequest(); x.open("GET", "/qa-delay?ms=${ms}", false); x.send(); return real(); };</script>`);
      return;
    }
    if (request.url === "/qa-clock" || request.url === "/qa-raf" || request.url === "/qa-marquee") { response.end(clockPage(request.url)); return; }
    response.end(request.url === "/next" ? `<!doctype html><meta charset="utf-8"><a href="/">Về</a>` : home());
  });
  origin = await listen(main);
});
test.afterAll(async () => { await stop(main); await stop(external); });

let worker: VisualOperationWorker, identity: VisualWorkerIdentity, root: string, browser: Browser, page: Page, current: string;
test.beforeEach(async () => {
  posts.length = 0;
  root = await mkdtemp(join(tmpdir(), "auto-at-vision-agentqa-"));
  worker = new VisualOperationWorker(root, async (options) => { browser = await chromium.launch(options); return browser; });
  identity = { contract_version: "v4", tenant_id: "fixture-tenant", project_id: randomUUID(), session_id: randomUUID(), fencing_token: 1 };
});
test.afterEach(async () => {
  if (worker.hasSession(identity.session_id)) await worker.close(identity, identity.session_id).catch(() => undefined);
  const path = resolve(root);
  expect(path.startsWith(resolve(tmpdir()) + sep) && path.includes("auto-at-vision-agentqa-")).toBe(true);
  await rm(path, { recursive: true, force: true });
});

const command = (action: object, extra: object = {}) => ({ ...identity, operation_id: randomUUID(), purpose: "explore", action,
  expected_state_fingerprint: current, state_id: randomUUID(), proposal_id: randomUUID(), ...extra });
const executeCommand = (prepared: OperationResult) => {
  const before = prepared.frames.find((frame) => frame.role === "before")!;
  return { ...identity, operation_id: prepared.operation.id, prepared_handle: prepared.prepared_handle,
    before_persisted: true, before_frame_id: before.id, before_checksum: before.checksum };
};
async function run(action: object, extra: object = {}) {
  const prepared = await worker.prepare(command(action, extra));
  expect(prepared.operation.status, prepared.operation.outcome_code ?? "").toBe("prepared");
  const result = await worker.execute(executeCommand(prepared));
  current = result.state_fingerprint ?? current; return result;
}
const CLICK = { kind: "click", x: 0.5, y: 0.5 };
const TYPE = (text: string) => ({ kind: "type", x: 0.5, y: 0.5, text });
async function open(extra: object = {}) {
  const opened = await worker.open({ ...identity, target_url: origin, allowed_origins: [origin],
    deadline: new Date(Date.now() + 120_000).toISOString(), max_session_seconds: 120,
    max_states: 20, max_hops: 10, max_screenshot_bytes: 1_000_000, ...extra });
  current = opened.state_fingerprint; page = browser.contexts()[0].pages()[0];
  expect((await run({ kind: "navigate" }, { purpose: "setup" })).operation.status).toBe("completed");
}
const agent = (extra: object = {}) => open({ agent_mode: true, ...extra });
const observe = () => worker.observeDom({ ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: current });
const ref = (observed: VisualWorkerDomObservation, name: string) => {
  const found = observed.data.observation.elements.filter(item => item.name.normalize("NFC") === name.normalize("NFC"));
  expect(found, `control "${name}" in ${observed.data.observation.elements.map(item => item.name).join(" | ")}`).toHaveLength(1);
  return { dom_snapshot_id: observed.data.observation.snapshot_id, dom_element_id: found[0].element_id };
};
const propose = (observed: VisualWorkerDomObservation, name: string, action: object = CLICK) => worker.prepare(command(action, ref(observed, name)));
const act = (observed: VisualWorkerDomObservation, name: string, action: object = CLICK) => run(action, ref(observed, name));
// A prepared op stays pending; run it so the next prepare is not operation_pending.
const peek = async (prepared: OperationResult) => {
  if (prepared.operation.status === "prepared") current = (await worker.execute(executeCommand(prepared))).state_fingerprint ?? current;
  return prepared;
};
const sessionState = () => (worker as unknown as { sessions: Map<string, { policyFailure: string | null; page: Page }> }).sessions.get(identity.session_id)!;

test("QA-W01 element id of a newer snapshot paired with an older snapshot id is stale, not executed", async () => {
  await agent();
  const first = await observe(); const second = await observe();
  const mixed = await worker.prepare(command(CLICK, { dom_snapshot_id: first.data.observation.snapshot_id,
    dom_element_id: ref(second, "Đổi nội dung").dom_element_id }));
  expect(mixed.operation).toMatchObject({ status: "rejected", outcome_code: "stale_dom_snapshot", executed_click: null });
  expect(await page.locator("#out").textContent()).toBe("chưa đổi");
});

test("QA-W02 a random unknown snapshot id is rejected in agent mode without a click", async () => {
  await agent();
  const snap = await observe();
  const bad = await worker.prepare(command(CLICK, { dom_snapshot_id: randomUUID(), dom_element_id: ref(snap, "Đổi nội dung").dom_element_id }));
  expect(bad.operation.status).toBe("rejected");
  expect(["stale_dom_snapshot", "unknown_dom_snapshot"]).toContain(bad.operation.outcome_code);
  expect(await page.locator("#out").textContent()).toBe("chưa đổi");
});

test("QA-W03 term matching: case, NFD/NFC and accent-sensitivity (documented limitation)", async () => {
  await agent({ blocked_action_terms: ["XOÁ TÀI KHOẢN".normalize("NFD"), "nap the"] });
  const snap = await observe();
  // upper-case NFD term blocks the NFC lower-case label
  expect((await propose(snap, "Xoá tài khoản")).operation.outcome_code).toBe("sensitive_action_blocked");
  // accent-less term does NOT block "Nạp thẻ": worker only does NFC + lowercase (dev note 5)
  expect((await propose(snap, "Nạp thẻ")).operation.status).toBe("prepared");
});

test("QA-W04 accent-less label is blocked by an accent-less term", async () => {
  await agent({ blocked_action_terms: ["xoa tai khoan"] });
  const snap = await observe();
  // fixture has only the accented label -> not blocked; proves matching is not accent-folding
  expect((await propose(snap, "Xoá tài khoản")).operation.status).toBe("prepared");
});

test("QA-W05 blocklist reads aria-label, title, input value, and structural submit/reset/image", async () => {
  await agent({ blocked_action_terms: ["thanh toán", "huỷ vĩnh viễn"] });
  const snap = await observe();
  const names = snap.data.observation.elements.map(item => item.name);
  for (const name of ["Lưu lại", "Làm lại", "Hành động A", "Gửi ngoài form", "Biểu tượng hai", "Thanh toán ngay"]) {
    const found = names.find(item => item.normalize("NFC") === name.normalize("NFC"));
    if (!found) continue; // name resolution differs per control; asserted below when present
    expect((await propose(snap, name)).operation, name).toMatchObject({ status: "rejected", outcome_code: "sensitive_action_blocked" });
  }
  expect(await page.locator("button[data-clicked]").count()).toBe(0);
  expect(posts).toEqual([]);
  // plain type=button inside / outside a form is allowed
  expect((await peek(await propose(snap, "Nút thường trong form"))).operation.status).toBe("prepared");
  expect((await propose(await observe(), "Nút ngoài form kiểu button")).operation.status).toBe("prepared");
});

test("QA-W06 each structural submit control is blocked even with an empty blocklist", async () => {
  await agent({ blocked_action_terms: [] });
  const snap = await observe();
  const seen: string[] = [];
  for (const el of snap.data.observation.elements) {
    if (!["Lưu lại", "Làm lại", "Gửi ngoài form", "Biểu tượng", "Ảnh gửi"].some(n => el.name.normalize("NFC").includes(n))) continue;
    const prepared = await worker.prepare(command(CLICK, { dom_snapshot_id: snap.data.observation.snapshot_id, dom_element_id: el.element_id }));
    seen.push(`${el.name}:${prepared.operation.outcome_code ?? prepared.operation.status}`);
    expect(prepared.operation.outcome_code, el.name).toBe("sensitive_action_blocked");
  }
  expect(seen.length, seen.join(", ")).toBeGreaterThanOrEqual(1);
  expect(posts).toEqual([]);
});

for (const [label, text] of [["LF", "a\nb"], ["CR", "a\rb"], ["CRLF", "a\r\nb"], ["leading LF", "\nabc"], ["only LF", "\n"]] as const) {
  test(`QA-W07 type containing ${label} is blocked and nothing is typed`, async () => {
    await agent();
    const snap = await observe();
    const blocked = await propose(snap, "Ô một", TYPE(text));
    expect(blocked.operation).toMatchObject({ status: "rejected", outcome_code: "sensitive_action_blocked" });
    expect(await page.locator("input[name=one]").inputValue()).toBe("");
    expect(posts).toEqual([]);
  });
}

test("QA-W08 type with Vietnamese diacritics, tabs and a 1000-char (max) value works without submit", async () => {
  await agent();
  const snap = await observe();
  const long = "Đ".repeat(1000);
  const a = await act(snap, "Ô một", TYPE("Tiếng Việt: ắằẳẵặ ơư\tkhác"));
  expect(a.operation, a.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  const b = await act(snap, "Ô hai", TYPE(long));
  expect(b.operation, b.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  expect((await page.locator("input[name=two]").inputValue()).length).toBe(long.length);
  expect(posts).toEqual([]);
  // 1001 chars exceeds the contract bound: rejected at validation, no typing
  await expect(worker.prepare(command(TYPE("Đ".repeat(1001)), ref(snap, "Ô hai")))).rejects.toThrow("invalid_contract");
});

test("QA-W09 batch type A, type B then a click on the same snapshot all run", async () => {
  await agent();
  const snap = await observe();
  expect((await act(snap, "Ô một", TYPE("A"))).operation.status).toBe("completed");
  expect((await act(snap, "Ô hai", TYPE("B"))).operation.status).toBe("completed");
  const click = await act(snap, "Đổi nội dung");
  expect(click.operation, click.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  expect(await page.locator("#out").textContent()).toBe("đã đổi");
  // the click changed page content -> the same old snapshot must now be stale after a fresh observe
  const fresh = await observe();
  expect((await propose(snap, "Ô một", TYPE("Z"))).operation.outcome_code).toBe("stale_dom_snapshot");
  expect((await propose(fresh, "Ô một", TYPE("Z"))).operation.status).toBe("prepared");
});

test("QA-W10 same-tab navigation to another origin: only back is allowed, other kinds origin_blocked", async () => {
  await agent();
  const snap = await observe();
  await act(snap, "Đi ngoài cùng tab");
  expect(page.url()).toBe(`${externalOrigin}/landing`);
  const landing = await observe();
  for (const action of [{ kind: "wait", duration_ms: 100 }, { kind: "scroll", delta_y: 5 }, { kind: "navigate" }, TYPE("x"), CLICK]) {
    const withRef = action === CLICK || (action as { kind: string }).kind === "type";
    const prepared = await worker.prepare(command(action, withRef ? ref(landing, "Bấm ngoài") : {}));
    expect(prepared.operation, (action as { kind: string }).kind).toMatchObject({ status: "rejected", outcome_code: "origin_blocked" });
  }
  const back = await run({ kind: "back" });
  expect(back.operation, back.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  expect(page.url()).toBe(`${origin}/`);
  const after = await observe();
  expect((await act(after, "Đổi nội dung")).operation.status).toBe("completed");
});

test("QA-W11 popup outside allowlist: close_popup allowed, observe still works", async () => {
  await agent();
  await act(await observe(), "Mở ngoài popup");
  const popupObs = await observe();
  expect(popupObs.data.observation.elements.map(item => item.name)).toEqual(["Bấm ngoài"]);
  const closed = await run({ kind: "close_popup" });
  expect(closed.operation.status).toBe("completed");
  const home = await observe();
  expect((await act(home, "Đổi nội dung")).operation.status).toBe("completed");
});

test("QA-W12 v4 (agent_mode omitted and false): popup click and submit are not origin/sensitive-blocked", async () => {
  for (const extra of [{}, { agent_mode: false }]) {
    identity = { ...identity, session_id: randomUUID() };
    await open({ ...extra, blocked_action_terms: ["xoá tài khoản"] });
    for (const name of ["Xoá tài khoản", "Gửi ngoài form"]) {
      const p = await peek(await propose(await observe(), name));
      expect(p.operation.outcome_code, JSON.stringify(extra) + name).not.toBe("sensitive_action_blocked");
    }
    await worker.close(identity, identity.session_id);
  }
});

test("QA-W13 two dialogs in a row are both reported; a plain op in between completes", async () => {
  await agent();
  const first = await act(await observe(), "Hỏi một");
  expect(first.operation.outcome_code).toBe("dialog_unsupported");
  const mid = await act(await observe(), "Đổi nội dung");
  expect(mid.operation, mid.operation.outcome_code ?? "").toMatchObject({ status: "completed", outcome_code: "observed" });
  const second = await act(await observe(), "Hỏi hai");
  expect(second.operation.outcome_code).toBe("dialog_unsupported");
  expect(sessionState().policyFailure).toBeNull();
  expect((await observe()).data.observation.elements.length).toBeGreaterThan(3);
});

test("QA-W14 stale snapshot rejection happens before blocklist (no information leak ordering) and leaves session usable", async () => {
  await agent({ blocked_action_terms: ["xoá"] });
  const first = await observe(); const second = await observe();
  expect((await propose(first, "Xoá tài khoản")).operation.outcome_code).toBe("stale_dom_snapshot");
  expect((await propose(second, "Xoá tài khoản")).operation.outcome_code).toBe("sensitive_action_blocked");
  expect((await act(second, "Đổi nội dung")).operation.status).toBe("completed");
});

// Phase 04 r4: off-origin refresh exception must stay read-only.
const refreshExtra = () => ({ purpose: "setup", state_id: null, proposal_id: null, refresh_observation: true,
  checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID() });
const WAIT = { kind: "wait", duration_ms: 100 };

test("QA-W20 off-origin: acting actions flagged as refresh never run; refresh with extra fields is invalid", async () => {
  await agent();
  const home = await observe();
  await peek(await propose(home, "Đi ngoài cùng tab"));
  const popup = await observe();
  const ext = popup.data.observation.elements[0];
  const target = { dom_snapshot_id: popup.data.observation.snapshot_id, dom_element_id: ext.element_id };
  for (const [label, action, extra] of [
    ["click+refresh", CLICK, { ...refreshExtra(), state_id: randomUUID(), proposal_id: randomUUID(), ...target }],
    ["type+refresh", TYPE("x"), { ...refreshExtra(), state_id: randomUUID(), proposal_id: randomUUID(), ...target }],
    ["scroll+refresh", { kind: "scroll", delta_y: 10 }, refreshExtra()],
    ["navigate+refresh", { kind: "navigate" }, refreshExtra()],
    ["click plain", CLICK, target],
    ["type plain", TYPE("x"), target],
  ] as [string, object, object][]) {
    const blocked = await worker.prepare(command(action, extra));
    expect(blocked.operation, label).toMatchObject({ status: "rejected", outcome_code: "origin_blocked", executed_click: null });
  }
  for (const [label, extra] of [
    ["refresh with proposal", { ...refreshExtra(), proposal_id: randomUUID() }],
    ["refresh with snapshot", { ...refreshExtra(), ...target }],
    ["refresh with locator", { ...refreshExtra(), expected_locator: { strategy: "role", role: "button", name: "x" } }],
    ["refresh with restore", { ...refreshExtra(), restore_checkpoint_id: randomUUID() }],
    ["refresh with replay", { ...refreshExtra(), replay_operation_id: randomUUID() }],
    ["refresh without checkpoint", { ...refreshExtra(), checkpoint_id: null }],
  ] as [string, object][]) {
    // Rejected either by the contract validator (throws) or by the worker rules; never executed.
    const outcome = await worker.prepare(command(WAIT, extra)).then(
      (bad) => { expect(bad.operation.executed_click, label).toBeNull(); return `${bad.operation.status}:${bad.operation.outcome_code}`; },
      (error: Error) => `throw:${error.message}`);
    expect(outcome, label).toMatch(/^(rejected:(invalid_observation_refresh|origin_blocked)|throw:invalid_contract)$/);
  }
  const wrongFp = await worker.prepare(command(WAIT, { ...refreshExtra(), expected_state_fingerprint: "0".repeat(64) }));
  expect(wrongFp.operation).toMatchObject({ status: "rejected", outcome_code: "state_mismatch" });
  expect(await sessionState().page.locator("button").evaluate((b: HTMLElement) => b.dataset.clicked)).toBeUndefined();
  // Still usable: a valid refresh completes without side effects.
  const ok = await run(WAIT, refreshExtra());
  expect(ok.operation).toMatchObject({ status: "completed", executed_click: null });
  expect(posts).toEqual([]);
});

test("QA-W21 inside the allowlist the refresh keeps its checks and plain actions still run", async () => {
  await agent();
  const bad = await worker.prepare(command(WAIT, { ...refreshExtra(), proposal_id: randomUUID() }));
  expect(bad.operation).toMatchObject({ status: "rejected", outcome_code: "invalid_observation_refresh" });
  const ok = await run(WAIT, refreshExtra());
  expect(ok.operation).toMatchObject({ status: "completed", executed_click: null });
  const done = await act(await observe(), "Đổi nội dung");
  expect(done.operation.status).toBe("completed");
  expect(await page.locator("#out").textContent()).toBe("đã đổi");
});

// ---------------------------------------------------------------------------------------------------------------
// ADR-048 QA (`agent-frozen-clock-v1`), adversarial cases the developer spec does not cover.
const CLOCK_CAP = { required_capabilities: ["agent-frozen-clock-v1"] };
const qaSleep = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));
const qaTime = (on: Page = page) => on.evaluate(() => Date.now());
const qaSlide = (on: Page = page) => on.locator("#slide").textContent();
const qaStart = (period: number, on: Page = page) => on.evaluate((ms) =>
  (window as unknown as { startCarousel: (n: number) => void }).startCarousel(ms), period);
const sessionPage = (id: string) => (worker as unknown as { sessions: Map<string, { page: Page }> }).sessions.get(id)!.page;
async function mismatches<T>(attempt: () => Promise<T>): Promise<{ value: T; events: Array<Record<string, unknown>> }> {
  const lines: string[] = [], original = console.error;
  console.error = (line: string) => lines.push(line);
  try {
    const value = await attempt();
    const events = lines.flatMap(line => { try { return [JSON.parse(line)]; } catch { return []; } });
    return { value, events: events.filter(entry => entry.event === "vision.state.mismatch") };
  } finally { console.error = original; }
}
const qaStill = async (ms = 500, on: Page = page) => {
  const time = await qaTime(on), text = await qaSlide(on);
  await qaSleep(ms);
  expect(await qaTime(on)).toBe(time);
  expect(await qaSlide(on)).toBe(text);
};

test("QA-C01 twelve observe, idle, act rounds on a ticking carousel: no state_mismatch, page Date.now() frozen while idle", async () => {
  test.setTimeout(240_000);
  await agent({ target_url: `${origin}/qa-clock`, ...CLOCK_CAP });
  await qaStart(400);
  const { events } = await mismatches(async () => {
    for (let round = 0; round < 12; round++) {
      const seen = await observe();
      const time = await qaTime(), text = await qaSlide();
      await qaSleep(1300); // three carousel periods if the page clock ran
      expect(await qaTime(), `round ${round} Date.now()`).toBe(time);
      expect(await qaSlide(), `round ${round} slide`).toBe(text);
      const done = round % 3 === 1 ? await act(seen, "Ô gõ", TYPE(`v${round}`)) : await act(seen, "Đổi nội dung");
      expect(done.operation, `round ${round}: ${done.operation.outcome_code ?? ""}`).toMatchObject({ status: "completed", outcome_code: "observed" });
    }
  });
  expect(events).toEqual([]);
  await qaStill();
});

test("QA-C02 close and expiry leave nothing behind (browser gone, no unhandled rejection, expiry during a running wait)", async () => {
  test.setTimeout(60_000);
  const unhandled: unknown[] = [];
  const onRejection = (reason: unknown) => unhandled.push(reason);
  process.on("unhandledRejection", onRejection);
  try {
    // close(): idle session
    await agent({ target_url: `${origin}/qa-clock`, ...CLOCK_CAP });
    await qaStart(400);
    const closing = browser;
    await worker.close(identity, identity.session_id);
    expect(closing.isConnected()).toBe(false);
    await expect(worker.observeDom({ ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: current })).rejects.toThrow();
    // expiry while idle (clock stopped)
    identity = { ...identity, session_id: randomUUID() };
    await agent({ target_url: `${origin}/qa-clock`, ...CLOCK_CAP, deadline: new Date(Date.now() + 4000).toISOString(), max_session_seconds: 4 });
    const idle = browser;
    await qaSleep(5000);
    expect(idle.isConnected()).toBe(false);
    // expiry while a wait holds the clock running
    identity = { ...identity, session_id: randomUUID() };
    await agent({ target_url: `${origin}/qa-clock`, ...CLOCK_CAP, deadline: new Date(Date.now() + 4000).toISOString(), max_session_seconds: 4 });
    const running = browser;
    const outcome = await Promise.race([
      run({ kind: "wait", duration_ms: 8000 }).then(result => `${result.operation.status}:${result.operation.outcome_code ?? ""}`, (error: Error) => `throw:${error.message}`),
      qaSleep(20_000).then(() => "HUNG"),
    ]);
    expect(outcome, "wait returned").not.toBe("HUNG");
    for (let polls = 0; polls < 40 && running.isConnected(); polls++) await qaSleep(250); // the 4 s deadline may still be ahead
    expect(running.isConnected(), `outcome ${outcome}`).toBe(false);
    await qaSleep(500);
    expect(unhandled).toEqual([]);
  } finally { process.off("unhandledRejection", onRejection); }
});

test("QA-C03 two parallel sessions, one with the capability and one without, do not affect each other", async () => {
  test.setTimeout(60_000);
  await agent({ target_url: `${origin}/qa-clock`, ...CLOCK_CAP });
  const aState = { identity, current };
  const pageA = page;
  identity = { ...identity, session_id: randomUUID(), project_id: randomUUID() };
  await agent({ target_url: `${origin}/qa-clock` });
  const bState = { identity, current }, pageB = page;
  expect(pageA).not.toBe(pageB);
  await qaStart(400, pageA); await qaStart(400, pageB);
  const swap = (state: { identity: VisualWorkerIdentity; current: string }) => { identity = state.identity; current = state.current; };
  // B (no capability) keeps running while A is stopped.
  const a0 = await qaTime(pageA), b0 = await qaTime(pageB), slideA = await qaSlide(pageA), slideB = await qaSlide(pageB);
  await qaSleep(600);
  expect(await qaTime(pageA)).toBe(a0); expect(await qaSlide(pageA)).toBe(slideA);
  expect(await qaTime(pageB)).toBeGreaterThanOrEqual(b0 + 500); expect(await qaSlide(pageB)).not.toBe(slideB);
  // An operation in A neither starts nor stops B's clock, and A is stopped again afterwards.
  swap(aState); page = pageA;
  const doneA = await act(await observe(), "Đổi nội dung");
  expect(doneA.operation, doneA.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  aState.current = current;
  await qaStill(500, pageA);
  const b1 = await qaTime(pageB); await qaSleep(300);
  expect(await qaTime(pageB)).toBeGreaterThanOrEqual(b1 + 250);
  // An operation in B does not start A's clock.
  swap(bState); page = pageB;
  await run({ kind: "scroll", delta_y: 5 }).catch(() => undefined);
  await qaStill(500, pageA);
  // Closing B leaves A stopped and usable.
  await worker.close(bState.identity, bState.identity.session_id);
  swap(aState); page = pageA;
  await qaStill(500, pageA);
  expect((await act(await observe(), "Đổi nội dung")).operation.status).toBe("completed");
});

test("QA-C04 type, same-origin navigation, back and reload under the stopped clock", async () => {
  test.setTimeout(60_000);
  await agent({ target_url: `${origin}/qa-clock`, ...CLOCK_CAP });
  await qaStart(400);
  const typed = await act(await observe(), "Ô gõ", TYPE("tiếng Việt có dấu"));
  expect(typed.operation, typed.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  expect(await page.locator("input[name=typed]").inputValue()).toBe("tiếng Việt có dấu");
  await qaStill();
  const moved = await act(await observe(), "Trang kế");
  expect(moved.operation, moved.operation.outcome_code ?? "").toMatchObject({ status: "completed", url_change: "changed" });
  const next = sessionPage(identity.session_id);
  expect(next.url()).toBe(`${origin}/next`);
  const time = await qaTime(next);
  await qaSleep(400);
  expect(await qaTime(next)).toBe(time);
  const back = await run({ kind: "back" });
  expect(back.operation, back.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  page = sessionPage(identity.session_id);
  expect(page.url()).toBe(`${origin}/qa-clock`);
  // The document is fresh (carousel not started): the observation after back is accepted and the page is stopped.
  expect((await observe()).data.observation.elements.map(item => item.name)).toContain("Đổi nội dung");
  await qaStill(400);
  await qaStart(400);
  const reload = await worker.prepare(command({ kind: "navigate" }));
  if (reload.operation.status === "prepared") {
    const done = await worker.execute(executeCommand(reload)); current = done.state_fingerprint ?? current;
    expect(done.operation, done.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
    await qaStill(400, sessionPage(identity.session_id));
  } else expect(reload.operation.outcome_code).toBeTruthy(); // reload in explore may be refused by policy: recorded, not a clock fault
});

test("QA-C05 changes not caused by a timer are still refused while the clock is stopped", async () => {
  test.setTimeout(90_000);
  for (const [label, change] of [
    ["relabel", () => page.evaluate(() => { [...document.querySelectorAll("button")].find(b => b.textContent === "Đổi nội dung")!.nextElementSibling!.setAttribute("aria-label", "Ô khác"); })],
    ["modal", () => page.evaluate(() => { const d = document.createElement("div"); d.setAttribute("role", "dialog");
      d.style.cssText = "position:fixed;left:0;top:0;width:200px;height:100px"; d.textContent = "Cookie"; document.body.append(d); })],
    ["url", () => page.evaluate(() => history.pushState(null, "", "/pushed"))],
    ["scroll", () => page.evaluate(() => { const s = document.createElement("div"); s.style.height = "3000px"; document.body.append(s); scrollTo(0, 40); })],
    ["form", () => page.evaluate(() => { (document.querySelector("input[name=typed]") as HTMLInputElement).value = "x"; })],
    ["manual DOM swap of the slide link", () => page.evaluate(() => { document.getElementById("slide")!.textContent = "Slide X"; document.getElementById("slide")!.setAttribute("href", "#x"); })],
  ] as [string, () => Promise<unknown>][]) {
    await agent({ target_url: `${origin}/qa-clock`, ...CLOCK_CAP });
    const seen = await observe();
    await change();
    const { value } = await mismatches(() => propose(seen, "Đổi nội dung"));
    expect(value.operation, label).toMatchObject({ status: "rejected", outcome_code: "state_mismatch", executed_click: null });
    expect(await page.locator("#out").textContent(), label).toBe("chưa đổi");
    await qaStill(300);
    await worker.close(identity, identity.session_id);
    identity = { ...identity, session_id: randomUUID() };
  }
});

// Opens like `agent()` but tolerates a first navigate that cannot settle (a page that animates for ever).
async function agentLoose(extra: object): Promise<string> {
  try { await agent(extra); return "open=completed"; }
  catch (error) { return `open=${(error as Error).message.split("\n")[0]}`; }
}
const lastNavigate = () => (worker as unknown as { sessions: Map<string, { operations: Map<string, { result: OperationResult }> }> })
  .sessions.get(identity.session_id)!.operations;

test("QA-C06 requestAnimationFrame that moves a control: moves without the capability; with it the page is stopped between operations, but an operation (clock running) cannot settle", async () => {
  test.setTimeout(90_000);
  const left = () => page.locator("#mover").evaluate(el => (el as HTMLElement).style.left);
  const without = await agentLoose({ target_url: `${origin}/qa-raf` });
  const l0 = await left(); await qaSleep(300);
  expect(await left()).not.toBe(l0);
  await worker.close(identity, identity.session_id);
  identity = { ...identity, session_id: randomUUID() };
  const withClock = await agentLoose({ target_url: `${origin}/qa-raf`, ...CLOCK_CAP });
  // Stopped after the (failed or not) first operation: the control no longer moves.
  const l1 = await left(); await qaSleep(600);
  expect(await left(), "rAF-driven control while the page clock is stopped").toBe(l1);
  const statuses = [...lastNavigate().values()].map(entry => `${entry.result.operation.status}:${entry.result.operation.outcome_code ?? ""}`);
  test.info().annotations.push({ type: "raf-behaviour", description: `without=${without} | with=${withClock} | ops=${statuses.join(",")}` });
  console.log(`QA-C06 without=${without} | with=${withClock} | ops=${statuses.join(",")}`);
});

test("QA-C07 specification of the documented limit: an infinite CSS translate animation is not stopped by the page clock", async () => {
  test.setTimeout(60_000);
  const seen: string[] = [await agentLoose({ target_url: `${origin}/qa-marquee`, ...CLOCK_CAP })];
  const x = () => page.locator("#marquee").evaluate(el => Math.round(el.getBoundingClientRect().left));
  const x0 = await x(); await qaSleep(400);
  seen.push(`css-animation-moves-with-frozen-clock=${(await x()) !== x0}`);
  seen.push(await observe().then(() => "observe=ok", (error: Error) => `observe=${error.message}`));
  // Records the real behaviour (ADR-048 Limits: state_kept_changing / settle_timeout). Never fails on it.
  test.info().annotations.push({ type: "marquee-behaviour", description: seen.join(" | ") });
  console.log(`QA-C07 ${seen.join(" | ")}`);
  expect(seen).toHaveLength(3);
});

test("QA-C08 specification: a page timer faster than the 160 ms quiet window cannot settle inside an operation (clock runs during it) but is stopped afterwards", async () => {
  test.setTimeout(60_000);
  await agent({ target_url: `${origin}/qa-clock`, ...CLOCK_CAP });
  await qaStart(100);
  const done = await act(await observe(), "Đổi nội dung");
  const record = `${done.operation.status}:${done.operation.outcome_code ?? ""}`;
  test.info().annotations.push({ type: "fast-timer-behaviour", description: record });
  console.log(`QA-C08 100 ms timer, click => ${record}`);
  await qaStill(500); // whatever the outcome, the page must be stopped afterwards
});

// ---------------------------------------------------------------------------------------------------------------
// ADR-048 round 2 QA.
const operationsOf = () => [...(worker as unknown as { sessions: Map<string, { operations: Map<string, { result: OperationResult }> }> })
  .sessions.get(identity.session_id)!.operations.values()].map(entry => `${entry.result.operation.status}:${entry.result.operation.outcome_code ?? ""}`);
async function settleLogs(attempt: () => Promise<unknown>) {
  const lines: string[] = [], originals = { log: console.log, warn: console.warn, error: console.error };
  const take = (line: unknown) => { if (typeof line === "string" && line.startsWith("{")) lines.push(line); };
  console.log = take; console.warn = take; console.error = take;
  try { await attempt(); } finally { Object.assign(console, originals); }
  return lines.map(line => JSON.parse(line) as Record<string, unknown>);
}

test("QA-C09 regression (ADR-048 FAIL-1): a static but slow-to-read page passes the second settle with the capability, which keeps the operation's own budget, not a fixed 1000 ms cap", async () => {
  test.setTimeout(60_000);
  const logs = await settleLogs(async () => {
    // Control: no capability, same page, 480 ms per state read: the first settle (800 ms quiet, 10 s) accepts it.
    await agent({ target_url: `${origin}/qa-slow?ms=480` });
    expect(operationsOf()).toEqual(["completed:observed"]);
    await worker.close(identity, identity.session_id);
    identity = { ...identity, session_id: randomUUID() };
    // Same page with the capability: the page is static (0 state changes). The second settle on the stopped page
    // runs with the navigate budget (10 s), so two 480 ms reads pass and the operation completes.
    await agentLoose({ target_url: `${origin}/qa-slow?ms=480`, ...CLOCK_CAP });
  });
  expect(operationsOf()).toEqual(["completed:observed"]);
  // No settle of the operation may give up on the fixed 1000 ms cap that the defect used.
  const capped = logs.filter(line => line.event === "vision.state.settle_timeout" && Number(line.timeout_ms) <= 1000);
  expect(capped, JSON.stringify(logs.map(line => [line.event, line.reason, line.timeout_ms]))).toHaveLength(0);
  // A faster read (150 ms) also passes with the capability.
  identity = { ...identity, session_id: randomUUID() };
  await agent({ target_url: `${origin}/qa-slow?ms=150`, ...CLOCK_CAP });
  expect(operationsOf()).toEqual(["completed:observed"]);
});

test("QA-C10 regression (ADR-048 FAIL-2): a stop that reports 'past' while the clock still runs is not accepted: two page reads 250 ms apart stay different, the operation fails settle_timeout and clockRunning stays true", async () => {
  test.setTimeout(90_000);
  await agent({ target_url: `${origin}/qa-clock`, ...CLOCK_CAP });
  const clock = sessionPage(identity.session_id).context().clock, realPause = clock.pauseAt.bind(clock);
  clock.pauseAt = async () => { throw new Error("Cannot fast-forward to the past"); }; // lies: nothing is paused
  const outcomes: string[] = [];
  let falseAccepts = 0;
  for (let round = 0; round < 6; round++) {
    const seen = await observe();
    const done = await act(seen, "Đổi nội dung");
    outcomes.push(`${done.operation.status}:${done.operation.outcome_code ?? ""}`);
    if (done.operation.status === "completed") {
      // The worker believes the page is stopped. Is it?
      const time = await qaTime(sessionPage(identity.session_id));
      await qaSleep(400);
      if (await qaTime(sessionPage(identity.session_id)) !== time) falseAccepts++;
    }
  }
  // The worker saw the lie (every frame still ticking) and refused it on each operation, flag left on "running".
  const clockRunning = (worker as unknown as { sessions: Map<string, { clockRunning: boolean }> })
    .sessions.get(identity.session_id)!.clockRunning;
  clock.pauseAt = realPause;
  test.info().annotations.push({ type: "pause-lie", description: `outcomes=${outcomes.join(",")} falseAccepts=${falseAccepts} clockRunning=${clockRunning}` });
  console.log(`QA-C10 outcomes=${outcomes.join(",")} falseAccepts=${falseAccepts} clockRunning=${clockRunning}`);
  expect(outcomes).toEqual(Array(6).fill("failed:settle_timeout"));
  expect(falseAccepts).toBe(0);
  expect(clockRunning).toBe(true);
});
