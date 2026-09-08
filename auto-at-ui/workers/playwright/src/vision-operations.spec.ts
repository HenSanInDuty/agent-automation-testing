import { randomUUID } from "node:crypto";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve, sep } from "node:path";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { chromium, expect, test, type Browser, type Page } from "@playwright/test";
import { VisualOperationWorker, type OperationResult } from "./vision-operations.js";
import { visualHttpHandler } from "./vision-http.js";
import { digest, validateVision, type VisualWorkerIdentity } from "./vision-contract.js";
import { startVisionTarget } from "./fixtures/vision-target.js";

let target: Awaited<ReturnType<typeof startVisionTarget>>;
let worker: VisualOperationWorker, identity: VisualWorkerIdentity, root: string, browser: Browser, page: Page;
let current: string;
test.beforeAll(async () => { target = await startVisionTarget(); });
test.afterAll(async () => { await target.close(); });
test.beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "auto-at-vision-operations-"));
  worker = new VisualOperationWorker(root, async (options) => { browser = await chromium.launch(options); return browser; });
  identity = { contract_version: "v4", tenant_id: "fixture-tenant", project_id: randomUUID(), session_id: randomUUID(), fencing_token: 1 };
  const opened = await worker.open({ ...identity, target_url: target.origin, allowed_origins: [target.origin],
    deadline: new Date(Date.now() + 60_000).toISOString(), max_session_seconds: 60,
    max_states: 20, max_hops: 10, max_screenshot_bytes: 1_000_000 });
  current = opened.state_fingerprint; page = browser.contexts()[0].pages()[0];
});
test.afterEach(async () => {
  if (worker.hasSession(identity.session_id)) await worker.close(identity, identity.session_id);
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
  expect(await worker.execute(executeCommand(prepared))).toEqual(result);
  expect(worker.read(identity, identity.session_id, result.operation.id)).toEqual(result);
  expect(await page.getByRole("button", { name: "Icon action" }).getAttribute("data-count")).toBe("1");
  await expect(worker.acknowledge({ ...identity, operation_id: result.operation.id, persisted_frame_ids: [] })).rejects.toThrow("frame_ack_mismatch");
  await worker.acknowledge({ ...identity, operation_id: result.operation.id, persisted_frame_ids: result.frames.map((f) => f.id) });
  await expect(worker.frame(identity, identity.session_id, result.operation.id, result.frames[0].id)).rejects.toThrow("frame_unavailable");
  expect(worker.read(identity, identity.session_id, result.operation.id).acknowledged).toBe(true);
});
test("hydration replacing an identical DOM target rejects stale prepared locator", async () => {
  await setup(); const prepared = await worker.prepare(command(click(340)));
  await page.getByRole("button", { name: "Icon action" }).evaluate((el) => el.replaceWith(el.cloneNode(true)));
  const result = await worker.execute(executeCommand(prepared));
  expect(result.operation).toMatchObject({ status: "rejected", outcome_code: "stale_locator" });
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
test("origin policy covers denied popups", async () => {
  await setup(); const denied = await run(click(460));
  expect(denied.operation.status).not.toBe("completed");
  expect(denied.operation.outcome_code).toBe("origin_denied");
  expect(denied.operation.actual_before_frame_id).not.toBeNull();
});
test("before capture failure rejects without action and after failure retains actual action", async () => {
  await setup(); const original = page.screenshot.bind(page);
  page.screenshot = async () => { throw new Error("fixture capture unavailable"); };
  const rejected = await worker.prepare(command(click(340)));
  expect(rejected.operation).toMatchObject({ status: "rejected", before_unavailable_reason: "capture_failed" });
  page.screenshot = original;
  const prepared = await worker.prepare(command(click(340)));
  page.screenshot = async () => { throw new Error("fixture capture unavailable"); };
  const result = await worker.execute(executeCommand(prepared));
  expect(result.operation).toMatchObject({ status: "completed", after_unavailable_reason: "capture_failed" });
  expect(result.frames).toHaveLength(1);
  expect(await page.getByRole("button", { name: "Icon action" }).getAttribute("data-count")).toBe("1");
  page.screenshot = original;
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

for (const [name, selector, code] of [
  ["dialog", "button", "dialog_unsupported"], ["download", "a", "download_unsupported"],
] as const) test(`unsupported ${name} has an explicit recorded outcome`, async () => {
  await setup();
  const control = selector === "button" ? page.getByRole("button", { name: "Dialog", exact: true }) : page.getByRole("link", { name: "Download fixture" });
  const box = (await control.boundingBox())!;
  const result = await run({ kind: "click", x: (box.x + box.width / 2) / 1279, y: (box.y + box.height / 2) / 719 });
  expect(result.operation).toMatchObject({ status: "failed", outcome_code: code });
  expect(result.frames.map((f) => f.role)).toEqual(["before", "after"]);
});

test("settle timeout is bounded and retains after evidence", async () => {
  await setup();
  await page.getByRole("button", { name: "No operation" }).evaluate((el) => {
    el.addEventListener("click", () => { let count = 0; setInterval(() => el.setAttribute("data-changing", String(++count)), 20); });
  });
  const result = await run(click(400));
  expect(result.operation).toMatchObject({ status: "failed", outcome_code: "settle_timeout" });
  expect(result.frames).toHaveLength(2);
  expect(result.duration_ms).toBeLessThan(5000);
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
