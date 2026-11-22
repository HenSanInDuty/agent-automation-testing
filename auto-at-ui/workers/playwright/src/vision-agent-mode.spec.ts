import { randomUUID } from "node:crypto";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve, sep } from "node:path";
import { chromium, expect, test, type Browser, type Page } from "@playwright/test";
import { VisualOperationWorker, type OperationResult } from "./vision-operations.js";
import type { VisualWorkerIdentity, VisualWorkerDomObservation } from "./vision-contract.js";
import { startAgentLoopTarget } from "./fixtures/agent-loop-target.js";

let target: Awaited<ReturnType<typeof startAgentLoopTarget>>;
let worker: VisualOperationWorker, identity: VisualWorkerIdentity, root: string, browser: Browser, page: Page;
let current: string;
test.beforeAll(async () => { target = await startAgentLoopTarget(); });
test.afterAll(async () => { await target.close(); });
test.beforeEach(async () => {
  target.requests.length = 0; target.externalRequests.length = 0;
  root = await mkdtemp(join(tmpdir(), "auto-at-vision-agent-"));
  worker = new VisualOperationWorker(root, async (options) => { browser = await chromium.launch(options); return browser; });
  identity = { contract_version: "v4", tenant_id: "fixture-tenant", project_id: randomUUID(), session_id: randomUUID(), fencing_token: 1 };
});
test.afterEach(async () => {
  if (worker.hasSession(identity.session_id)) await worker.close(identity, identity.session_id).catch(() => undefined);
  const path = resolve(root);
  expect(path.startsWith(resolve(tmpdir()) + sep) && path.includes("auto-at-vision-agent-")).toBe(true);
  await rm(path, { recursive: true, force: true });
});

// Same shape as vision-operations.spec.ts: command() / executeCommand() / run().
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
const CLICK = { kind: "click", x: 0.5, y: 0.5 };
const TYPE = (text: string) => ({ kind: "type", x: 0.5, y: 0.5, text });
const normalized = (value: string) => value.normalize("NFC");

async function openSession(extra: object = {}) {
  const opened = await worker.open({ ...identity, target_url: target.origin, allowed_origins: [target.origin],
    deadline: new Date(Date.now() + 120_000).toISOString(), max_session_seconds: 120,
    max_states: 20, max_hops: 10, max_screenshot_bytes: 1_000_000, ...extra });
  current = opened.state_fingerprint; page = browser.contexts()[0].pages()[0];
  const loaded = await run({ kind: "navigate" }, { purpose: "setup" });
  expect(loaded.operation.status, loaded.operation.outcome_code ?? "").toBe("completed");
  return opened;
}
const agent = (extra: object = {}) => openSession({ agent_mode: true, ...extra });
const observe = () => worker.observeDom({ ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: current });
function ref(observed: VisualWorkerDomObservation, name: string) {
  const found = observed.data.observation.elements.filter(item => normalized(item.name) === normalized(name));
  expect(found, `control "${name}" in ${observed.data.observation.elements.map(item => item.name).join(" | ")}`).toHaveLength(1);
  return { dom_snapshot_id: observed.data.observation.snapshot_id, dom_element_id: found[0].element_id };
}
const propose = (observed: VisualWorkerDomObservation, name: string, action: object = CLICK) =>
  worker.prepare(command(action, ref(observed, name)));
const act = (observed: VisualWorkerDomObservation, name: string, action: object = CLICK, extra: object = {}) =>
  run(action, { ...ref(observed, name), ...extra });
const internals = () => (worker as unknown as { sessions: Map<string, { page: Page; domSnapshots: Map<string, {
  document: { evaluate: (fn: () => number) => Promise<number> };
  anonymousTargets: Map<string, { evaluate: (fn: () => number) => Promise<number> }> }>; policyFailure: string | null }> })
  .sessions.get(identity.session_id)!;
const out = () => page.locator("#out").textContent();

