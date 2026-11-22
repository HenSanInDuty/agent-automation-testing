import { expect, test, type Page } from "@playwright/test";
import { equivalentState, inspectState, settleState } from "./vision-checkpoints.js";
type Probe = Window & { __clicked: string; __done: number; __n: number; __timer: number; __stop: () => void; __paused?: Animation[] };

// r21 probe (offline, no source change): would suppressing animation while the worker settles stabilise a page like
// mongchiton.vn "mount-switcher"? On the live site (r21 report, tsx probes) a global `transition:none` + paused
// animations, or `1ms` durations, cut the churn from about 22 state changes per 4 s to 1-2, a CSS-driven hop is
// absorbed. This spec documents on a LOCAL fixture what the measures cost semantically, so the decision does not depend
// on the live site:
//   - pausing animations/transitions (variant "pause") freezes the page in an intermediate frame and swallows
//     `transitionend`; `transition:none` (variant "none") swallows it too;
//   - `1ms` durations (variant "fast") end every finite animation/transition at its real end state and still fire the
//     end events, so the page keeps its semantics; and
//   - none of them helps when a JS timer itself moves the controls.
const PAUSE_CSS = "*,*::before,*::after{animation-play-state:paused!important;transition:none!important}";
const NONE_CSS = "*,*::before,*::after{transition:none!important;animation:none!important}";
const FAST_CSS = "*,*::before,*::after{animation-duration:1ms!important;animation-delay:0s!important;transition-duration:1ms!important;transition-delay:0s!important}";

// A carousel hop every 1000 ms; each hop is a 600 ms CSS transition, so the quiet gap (400 ms) is under the 800 ms
// settle window and the baseline never settles. `transitionend` marks the hop as done (page semantics: "ready").
const carouselHtml = `<!doctype html><style>
  body{margin:0;background:#fff}
  #view{position:relative;width:600px;height:140px;overflow:hidden;margin:20px}
  #track{display:flex;width:900px;transform:translateX(0);transition:transform 600ms linear}
  .slide{flex:0 0 300px;height:140px;display:block;box-sizing:border-box;background:#cde;border-right:1px solid #446;font:20px sans-serif}
</style><div id="view"><div id="track"><a class="slide" id="s0" href="#s0">S0</a><a class="slide" id="s1" href="#s1">S1</a><a class="slide" id="s2" href="#s2">S2</a></div></div>
<script>
  window.__clicked = ""; window.__done = 0; window.__n = 0;
  const track = document.getElementById("track");
  track.addEventListener("transitionend", () => { window.__done++; });
  document.querySelectorAll(".slide").forEach(a => a.addEventListener("click", e => { e.preventDefault(); window.__clicked = a.id; }));
  window.__timer = setInterval(() => { window.__n = (window.__n + 1) % 3; track.style.transform = "translateX(" + (-300 * window.__n) + "px)"; }, 1000);
  window.__stop = () => clearInterval(window.__timer);
</script>`;

// A JS timer that moves the controls itself (inline `left`, no CSS animation involved): suppressing animation cannot
// stop it. (r21 finding: with only z-index re-stacking and the animation removed, the hit probes did not flip in this
// fixture, so the r20 fixture's churn came from its `scale`/`margin-left` animation, not from the class toggle.)
const timerHtml = `<!doctype html><style>
  body{margin:0}#row{position:relative;height:200px;width:520px;margin:20px}
  .card{position:absolute;top:0;width:140px;height:160px;display:block;background:#ccd;border:1px solid #446}
  .card:nth-child(1){left:0}.card:nth-child(2){left:150px}.card:nth-child(3){left:300px}
</style><div id="row"><a class="card" href="#a">A</a><a class="card" href="#b">B</a><a class="card" href="#c">C</a></div>
<script>(() => {
  const first = document.querySelector(".card"); let step = 0;
  setInterval(() => { first.style.left = (step++ % 2 ? 0 : 60) + "px"; }, 100);
})();</script>`;

const inject = (page: Page, css: string) => page.evaluate(c => { const s = document.createElement("style"); s.id = "__suppress"; s.textContent = c; document.head.appendChild(s); }, css);
const remove = (page: Page) => page.evaluate(() => document.getElementById("__suppress")?.remove());
// Pause variant of "pause all animations": JS pause() of every running Animation/Transition, like document.getAnimations().
const pauseAll = (page: Page) => page.evaluate(async () => {
  const running = document.getAnimations().filter(a => a.playState === "running");
  (window as unknown as Probe).__paused = running; running.forEach(a => a.pause());
  await Promise.all(running.map(a => a.ready)); return running.length;
});
const resumeAll = (page: Page) => page.evaluate(() => (window as unknown as Probe).__paused?.forEach((a: Animation) => a.play()));
const tx = (page: Page) => page.evaluate(() => new DOMMatrix(getComputedStyle(document.getElementById("track")!).transform).m41);

