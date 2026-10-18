import { test, expect, type Page } from "@playwright/test";

const dashboard = process.env.VISION_DASHBOARD_URL;
test.skip(!dashboard, "Set VISION_DASHBOARD_URL to the local dashboard fixture server.");
const sessionA = "00000000-0000-4000-8000-000000000001";
const sessionB = "00000000-0000-4000-8000-000000000002";
const sessionC = "00000000-0000-4000-8000-000000000004";
const project = "00000000-0000-4000-8000-000000000003";
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1kAAAAASUVORK5CYII=", "base64");

let clickBefore: Buffer, clickAfter: Buffer;
test.beforeAll(async ({ browser }) => {
  const preview = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  await preview.setContent('<body style="margin:0;background:#eef2f6;font:24px Arial;color:#16263c"><header style="padding:32px;background:white">Synthetic storefront</header><h1 style="margin:48px">Explore products</h1><button style="position:absolute;left:280px;top:220px;width:180px;height:48px;background:#2459c4;color:white;border:0">Open details</button><p style="position:absolute;left:48px;top:360px">Recorded before the browser action</p></body>');
  clickBefore = await preview.screenshot();
  await preview.setContent('<body style="margin:0;background:#e8f4ee;font:24px Arial;color:#16482c"><h1 style="margin:64px">Product details</h1><p style="margin:64px">Recorded after navigation</p></body>');
  clickAfter = await preview.screenshot();
  await preview.close();
});

