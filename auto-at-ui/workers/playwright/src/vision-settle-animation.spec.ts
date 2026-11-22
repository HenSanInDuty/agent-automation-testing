import { expect, test, type Page } from "@playwright/test";
import { equivalentState, inspectState, interactionDiff, settleState } from "./vision-checkpoints.js";
import { visionLogScope } from "./vision-observability.js";
import { carouselHtml, leftAnimationHtml, marqueeTranslateHtml, pulsingControlHtml, spinFadeHtml, staticControlHtml,
  strongPulseHtml, widthAnimationHtml } from "./fixtures/settle-animated-control.js";

// r13 diagnosis of the r12 `settle_timeout` on the homepage: the scope-`all` interaction fingerprint kept the
// clipped bounds of every visible control, so an infinite CSS scale animation on a control's ancestor made the
// state differ on nearly every sample. r14 / ADR 042: `equivalentState` tolerates small box drift (A) and measures
// controls under a presentation-only infinite animation by layout box (B). Anything that really changes stays a change.

async function settleWithLog(page: Page, windowMs: number, quietMs: number) {
  const lines: string[] = [], original = console.error;
  console.error = (line: string) => lines.push(line);
  try {
    const result = await visionLogScope.run({ context: {}, fields: { session_id: "r14", operation_id: "r14", stage: "operation_execute" } },
      () => settleState(page, Date.now() + windowMs, quietMs));
    return { result, log: lines.length ? JSON.parse(lines[0]) : null };
  } finally { console.error = original; }
}
// Freeze every animation at a chosen time so the two snapshots are deterministic.
const seek = (page: Page, ms: number) => page.evaluate((time) => document.getAnimations().forEach(a => { a.pause(); a.currentTime = time; }), ms);
async function snapshotPair(page: Page, mutate: () => Promise<void>) {
  const before = await inspectState(page, true);
  const unchanged = equivalentState(before, await inspectState(page, true));
  await mutate();
  return { unchanged, equivalent: equivalentState(before, await inspectState(page, true)) };
}

test("a static copy of the widget settles (negative control)", async ({ page }) => {
  await page.setContent(staticControlHtml);
  const { result, log } = await settleWithLog(page, 3000, 800);
  expect(result.settled).toBe(true);
  expect(log).toBeNull();
});

test("a presentation-only pulse should not block settle (r13 failure, fixed by ADR 042)", async ({ page }) => {
  await page.setContent(pulsingControlHtml);
  const { result, log } = await settleWithLog(page, 4000, 800);
  expect(result.settled).toBe(true);
  expect(log).toBeNull();
});

test("a strong pulse and a rotate+fade animation also settle", async ({ page }) => {
  for (const html of [strongPulseHtml, spinFadeHtml]) {
    await page.setContent(html);
    expect((await settleWithLog(page, 4000, 800)).result.settled).toBe(true);
  }
});

test("the pulse changes geometry only: no control is added, removed or relabelled", async ({ page }) => {
  await page.setContent(pulsingControlHtml);
  const first = await inspectState(page, true);
  let diff = interactionDiff(first, first);
  // Sample until the animation has moved the link's size at least once.
  for (let i = 0; i < 40 && diff.interaction_geometry_only === 0; i++) {
    await page.waitForTimeout(60);
    diff = interactionDiff(first, await inspectState(page, true));
  }
  expect(diff).toMatchObject({ interaction_content_added: 0, interaction_content_removed: 0, interaction_changed_tags: {} });
  expect(diff.interaction_geometry_only).toBeGreaterThan(0);
});

test("pulse phases compare equal, including an amplitude beyond the IoU tolerance (layout box)", async ({ page }) => {
  for (const html of [pulsingControlHtml, strongPulseHtml, spinFadeHtml]) {
    await page.setContent(html);
    await seek(page, 0);
    const base = await inspectState(page, true);
    await seek(page, 600);
    const peak = await inspectState(page, true);
    expect(base.fingerprint).not.toBe(peak.fingerprint); // the stored fingerprint still differs...
    expect(equivalentState(base, peak)).toBe(true); // ...but the states are the same for settle/dispatch gates
    expect(equivalentState(peak, base)).toBe(true);
  }
});

