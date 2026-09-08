import { test, expect, type Page } from "@playwright/test";

const dashboard = process.env.VISION_DASHBOARD_URL;
test.skip(!dashboard, "Set VISION_DASHBOARD_URL to the local dashboard fixture server.");
const sessionA = "00000000-0000-4000-8000-000000000001";
const sessionB = "00000000-0000-4000-8000-000000000002";
const project = "00000000-0000-4000-8000-000000000003";
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1kAAAAASUVORK5CYII=", "base64");

async function fixture(page: Page, legacy = false) {
  page.on("pageerror", (error) => { console.log("Fixture dashboard error:", error.message); });
  const state = { extra: 0, calls: 0, delay: false, release: () => {}, exploration: "running" };
  const session = (id: string) => ({ id, project_id: project, correlation_id: id, state: state.exploration, trace_version: legacy ? "legacy" : "v4", max_hops: 3, max_states: 8, max_session_seconds: 60 });
  const frame = (id: string) => ({ id, availability: "retained", reason_code: null });
  const operation = (number: number, id: string) => ({ id: `${id}-op${number}`, sequence: number, purpose: number === 1 ? "setup" : number === 3 ? "restore" : "explore", action_kind: number === 1 ? "navigate" : number === 3 ? "back" : "click", status: "completed", started_at: "2026-09-08T12:00:00Z", outcome_code: "observed", state_id: "root", locator_id: `${id}-locator${number}`, before: frame(`${id}-before${number}`), after: frame(`${id}-after${number}`) });
  const locators = (id: string) => [2, 4].map((n) => ({ id: `${id}-locator${n}`, operation_id: `${id}-op${n}`, status: "verified", reason_code: null, verified_at: "2026-09-08T12:00:00Z", descriptor: { strategy: "role", role: "button", value: n === 2 ? "Branch A" : "Branch B", scope: [] }, bounding_box: { x: .2, y: .2, width: .2, height: .1 } }));
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const id = path.includes(sessionB) ? sessionB : sessionA;
    const headers = { "access-control-allow-origin": dashboard!, "access-control-allow-credentials": "true" };
    const json = (body: unknown) => route.fulfill({ json: body, headers });
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers });
    if (path.endsWith("/auth/me")) return json({ role: "viewer", email: "reader@fixture.test", tenant_id: "fixture" });
    if (path.endsWith("/projects")) return json([{ id: project, name: "Fixture project", default_target: "web_ui" }]);
    if (path.endsWith("/policy")) return json({ enabled: false, raw_screenshot_transfer_accepted: false, allowed_origins: [], vision_max_hops: 3, vision_max_states: 8 });
    if (path.endsWith("/explorations")) return json({ items: [session(sessionA), session(sessionB)], total: 2 });
    if (path.endsWith("/trace")) {
      state.calls++;
      if (state.delay && id === sessionA) { state.delay = false; await new Promise<void>((resolve) => { state.release = resolve; }); }
      return json({ session_id: id, schema_version: "v1", revision: String(state.extra), trace_version: legacy ? "legacy" : "v4", items: Array.from({ length: 4 + state.extra }, (_, n) => operation(n + 1, id)), locators: locators(id), next_sequence: 4 + state.extra, has_more: false });
    }
    if (path.endsWith("/result")) return json({ schema_version: "v1", session_id: id, project_id: project, revision: String(state.extra), exploration_state: state.exploration, completion_reason: null, evidence_status: legacy ? "legacy_evidence_only" : "available", counts: { operations: 4 + state.extra, verified_locators: 2 }, branches: [], handoffs: [{ id: "handoff", branches: [2, 4].map((n, i) => ({ id: `branch${i}`, status: "ready", reason_code: null, steps: [{ operation_id: `${id}-op1` }, { operation_id: `${id}-op${n}` }] })) }], links: { handoff: { state: "ready" }, generation: { state: "failed" }, draft: { state: "not_started" }, run: { state: "failed", id: "run-fixture", href: "/runs/run-fixture" }, report: { state: "unavailable" } }, limitations: ["Business outcome unverified."] });
    if (path.endsWith("/locators")) return json({ items: locators(id), has_more: false, next_id: null });
    if (path.includes("/operation-frames/")) {
      if (path.endsWith("after2")) return route.fulfill({ status: 404, json: { detail: "Frame unavailable." }, headers });
      return route.fulfill({ body: png, contentType: "image/png", headers });
    }
    if (path.endsWith("/activities/stream")) return route.abort();
    if (path.endsWith("/activities") || path.endsWith("/actions")) return json([]);
    if (path.endsWith("/replay-frames")) return json({ items: legacy ? Array.from({ length: 7 }, (_, n) => ({ id: `frame${n}`, state_id: `state${n}`, sequence: n + 1, checksum: "a".repeat(64), size: png.length, content_type: "image/png", captured_at: "2026-09-08T12:00:00Z", actions: [] })) : [] });
    if (path.includes("/replay-frames/")) return route.fulfill({ body: png, contentType: "image/png", headers });
    if (legacy && path.endsWith("/trajectory")) return json({ session: session(id), trajectory_available: true, legacy_label: null, proposals: [], states: Array.from({ length: 7 }, (_, n) => ({ id: `state${n}`, parent_id: n ? "state0" : null, hop: n ? 1 : 0, sequence: n + 1, captured_at: "2026-09-08T12:00:00Z", frame_id: `frame${n}` })), edges: Array.from({ length: 6 }, (_, n) => ({ id: `edge${n}`, parent_state_id: "state0", proposal_id: `proposal${n}`, attempt: 1, action: { kind: "click", x: .5, y: .5 }, confidence: 1 - n / 10, status: "observed", outcome_code: null, child_state_id: `state${n + 1}`, observed_at: "2026-09-08T12:00:00Z", duration_ms: 100, url_change: "changed" })) });
    if (path.endsWith("/trajectory")) return json({ session: session(id), trajectory_available: false, legacy_label: null, states: [], proposals: [], edges: [] });
    return json(session(id));
  });
  return state;
}