async function fixture(page: Page, legacy = false) {
  page.on("pageerror", (error) => { console.log("Fixture dashboard error:", error.message); });
  const state = { highlight: false, report: null as Record<string, unknown> | null, extra: 0, calls: 0, delay: false, release: () => {}, exploration: "running", completionReason: null as string | null, role: "viewer", configured: true, catalogueFails: false, evidenceFails: false, screenFails: false, screenCalls: 0, missingCapture: false, saveFails: false, stale: false, writes: [] as unknown[], submissions: [] as unknown[], reloads: [] as { sessionId: string; payload: unknown; key: string | undefined }[],
    policy: { enabled: false, provider: "huggingface", model: "custom/hf-model", raw_screenshot_transfer_accepted: true, raw_screenshot_transfer_provider: "huggingface" as string | null, max_steps: 3, max_screenshot_bytes: 1000, max_session_seconds: 120, max_cost_usd: 0, max_requests_per_minute: 5 } };
  const session = (id: string) => ({ id, project_id: project, correlation_id: id, state: state.exploration, provider: id === sessionC ? state.policy.provider : "huggingface", model: id === sessionC ? state.policy.model : "historical/hf-model", trace_version: legacy ? "legacy" : "v4", max_hops: 3, max_states: 8, max_session_seconds: 60 });
  const frame = (id: string) => ({ id, availability: "retained", reason_code: null });
  const operation = (number: number, id: string) => ({ id: `${id}-op${number}`, sequence: number, purpose: number === 1 ? "setup" : number === 3 ? "restore" : "explore", action_kind: number === 1 ? "navigate" : number === 3 ? "back" : "click", status: "completed", started_at: "2026-09-08T12:00:00Z", outcome_code: "observed", state_id: "root", locator_id: `${id}-locator${number}`, executed_click: state.highlight && number !== 1 && number !== 3 ? { x: 320 / 1279, y: 240 / 719, viewport_width: 1280, viewport_height: 720, before_frame_id: id + "-before" + number, confirmed_at: "2026-09-08T12:00:01Z" } : null, before: frame(`${id}-before${number}`), after: state.missingCapture ? { id: null, availability: "missing", reason_code: "capture_failed" } : frame(`${id}-after${number}`) });
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
    if (path.endsWith("/reload") && route.request().method() === "POST") {
      state.reloads.push({ sessionId: id, payload: route.request().postDataJSON(), key: route.request().headers()["idempotency-key"] });
      if (state.stale) return route.fulfill({ status: 409, json: { detail: { code: "vision_policy_changed" } }, headers });
      return json(session(sessionC));
    }
    if (path.endsWith("/explorations")) return json({ items: [...(state.submissions.length || state.reloads.length ? [session(sessionC)] : []), session(sessionA), session(sessionB)], total: state.submissions.length || state.reloads.length ? 3 : 2 });
    if (path.endsWith("/trace")) {
      state.calls++;
      if (state.delay && id === sessionA) { state.delay = false; await new Promise<void>((resolve) => { state.release = resolve; }); }
      return json({ session_id: id, schema_version: "v1", revision: String(state.extra), trace_version: legacy ? "legacy" : "v4", items: Array.from({ length: 4 + state.extra }, (_, n) => operation(n + 1, id)), locators: locators(id), next_sequence: 4 + state.extra, has_more: false });
    }
    if (path.endsWith("/result")) return json({ exploration_report: state.report ?? undefined, schema_version: "v1", session_id: id, project_id: project, revision: String(state.extra), exploration_state: state.exploration, completion_reason: state.completionReason, evidence_status: legacy ? "legacy_evidence_only" : "available", counts: { operations: 4 + state.extra, verified_locators: 2 }, branches: [], handoffs: [{ id: "handoff", branches: [2, 4].map((n, i) => ({ id: `branch${i}`, status: "ready", reason_code: null, steps: [{ operation_id: `${id}-op1` }, { operation_id: `${id}-op${n}` }] })) }], links: { handoff: { state: "ready" }, generation: { state: "failed" }, draft: { state: "not_started" }, run: { state: "failed", id: "run-fixture", href: "/runs/run-fixture" }, report: { state: "unavailable" } }, limitations: ["Business outcome unverified."] });
    if (path.endsWith("/locators") && state.evidenceFails) return route.fulfill({ status: 503, headers });
    if (path.endsWith("/screen")) { state.screenCalls++; return state.screenFails ? route.fulfill({ status: 503, headers }) : route.fulfill({ body: png, contentType: "image/png", headers }); }
    if (path.endsWith("/locators")) return json({ items: locators(id), has_more: false, next_id: null });
    if (path.includes("/operation-frames/")) {
      if (path.endsWith("after2")) return route.fulfill({ status: 404, json: { detail: "Frame unavailable." }, headers });
      return route.fulfill({ body: state.highlight ? (path.includes("before") ? clickBefore : clickAfter) : png, contentType: "image/png", headers });
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

test("partial exploration report is discoverable without a generated test report", async ({ page }) => {
  const state = await fixture(page);
  state.exploration = "unavailable"; state.completionReason = "model_output_invalid";
  state.report = {
    status: "partial", coverage: "not_established", stop_reason: "model_output_invalid",
    limits: { max_steps: 3, max_session_seconds: 120, max_hops: 5, max_states: 50 },
    summary: { controls_acted_on: 1, actions_rejected: 25, actions_failed: 0, actions_unknown: 0, scrolls_completed: 1, candidates_not_attempted: 10 },
    findings: [
      { operation_id: "op2", sequence: 2, action_kind: "click", status: "rejected", reason_code: "multiple_matches", target: null, url_change: "unavailable", visual_change: "unavailable" },
      { operation_id: "op28", sequence: 28, action_kind: "click", status: "completed", reason_code: "observed", target: "Open details", url_change: "unchanged", visual_change: "changed" },
    ],
  };
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  const report = page.locator('[aria-label="Vision result"]');
  await expect(page.getByRole("region", { name: "Exploration summary" })).toBeVisible();
  await page.getByRole("link", { name: "View exploration report", exact: true }).click();
  await expect(report.getByRole("heading", { name: "Exploration report", exact: true })).toBeInViewport();
  await expect(report).toContainText("Partial coverage");
  await expect(report).toContainText("3 model requests, 120 seconds");
  await expect(report.getByRole("cell", { name: "Not executed", exact: true })).toBeVisible();
  await expect(report.getByRole("cell", { name: "Observed", exact: true })).toBeVisible();
  await expect(report).toContainText("More than one control matches this locator");
  await expect(report.getByRole("link", { name: "Download report JSON" })).toHaveAttribute("href", new RegExp(`/explorations/${sessionA}/result/export$`));
  await expect(report).toContainText("A Playwright execution report becomes available after a generated draft is approved and run");
  await report.screenshot({ path: "../../.pytest_cache/vision-report-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("image authorization failure explains why completed navigation is not completed coverage", async ({ page }) => {
  const state = await fixture(page);
  state.exploration = "unavailable";
  state.completionReason = "image_delivery_auth_required";
  state.extra = -3;
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  const result = page.locator('[aria-label="Vision result"]');
  await expect(result).toContainText("Google Drive authorization must be renewed");
  await expect(result).toContainText("Button coverage is incomplete");
  await expect(page.getByRole("region", { name: "Operation trace", exact: true })).toContainText("Open page");
});

test("live screen keeps updating when evidence fails, recovers and stops polling at completion", async ({ page }) => {
  const state = await fixture(page);
  state.evidenceFails = true;
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  await expect(page.getByAltText("Vision browser screen")).toBeVisible();
  await expect(page.getByText("Some saved evidence is unavailable. Live progress is shown independently.")).toBeVisible();
  await expect.poll(() => state.screenCalls).toBeGreaterThan(1);
  state.screenFails = true;
  await expect(page.getByText(/Screen connection interrupted/)).toBeVisible();
  state.screenFails = false;
  await expect(page.getByText("Live browser · updates every second")).toBeVisible();
  state.exploration = "completed";
  await expect(page.getByText("Session stopped · last saved screen")).toBeVisible({ timeout: 12_000 });
  const calls = state.screenCalls;
  await page.waitForTimeout(1600);
  expect(state.screenCalls).toBe(calls);
});

test("failed initial capture shows the cause instead of a blank before image", async ({ page }) => {
  const state = await fixture(page);
  state.exploration = "unavailable"; state.missingCapture = true; state.extra = -3;
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  await expect(page.getByRole("region", { name: "Vision browser screen" })).toContainText("The page screenshot could not be captured");
  await expect(page.getByAltText("Before operation frame")).toHaveCount(0);
  expect(state.screenCalls).toBe(0);
});

test("Vision cards align on desktop, keep spacing and stack without mobile overflow", async ({ page }) => {
  const state = await fixture(page);
  state.exploration = "unavailable";
  state.completionReason = "state_restore_failed";
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  const screen = page.getByRole("region", { name: "Vision browser screen", exact: true });
  const progress = page.getByRole("region", { name: "Operation trace", exact: true });
  const result = page.locator('[aria-label="Vision result"]');
  await expect(screen.getByRole("img")).toBeInViewport();
  await expect(result).toContainText("could not restore the recorded page state");
  const a = (await screen.boundingBox())!, b = (await progress.boundingBox())!, c = (await result.boundingBox())!;
  expect(Math.abs(a.y - b.y)).toBeLessThan(1);
  expect(Math.abs(a.height - b.height)).toBeLessThan(1);
  expect(b.x - a.x - a.width).toBeGreaterThanOrEqual(23);
  expect(c.y - a.y - a.height).toBeGreaterThanOrEqual(23);
  await page.locator(".vision-live-workspace").screenshot({ path: "../../.pytest_cache/vision-cards-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  const mobileScreen = (await screen.boundingBox())!, mobileProgress = (await progress.boundingBox())!;
  expect(mobileProgress.y - mobileScreen.y - mobileScreen.height).toBeGreaterThanOrEqual(23);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.locator(".vision-live-workspace").screenshot({ path: "../../.pytest_cache/vision-cards-mobile.png" });
});

test("rejected origin is not presented as a screenshot capture failure", async ({ page }) => {
  const state = await fixture(page);
  state.exploration = "unavailable";
  await page.route("**/trace*", async (route) => {
    // A policy rejection occurs before capture and has no corresponding page image.
    await route.fulfill({ headers: { "access-control-allow-origin": dashboard!, "access-control-allow-credentials": "true" }, json: { session_id: sessionA, schema_version: "v1", revision: "1", trace_version: "v4", items: [{ id: "rejected", sequence: 1, purpose: "restore", action_kind: "back", status: "rejected", started_at: "2026-09-08T12:00:00Z", outcome_code: "origin_denied", locator_id: null, before: { id: null, availability: "missing", reason_code: "capture_failed" }, after: { id: null, availability: "missing", reason_code: "action_not_executed" } }], locators: [], has_more: false, next_sequence: 1 } });
  });
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  const screen = page.getByRole("region", { name: "Vision browser screen", exact: true });
  await expect(screen).toContainText("outside the project's allowed origins");
  await expect(screen).not.toContainText("screenshot could not be captured");
});

test("activity stream appends browser and model progress without a page reload", async ({ page }) => {
  await fixture(page);
  await page.route("**/activities/stream", async (route) => {
    const event = { id: "event-live", source: "vision", stage: "candidate.requested", status: "running", safe_summary: "Analyzing the current page", metadata: {}, occurred_at: "2026-09-08T12:00:00Z" };
    await route.fulfill({ contentType: "text/event-stream", headers: { "access-control-allow-origin": dashboard!, "access-control-allow-credentials": "true" }, body: `event: activity\ndata: ${JSON.stringify(event)}\n\n` });
  });
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  await expect(page.locator('[role="log"]')).toContainText("Analyzing the current page");
  await expect(page.locator('[role="log"]')).toContainText("Requesting advisory candidates");
});

test("external origins appear as informational progress while Vision keeps running", async ({ page }) => {
  await fixture(page);
  await page.route("**/activities", (route) => route.fulfill({
    headers: { "access-control-allow-origin": dashboard!, "access-control-allow-credentials": "true" },
    json: [{ id: "origin-1", source: "vision", stage: "origin.observed", status: "info",
      safe_summary: "External origin observed; browsing continued.",
      metadata: { origin: "https://cdn.fixture.test", request_kind: "resource" },
      occurred_at: "2026-09-08T12:00:00Z" }],
  }));
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  await expect(page.locator('[role="log"]')).toContainText("External origin recorded");
  await expect(page.locator('[role="log"]')).toContainText("https://cdn.fixture.test");
  await expect(page.locator('[role="log"]')).toContainText("browsing continued");
  await expect(page.getByRole("button", { name: "Reload", exact: true })).toBeDisabled();
  await expect(page.getByAltText("Vision browser screen")).toBeVisible();
});

test("saved branches, independent image errors, scrub preservation and live follow", async ({ page }) => {
  test.setTimeout(60_000);
  const state = await fixture(page);
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  await expect(page.locator('[aria-label="Vision result"]')).toContainText("Draft generation failed");
  const trace = page.getByRole("region", { name: "Operation trace", exact: true });
  await trace.locator("summary").filter({ hasText: "Filter steps" }).click();
  await trace.getByRole("button", { name: "Branch 2", exact: true }).click();
  await expect(trace.getByLabel("Selected operation")).toContainText("Operation 4");
  await expect(trace.getByLabel("Selected operation")).toContainText("Branch B");
  await trace.getByRole("button", { name: "All operations", exact: true }).click();
  await trace.getByRole("button", { name: "View operation 2 click", exact: true }).click();
  await expect(trace.getByAltText("Before operation frame")).toHaveCount(0);
  await expect(trace.getByAltText("After operation frame")).toHaveCount(0);
  await expect(page.getByAltText("Vision browser screen")).toBeVisible();
  state.extra = 1;
  await expect(trace.getByRole("button", { name: "View operation 5 click", exact: true })).toBeVisible({ timeout: 12_000 });
  await expect(trace.getByLabel("Selected operation")).toContainText("Operation 2");
  await trace.getByLabel("Follow live").check();
  await expect(trace.getByLabel("Selected operation")).toContainText("Operation 5");
  await page.getByRole("button", { name: "New exploration", exact: true }).click();
  const input = page.getByLabel("Target URL", { exact: true });
  await input.fill("https://fixture.test/"); await input.press("Home");
  await expect(trace.getByLabel("Selected operation")).toContainText("Operation 5");
  await trace.focus(); await page.keyboard.press("Home");
  await expect(trace.getByLabel("Selected operation")).toContainText("Operation 1");
  state.exploration = "completed";
  await page.reload();
  await expect(page.locator('[aria-label="Vision result"]')).toContainText(sessionA);
  await page.locator("summary").filter({ hasText: /^Technical details$/ }).click();
  await expect(page.getByText("Saved progress", { exact: true })).toBeVisible();
});

test("a saved session focuses the website and New opens a consent-gated form", async ({ page }) => {
  const state = await fixture(page);
  state.policy.enabled = true;
  state.exploration = "unavailable";
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  const form = page.getByRole("region", { name: "Vision exploration", exact: true });
  await expect(page.getByRole("region", { name: "Vision browser screen" })).toBeInViewport();
  await expect(form).toBeHidden();
  await page.getByRole("button", { name: "New exploration", exact: true }).click();
  await expect(form.getByLabel("Target URL", { exact: true })).toBeVisible();
  await expect(page.locator('[aria-label="Vision result"]')).toContainText(sessionA);
  await form.getByLabel("Target URL", { exact: true }).fill("https://fixture.test/");
  await form.getByLabel("Exploration intent", { exact: true }).fill("Explore the fixture navigation");
  await expect(form.getByLabel("Use Vision Agent", { exact: true })).toHaveCount(0);
  await form.getByRole("button", { name: "Start advisory exploration", exact: true }).click();
  expect(state.submissions).toHaveLength(0);
  await page.getByRole("dialog").getByRole("button", { name: "Start advisory exploration", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(sessionC));
  await expect(page.locator('[aria-label="Vision result"]')).toContainText(sessionC);
  expect(state.submissions).toEqual([{ project_id: project, target_url: "https://fixture.test/", task_intent: "Explore the fixture navigation", use_vision: true, expected_provider: "huggingface", expected_model: "custom/hf-model" }]);
  await page.reload();
  await expect(page.locator('[aria-label="Vision result"]')).toContainText(sessionC);
  await expect(form).toBeHidden();
  expect(state.submissions).toHaveLength(1);
});

for (const legacy of [false, true]) test(`Reload starts a new ${legacy ? "legacy" : "v4"} session from the saved request`, async ({ page }) => {
  const state = await fixture(page, legacy);
  state.policy.enabled = true;
  state.exploration = "unavailable";
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  // Reload must work with an empty form after a direct navigation to a saved session.
  const form = page.getByRole("region", { name: "Vision exploration", exact: true });
  await expect(page.locator("#vision-new input[type=url]")).toHaveValue("");
  await expect(form).toBeHidden();
  const reload = page.getByRole("button", { name: "Reload", exact: true });
  await reload.click();
  await expect(page.getByRole("dialog")).toContainText("saved target and intent");
  expect(state.reloads).toHaveLength(0);
  await page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }).click();
  expect(state.reloads).toHaveLength(0);
  await reload.click();
  await page.getByRole("dialog").getByRole("button", { name: "Start new session", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(sessionC));
  expect(state.reloads).toHaveLength(1);
  expect(state.reloads[0]).toMatchObject({ sessionId: sessionA, payload: { expected_provider: "huggingface", expected_model: "custom/hf-model" } });
  expect(state.reloads[0].key).toBeTruthy();
  expect(state.submissions).toHaveLength(0);
  await page.getByRole("button", { name: "History", exact: true }).click();
  await expect(page.getByRole("region", { name: "Visual exploration sessions", exact: true })).toContainText(sessionA);
  await page.reload();
  await expect(page).toHaveURL(new RegExp(sessionC));
  expect(state.reloads).toHaveLength(1);
});

test("Reload is disabled while running or when Vision is disabled", async ({ page }) => {
  const state = await fixture(page);
  state.policy.enabled = true;
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  await expect(page.getByRole("button", { name: "Reload", exact: true })).toBeDisabled();
  state.exploration = "completed";
  state.policy.enabled = false;
  await page.reload();
  await expect(page.getByRole("button", { name: "Reload", exact: true })).toBeDisabled();
  expect(state.reloads).toHaveLength(0);
});

test("switching session discards a late response from the prior session", async ({ page }) => {
  test.setTimeout(45_000);
  const state = await fixture(page);
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  await expect(page.getByRole("region", { name: "Operation trace", exact: true })).toBeVisible();
  state.delay = true;
  await page.locator("summary").filter({ hasText: /^Technical details$/ }).click();
  await page.getByRole("button", { name: "Refresh saved result", exact: true }).click();
  await expect.poll(() => state.delay).toBe(false);
  await page.getByRole("button", { name: "History", exact: true }).click();
  await page.getByRole("region", { name: "Visual exploration sessions", exact: true }).getByRole("button", { name: "View", exact: true }).nth(1).click();
  await expect(page.locator('[aria-label="Vision result"]')).toContainText(sessionB);
  state.release();
  await expect(page.locator('[aria-label="Vision result"]')).not.toContainText(sessionA);
  await expect(page).toHaveURL(new RegExp(sessionB));
});


test("legacy seven-frame gallery can select the sixth sibling", async ({ page }) => {
  await fixture(page, true);
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  await expect(page.getByRole("region", { name: "Exploration summary" }).getByText("Legacy evidence only. Verified locators were not recorded for this session.")).toBeVisible();
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
  await page.getByRole("button", { name: "New exploration", exact: true }).click();
  const form = page.getByRole("region", { name: "Vision exploration", exact: true });
  await form.getByLabel("Target URL", { exact: true }).fill("https://fixture.test/");
  await form.getByLabel("Exploration intent", { exact: true }).fill("Explore synthetic controls");
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
  await expect(form.getByLabel("Use Vision Agent", { exact: true })).toHaveCount(0);
  expect(state.submissions).toHaveLength(1);
  expect(state.submissions[0]).toMatchObject({ expected_provider: "huggingface", expected_model: "custom/hf-model" });
  state.stale = false;
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
  await expect(settings.getByText("Vision settings could not be loaded.", { exact: true })).toBeVisible();
  state.catalogueFails = false;
  await settings.getByRole("button", { name: "Retry Vision settings" }).click();
  await settings.getByLabel("Vision provider", { exact: true }).selectOption("gemini");
  await expect(settings).toContainText("Gehihi (Google Gemini) is not configured on the server.");
  await settings.getByRole("checkbox", { name: /I accept raw screenshot/ }).check();
  await expect(settings.getByLabel("Enable vision exploration")).toBeDisabled();
  await expect(settings.getByRole("textbox")).toHaveCount(0);
});

test("selected operation changes the single viewer and keeps image failure independent", async ({ page }) => {
  await fixture(page);
  await page.goto(dashboard + "/agent?vision=" + sessionA);
  const screen = page.getByRole("region", { name: "Vision browser screen" });
  await page.getByRole("button", { name: "View operation 2 click", exact: true }).click();
  await expect(screen).toContainText("Before operation 2");
  await expect(screen.getByRole("img")).toBeVisible();
  await screen.getByRole("button", { name: "After", exact: true }).click();
  await expect(screen).toContainText("Screen unavailable or access revoked.");
  await expect(screen.getByRole("img")).toHaveCount(0);
  await page.getByRole("button", { name: "View operation 4 click", exact: true }).click();
  await expect(screen).toContainText("Before operation 4");
  await expect(screen.getByRole("img")).toBeVisible();
  await screen.getByRole("button", { name: "After", exact: true }).click();
  await expect(screen).toContainText("After operation 4");
  await screen.getByRole("button", { name: "Return to live" }).click();
  await expect(screen).toContainText("Live browser");
});

test("Vision project settings save to the selected project rather than the generation default", async ({ page }) => {
  await fixture(page);
  const otherProject = "00000000-0000-4000-8000-000000000099";
  const writes: string[] = [];
  const headers = { "access-control-allow-origin": dashboard!, "access-control-allow-credentials": "true" };
  await page.route("**/api/v1/projects", (route) => route.fulfill({ headers, json: [
    { id: project, name: "First project", default_target: "web_ui" },
    { id: otherProject, name: "Second project", default_target: "web_ui" },
  ] }));
  await page.route("**/test-generations/projects/*/policy", async (route) => {
    if (route.request().method() === "PUT") writes.push(route.request().url());
    await route.fulfill({ headers, json: { allowed_origins: ["https://fixture.test"], vision_max_hops: 3, vision_max_states: 8 } });
  });
  await page.route("**/vision/explorations/" + sessionA, (route) => route.fulfill({ headers, json: {
    id: sessionA, project_id: otherProject, state: "completed", trace_version: "v4", provider: "huggingface", model: "fixture", correlation_id: sessionA,
  } }));
  await page.goto(dashboard + "/agent?vision=" + sessionA);
  await expect(page.getByLabel("Session controls")).toContainText("Second project");
  await page.locator("summary").filter({ hasText: /^Project settings$/ }).click();
  await page.getByLabel("Allowed origins", { exact: true }).fill("https://second.fixture.test");
  await page.getByRole("button", { name: "Save project policy" }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toContain("/projects/" + otherProject + "/policy");
});

test("default exploration and draft deep links retain the human approval dialog", async ({ page }) => {
  await fixture(page);
  const headers = { "access-control-allow-origin": dashboard!, "access-control-allow-credentials": "true" };
  const decisions: unknown[] = [];
  const draft = { id: "fixture-draft", planning_request_id: "fixture-request", correlation_id: "fixture", state: "pending_review", title: "Fixture draft", playwright_test_source: "test('fixture', async () => {});", source_hash: "a".repeat(64), assumptions: [], stop_conditions: [], provenance: {}, linked_test_case_id: null, linked_run_id: null };
  await page.route("**/test-generations/drafts/fixture-draft", (route) => route.fulfill({ headers, json: draft }));
  await page.route("**/test-generations/fixture-request", (route) => route.fulfill({ headers, json: { id: "fixture-request", project_id: project, state: "completed", redacted_request: "Test synthetic controls", target_url: "https://fixture.test", correlation_id: "fixture", request_hash: "a".repeat(64) } }));
  await page.route("**/test-generations/drafts/fixture-draft/decision", (route) => { decisions.push(route.request().postDataJSON()); return route.fulfill({ headers, json: { ...draft, state: "approved" } }); });
  await page.goto(dashboard + "/agent");
  await expect(page.getByRole("tab", { name: "Vision Agent" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByAltText("Vision browser screen")).toBeVisible();
  await page.evaluate(() => window.history.pushState(null, "", "?draft=fixture-draft&vision=00000000-0000-4000-8000-000000000001"));
  await expect(page.getByRole("tab", { name: "Playwright test" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("region", { name: "Generated draft" })).toContainText("Fixture draft");
  await page.getByRole("button", { name: "Approve and dispatch once" }).click();
  expect(decisions).toHaveLength(0);
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
  expect(decisions).toHaveLength(0);
  await page.getByRole("button", { name: "Approve and dispatch once" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Approve and dispatch", exact: true }).click();
  await expect.poll(() => decisions.length).toBe(1);
});

test("click highlight stays on its before frame and scales on desktop and mobile", async ({ page }) => {
  const state = await fixture(page); state.highlight = true;
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(dashboard + "/agent?vision=" + sessionA);
  const screen = page.getByRole("region", { name: "Vision browser screen" });
  const marker = screen.getByTestId("vision-click-marker");
  await page.getByRole("button", { name: "View operation 4 click", exact: true }).click();
  await expect(marker).toBeVisible();
  const checkPosition = async () => {
    const error = await screen.evaluate((node) => {
      const img = node.querySelector("img")!.getBoundingClientRect();
      const point = node.querySelector('[data-testid="vision-click-marker"]')!.getBoundingClientRect();
      const scale = Math.min(img.width / 1280, img.height / 720);
      return {
        x: Math.abs(point.x + point.width / 2 - (img.x + (img.width - 1280 * scale) / 2 + 320 * scale)),
        y: Math.abs(point.y + point.height / 2 - (img.y + (img.height - 720 * scale) / 2 + 240 * scale)),
      };
    });
    expect(error.x).toBeLessThan(2); expect(error.y).toBeLessThan(2);
  };
  await checkPosition();
  await page.screenshot({ path: "../../.pytest_cache/agent-highlight-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(marker).toBeVisible();
  await expect.poll(async () => marker.evaluate(el => el.getBoundingClientRect().width)).toBe(32);
  await checkPosition();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await screen.screenshot({ path: "../../.pytest_cache/agent-highlight-mobile.png" });
  await screen.getByRole("button", { name: "After", exact: true }).click();
  await expect(screen).toContainText("After operation 4");
  await expect(marker).toHaveCount(0);
  await screen.getByRole("button", { name: "Return to live" }).click();
  await expect(screen).toContainText("Live browser");
  await expect(marker).toHaveCount(0);
});

test("new click previews once, honors reduced motion and keeps live polling", async ({ page }) => {
  test.setTimeout(40_000);
  const state = await fixture(page); state.highlight = true;
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(dashboard + "/agent?vision=" + sessionA);
  const screen = page.getByRole("region", { name: "Vision browser screen" });
  const marker = screen.getByTestId("vision-click-marker");
  await expect(page.getByRole("button", { name: "View operation 4 click", exact: true })).toBeVisible();
  await expect(marker).toHaveCount(0);
  const calls = state.screenCalls;
  state.extra = 1;
  await expect(marker).toBeVisible({ timeout: 12_000 });
  await expect(screen.getByText("Recent click · operation 5 · recorded frame")).toBeVisible();
  expect(await marker.evaluate(el => getComputedStyle(el).animationName)).toBe("none");
  await expect(marker).toHaveCount(0, { timeout: 4000 });
  await expect(screen.getByText("Live browser · updates every second")).toBeVisible();
  expect(state.screenCalls).toBeGreaterThan(calls);
  await page.waitForTimeout(5500);
  await expect(marker).toHaveCount(0);
});

test("late click frame and session switch cannot put a marker on a different image", async ({ page }) => {
  const state = await fixture(page); state.highlight = true;
  let requested = false, release = () => {};
  await page.route("**/operation-frames/" + sessionA + "-before2", async route => {
    requested = true;
    await new Promise<void>(resolve => { release = resolve; });
    await route.fulfill({ body: clickBefore, contentType: "image/png", headers: { "access-control-allow-origin": dashboard!, "access-control-allow-credentials": "true" } }).catch(() => undefined);
  });
  await page.goto(dashboard + "/agent?vision=" + sessionA);
  const screen = page.getByRole("region", { name: "Vision browser screen" });
  await page.getByRole("button", { name: "View operation 2 click", exact: true }).click();
  await expect.poll(() => requested).toBe(true);
  await expect(screen.getByTestId("vision-click-marker")).toHaveCount(0);
  await page.getByRole("button", { name: "View operation 4 click", exact: true }).click();
  await expect(screen.getByTestId("vision-click-marker")).toBeVisible();
  release();
  await expect(screen).toContainText("Before operation 4");
  await page.getByRole("button", { name: "History", exact: true }).click();
  await page.getByRole("region", { name: "Visual exploration sessions" }).getByRole("button", { name: "View", exact: true }).nth(1).click();
  await expect(page).toHaveURL(new RegExp(sessionB));
  await expect(screen.getByTestId("vision-click-marker")).toHaveCount(0);
  await expect(screen).toContainText("Live browser");
});

for (const condition of ["rejected", "unknown", "deleted", "mismatch", "denied", "temporary", "aspect"] as const) test("no fabricated click highlight for " + condition, async ({ page }) => {
  const state = await fixture(page); state.highlight = true;
  const headers = { "access-control-allow-origin": dashboard!, "access-control-allow-credentials": "true" };
  await page.route("**/trace*", route => route.fulfill({ headers, json: {
    session_id: sessionA, schema_version: "v1", revision: "1", trace_version: "v4", locators: [], next_sequence: 1, has_more: false,
    items: [{ id: "click-fixture", sequence: 1, purpose: "explore", action_kind: "click", status: ["rejected", "unknown"].includes(condition) ? condition : "completed", started_at: "2026-09-08T12:00:00Z", outcome_code: "observed", locator_id: null,
      before: { id: "fixture-before", availability: condition === "deleted" ? "deleted" : "retained", reason_code: null },
      after: { id: null, availability: "missing", reason_code: "capture_failed" },
      executed_click: { x: 0.5, y: 0.5, viewport_width: 1280, viewport_height: 720, before_frame_id: condition === "mismatch" ? "wrong" : "fixture-before", confirmed_at: "2026-09-08T12:00:01Z" },
    }],
  } }));
  await page.route("**/operation-frames/fixture-before", route => ["denied", "temporary"].includes(condition)
    ? route.fulfill({ status: condition === "denied" ? 403 : 503, headers })
    : route.fulfill({ body: condition === "aspect" ? png : clickBefore, contentType: "image/png", headers }));
  await page.goto(dashboard + "/agent?vision=" + sessionA);
  await page.getByRole("button", { name: "View operation 1 click" }).click();
  const screen = page.getByRole("region", { name: "Vision browser screen" });
  if (condition === "deleted") await expect(screen).toContainText("This frame was deleted.");
  else if (condition === "denied") await expect(screen).toContainText("Screen unavailable or access revoked.");
  else if (condition === "temporary") await expect(screen).toContainText("Saved screen unavailable.");
  else await expect(screen.getByRole("img")).toBeVisible();
  await expect(screen.getByTestId("vision-click-marker")).toHaveCount(0);
});

test("nonadmin reads policy and safe failures while partial trace and draft failure stay visible", async ({ page }) => {
  const state = await fixture(page); state.exploration = "unavailable"; state.completionReason = "provider_rate_limited";
  await page.goto(`${dashboard}/agent?vision=${sessionA}`);
  const settings = await openSettings(page);
  await expect(settings).toContainText("Provider: Hugging Face");
  await expect(settings.getByRole("combobox")).toHaveCount(0);
  await expect(settings.getByRole("button", { name: "Save vision settings" })).toHaveCount(0);
  const result = page.locator('[aria-label="Vision result"]');
  await expect(result).toContainText("quota or request rate limit");
  await expect(result).toContainText("Draft generation failed");
  await expect(page.getByRole("region", { name: "Operation trace", exact: true })).toContainText("Open page");
  expect(state.writes).toHaveLength(0);
});