test("a drifting control is a change beyond the geometry tolerance", async ({ page }) => {
  await page.setContent(staticControlHtml);
  const widget = (px: number) => page.evaluate((left) => { (document.querySelector(".widget") as HTMLElement).style.left = `${left}px`; }, 600 + px);
  expect(await snapshotPair(page, () => widget(2))).toEqual({ unchanged: true, equivalent: true });
  await widget(0);
  expect(await snapshotPair(page, () => widget(20))).toEqual({ unchanged: true, equivalent: false });
  await widget(0);
  // Same centre but 30% wider: IoU below the ratio.
  expect(await snapshotPair(page, () => page.evaluate(() => { (document.querySelector(".widget") as HTMLElement).style.width = "130px"; })))
    .toEqual({ unchanged: true, equivalent: false });
});

test("relabelling a control is a change (aria-label, text, disabled)", async ({ page }) => {
  for (const mutate of [
    () => page.evaluate(() => document.querySelector("a")!.setAttribute("aria-label", "Stop now")),
    () => page.evaluate(() => { document.querySelector("button")!.textContent = "Renamed"; }),
    () => page.evaluate(() => { (document.querySelector("button") as HTMLButtonElement).disabled = true; }),
  ]) {
    await page.setContent(pulsingControlHtml);
    await seek(page, 0);
    expect(await snapshotPair(page, mutate)).toEqual({ unchanged: true, equivalent: false });
  }
});

test("a control that appears or disappears is a change", async ({ page }) => {
  await page.setContent(pulsingControlHtml);
  await seek(page, 0);
  expect(await snapshotPair(page, () => page.evaluate(() => { document.body.insertAdjacentHTML("beforeend", '<button style="position:absolute;top:50px">New</button>'); })))
    .toEqual({ unchanged: true, equivalent: false });
  await page.setContent(pulsingControlHtml);
  await seek(page, 0);
  expect(await snapshotPair(page, () => page.evaluate(() => document.querySelector("button")!.remove())))
    .toEqual({ unchanged: true, equivalent: false });
});

test("an opaque non-control overlay covering the pulsing control is a change (centre hit test)", async ({ page }) => {
  await page.setContent(pulsingControlHtml);
  await seek(page, 0);
  expect(await snapshotPair(page, () => page.evaluate(() => {
    document.body.insertAdjacentHTML("beforeend", '<div style="position:absolute;left:560px;top:260px;width:200px;height:200px;background:#fff"></div>');
  }))).toEqual({ unchanged: true, equivalent: false });
});

test("a control overlay covering the pulsing control is a change", async ({ page }) => {
  await page.setContent(pulsingControlHtml);
  await seek(page, 0);
  expect(await snapshotPair(page, () => page.evaluate(() => {
    document.body.insertAdjacentHTML("beforeend", '<button style="position:absolute;left:560px;top:260px;width:200px;height:200px">Cover</button>');
  }))).toEqual({ unchanged: true, equivalent: false });
});

test("a carousel translate bringing another slide or moving a slide is a change, even next to an eligible pulse", async ({ page }) => {
  for (const shift of [300, 20]) {
    await page.setContent(carouselHtml);
    await seek(page, 0);
    expect(await snapshotPair(page, () => page.evaluate((px) => { document.getElementById("track")!.style.transform = `translateX(-${px}px)`; }, shift)))
      .toEqual({ unchanged: true, equivalent: false });
  }
});

test("infinite animations that translate or resize are never exempt (marquee, left, width)", async ({ page }) => {
  for (const html of [marqueeTranslateHtml, leftAnimationHtml, widthAnimationHtml]) {
    await page.setContent(html);
    await seek(page, 0);
    const base = await inspectState(page, true);
    await seek(page, 900);
    expect(equivalentState(base, await inspectState(page, true))).toBe(false);
  }
});

test("a moving infinite animation keeps settle from succeeding (state_kept_changing)", async ({ page }) => {
  await page.setContent(leftAnimationHtml);
  const { result, log } = await settleWithLog(page, 2500, 800);
  expect(result.settled).toBe(false);
  expect(log).toMatchObject({ reason: "state_kept_changing", url_changes: 0, form_value_changes: 0 });
  expect(log.state_changes).toBeGreaterThan(3);
});

test("slow drift is compared to the quiet-window reference, not the previous sample", async ({ page }) => {
  await page.setContent(staticControlHtml);
  // 2 px steps stay inside the tolerance sample to sample, but the control walks away by 40 px in total.
  await page.evaluate(() => {
    const el = document.querySelector(".widget") as HTMLElement; let left = 600;
    setInterval(() => { left += 2; el.style.left = `${left}px`; }, 50);
  });
  const { result, log } = await settleWithLog(page, 2500, 800);
  expect(result.settled).toBe(false);
  expect(log).toMatchObject({ reason: "state_kept_changing" });
});
