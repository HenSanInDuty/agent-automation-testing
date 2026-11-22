/** Read-only production-page diagnostic: no model calls or physical clicks. */
import { chromium } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { inspectState, settleState } from "../vision-checkpoints.js";
import { observeDom } from "../vision-dom.js";
import { revalidateDom } from "../vision-revalidation.js";
import { validateVision, type VisualWorkerObserveDom } from "../vision-contract.js";

const browser = await chromium.launch({ headless: true });
const results: unknown[] = [];
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, reducedMotion: "reduce",
    serviceWorkers: "block", acceptDownloads: false });
  await page.goto("https://mongchiton.vn", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(3500);
  await page.evaluate(() => scrollTo(0, 1136));
  const identity = { tenant_id: "read-only-probe", project_id: randomUUID(), session_id: randomUUID(), fencing_token: 1 };
  const observe = async () => {
    for (let attempt = 0; ; attempt++) {
      await settleState(page, Date.now() + 10_000, 160);
      try { return await observeDom(page, validateVision<VisualWorkerObserveDom>("VisualWorkerObserveDom", {
        ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: (await inspectState(page)).fingerprint,
      })); } catch (error) { if (attempt === 2) throw error; }
    }
  };
  for (let i = 0; i < 4; i++) {
    const old = await observe();
    await page.waitForTimeout(4500);
    const fresh = await observe();
    const ids = old.data.observation.elements.slice(0, 10).map(e => e.element_id);
    let reason: string | null = null;
    try { await revalidateDom(old, fresh, ids); }
    catch (error) { reason = (error as Error).message; }
    results.push({ trial: i + 1, scroll_y: old.state.scroll_y, full_state_matches: old.state.fingerprint === fresh.state.fingerprint,
      target_count: ids.length, revalidated: reason === null, reason });
  }
  console.log(JSON.stringify({ target: "https://mongchiton.vn", scroll_y: 1136,
    delay_ms: 4500, model_calls: 0, clicks: 0, results }));
} finally { await browser.close(); }
