import { expect, test } from "@playwright/test";
import { inspectState } from "./vision-checkpoints.js";
import { captureHistory, returnToHistory, validateHistory } from "./vision-history.js";

test.beforeEach(async ({ page }) => {
  await page.route("http://history.test/**", route => route.fulfill({
    contentType: "text/html", body: '<button>Continue</button><input type="hidden" value="original">',
  }));
  await page.goto("http://history.test/source");
});

test("one saved-entry restoration skips duplicate history entries without replay", async ({ page }) => {
  const saved = await captureHistory(page, await inspectState(page), "GET");
  expect(saved).not.toBeNull();
  await page.evaluate(() => { history.pushState({}, "", "/next"); history.pushState({}, "", "/next?view=latest"); });
  const from = await validateHistory(saved, page);
  await returnToHistory(saved!, page, from, 2000);
  expect(page.url()).toBe("http://history.test/source");
  await expect(validateHistory(saved, page)).rejects.toThrow("history_checkpoint_unavailable");
});

for (const mutation of ["other_page", "overwritten", "missing", "current_changed"] as const) {
  test(`history selection rejects ${mutation}`, async ({ page, context }) => {
    const saved = await captureHistory(page, await inspectState(page), "GET");
    if (mutation === "overwritten") await page.evaluate(() => history.replaceState({}, "", "/overwritten"));
    await page.evaluate(() => history.pushState({}, "", "/next"));
    if (mutation === "current_changed") {
      const from = await validateHistory(saved, page);
      await page.evaluate(() => history.pushState({}, "", location.href));
      await expect(returnToHistory(saved!, page, from, 2000)).rejects.toThrow("history_checkpoint_unavailable");
      expect(page.url()).toBe("http://history.test/next");
    } else {
      if (mutation === "missing") {
        const cdp = await context.newCDPSession(page);
        await cdp.send("Page.resetNavigationHistory");
        await cdp.detach();
      }
      const target = mutation === "other_page" ? await context.newPage() : page;
      await expect(validateHistory(saved, target)).rejects.toThrow("history_checkpoint_unavailable");
    }
  });
}

test("unknown and POST documents cannot supply history capabilities", async ({ page }) => {
  const state = await inspectState(page);
  expect(await captureHistory(page, state)).toBeNull();
  expect(await captureHistory(page, state, "POST")).toBeNull();
  await page.evaluate(() => history.replaceState({}, "", "/changed"));
  expect(await captureHistory(page, state, "GET")).toBeNull();
});

test("a form-submit history entry is rejected even with a stale GET hint", async ({ page }) => {
  await page.setContent('<form action="/submitted" method="post"><button>Submit fixture</button></form>');
  await Promise.all([page.waitForURL("**/submitted"), page.getByRole("button").click()]);
  expect(await captureHistory(page, await inspectState(page), "GET")).toBeNull();
});

test("an expired restoration budget never starts history navigation", async ({ page }) => {
  const saved = await captureHistory(page, await inspectState(page), "GET");
  await page.evaluate(() => history.pushState({}, "", "/next"));
  const from = await validateHistory(saved, page);
  await expect(returnToHistory(saved!, page, from, 0)).rejects.toThrow("history_restore_timeout");
  expect(page.url()).toBe("http://history.test/next");
});
