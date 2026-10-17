import { test, expect, type Page } from "@playwright/test";

const dashboard = process.env.VISION_DASHBOARD_URL;
test.skip(!dashboard, "Set VISION_DASHBOARD_URL to the local dashboard fixture server.");
const sessionA = "00000000-0000-4000-8000-000000000001";
const sessionB = "00000000-0000-4000-8000-000000000002";
const sessionC = "00000000-0000-4000-8000-000000000004";
const project = "00000000-0000-4000-8000-000000000003";
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1kAAAAASUVORK5CYII=", "base64");

async function fixture(page: Page, legacy = false) {
  page.on("pageerror", (error) => { console.log("Fixture dashboard error:", error.message); });
  const state = { extra: 0, calls: 0, delay: false, release: () => {}, exploration: "running", completionReason: null as string | null, role: "viewer", configured: true, catalogueFails: false, saveFails: false, stale: false, writes: [] as unknown[], submissions: [] as unknown[],
    policy: { enabled: false, provider: "huggingface", model: "custom/hf-model", raw_screenshot_transfer_accepted: true, raw_screenshot_transfer_provider: "huggingface" as string | null, max_steps: 3, max_screenshot_bytes: 1000, max_session_seconds: 120, max_cost_usd: 0, max_requests_per_minute: 5 } };
  const session = (id: string) => ({ id, project_id: project, correlation_id: id, state: state.exploration, provider: id === sessionC ? state.policy.provider : "huggingface", model: id === sessionC ? state.policy.model : "historical/hf-model", trace_version: legacy ? "legacy" : "v4", max_hops: 3, max_states: 8, max_session_seconds: 60 });
  const frame = (id: string) => ({ id, availability: "retained", reason_code: null });
  const operation = (number: number, id: string) => ({ id: `${id}-op${number}`, sequence: number, purpose: number === 1 ? "setup" : number === 3 ? "restore" : "explore", action_kind: number === 1 ? "navigate" : number === 3 ? "back" : "click", status: "completed", started_at: "2026-09-08T12:00:00Z", outcome_code: "observed", state_id: "root", locator_id: `${id}-locator${number}`, before: frame(`${id}-before${number}`), after: frame(`${id}-after${number}`) });
  const locators = (id: string) => [2, 4].map((n) => ({ id: `${id}-locator${n}`, operation_id: `${id}-op${n}`, status: "verified", reason_code: null, verified_at: "2026-09-08T12:00:00Z", descriptor: { strategy: "role", role: "button", value: n === 2 ? "Branch A" : "Branch B", scope: [] }, bounding_box: { x: .2, y: .2, width: .2, height: .1 } }));
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const id = path.includes(sessionC) ? sessionC : path.includes(sessionB) ? sessionB : sessionA;
    const headers = { "access-control-allow-origin": dashboard!, "access-control-allow-credentials": "true" };
    const json = (body: unknown) => route.fulfill({ json: body, headers });
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers });
    if (path.endsWith("/auth/me")) return json({ role: state.role, email: "reader@fixture.test", tenant_id: "fixture" });
    if (path.endsWith("/projects")) return json([{ id: project, name: "Fixture project", default_target: "web_ui" }]);
    if (path.endsWith("/vision/providers")) return state.catalogueFails ? route.fulfill({ status: 503, json: {}, headers }) : json({ items: [
      { id: "huggingface", display_name: "Hugging Face", models: [{ id: "custom/hf-model", display_name: "custom/hf-model" }], configured: true, supports_inline_images: false },
      { id: "gemini", display_name: "Gehihi (Google Gemini)", models: [{ id: "gemini-3.8-flash", display_name: "gemini-3.8-flash" }], configured: state.configured, supports_inline_images: true },
    ] });
    if (path.endsWith("/vision/policy")) {
      if (route.request().method() === "PUT") {
        state.writes.push(route.request().postDataJSON());
        if (state.saveFails) return route.fulfill({ status: 409, json: { detail: { code: "provider_not_configured" } }, headers });
        state.policy = route.request().postDataJSON();
      }
      return json(state.policy);
    }
    if (path.endsWith("/policy")) return json({ allowed_origins: [], vision_max_hops: 3, vision_max_states: 8 });
    if (path.endsWith("/explorations") && route.request().method() === "POST") {
      state.submissions.push(route.request().postDataJSON());
      if (state.stale) return route.fulfill({ status: 409, json: { detail: { code: "vision_policy_changed" } }, headers });
      return json(session(sessionC));
    }
    if (path.endsWith("/explorations")) return json({ items: [...(state.submissions.length ? [session(sessionC)] : []), session(sessionA), session(sessionB)], total: state.submissions.length ? 3 : 2 });
    if (path.endsWith("/trace")) {
      state.calls++;
      if (state.delay && id === sessionA) { state.delay = false; await new Promise<void>((resolve) => { state.release = resolve; }); }
      return json({ session_id: id, schema_version: "v1", revision: String(state.extra), trace_version: legacy ? "legacy" : "v4", items: Array.from({ length: 4 + state.extra }, (_, n) => operation(n + 1, id)), locators: locators(id), next_sequence: 4 + state.extra, has_more: false });
    }
    if (path.endsWith("/result")) return json({ schema_version: "v1", session_id: id, project_id: project, revision: String(state.extra), exploration_state: state.exploration, completion_reason: state.completionReason, evidence_status: legacy ? "legacy_evidence_only" : "available", counts: { operations: 4 + state.extra, verified_locators: 2 }, branches: [], handoffs: [{ id: "handoff", branches: [2, 4].map((n, i) => ({ id: `branch${i}`, status: "ready", reason_code: null, steps: [{ operation_id: `${id}-op1` }, { operation_id: `${id}-op${n}` }] })) }], links: { handoff: { state: "ready" }, generation: { state: "failed" }, draft: { state: "not_started" }, run: { state: "failed", id: "run-fixture", href: "/runs/run-fixture" }, report: { state: "unavailable" } }, limitations: ["Business outcome unverified."] });
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

