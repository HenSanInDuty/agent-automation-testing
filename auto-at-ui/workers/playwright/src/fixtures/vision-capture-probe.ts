/** Read-only capture timing probe. No model calls, clicks, or form inputs. */
import { chromium } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { inspectState, settleState, equivalentState } from "../vision-checkpoints.js";
import { observeDom } from "../vision-dom.js";
import { captureVisionScreen } from "../vision-screen.js";
import { validateVision, type VisualWorkerObserveDom } from "../vision-contract.js";

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 },
    reducedMotion: "reduce", serviceWorkers: "block", acceptDownloads: false });
  await page.goto("https://mongchiton.vn", { waitUntil: "domcontentloaded" });
  const identity = { tenant_id: "read-only-probe", project_id: randomUUID(), session_id: randomUUID(), fencing_token: 1 };
  const results: unknown[] = [];
  for (const y of [576, 1152, 1728, 2304]) {
    await page.evaluate(y => scrollTo(0, y), y);
    for (let trial = 1; trial <= 3; trial++) {
      const settled = await settleState(page, Date.now() + 10_000, 800);
      const start = performance.now();
      await captureVisionScreen(page, 3000);
      const captured = await inspectState(page), screenshotMs = Math.round(performance.now() - start);
      const domStart = performance.now();
      let code: string | null = null, count = 0;
      try {
        const snapshot = await observeDom(page, validateVision<VisualWorkerObserveDom>("VisualWorkerObserveDom", {
          ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: captured.fingerprint,
        }));
        count = snapshot.data.observation.elements.length;
      } catch (error) { code = (error as Error).message; }
      results.push({ y, trial, settled: settled.settled, screenshot_ms: screenshotMs,
        capture_stable: equivalentState(settled.state, captured), dom_ms: Math.round(performance.now() - domStart), count, code });
    }
  }
  console.log(JSON.stringify({ model_calls: 0, clicks: 0, results }));
} finally { await browser.close(); }
