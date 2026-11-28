import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve, sep } from "node:path";
import { chromium, expect, test, type Browser, type Page } from "@playwright/test";
import { VisualOperationWorker, type OperationResult } from "./vision-operations.js";
import { canonical, type VisualWorkerIdentity, type VisualWorkerDomObservation } from "./vision-contract.js";
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

test("an owned test target (ADR-046) may use sensitive and submit controls, never downloads or Enter", async () => {
  const opened = await agent({ blocked_action_terms: [], required_capabilities: ["owned-test-target-v1"] });
  expect(opened.capabilities).toContain("owned-test-target-v1");
  const home = await observe();
  const download = await propose(home, "Tải về");
  expect(download.operation, "download").toMatchObject({ status: "rejected", outcome_code: "sensitive_action_blocked" });
  const newline = await propose(home, "Ô một", TYPE("a\nb"));
  expect(newline.operation.outcome_code).toBe("sensitive_action_blocked");
  const sensitive = await act(home, "Xoá tài khoản");
  expect(sensitive.operation, sensitive.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  const submit = await propose(await observe(), "Gửi đi");
  expect(submit.operation.status, submit.operation.outcome_code ?? "").toBe("prepared");
});

test("a password input stays out of the snapshot of a read-only agent session", async () => {
  await agent({ target_url: `${target.origin}/login` });
  const hidden = await observe();
  expect(hidden.data.observation.elements.map(item => item.name)).toEqual(["Tên đăng nhập", "Đăng nhập"]);
  expect(hidden.data.observation.skipped_count).toBe(1);
});

test("on an owned test target a password input is a control and its value is never exported", async () => {
  await agent({ target_url: `${target.origin}/login`, blocked_action_terms: [], required_capabilities: ["owned-test-target-v1"] });
  const shown = await observe();
  expect(shown.data.observation.elements.map(item => [item.name, item.input_type, item.editable])).toEqual([
    ["Tên đăng nhập", "text", true], ["Mật khẩu", "other", true], ["Đăng nhập", null, false]]);
  expect(shown.data.observation.skipped_count).toBe(0);
  const typed = await act(shown, "Mật khẩu", TYPE("Demo1234"));
  expect(typed.operation, typed.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  expect(await page.locator("#password").inputValue()).toBe("Demo1234");
  // The grounded locator is the accessible name; no descriptor, name or result field carries the typed value.
  expect(typed.locator?.descriptor).toMatchObject({ strategy: "role", value: "Mật khẩu" });
  expect(JSON.stringify([typed, await observe()])).not.toContain("Demo1234");
});

test("without the capability an empty term list still blocks submit controls in agent mode", async () => {
  await agent({ blocked_action_terms: [] });
  const blocked = await propose(await observe(), "Gửi đi");
  expect(blocked.operation).toMatchObject({ status: "rejected", outcome_code: "sensitive_action_blocked" });
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

// ADR-046 page text (`page-text-v1`): visible text for the agent, in agent mode and on request only.
const PAGE_TEXT = { required_capabilities: ["page-text-v1"] };
const textOf = (observed: VisualWorkerDomObservation) => observed.data.observation.page_text.map(item => [item.kind, item.text]);

test("page text is read, in priority order, from what the page shows and nothing it hides", async () => {
  const opened = await agent({ target_url: `${target.origin}/page-text`, ...PAGE_TEXT });
  expect(opened.capabilities).toContain("page-text-v1");
  const seen = (await observe()).data.observation;
  const items = seen.page_text.map(item => [item.kind, item.text]);
  const long = items.find(([, text]) => text.startsWith("Chữ dài"))!;
  expect(items.filter(item => item !== long)).toEqual([
    ["alert", "Sai tên đăng nhập"], ["alert", "Lỗi Hết phiên làm việc"], ["status", "Còn 3 việc"],
    ["heading", "Trang thử chữ"], ["heading", "Tiêu đề hai"],
    ["paragraph", "Đoạn văn ngắn hiển thị."], ["paragraph", "Trước sau"], ["paragraph", "Chữ thường và hết"]]);
  // An over-long paragraph is cut to the cap, with a visible mark; that is not "more items than fit".
  expect(long[0]).toBe("paragraph");
  expect([...long[1]].length).toBeLessThanOrEqual(160);
  expect(long[1].endsWith("…")).toBe(true);
  expect(seen).toMatchObject({ page_text_truncated: false, page_text_skipped: 0 });
  // Field values, hidden text, script/style and contenteditable text never leave the worker.
  const wire = JSON.stringify(seen);
  for (const hidden of ["giá-trị-ô-nhập", "MatKhauBiMat1", "nội dung textarea", "ẩn", "mờ", "trình đọc", "ngoài màn hình",
    "trong script", "trong style", "Đang gõ dở", "Đóng"]) expect(JSON.stringify(seen.page_text), hidden).not.toContain(hidden);
  expect(wire).not.toContain("giá-trị-ô-nhập");
});

test("without the capability, or outside agent mode, the observation carries no page text", async () => {
  await agent({ target_url: `${target.origin}/page-text` });
  expect((await observe()).data.observation).toMatchObject({ page_text: [], page_text_truncated: false, page_text_skipped: 0 });
  await worker.close(identity, identity.session_id);
  identity = { ...identity, session_id: randomUUID() };
  const opened = await openSession({ target_url: `${target.origin}/page-text`, ...PAGE_TEXT });
  expect(opened.capabilities).toContain("page-text-v1");
  expect((await observe()).data.observation).toMatchObject({ page_text: [], page_text_truncated: false, page_text_skipped: 0 });
});

test("sensitive page text is dropped and counted, also on an owned test target", async () => {
  for (const extra of [{}, { blocked_action_terms: [], required_capabilities: ["owned-test-target-v1", "page-text-v1"] }]) {
    await agent({ target_url: `${target.origin}/page-text-sensitive`, ...PAGE_TEXT, ...extra });
    const seen = (await observe()).data.observation;
    expect(textOf(await observe())).toEqual([["alert", "Sai mật khẩu"], ["heading", "Hồ sơ"], ["paragraph", "An toàn: còn 5 lượt"]]);
    expect(seen.page_text_skipped).toBe(6);
    expect(JSON.stringify(seen)).not.toMatch(/nguoi\.dung|abc123|abcdef|1234567890|example\.com|Reset/);
    await worker.close(identity, identity.session_id);
    identity = { ...identity, session_id: randomUUID() };
  }
});

test("page text is capped by item count, by total bytes and by the observation byte limit", async () => {
  await agent({ target_url: `${target.origin}/page-text-many`, ...PAGE_TEXT });
  const many = (await observe()).data.observation;
  expect(many.page_text).toHaveLength(24);
  expect(many).toMatchObject({ page_text_truncated: true });
  expect(many.page_text[0]).toEqual({ kind: "heading", text: "Danh sách" });
  await worker.close(identity, identity.session_id);
  identity = { ...identity, session_id: randomUUID() };

  await agent({ target_url: `${target.origin}/page-text-bytes`, ...PAGE_TEXT });
  const wide = (await observe()).data.observation;
  expect(wide.page_text).toHaveLength(9);
  expect(wide.page_text.reduce((sum, item) => sum + Buffer.byteLength(item.text), 0)).toBeLessThanOrEqual(4096);
  expect(wide.page_text_truncated).toBe(true);

  // A request byte cap smaller than the observation drops text first and says so; the controls stay.
  const room = Buffer.byteLength(canonical(wide)) - 1500;
  const tight = (await worker.observeDom({ ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: current,
    max_bytes: room })).data.observation;
  expect(Buffer.byteLength(canonical(tight))).toBeLessThanOrEqual(room);
  expect(tight.page_text.length).toBeLessThan(9);
  expect(tight.page_text.length).toBeGreaterThan(0);
  expect(tight.page_text_truncated).toBe(true);
});

test("page text filter matches the Python contract on non-ASCII digits, e-mail and case folding", async () => {
  // Same strings as tests/test_codex_bridge_contracts.py: whatever the worker keeps, CodexPageTextItem must accept.
  const { samples } = JSON.parse(readFileSync(new URL("../../../packages/contracts/fixtures/vision-page-text-v1/samples.json", import.meta.url), "utf8")) as
    { samples: Array<{ text: string; worker_keeps: boolean }> };
  await agent({ target_url: `${target.origin}/page-text-samples`, ...PAGE_TEXT });
  const seen = (await observe()).data.observation;
  expect(seen.page_text.map(item => item.text)).toEqual(samples.filter(sample => sample.worker_keeps).map(sample => sample.text));
  expect(seen.page_text_skipped).toBe(samples.filter(sample => !sample.worker_keeps).length);
});

// ADR-048 (`agent-frozen-clock-v1`): the page's timers stand still between operations, so a page that changes
// by itself (autoplay carousel) keeps the state the model was shown. Nothing here relies on the real site.
const CLOCK = { required_capabilities: ["agent-frozen-clock-v1"] };
const CAROUSEL = `/carousel`;
const sleep = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));
const startCarousel = (period: number) => page.evaluate((ms) =>
  (window as unknown as { startCarousel: (n: number) => void }).startCarousel(ms), period);
const slide = () => page.locator("#slide").textContent();
const pageTime = (on: Page = page) => on.evaluate(() => Date.now());
const slideOn = async (on: Page) => await on.locator("#slide").count() ? on.locator("#slide").textContent() : null;
async function expectStill(on: Page = page, ms = 600) {
  const time = await pageTime(on), text = await slideOn(on);
  await sleep(ms);
  expect(await pageTime(on)).toBe(time);
  expect(await slideOn(on)).toBe(text);
}

test("without the capability a page timer moves the state while the model is idle (behaviour before ADR-048)", async () => {
  await agent({ target_url: `${target.origin}${CAROUSEL}` });
  await startCarousel(1000);
  const seen = await observe();
  await sleep(1500); // one tick, the next is at 2 s
  const { result, mismatch } = await captureMismatch(() => propose(seen, "Đổi nội dung"));
  expect(result.operation).toMatchObject({ status: "rejected", outcome_code: "state_mismatch", executed_click: null });
  expect(mismatch).toMatchObject({ failure_stage: "prepare_start", interaction_changed: true });
  expect(await out()).toBe("chưa đổi");
});

test("with the capability the state survives many timer periods between observe, prepare and execute", async () => {
  const opened = await agent({ target_url: `${target.origin}${CAROUSEL}`, ...CLOCK });
  expect(opened.capabilities).toContain("agent-frozen-clock-v1");
  await startCarousel(300);
  for (const round of [1, 2]) {
    const seen = await observe();
    await sleep(2500); // eight periods if the page clock were running
    const { result, mismatch } = await captureMismatch(async () => {
      const prepared = await propose(seen, "Đổi nội dung");
      expect(prepared.operation, `round ${round}: ${prepared.operation.outcome_code ?? ""}`).toMatchObject({ status: "prepared" });
      await sleep(1000);
      const done = await worker.execute(executeCommand(prepared)); current = done.state_fingerprint ?? current; return done;
    });
    expect(result.operation, `round ${round}: ${result.operation.outcome_code ?? ""}`).toMatchObject({ status: "completed", outcome_code: "observed" });
    expect(mismatch).toBeUndefined();
    expect(await out()).toBe("đã đổi");
    // The state published by the operation is the one the next round's observe still finds.
    await sleep(1000);
  }
  await expectStill();
});

test("wait lets the page's time pass (the carousel moves), then the page stands still again", async () => {
  await agent({ target_url: `${target.origin}${CAROUSEL}`, ...CLOCK });
  await startCarousel(300);
  const before = { fingerprint: current, slide: await slide() };
  const waited = await run({ kind: "wait", duration_ms: 1000 });
  expect(waited.operation, waited.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  expect(waited.state_fingerprint).not.toBe(before.fingerprint);
  const after = await slide();
  expect(after).not.toBe(before.slide);
  expect(Number(after!.replace("Slide ", ""))).toBeGreaterThanOrEqual(2);
  await sleep(1200);
  expect(await slide()).toBe(after);
  await expectStill();
  // The refresh wait of the control-plane loop passes time too, and observe accepts what it published.
  const refreshed = await refreshWait();
  expect(refreshed.operation, refreshed.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  expect((await observe()).data.observation.elements.map(item => item.name)).toContain("Đổi nội dung");
});

test("click, type, scroll and capture work on a stopped page; a timer started by the click still fires", async () => {
  await agent({ target_url: `${target.origin}${CAROUSEL}`, ...CLOCK });
  await startCarousel(1500); // slower than the 800 ms scroll settle window, as a real autoplay is
  let seen = await observe();
  const clicked = await act(seen, "Chạm trễ");
  expect(clicked.operation, clicked.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  expect(clicked.frames.map(frame => frame.role).sort()).toEqual(["after", "before"]);
  expect(await page.locator("#late-out").textContent()).toBe("xong");
  await expectStill();
  seen = await observe();
  const typed = await act(seen, "Ô gõ", TYPE("abc"));
  expect(typed.operation, typed.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  expect(await page.locator("input[name=typed]").inputValue()).toBe("abc");
  await expectStill();
  const scrolled = await run({ kind: "scroll", delta_y: 400 });
  expect(scrolled.operation, scrolled.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  expect(await page.evaluate(() => scrollY)).toBeGreaterThan(0);
  await expectStill();
  expect((await worker.screen(identity, identity.session_id)).length).toBeGreaterThan(0);
  expect((await run({ kind: "scroll", delta_y: -400 })).operation.status).toBe("completed");
  expect((await observe()).data.observation.elements.length).toBeGreaterThan(0);
});

test("a popup and a new document get the stopped clock too", async () => {
  test.setTimeout(60_000);
  await agent({ target_url: `${target.origin}${CAROUSEL}`, ...CLOCK });
  const popup = await act(await observe(), "Mở popup");
  expect(popup.operation, popup.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  const child = internals().page;
  expect(child.url()).toBe(`${target.externalOrigin}/popup`);
  await expectStill(child);
  const closed = await run({ kind: "close_popup" });
  expect(closed.operation, closed.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  await expectStill(internals().page);
  // `/carousel-late` starts its timer 4 s of page time after load; the operation only runs the clock for ~1.5 s.
  const moved = await act(await observe(), "Sang trang trễ");
  expect(moved.operation, moved.operation.outcome_code ?? "").toMatchObject({ status: "completed", url_change: "changed" });
  expect(internals().page.url()).toBe(`${target.origin}/carousel-late`);
  await expectStill(internals().page);
  await sleep(4500);
  expect(await slide()).toBe("Slide 0");
  expect((await observe()).data.observation.elements.map(item => item.name)).toContain("Slide 0");
});

test("a rejected or failed operation leaves the clock stopped", async () => {
  await agent({ target_url: `${target.origin}${CAROUSEL}`, ...CLOCK });
  await startCarousel(300);
  // Rejected at prepare (stale snapshot): no dispatch.
  const first = await observe();
  await observe();
  const stale = await propose(first, "Đổi nội dung");
  expect(stale.operation).toMatchObject({ status: "rejected", outcome_code: "stale_dom_snapshot" });
  await expectStill();
  // Rejected at execute before dispatch: the page changed between prepare and execute; the clock never ran.
  const seen = await observe();
  const prepared = await propose(seen, "Đổi nội dung");
  expect(prepared.operation.status).toBe("prepared");
  const time = await pageTime();
  await page.evaluate(() => scrollTo(0, 40));
  const rejected = await worker.execute(executeCommand(prepared));
  expect(rejected.operation).toMatchObject({ status: "rejected", outcome_code: "state_mismatch" });
  expect(rejected.failure_stage).toBe("before_dispatch");
  expect(await pageTime()).toBe(time);
  await expectStill();
  current = rejected.state_fingerprint ?? current;
  current = (await refreshWait()).state_fingerprint ?? current;
  // Fails after dispatch started (outcome unknown): the clock was running, and is stopped again.
  internals().page.mouse.wheel = async () => { throw new Error("browser lost"); };
  const lost = await run({ kind: "scroll", delta_y: 10 });
  expect(lost.operation).toMatchObject({ status: "unknown", outcome_code: "action_outcome_unknown" });
  await expectStill();
});

test("a session without the capability never gets a fake clock, and open reports the capability when asked", async () => {
  await agent({ target_url: `${target.origin}${CAROUSEL}` });
  const time = await pageTime();
  await sleep(300);
  expect(await pageTime()).toBeGreaterThanOrEqual(time + 250);
  await worker.close(identity, identity.session_id);
  identity = { ...identity, session_id: randomUUID() };
  // v4 mode (no agent_mode) asks for the capability and is not given a stopped clock either.
  const v4 = await openSession({ target_url: `${target.origin}${CAROUSEL}`, ...CLOCK });
  expect(v4.capabilities).toContain("agent-frozen-clock-v1");
  const v4time = await pageTime();
  await sleep(300);
  expect(await pageTime()).toBeGreaterThanOrEqual(v4time + 250);
});

// ADR-048 round 2: live, 1 of 15 sessions ended `initial_capture_failed` because stopping the clock threw
// "Cannot fast-forward to the past" on a page with child frames (a child frame's clock is ahead of the main one).
const framesTimes = (on: Page) => Promise.all(on.frames().map(frame => frame.evaluate(() => Date.now())));
async function logLines(attempt: () => Promise<unknown>) {
  const lines: string[] = [], originals = { log: console.log, warn: console.warn, error: console.error };
  const take = (line: unknown) => { if (typeof line === "string" && line.startsWith("{")) lines.push(line); };
  console.log = take; console.warn = take; console.error = take;
  try { await attempt(); } finally { Object.assign(console, originals); }
  return lines.map(line => JSON.parse(line) as Record<string, unknown>);
}

test("a page with child frames still opens, runs operations and ends every operation with every frame stopped", async () => {
  const lines = await logLines(async () => {
    await agent({ target_url: `${target.origin}/carousel-frames`, ...CLOCK });
    expect(page.frames().length).toBeGreaterThanOrEqual(4);
    for (const round of [1, 2]) {
      const seen = await observe();
      const done = await act(seen, "Đổi nội dung");
      expect(done.operation, `round ${round}: ${done.operation.outcome_code ?? ""}`).toMatchObject({ status: "completed" });
      const before = await framesTimes(page);
      await sleep(400);
      expect(await framesTimes(page)).toEqual(before);
    }
    const waited = await run({ kind: "wait", duration_ms: 300 });
    expect(waited.operation, waited.operation.outcome_code ?? "").toMatchObject({ status: "completed" });
  });
  expect(lines.filter(line => line.event === "vision.clock.freeze_failed")).toEqual([]);
  expect(lines.filter(line => line.event === "vision.state.mismatch")).toEqual([]);
});

test("when the page cannot be stopped the operation says so, the session keeps the clock marked running and recovers", async () => {
  await agent({ target_url: `${target.origin}/carousel-frames`, ...CLOCK });
  const clock = internals().page.context().clock, realPause = clock.pauseAt.bind(clock);
  clock.pauseAt = async () => { throw new Error("stop refused for https://secret.example/token"); };
  let failed: OperationResult | undefined;
  const lines = await logLines(async () => {
    const seen = await observe();
    failed = await act(seen, "Đổi nội dung");
  });
  expect(failed!.operation).toMatchObject({ status: "failed", outcome_code: "settle_timeout" });
  expect((worker as unknown as { sessions: Map<string, { clockRunning: boolean }> }).sessions.get(identity.session_id)!.clockRunning).toBe(true);
  const logged = lines.filter(line => line.event === "vision.clock.freeze_failed");
  expect(logged.length).toBeGreaterThan(0);
  expect(logged[0]).toMatchObject({ error_type: "unexpected_error", error_name: "Error" });
  expect(typeof logged[0].error_digest).toBe("string");
  expect(JSON.stringify(logged)).not.toContain("secret.example");
  // The stop works again: the next operation brings the page to a stop and the flag is honest.
  clock.pauseAt = realPause;
  current = failed!.state_fingerprint ?? current;
  const recovered = await run({ kind: "wait", duration_ms: 200 }, { purpose: "setup", state_id: null, proposal_id: null,
    refresh_observation: true, checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID() }).catch(() => null);
  expect(recovered).not.toBeNull();
  await expectStill();
});