test("agent mode keeps only the latest snapshot and rejects an older one before any click", async () => {
  await agent();
  const first = await observe();
  const second = await observe();
  expect([...internals().domSnapshots.keys()]).toEqual([second.data.observation.snapshot_id]);
  const stale = await propose(first, "Đổi nội dung");
  expect(stale.operation).toMatchObject({ status: "rejected", outcome_code: "stale_dom_snapshot", executed_click: null });
  expect(stale.frames).toEqual([]);
  expect(await out()).toBe("chưa đổi");
  expect((await act(second, "Đổi nội dung")).operation.status).toBe("completed");
  expect(await out()).toBe("đã đổi");
});

test("agent mode runs long sequences past max_states/max_hops while v4 hits the limits", async () => {
  // max_states=3, max_hops=2 give an operation budget of 1 + 3 * (2 * 2 + 3) = 22 (formula unchanged by this phase),
  // so 1 setup + 20 observe/click rounds = 21 operations is the longest run that fits.
  test.setTimeout(120_000);
  await agent({ max_states: 3, max_hops: 2 });
  let firstSnapshot: ReturnType<typeof internals>["domSnapshots"] extends Map<string, infer S> ? S | undefined : never;
  // Handles retained by the oldest snapshot must be disposed once newer snapshots replace it.
  for (let round = 0; round < 20; round++) {
    const observed = await observe();
    firstSnapshot ??= internals().domSnapshots.get(observed.data.observation.snapshot_id);
    const result = await act(observed, "Đổi nội dung");
    expect(result.operation.status, `round ${round}: ${result.operation.outcome_code ?? ""}`).toBe("completed");
    expect(result.operation.outcome_code).toBe("observed");
  }
  expect(internals().domSnapshots.size).toBe(1);
  await expect(firstSnapshot!.document.evaluate(() => 1)).rejects.toThrow();
  for (const handle of firstSnapshot!.anonymousTargets.values()) await expect(handle.evaluate(() => 1)).rejects.toThrow();
});

test("v4 mode with the same limits still stops at the snapshot, hop and state caps", async () => {
  await openSession({ max_states: 3, max_hops: 2 });
  const codes: string[] = [];
  for (let round = 0; round < 4; round++) {
    let observed: VisualWorkerDomObservation;
    try { observed = await observe(); } catch (error) { codes.push((error as Error).message); break; }
    const prepared = await propose(observed, "Đổi nội dung");
    if (prepared.operation.status !== "prepared") { codes.push(prepared.operation.outcome_code!); break; }
    current = (await worker.execute(executeCommand(prepared))).state_fingerprint!;
  }
  expect(codes).toHaveLength(1);
  expect(["dom_snapshot_limit", "hop_limit", "state_limit"]).toContain(codes[0]);
  // One snapshot reused across clicks reaches the hop/state caps instead.
  const reused = await worker.close(identity, identity.session_id).then(async () => {
    identity = { ...identity, session_id: randomUUID() };
    await openSession({ max_states: 3, max_hops: 2 });
    const observed = await observe(), seen: string[] = [];
    for (let round = 0; round < 4 && seen.length === 0; round++) {
      const prepared = await propose(observed, "Đổi nội dung");
      if (prepared.operation.status !== "prepared") { seen.push(prepared.operation.outcome_code!); break; }
      current = (await worker.execute(executeCommand(prepared))).state_fingerprint!;
    }
    return seen;
  });
  expect(["hop_limit", "state_limit"]).toContain(reused[0]);
});

test("agent mode allows back and navigate for purpose explore; v4 mode refuses them", async () => {
  await agent();
  const home = await observe();
  const moved = await act(home, "Trang kế");
  expect(moved.operation).toMatchObject({ status: "completed", url_change: "changed" });
  expect(page.url()).toBe(`${target.origin}/next`);
  const back = await run({ kind: "back" });
  expect(back.operation, back.operation.outcome_code ?? "").toMatchObject({ status: "completed", url_change: "changed" });
  expect(page.url()).toBe(`${target.origin}/`);
  await act(await observe(), "Trang kế");
  const navigated = await run({ kind: "navigate" });
  expect(navigated.operation, navigated.operation.outcome_code ?? "").toMatchObject({ status: "completed", url_change: "changed" });
  expect(page.url()).toBe(`${target.origin}/`);

  await worker.close(identity, identity.session_id);
  identity = { ...identity, session_id: randomUUID() };
  await openSession();
  expect((await worker.prepare(command({ kind: "back" }))).operation.outcome_code).toBe("invalid_restore_purpose");
  expect((await worker.prepare(command({ kind: "navigate" }))).operation.outcome_code).toBe("invalid_navigation_purpose");
});

