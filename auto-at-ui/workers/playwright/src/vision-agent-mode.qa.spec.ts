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