test("saved branches, independent image errors, scrub preservation and live follow", async ({ page }) => {
  test.setTimeout(60_000);
  const state = await fixture(page);
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  await expect(page.getByRole("region", { name: "Vision result", exact: true })).toContainText("Draft generation failed");
  const trace = page.getByRole("region", { name: "Operation trace", exact: true });
  await trace.getByRole("button", { name: "Branch 2", exact: true }).click();
  await expect(trace.getByLabel("Selected operation")).toContainText("Operation 4");
  await expect(trace.getByLabel("Selected operation")).toContainText("Branch B");
  await trace.getByRole("button", { name: "All operations", exact: true }).click();
  await trace.getByRole("button", { name: "View operation 2 click", exact: true }).click();
  await expect(trace.getByAltText("Before operation frame")).toBeVisible();
  await expect(trace.getByText("Frame unavailable or access revoked.", { exact: true })).toBeVisible();
  state.extra = 1;
  await expect(trace.getByRole("button", { name: "View operation 5 click", exact: true })).toBeVisible({ timeout: 12_000 });
  await expect(trace.getByLabel("Selected operation")).toContainText("Operation 2");
  await trace.getByLabel("Follow live").check();
  await expect(trace.getByLabel("Selected operation")).toContainText("Operation 5");
  await page.getByText("Start an exploration and settings", { exact: true }).click();
  const input = page.getByLabel("Target URL", { exact: true });
  await input.fill("https://fixture.test/"); await input.press("Home");
  await expect(trace.getByLabel("Selected operation")).toContainText("Operation 5");
  await trace.focus(); await page.keyboard.press("Home");
  await expect(trace.getByLabel("Selected operation")).toContainText("Operation 1");
  state.exploration = "completed";
  await page.reload();
  await expect(page.getByRole("region", { name: "Vision result", exact: true })).toContainText(sessionA);
  await expect(page.getByText("Saved progress", { exact: true })).toBeVisible();
});

test("switching session discards a late response from the prior session", async ({ page }) => {
  test.setTimeout(45_000);
  const state = await fixture(page);
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  await expect(page.getByRole("region", { name: "Operation trace", exact: true })).toBeVisible();
  state.delay = true;
  await page.getByRole("button", { name: "Refresh saved result", exact: true }).click();
  await expect.poll(() => state.delay).toBe(false);
  await page.getByRole("region", { name: "Visual exploration sessions", exact: true }).getByRole("button", { name: "View", exact: true }).nth(1).click();
  await expect(page.getByRole("region", { name: "Vision result", exact: true })).toContainText(sessionB);
  state.release();
  await expect(page.getByRole("region", { name: "Vision result", exact: true })).not.toContainText(sessionA);
  await expect(page).toHaveURL(new RegExp(sessionB));
});


test("legacy seven-frame gallery can select the sixth sibling", async ({ page }) => {
  await fixture(page, true);
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  await expect(page.getByText("Legacy evidence only. Verified locators were not recorded for this session.")).toBeVisible();
  const trajectory = page.getByRole("region", { name: "Exploration evidence trajectory", exact: true });
  await trajectory.getByLabel("Branch alternatives").getByRole("button").nth(5).click();
  await expect(trajectory.getByRole("heading", { name: /After/ })).toContainText("7");
  await trajectory.getByRole("button", { name: "View this frame", exact: true }).click();
  await expect(trajectory.getByText("Current gallery selection: state 7.")).toBeVisible();
});