// The first hop fires at 1000 ms; start measuring after it so the initial quiet window cannot count as settled.
const afterFirstHop = (page: Page) => page.waitForTimeout(1100);

async function settle(page: Page, ms: number) {
  const r = await settleState(page, Date.now() + ms, 800, true);
  return r.settled;
}

test("baseline: 600 ms hops every 1000 ms never leave an 800 ms quiet window", async ({ page }) => {
  await page.setContent(carouselHtml);
  await afterFirstHop(page);
  expect(await settle(page, 4500)).toBe(false);
});

test("transition:none settles the hop but swallows transitionend (page semantics change)", async ({ page }) => {
  await page.setContent(carouselHtml);
  await afterFirstHop(page);
  await inject(page, PAUSE_CSS);
  expect(await settle(page, 4500)).toBe(true);
  expect(await page.evaluate(() => (window as unknown as Probe).__n)).toBeGreaterThan(0); // the JS timer kept running, DOM kept changing
  expect(await page.evaluate(() => (window as unknown as Probe).__done)).toBe(0); // no transitionend ever fired
  await remove(page);
});

test("1ms durations settle the hop, end at the real end state and keep firing transitionend", async ({ page }) => {
  await page.setContent(carouselHtml);
  await afterFirstHop(page);
  await inject(page, FAST_CSS);
  expect(await settle(page, 4500)).toBe(true);
  expect(await page.evaluate(() => (window as unknown as Probe).__done)).toBeGreaterThan(0);
  await page.evaluate(() => (window as unknown as Probe).__stop());
  const suppressedShot = await page.screenshot();
  await remove(page);
  await page.waitForTimeout(800);
  expect(await tx(page)).toBe(-300 * (await page.evaluate(() => (window as unknown as Probe).__n)));
  expect(Buffer.compare(suppressedShot, await page.screenshot())).toBe(0); // the suppressed frame is the real end state
});

test("pausing running animations freezes an intermediate frame that differs from the real end state", async ({ page }) => {
  await page.setContent(carouselHtml);
  await page.waitForTimeout(1150); // inside the first hop transition
  const paused = await pauseAll(page);
  expect(paused).toBeGreaterThan(0);
  const frozen = await tx(page);
  expect(frozen).toBeLessThan(0);
  expect(frozen).toBeGreaterThan(-300); // mid-way, not at the end state
  await page.evaluate(() => (window as unknown as Probe).__stop());
  const frozenShot = await page.screenshot();
  const before = await inspectState(page, true);
  await page.waitForTimeout(700);
  expect(await tx(page)).toBe(frozen); // still frozen, a settle would "succeed" here
  await resumeAll(page);
  await page.waitForTimeout(900);
  expect(await tx(page)).toBe(-300); // real end state after resume
  expect(Buffer.compare(frozenShot, await page.screenshot())).not.toBe(0);
  expect(equivalentState(before, await inspectState(page, true))).toBe(false); // held (frozen) state != fresh state after resume
});

test("a JS timer that moves the controls keeps the page unsettled under every suppression", async ({ page }) => {
  for (const css of [PAUSE_CSS, NONE_CSS, FAST_CSS]) {
    await page.setContent(timerHtml);
    await inject(page, css);
    const ok = await settle(page, 2500);
    expect(ok).toBe(false);
  }
});

test("after resume the exact node is hit and receives the click", async ({ page }) => {
  await page.setContent(carouselHtml);
  await afterFirstHop(page);
  await inject(page, FAST_CSS);
  expect(await settle(page, 4500)).toBe(true);
  await page.evaluate(() => (window as unknown as Probe).__stop());
  await remove(page);
  await page.waitForTimeout(800);
  const n = await page.evaluate(() => (window as unknown as Probe).__n);
  const centre = await page.evaluate(() => { const r = document.getElementById("s" + (window as unknown as Probe).__n)!.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
  expect(await page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.id, centre)).toBe("s" + n);
  await page.mouse.click(centre.x, centre.y);
  expect(await page.evaluate(() => (window as unknown as Probe).__clicked)).toBe("s" + n);
});