test("a popup outside the allowlist opens for observation but cannot be acted on", async () => {
  await agent();
  const home = await observe();
  const opened = await act(home, "Liên kết ngoài");
  expect(opened.operation, opened.operation.outcome_code ?? "").toMatchObject({ status: "completed", outcome_code: "observed" });
  expect(internals().page.url()).toBe(`${target.externalOrigin}/popup`);
  // Sub-resource from another origin is not blocked.
  expect(target.externalRequests).toContain("GET /pixel.png");
  expect(await page.locator("img").evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth)).toBe(1);

  const popup = await observe();
  expect(popup.data.observation.elements.map(item => item.name)).toEqual(["Bấm trong popup"]);
  for (const action of [CLICK, TYPE("x"), { kind: "scroll", delta_y: 10 }, { kind: "navigate" }]) {
    const blocked = await worker.prepare(command(action, action === CLICK ? ref(popup, "Bấm trong popup") : {}));
    expect(blocked.operation, `${(action as { kind: string }).kind}`).toMatchObject({ status: "rejected", outcome_code: "origin_blocked", executed_click: null });
  }
  const closed = await run({ kind: "close_popup" });
  expect(closed.operation, closed.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  expect(internals().page.url()).toBe(`${target.origin}/`);
  expect(target.externalRequests.filter(line => line.startsWith("POST"))).toEqual([]);
});

test("only the read-only observation refresh may run outside the allowlist, to resync a stale page", async () => {
  await agent();
  const home = await observe();
  await act(home, "Liên kết ngoài");
  const external = internals().page;
  expect(external.url()).toBe(`${target.externalOrigin}/popup`);
  // A redirect/hydration race: the page changed after the last operation, so the stored state is stale.
  await external.evaluate(() => { document.querySelector("button")!.textContent = "Đã đổi"; });
  await expect(observe()).rejects.toThrow("state_mismatch");

  const refreshExtra = { purpose: "setup", state_id: null, proposal_id: null, refresh_observation: true,
    checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID() };
  const wait = { kind: "wait", duration_ms: 100 };
  // Everything else stays blocked: a plain wait, an explore refresh, and scroll/navigate flagged as a refresh (click/type need a ref, see the popup test above).
  for (const [label, action, extra] of [
    ["plain explore wait", wait, {}],
    ["setup wait without refresh flag", wait, { purpose: "setup", proposal_id: null }],
    ["refresh with purpose explore", wait, { ...refreshExtra, purpose: "explore" }],
    ["refresh flagged scroll", { kind: "scroll", delta_y: 10 }, refreshExtra],
    ["refresh flagged navigate", { kind: "navigate" }, refreshExtra],
  ] as [string, object, object][]) {
    const blocked = await worker.prepare(command(action, extra));
    expect(blocked.operation, label).toMatchObject({ status: "rejected", outcome_code: "origin_blocked", executed_click: null });
  }

  const refreshed = await run(wait, refreshExtra);
  expect(refreshed.operation, refreshed.operation.outcome_code ?? "").toMatchObject({ status: "completed", executed_click: null });
  expect(internals().page.url()).toBe(`${target.externalOrigin}/popup`);
  const popup = await observe();
  expect(popup.data.observation.elements.map(item => item.name)).toEqual(["Đã đổi"]);
  expect(await external.locator("button").evaluate((button: HTMLElement) => button.dataset.clicked)).toBeUndefined();
  expect(target.externalRequests.filter(line => line.startsWith("POST"))).toEqual([]);
  // The page is still observe-only afterwards.
  const after = await worker.prepare(command(CLICK, ref(popup, "Đã đổi")));
  expect(after.operation).toMatchObject({ status: "rejected", outcome_code: "origin_blocked" });
});

