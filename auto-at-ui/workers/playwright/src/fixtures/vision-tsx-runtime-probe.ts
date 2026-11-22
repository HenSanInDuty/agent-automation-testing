// Run ONLY through the production transform (`tsx`, esbuild keepNames), see vision-tsx-runtime.spec.ts.
// r17/r18: Playwright's own test transform never injects `__name`, so specs cannot see a named closure inside a
// browser callback break; this probe exercises the same entry path as `npm run start` and prints one JSON line.
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { chromium, type Browser } from "@playwright/test";
import { VisualOperationWorker } from "../vision-operations.js";
import { inspectState, isPresentationOnlyAnimated } from "../vision-checkpoints.js";
import { pulsingControlHtml } from "./settle-animated-control.js";

const root = await mkdtemp(join(tmpdir(), "auto-at-vision-tsx-"));
let browser: Browser | undefined;
const worker = new VisualOperationWorker(root, async (options) => { browser = await chromium.launch(options); return browser; });
const identity = { contract_version: "v4" as const, tenant_id: "fixture-tenant", project_id: randomUUID(), session_id: randomUUID(), fencing_token: 1 };
const out: Record<string, unknown> = {};
try {
  const opened = await worker.open({ ...identity, target_url: "http://127.0.0.1:9", allowed_origins: ["http://127.0.0.1:9"],
    deadline: new Date(Date.now() + 60_000).toISOString(), max_session_seconds: 60,
    max_states: 20, max_hops: 10, max_screenshot_bytes: 1_000_000 });
  out.open = opened.state_fingerprint.length > 0;
  // Observe path: re-inspect an animated page (runs the layoutBox branch) and the animated-control check.
  const page = browser!.contexts()[0].pages()[0];
  await page.setContent(pulsingControlHtml);
  const state = await inspectState(page);
  out.inspect_animated = state.privateInteractions.some(item => item.animated);
  // A context without the open() guard: the browser callbacks themselves must not depend on `__name`.
  const bare = await (await browser!.newContext()).newPage();
  await bare.setContent(pulsingControlHtml);
  out.inspect_without_guard = (await inspectState(bare)).privateInteractions.some(item => item.animated);
  const handle = await page.locator("a[href='#play']").elementHandle();
  out.presentation_only = await isPresentationOnlyAnimated(handle!);
  await worker.close(identity, identity.session_id);
  out.close = true;
} catch (error) {
  out.error = `${(error as Error)?.name}: ${String((error as Error)?.message).slice(0, 300)}`;
  process.exitCode = 1;
} finally {
  await browser?.close().catch(() => undefined);
  await rm(root, { recursive: true, force: true });
}
console.log(JSON.stringify(out));
process.exit(process.exitCode ?? 0);
