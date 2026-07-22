import { createHash } from "node:crypto";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { chromium, type Page } from "@playwright/test";

import {
  type ExecutionRequestV1,
  type ExecutionResultV1,
  validateExecutionRequestV1,
} from "./contract.js";

export type Step =
  | { action: "goto"; url: string }
  | { action: "expect_text"; text: string }
  | { action: "click"; selector: string };

export type WebUiConfig = {
  browser: "chromium";
  step_timeout_ms: number;
  timeout_ms: number;
  steps: Step[];
};

const DEFAULT_STEP_TIMEOUT_MS = 10_000;
const DEFAULT_TIMEOUT_MS = 60_000;
const MAX_STEPS = 100;
const MAX_TIMEOUT_MS = 10 * 60_000;

class ExecutionTimeoutError extends Error {}

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

function timeoutOf(value: unknown, name: string, defaultValue: number): number {
  if (value === undefined) return defaultValue;
  if (
    typeof value !== "number" ||
    !Number.isInteger(value) ||
    value < 1 ||
    value > MAX_TIMEOUT_MS
  ) {
    throw new Error(`${name} must be an integer between 1 and ${MAX_TIMEOUT_MS}`);
  }
  return value;
}

function stepOf(value: unknown): Step {
  if (!isObject(value)) throw new Error("each web_ui step must be an object");
  if (value.action === "goto" && typeof value.url === "string" && value.url.length > 0) {
    let url: URL;
    try {
      url = new URL(value.url);
    } catch {
      throw new Error("goto step url must be an absolute URL");
    }
    if (!["http:", "https:"].includes(url.protocol)) {
      throw new Error("goto step url must use http or https");
    }
    return { action: "goto", url: value.url };
  }
  if (value.action === "expect_text" && typeof value.text === "string" && value.text.length > 0) {
    return { action: "expect_text", text: value.text };
  }
  if (value.action === "click" && typeof value.selector === "string" && value.selector.length > 0) {
    return { action: "click", selector: value.selector };
  }
  throw new Error("web_ui step is invalid");
}

export function configOf(request: ExecutionRequestV1): WebUiConfig {
  if (request.target_type !== "web_ui") throw new Error("Playwright supports only web_ui targets");
  const config = request.runner_config;
  if (config.browser !== undefined && config.browser !== "chromium") throw new Error("only pinned chromium is supported");
  if (!Array.isArray(config.steps) || config.steps.length === 0 || config.steps.length > MAX_STEPS) {
    throw new Error(`web_ui steps must contain between 1 and ${MAX_STEPS} entries`);
  }
  return {
    browser: "chromium",
    step_timeout_ms: timeoutOf(config.step_timeout_ms, "step_timeout_ms", DEFAULT_STEP_TIMEOUT_MS),
    timeout_ms: timeoutOf(config.timeout_ms, "timeout_ms", DEFAULT_TIMEOUT_MS),
    steps: config.steps.map(stepOf),
  };
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

async function withinTimeout<T>(operation: Promise<T>, timeoutMs: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      operation,
      new Promise<T>((_, reject) => {
        timer = setTimeout(
          () => reject(new ExecutionTimeoutError(`Browser run exceeded ${timeoutMs}ms.`)),
          timeoutMs,
        );
      }),
    ]);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
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
  const video = page.video();
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("requestfailed", (requestFailed) => networkFailures.push(`${requestFailed.method()} ${requestFailed.url()} ${requestFailed.failure()?.errorText ?? "failed"}`));
  await context.tracing.start({ screenshots: true, snapshots: true });
  let status: ExecutionResultV1["status"] = "passed";
  let summary = "All configured browser steps passed.";
  try {
    await withinTimeout(
      (async () => {
        for (const step of config.steps) {
          try {
            await performStep(page, step, config.step_timeout_ms);
            steps.push({ step, status: "passed" });
          } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            steps.push({ step, status: "failed", error: message });
            status = "failed";
            summary = `Browser step failed: ${step.action}.`;
            break;
          }
        }
      })(),
      config.timeout_ms,
    );
  } catch (error) {
    if (error instanceof ExecutionTimeoutError) {
      status = "failed";
      summary = error.message;
    } else {
      status = "errored";
      summary = error instanceof Error ? error.message : String(error);
    }
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
    if (video !== null) {
      const videoPath = await video.path();
      if (status !== "passed") {
        await addEvidence(artifactRoot, request.run_id, "video", "webm", "video/webm", await readFile(videoPath), artifacts, evidence);
      } else {
        await rm(videoPath, { force: true });
      }
    }
    await browser.close();
  }
  return { contract_version: "v1", run_id: request.run_id, correlation_id: request.correlation_id, status, started_at: startedAt, completed_at: new Date().toISOString(), summary, artifacts, runner_metadata: { browser: "chromium", playwright_version: "1.50.1", steps, console_errors: consoleErrors, network_failures: networkFailures, evidence } };
}
