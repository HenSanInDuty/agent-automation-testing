import { expect, test, type Page } from "@playwright/test";
import { equivalentState, inspectState, interactionDiff, settleState } from "./vision-checkpoints.js";

// r20 diagnosis (offline, read-only probes of https://mongchiton.vn under the worker's own inspectState/settleState):
// with the NHAN VAT / THU CUOI tabs active and the viewport on their panel (scroll y about 1200), the home page runs
// a "switcher" widget: overlapping cards whose `.active` class moves on a timer, restarting a FINITE (iterations 1)
// scale / margin-left animation on each step and re-ordering the stacking, so the five hit probes of the same
// control flip on nearly every sample (140+ changes in one 25 s burst, every 125 ms, longest quiet about 120-250 ms,
// repeating about every 36 s). ADR 042 does not absorb it: (A) tolerates only 3 px / IoU 0.8 on the box and requires
// equal hit tests; (B) needs an INFINITE passive CSS animation. A scroll op that lands inside a burst ends with
// `settle_timeout` / `state_kept_changing` (r12 op 8, r19 op 9; the TOP click is incidental).
// The fixture reproduces only that mechanism (timer-driven finite animations on overlapping cards), not the site.
const switcherHtml = (churnMs: number) => `<!doctype html><style>
  body{margin:0;background:#fff}
  #row{position:relative;height:200px;width:520px;margin:20px}
  .card{position:absolute;top:0;width:140px;height:160px;display:block;background:#ccd;border:1px solid #446;z-index:1}
  .card:nth-child(1){left:0}.card:nth-child(2){left:90px}.card:nth-child(3){left:180px}.card:nth-child(4){left:270px}
  .card.active{z-index:9;animation:pop 90ms ease-out 1}
  @keyframes pop{from{scale:.9;margin-left:12px}to{scale:1;margin-left:0}}
</style><div id="row"><a class="card" href="#a">A</a><a class="card" href="#b">B</a><a class="card" href="#c">C</a><a class="card" href="#d">D</a></div>
<script>
  const cards = Array.from(document.querySelectorAll(".card")); let step = 0;
  const timer = setInterval(() => { cards.forEach((c, i) => c.classList.toggle("active", i === step % cards.length)); step++; }, 100);
  setTimeout(() => { clearInterval(timer); cards.forEach(c => c.classList.remove("active")); }, ${churnMs});
</script>`;

async function churn(page: Page, samples: number) {
  const first = await inspectState(page, true);
  let reference = first, changes = 0, geometryOnly = 0;
  for (let i = 0; i < samples; i++) {
    await page.waitForTimeout(80);
    const current = await inspectState(page, true);
    if (!equivalentState(current, reference)) { changes++; reference = current; }
    const diff = interactionDiff(first, current);
    if (diff.interaction_geometry_only > 0 && diff.interaction_content_added === 0 && diff.interaction_content_removed === 0) geometryOnly++;
  }
  return { changes, geometryOnly };
}

test("switcher mechanism: geometry/hit-only churn from finite, timer-restarted animations", async ({ page }) => {
  await page.setContent(switcherHtml(60_000));
  const { changes, geometryOnly } = await churn(page, 30);
  expect(changes).toBeGreaterThanOrEqual(10);
  expect(geometryOnly).toBeGreaterThan(0);
  // No infinite animation exists, so ADR 042 (B) cannot apply; every running animation is finite.
  const iterations = await page.evaluate(() => document.getAnimations()
    .map(a => (a.effect as KeyframeEffect).getComputedTiming().iterations));
  expect(iterations.every(n => Number.isFinite(n))).toBe(true);
});

test("once the switcher stops, the page settles (negative control)", async ({ page }) => {
  await page.setContent(switcherHtml(1500));
  const result = await settleState(page, Date.now() + 6000, 800);
  expect(result.settled).toBe(true);
});

// Documents the open defect: a burst longer than the settle window keeps the page unsettled. Expected to fail
// until a fix (see r20 report: wait for scroll/animation quiet, bounded recovery, or an ADR) changes the gate.
test("a scroll that lands inside a switcher burst should settle (r12 op 8 / r19 op 9)", async ({ page }) => {
  test.fail();
  await page.setContent(switcherHtml(60_000));
  const result = await settleState(page, Date.now() + 5000, 800);
  expect(result.settled).toBe(true);
});