test("image authorization failure explains why completed navigation is not completed coverage", async ({ page }) => {
  const state = await fixture(page);
  state.exploration = "unavailable";
  state.completionReason = "image_delivery_auth_required";
  state.extra = -3;
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  const result = page.getByRole("region", { name: "Vision result", exact: true });
  await expect(result).toContainText("Google Drive authorization must be renewed");
  await expect(result).toContainText("Button coverage is incomplete");
  await expect(page.getByRole("region", { name: "Operation trace", exact: true })).toContainText("setup");
});

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

test("a saved session leaves the new exploration form visible and a new session survives reload", async ({ page }) => {
  const state = await fixture(page);
  state.policy.enabled = true;
  state.exploration = "unavailable";
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  const form = page.getByRole("region", { name: "Vision exploration", exact: true });
  await expect(form.getByRole("heading", { name: "Start a new Vision exploration" })).toBeInViewport();
  await expect(form.getByLabel("Target URL", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Vision result", exact: true })).toContainText(sessionA);
  await form.getByLabel("Target URL", { exact: true }).fill("https://fixture.test/");
  await form.getByLabel("Exploration intent", { exact: true }).fill("Explore the fixture navigation");
  await form.getByLabel("Use Vision Agent", { exact: true }).check();
  await form.getByRole("button", { name: "Start advisory exploration", exact: true }).click();
  expect(state.submissions).toHaveLength(0);
  await page.getByRole("dialog").getByRole("button", { name: "Start advisory exploration", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(sessionC));
  await expect(page.getByRole("region", { name: "Vision result", exact: true })).toContainText(sessionC);
  expect(state.submissions).toEqual([{ project_id: project, target_url: "https://fixture.test/", task_intent: "Explore the fixture navigation", use_vision: true, expected_provider: "huggingface", expected_model: "custom/hf-model" }]);
  await page.reload();
  await expect(page.getByRole("region", { name: "Vision result", exact: true })).toContainText(sessionC);
  await expect(form.getByLabel("Target URL", { exact: true })).toBeVisible();
  expect(state.submissions).toHaveLength(1);
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

async function openSettings(page: Page) {
  await page.locator("summary").filter({ hasText: /^Vision settings$/ }).click();
  return page.getByRole("region", { name: "Vision settings", exact: true });
}

async function prepareExploration(page: Page) {
  const form = page.getByRole("region", { name: "Vision exploration", exact: true });
  await form.getByLabel("Target URL", { exact: true }).fill("https://fixture.test/");
  await form.getByLabel("Exploration intent", { exact: true }).fill("Explore synthetic controls");
  await form.getByLabel("Use Vision Agent", { exact: true }).check();
  return form;
}

test("admin saves Gehihi consent, reloads and submits the saved model; historical session keeps its provider", async ({ page }) => {
  const state = await fixture(page); state.role = "tenant_admin";
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  let settings = await openSettings(page);
  await expect(settings.getByLabel("Vision model", { exact: true })).toHaveValue("custom/hf-model");
  await settings.getByLabel("Vision provider", { exact: true }).selectOption("gemini");
  await expect(settings.getByLabel("Vision model", { exact: true })).toHaveValue("gemini-3.8-flash");
  const consent = settings.getByRole("checkbox", { name: /I accept raw screenshot/ });
  await expect(consent).not.toBeChecked();
  await expect(settings.getByLabel("Enable vision exploration")).not.toBeChecked();
  await consent.check(); await settings.getByLabel("Enable vision exploration").check();
  await settings.getByRole("button", { name: "Save vision settings" }).click();
  await expect(page.getByText("Vision policy saved by the control plane.")).toBeVisible();
  expect(state.policy.raw_screenshot_transfer_provider).toBe("gemini");
  await page.reload(); settings = await openSettings(page);
  await expect(settings.getByLabel("Vision provider", { exact: true })).toHaveValue("gemini");
  await expect(settings.getByRole("checkbox", { name: /I accept raw screenshot/ })).toBeChecked();
  await expect(page.getByLabel("Saved Vision session")).toContainText("Session provider: Hugging Face");
  const form = await prepareExploration(page);
  await form.getByRole("button", { name: "Start advisory exploration", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Gehihi (Google Gemini)");
  await expect(dialog).toContainText("gemini-3.8-flash");
  await expect(dialog).toContainText("data-use conditions");
  await dialog.getByRole("button", { name: "Start advisory exploration" }).click();
  await expect(page).toHaveURL(new RegExp(sessionC));
  expect(state.submissions[0]).toMatchObject({ expected_provider: "gemini", expected_model: "gemini-3.8-flash" });
  await expect(page.getByLabel("Saved Vision session")).toContainText("Session provider: Gehihi (Google Gemini)");
});

test("unsaved and failed saves keep saved recipient and block runs until discarded", async ({ page }) => {
  const state = await fixture(page); state.role = "tenant_admin"; state.policy.enabled = true; state.saveFails = true;
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  const form = await prepareExploration(page); const settings = await openSettings(page);
  await settings.getByLabel("Vision provider", { exact: true }).selectOption("gemini");
  await expect(form).toContainText("Raw screenshots may be sent to Hugging Face");
  await expect(form.getByRole("button", { name: "Start advisory exploration" })).toBeDisabled();
  await settings.getByRole("button", { name: "Save vision settings" }).click();
  await expect(page.getByText(/The Vision provider is not configured/)).toBeVisible();
  await expect(settings.getByLabel("Vision provider", { exact: true })).toHaveValue("gemini");
  await expect(form).toContainText("Raw screenshots may be sent to Hugging Face");
  await settings.getByRole("button", { name: "Discard changes" }).click();
  await expect(settings.getByLabel("Vision model", { exact: true })).toHaveValue("custom/hf-model");
  await form.getByRole("button", { name: "Start advisory exploration" }).click();
  await expect(page.getByRole("dialog")).toContainText("Hugging Face");
  expect(state.submissions).toHaveLength(0);
});

test("stale confirmation sends frozen recipient, refreshes policy and requires a fresh confirmation", async ({ page }) => {
  const state = await fixture(page); state.policy.enabled = true;
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  const form = await prepareExploration(page);
  await form.getByRole("button", { name: "Start advisory exploration" }).click();
  state.policy = { ...state.policy, provider: "gemini", model: "gemini-3.8-flash", raw_screenshot_transfer_provider: "gemini" }; state.stale = true;
  await page.getByRole("dialog").getByRole("button", { name: "Start advisory exploration" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByText(/Vision settings changed. Review/)).toBeVisible();
  await expect(form).toContainText("sent to Google");
  await expect(form.getByLabel("Use Vision Agent", { exact: true })).not.toBeChecked();
  expect(state.submissions).toHaveLength(1);
  expect(state.submissions[0]).toMatchObject({ expected_provider: "huggingface", expected_model: "custom/hf-model" });
  state.stale = false;
  await form.getByLabel("Use Vision Agent", { exact: true }).check();
  await form.getByRole("button", { name: "Start advisory exploration" }).click();
  await expect(page.getByRole("dialog")).toContainText("gemini-3.8-flash");
  await page.getByRole("dialog").getByRole("button", { name: "Start advisory exploration" }).click();
  await expect(page).toHaveURL(new RegExp(sessionC));
  expect(state.submissions).toHaveLength(2);
});

test("missing key blocks enablement without a key input and catalogue failure can be retried", async ({ page }) => {
  const state = await fixture(page); state.role = "tenant_admin"; state.configured = false; state.catalogueFails = true;
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  const settings = await openSettings(page);
  await expect(settings.getByText("Vision settings could not be loaded.")).toBeVisible();
  state.catalogueFails = false;
  await settings.getByRole("button", { name: "Retry Vision settings" }).click();
  await settings.getByLabel("Vision provider", { exact: true }).selectOption("gemini");
  await expect(settings).toContainText("Gehihi (Google Gemini) is not configured on the server.");
  await settings.getByRole("checkbox", { name: /I accept raw screenshot/ }).check();
  await expect(settings.getByLabel("Enable vision exploration")).toBeDisabled();
  await expect(settings.getByRole("textbox")).toHaveCount(0);
});

test("nonadmin reads policy and safe failures while partial trace and draft failure stay visible", async ({ page }) => {
  const state = await fixture(page); state.exploration = "unavailable"; state.completionReason = "provider_rate_limited";
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  const settings = await openSettings(page);
  await expect(settings).toContainText("Provider: Hugging Face");
  await expect(settings.getByRole("combobox")).toHaveCount(0);
  await expect(settings.getByRole("button", { name: "Save vision settings" })).toHaveCount(0);
  const result = page.getByRole("region", { name: "Vision result", exact: true });
  await expect(result).toContainText("quota or request rate limit");
  await expect(result).toContainText("Draft generation failed");
  await expect(page.getByRole("region", { name: "Operation trace", exact: true })).toContainText("setup");
  expect(state.writes).toHaveLength(0);
});