test("agent mode blocks submit, form buttons, downloads and listed terms but not other labels", async () => {
  await agent({ blocked_action_terms: ["xoá tài khoản", "xoá", "delete"] });
  const home = await observe();
  for (const name of ["Gửi đi", "Tiếp tục", "Tải về", "Xoá tài khoản", "XOÁ".normalize("NFD")]) {
    const blocked = await propose(home, name);
    expect(blocked.operation, name).toMatchObject({ status: "rejected", outcome_code: "sensitive_action_blocked", executed_click: null });
  }
  expect(target.requests.filter(line => /submit|file\.bin/.test(line))).toEqual([]);
  expect(await page.locator("button[data-clicked]").count()).toBe(0);
  // Sensitive text typing must not be able to press Enter either.
  const newline = await propose(home, "Ô một", TYPE("a\nb"));
  expect(newline.operation.outcome_code).toBe("sensitive_action_blocked");

  const card = await act(home, "NẠP THẺ");
  expect(card.operation, card.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  expect(await page.locator("button", { hasText: "NẠP THẺ" }).getAttribute("data-clicked")).toBe("yes");
  const typed = await act(await observe(), "Ô một", TYPE("abc"));
  expect(typed.operation, typed.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  expect(await page.locator("input[name=one]").inputValue()).toBe("abc");
  expect(target.requests.filter(line => line.startsWith("POST"))).toEqual([]);
  expect(page.url()).toBe(`${target.origin}/`);
  const register = await act(await observe(), "ĐĂNG KÝ");
  expect(register.operation, register.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
});

test("v4 mode does not apply the agent blocklist", async () => {
  await openSession({ blocked_action_terms: ["xoá tài khoản"] });
  const home = await observe();
  const prepared = await propose(home, "Xoá tài khoản");
  expect(prepared.operation.status, prepared.operation.outcome_code ?? "").toBe("prepared");
  const done = await worker.execute(executeCommand(prepared));
  expect(done.operation.status).toBe("completed");
  const submit = await propose(await observe(), "Gửi đi");
  expect(submit.operation.status, submit.operation.outcome_code ?? "").toBe("prepared");
});

test("two typed values in one batch on the same snapshot both run in agent mode", async () => {
  await agent();
  const home = await observe();
  const first = await act(home, "Ô một", TYPE("A"));
  expect(first.operation, first.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  const second = await act(home, "Ô hai", TYPE("B"));
  expect(second.operation, second.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  const third = await act(home, "Ô ba", TYPE("C"));
  expect(third.operation, third.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  expect(await page.locator("input").evaluateAll(inputs => inputs.map(input => (input as HTMLInputElement).value))).toEqual(["A", "B", "C"]);
  expect(target.requests.filter(line => line.startsWith("POST"))).toEqual([]);
});

test("the same typed batch is rejected as stale in v4 mode (re-baseline is agent-only)", async () => {
  await openSession();
  const home = await observe();
  expect((await act(home, "Ô một", TYPE("A"))).operation.status).toBe("completed");
  const second = await propose(home, "Ô hai", TYPE("B"));
  expect(second.operation).toMatchObject({ status: "rejected", outcome_code: "stale_dom_snapshot" });
});

for (const [label, dialog] of [["confirm", "Hỏi xác nhận"], ["alert", "Báo động"], ["prompt", "Nhập liệu"]] as const) {
  test(`${label}() caused by a click is reported and the agent session stays usable`, async () => {
    await agent();
    const result = await act(await observe(), dialog);
    expect(result.operation.outcome_code).toBe("dialog_unsupported");
    expect(result.operation.status).toBe("failed");
    expect(internals().policyFailure).toBeNull();
    const next = await act(await observe(), "Đổi nội dung");
    expect(next.operation, next.operation.outcome_code ?? "").toMatchObject({ status: "completed", outcome_code: "observed" });
  });
  test(`${label}() still locks a v4 session`, async () => {
    await openSession();
    const result = await act(await observe(), dialog);
    expect(result.operation.outcome_code).toBe("dialog_unsupported");
    expect(internals().policyFailure).toBe("dialog_unsupported");
    await expect(observe()).rejects.toThrow("dialog_unsupported");
  });
}

test("beforeunload raised by a click is reported and the agent session stays usable", async () => {
  await agent();
  expect((await act(await observe(), "Trang beforeunload")).operation.status).toBe("completed");
  const leaving = await act(await observe(), "Rời trang");
  expect(leaving.operation.outcome_code).toBe("dialog_unsupported");
  expect(internals().policyFailure).toBeNull();
  expect(page.url()).toBe(`${target.origin}/beforeunload`);
  const again = await observe();
  expect(again.data.observation.elements.map(item => item.name)).toEqual(["Rời trang"]);
});

test("beforeunload still locks a v4 session", async () => {
  await openSession();
  await act(await observe(), "Trang beforeunload");
  const leaving = await act(await observe(), "Rời trang");
  expect(leaving.operation.outcome_code).toBe("dialog_unsupported");
  expect(internals().policyFailure).toBe("dialog_unsupported");
});

test("a download started by a click is cancelled and the next operation runs", async () => {
  await agent();
  const result = await act(await observe(), "Tệp đính kèm");
  expect(result.operation, result.operation.outcome_code ?? "").toMatchObject({ status: "completed", outcome_code: "download_started" });
  expect(internals().policyFailure).toBeNull();
  const next = await act(await observe(), "Đổi nội dung");
  expect(next.operation.status, next.operation.outcome_code ?? "").toBe("completed");
});

const startDownload = () => page.evaluate(() => {
  const link = document.createElement("a"); link.href = "/file.bin"; link.download = "fixture.bin"; link.click();
});

test("a download during a running non-click operation is recoverable in agent mode only", async () => {
  for (const agentMode of [true, false]) {
    identity = { ...identity, session_id: randomUUID() };
    await openSession({ agent_mode: agentMode });
    const prepared = await worker.prepare(command({ kind: "wait", duration_ms: 1200 }));
    expect(prepared.operation.status).toBe("prepared");
    const executing = worker.execute(executeCommand(prepared));
    await page.waitForTimeout(300);
    await startDownload();
    const result = await executing;
    current = result.state_fingerprint ?? current;
    expect(result.operation.outcome_code).toBe("download_unsupported");
    expect(internals().policyFailure).toBe(agentMode ? null : "download_unsupported");
    if (agentMode) expect((await run({ kind: "wait", duration_ms: 100 })).operation.status).toBe("completed");
    else expect((await worker.prepare(command({ kind: "wait", duration_ms: 100 }))).operation.outcome_code).toBe("download_unsupported");
    await worker.close(identity, identity.session_id);
  }
});

for (const agentMode of [true, false]) {
  test(`a download outside any operation locks the session (agent_mode=${agentMode})`, async () => {
    await openSession({ agent_mode: agentMode });
    await startDownload();
    await expect.poll(() => internals().policyFailure).toBe("download_unsupported");
    const rejected = await worker.prepare(command({ kind: "wait", duration_ms: 100 }));
    expect(rejected.operation).toMatchObject({ status: "rejected", outcome_code: "download_unsupported" });
  });
  test(`an unknown action outcome locks the session (agent_mode=${agentMode})`, async () => {
    await openSession({ agent_mode: agentMode });
    page.mouse.wheel = async () => { throw new Error("browser lost"); };
    const result = await run({ kind: "scroll", delta_y: 10 });
    expect(result.operation).toMatchObject({ status: "unknown", outcome_code: "action_outcome_unknown" });
    expect(internals().policyFailure).toBe("action_outcome_unknown");
    const rejected = await worker.prepare(command({ kind: "wait", duration_ms: 100 }));
    expect(rejected.operation.outcome_code).toBe("action_outcome_unknown");
  });
}

// Evidence r6: the page drifted while the model was thinking (no worker operation running), so the
// next action failed `state_mismatch` at prepare_start. These cases pin what must keep failing and
// what the diagnostic reports; the gate itself is deliberately unchanged.
async function captureMismatch(attempt: () => Promise<OperationResult>) {
  const lines: string[] = [], original = console.error;
  console.error = (line: string) => lines.push(line);
  try {
    const result = await attempt();
    return { result, mismatch: lines.map(line => JSON.parse(line)).find(entry => entry.event === "vision.state.mismatch") };
  } finally { console.error = original; }
}
const refreshWait = () => run({ kind: "wait", duration_ms: 100 }, { purpose: "setup", state_id: null, proposal_id: null,
  refresh_observation: true, checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID() });

test("an autoplay slide change during the model idle window rejects before dispatch and the refresh recovers", async () => {
  await agent();
  await page.evaluate(() => {
    const box = document.createElement("div"); box.id = "carousel";
    box.innerHTML = '<a href="#one">Slide one</a><a href="#two" style="display:none">Slide two</a>';
    document.body.append(box);
    (window as unknown as { advance: () => void }).advance = () =>
      box.querySelectorAll("a").forEach(link => { link.style.display = link.style.display === "none" ? "" : "none"; });
  });
  expect((await refreshWait()).operation.status).toBe("completed");
  const seen = await observe();
  await page.evaluate(() => (window as unknown as { advance: () => void }).advance()); // autoplay tick while idle
  const { result, mismatch } = await captureMismatch(() => propose(seen, "Đổi nội dung"));
  expect(result.operation).toMatchObject({ status: "rejected", outcome_code: "state_mismatch", executed_click: null });
  expect(mismatch).toMatchObject({ failure_stage: "prepare_start", url_changed: false, scroll_changed: false,
    form_values_changed: false, interaction_changed: true, interaction_content_added: 1, interaction_content_removed: 1,
    interaction_geometry_only: 0, interaction_changed_tags: { A: 2 } });
  expect(await out()).toBe("chưa đổi");
  // Same recovery as the control-plane loop: observe is refused (and logged), a read-only refresh resyncs.
  const refused = await captureMismatch(async () => { await expect(observe()).rejects.toThrow("state_mismatch"); return result; });
  expect(refused.mismatch).toMatchObject({ failure_stage: "observe_start", interaction_changed: true });
  expect((await refreshWait()).operation.status).toBe("completed");
  const click = await act(await observe(), "Đổi nội dung");
  expect(click.operation, click.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  expect(await out()).toBe("đã đổi");
});

for (const [label, change, expected] of [
  ["the target itself is relabelled", () => page.evaluate(() => {
    [...document.querySelectorAll("button")].find(b => b.textContent === "Đổi nội dung")!.textContent = "Đổi khác";
  }), { interaction_changed: true, interaction_changed_tags: { BUTTON: 2 } }],
  ["a control in the target region is replaced", () => page.evaluate(() => {
    const link = [...document.querySelectorAll("a")].find(a => a.textContent === "Trang kế")!;
    link.setAttribute("href", "/elsewhere");
  }), { interaction_changed: true, interaction_changed_tags: { A: 2 } }],
  ["a modal appears", () => page.evaluate(() => {
    const dialog = document.createElement("div"); dialog.setAttribute("role", "dialog");
    dialog.style.cssText = "position:fixed;left:0;top:0;width:200px;height:100px"; dialog.textContent = "Cookie";
    document.body.append(dialog);
  }), { interaction_changed: true, interaction_changed_tags: { DIV: 1 } }],
  ["the URL changes", () => page.evaluate(() => history.pushState(null, "", "/pushed")), { url_changed: true }],
  ["the page scrolls", () => page.evaluate(() => scrollTo(0, 40)), { scroll_changed: true }],
  ["a form value changes", () => page.evaluate(() => { (document.querySelector("input[name=one]") as HTMLInputElement).value = "x"; }),
    { form_values_changed: true }],
] as [string, () => Promise<unknown>, object][]) {
  test(`still state_mismatch before any click when ${label}`, async () => {
    await agent();
    // A tall spacer makes scrolling possible; settle on it first so only the case's change drifts.
    await page.evaluate(() => { const spacer = document.createElement("div"); spacer.style.height = "3000px"; document.body.append(spacer); });
    expect((await refreshWait()).operation.status).toBe("completed");
    const seen = await observe();
    await change();
    const { result, mismatch } = await captureMismatch(() => propose(seen, "Đổi nội dung"));
    expect(result.operation).toMatchObject({ status: "rejected", outcome_code: "state_mismatch", executed_click: null });
    expect(mismatch).toMatchObject({ failure_stage: "prepare_start", ...expected });
    expect(await out()).toBe("chưa đổi");
    expect(target.requests.filter(line => line.startsWith("POST"))).toEqual([]);
  });
}
