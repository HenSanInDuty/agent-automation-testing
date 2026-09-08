import { expect, test, type Locator, type Page } from "@playwright/test";
import { groundLocator } from "./vision-locators.js";
import { inspectState, equivalentState } from "./vision-checkpoints.js";
import { startVisionTarget } from "./fixtures/vision-target.js";

let target: Awaited<ReturnType<typeof startVisionTarget>>;
test.beforeAll(async () => { target = await startVisionTarget(); });
test.afterAll(async () => { await target.close(); });
test.beforeEach(async ({ page }) => { await page.setViewportSize({ width: 1280, height: 720 }); await page.goto(target.origin); });

async function ground(page: Page, locator: Locator, editable = false) {
  const box = await locator.boundingBox(); expect(box).not.toBeNull();
  return groundLocator(page, (box!.x + box!.width / 2) / 1279, (box!.y + box!.height / 2) / 719, editable);
}

test("grounds role/name to the exact nested icon's interactive ancestor", async ({ page }) => {
  const result = await ground(page, page.locator("svg"));
  expect(result).toMatchObject({ status: "verified", matched_count: 1, target_match: true, actionable: true,
    descriptor: { strategy: "role", role: "button", value: "Icon action" } });
  await result.target?.dispose();
});
test("duplicate accessible names stay ambiguous without a unique fallback", async ({ page }) => {
  const result = await groundLocator(page, 330 / 1279, 30 / 719);
  expect(result).toMatchObject({ status: "ambiguous", reason_code: "multiple_matches", matched_count: 2 });
});
test("open shadow and same-origin iframe carry explicit grounded scopes", async ({ page }) => {
  const shadow = await ground(page, page.getByRole("button", { name: "Shadow action" }));
  expect(shadow).toMatchObject({ status: "verified", descriptor: { scope: [{ kind: "shadow", selector: 'section[id="shadow-host"]' }] } });
  await shadow.target?.dispose();
  const embedded = await ground(page, page.frameLocator("#embedded").getByRole("button"));
  expect(embedded).toMatchObject({ status: "verified", descriptor: { scope: [{ kind: "iframe", selector: 'iframe[id="embedded"]' }] } });
  await embedded.target?.dispose();
});
test("sensitive accessible identity never becomes verified", async ({ page }) => {
  const result = await ground(page, page.getByRole("button", { name: "user@example.test" }));
  expect(result).toMatchObject({ status: "redacted", descriptor: null });
  expect(JSON.stringify(result)).not.toContain("user@example.test");
});
test("Playwright confirms the accessible name rather than assuming innerText", async ({ page }) => {
  await page.getByRole("button", { name: "No operation" }).evaluate((el) => el.setAttribute("aria-label", "Accessible replacement"));
  const result = await ground(page, page.getByRole("button", { name: "Accessible replacement" }));
  expect(result.descriptor?.value).toBe("Accessible replacement");
  await result.target?.dispose();
});
test("disabled, covered, password, closed shadow and canvas targets are unresolved", async ({ page }) => {
  await page.setContent('<button disabled style="width:100px;height:40px">Disabled</button><input type="password" aria-label="Sign in"><canvas width="100" height="50"></canvas><div id="closed"></div>');
  expect((await ground(page, page.getByRole("button"))).status).not.toBe("verified");
  expect((await ground(page, page.locator("input"), true)).reason_code).toBe("credential_input_unsupported");
  expect((await ground(page, page.locator("canvas"))).status).toBe("unsupported");
  await page.locator("#closed").evaluate((el) => { el.attachShadow({ mode: "closed" }).innerHTML = '<button>Hidden</button>'; });
  expect((await ground(page, page.locator("#closed"))).status).toBe("unsupported");
  await page.setContent('<button style="width:100px;height:40px">Covered</button><div style="position:fixed;inset:0;background:white"></div>');
  expect((await ground(page, page.getByRole("button"))).status).toBe("unsupported");
});
test("cross-origin frame is explicitly unsupported", async ({ page }) => {
  const other = await startVisionTarget();
  try {
    await page.locator("#embedded").evaluate((el, url) => (el as HTMLIFrameElement).src = `${url}/frame`, other.origin);
    await page.frameLocator("#embedded").getByRole("button").waitFor();
    expect((await ground(page, page.frameLocator("#embedded").getByRole("button"))).reason_code).toBe("cross_origin_frame");
  } finally { await other.close(); }
});
test("same URL modal and form/scroll changes fail checkpoint equivalence", async ({ page }) => {
  const before = await inspectState(page);
  await page.getByRole("button", { name: "Toggle modal" }).click();
  const modal = await inspectState(page);
  expect(modal.url_fingerprint).toBe(before.url_fingerprint);
  expect(equivalentState(before, modal)).toBe(false);
  await page.getByRole("button", { name: "Toggle modal" }).click();
  expect(equivalentState(before, await inspectState(page))).toBe(true);
  await page.getByRole("textbox").fill("private fixture value");
  const form = await inspectState(page);
  expect(form.fingerprint).toBe(before.fingerprint);
  expect(equivalentState(before, form)).toBe(false);
  await page.mouse.wheel(0, 300); await page.waitForTimeout(100);
  expect(equivalentState(form, await inspectState(page))).toBe(false);
});
