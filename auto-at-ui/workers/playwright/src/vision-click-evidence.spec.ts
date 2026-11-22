import { test, expect } from "@playwright/test";
import { observeClick } from "./vision-click-evidence.js";

test("trusted click coordinates remain observable on a transformed target", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.setContent('<button style="margin:80px;transform:scale(1.4);border:3px solid black">News</button>');
  const target = await page.getByRole("button", { name: "News" }).elementHandle();
  const capture = await observeClick(target!);
  let settled = false;
  void capture.result.then(() => { settled = true; });
  await page.getByRole("button").dispatchEvent("pointerdown", { clientX: 1, clientY: 1 });
  expect(settled).toBe(false);
  const bounds = await target!.boundingBox();
  await page.getByRole("button").click();
  const point = await capture.result;
  expect(point).toMatchObject({ width: 1280, height: 720 });
  expect(point!.x).toBeGreaterThanOrEqual(bounds!.x);
  expect(point!.x).toBeLessThanOrEqual(bounds!.x + bounds!.width);
  expect(point!.y).toBeGreaterThanOrEqual(bounds!.y);
  expect(point!.y).toBeLessThanOrEqual(bounds!.y + bounds!.height);
  await capture.dispose();
});

test("disposing without an actual click records no point", async ({ page }) => {
  await page.setContent("<button>News</button>");
  const capture = await observeClick((await page.getByRole("button").elementHandle())!);
  await capture.dispose();
  expect(await capture.result).toBeNull();
});
