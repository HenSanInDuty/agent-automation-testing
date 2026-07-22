import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { chromium, type Page } from "@playwright/test";

import {
  type ExecutionRequestV1,
  type ExecutionResultV1,
  validateExecutionRequestV1,
} from "./contract.js";

type Step = { action: "goto"; url: string } | { action: "expect_text"; text: string } | { action: "click"; selector: string };
type WebUiConfig = { browser?: "chromium"; step_timeout_ms?: number; timeout_ms?: number; steps: Step[] };

function configOf(request: ExecutionRequestV1): WebUiConfig {
  if (request.target_type !== "web_ui") throw new Error("Playwright supports only web_ui targets");
  const config = request.runner_config as Partial<WebUiConfig>;
  if (config.browser !== undefined && config.browser !== "chromium") throw new Error("only pinned chromium is supported");
  if (!Array.isArray(config.steps) || config.steps.length === 0) throw new Error("web_ui steps are required");
  return { step_timeout_ms: 10_000, timeout_ms: 60_000, ...config, browser: "chromium" } as WebUiConfig;
}

async function addEvidence(
  root: string, runId: string, kind: string, extension: string, contentType: string, body: Buffer | string,
  artifacts: ExecutionResultV1["artifacts"], evidence: Record<string, { checksum: string; size: number }>,
): Promise<void> {
  const directory = resolve(root, runId);
  await mkdir(directory, { recursive: true });
  const path = join(directory, `${kind}.${extension}`);
  const bytes = typeof body === "string" ? Buffer.from(body) : body;
  await writeFile(path, bytes);
  const uri = `file://${path}`;
  artifacts.push({ kind, uri, content_type: contentType });
  evidence[uri] = { checksum: createHash("sha256").update(bytes).digest("hex"), size: bytes.length };
}

async function performStep(page: Page, step: Step, timeout: number): Promise<void> {
  if (step.action === "goto") await page.goto(step.url, { timeout, waitUntil: "domcontentloaded" });
  else if (step.action === "expect_text") await page.getByText(step.text, { exact: false }).waitFor({ timeout });
  else if (step.action === "click") await page.locator(step.selector).click({ timeout });
}

export async function executeRequest(value: unknown, artifactRoot = process.env.ARTIFACT_ROOT ?? "/artifacts"): Promise<ExecutionResultV1> {
  const request = validateExecutionRequestV1(value);
  const config = configOf(request);
  const startedAt = new Date().toISOString();
  const artifacts: ExecutionResultV1["artifacts"] = [];
  const evidence: Record<string, { checksum: string; size: number }> = {};
  const steps: Array<{ step: Step; status: "passed" | "failed"; error?: string }> = [];
  const consoleErrors: string[] = [];
  const networkFailures: string[] = [];
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ recordVideo: request.artifact_policy.video_on_failure ? { dir: join(artifactRoot, request.run_id, "video") } : undefined });
  const page = await context.newPage();
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("requestfailed", (requestFailed) => networkFailures.push(`${requestFailed.method()} ${requestFailed.url()} ${requestFailed.failure()?.errorText ?? "failed"}`));
  await context.tracing.start({ screenshots: true, snapshots: true });
  let status: ExecutionResultV1["status"] = "passed";
  let summary = "All configured browser steps passed.";
  try {
    for (const step of config.steps) {
      try {
        await performStep(page, step, config.step_timeout_ms ?? 10_000);
        steps.push({ step, status: "passed" });
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        steps.push({ step, status: "failed", error: message });
        status = "failed";
        summary = `Browser step failed: ${step.action}.`;
        break;
      }
    }
  } catch (error) {
    status = "errored";
    summary = error instanceof Error ? error.message : String(error);
  } finally {
    const snapshot = await page.locator("body").innerText().catch(() => "");
    const dom = await page.locator("body").evaluate((body) => body.outerHTML.slice(0, 20_000)).catch(() => "");
    const accessibility = await page.accessibility.snapshot().catch(() => null);
    await addEvidence(artifactRoot, request.run_id, "step-history", "json", "application/json", JSON.stringify(steps), artifacts, evidence);
    await addEvidence(artifactRoot, request.run_id, "page-url", "txt", "text/plain", page.url(), artifacts, evidence);
    await addEvidence(artifactRoot, request.run_id, "accessibility", "json", "application/json", JSON.stringify(accessibility), artifacts, evidence);
    await addEvidence(artifactRoot, request.run_id, "dom-fragment", "html", "text/html", dom || snapshot, artifacts, evidence);
    await addEvidence(artifactRoot, request.run_id, "console-errors", "json", "application/json", JSON.stringify(consoleErrors), artifacts, evidence);
    await addEvidence(artifactRoot, request.run_id, "network-failures", "json", "application/json", JSON.stringify(networkFailures), artifacts, evidence);
    if (status !== "passed" && request.artifact_policy.screenshot_on_failure) {
      const image = await page.screenshot({ fullPage: true }).catch(() => Buffer.alloc(0));
      await addEvidence(artifactRoot, request.run_id, "screenshot", "png", "image/png", image, artifacts, evidence);
    }
    if (status !== "passed" && request.artifact_policy.trace_on_failure) {
      const tracePath = join(artifactRoot, request.run_id, "trace.zip");
      await context.tracing.stop({ path: tracePath });
      const trace = await readFile(tracePath);
      await addEvidence(artifactRoot, request.run_id, "trace", "zip", "application/zip", trace, artifacts, evidence);
    } else await context.tracing.stop();
    await context.close();
    await browser.close();
  }
  return { contract_version: "v1", run_id: request.run_id, correlation_id: request.correlation_id, status, started_at: startedAt, completed_at: new Date().toISOString(), summary, artifacts, runner_metadata: { browser: "chromium", playwright_version: "1.50.1", steps, console_errors: consoleErrors, network_failures: networkFailures, evidence } };
}
