import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, readdir, rm, symlink, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { spawn } from "node:child_process";
import { chromium, type Page } from "@playwright/test";

import {
  type ExecutionRequestV1,
  type ExecutionResultV1,
  validateExecutionRequestV1,
  validatePlaywrightTestSourceMode,
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
export class ExecutionCancelledError extends Error {}
export type ProgressReporter = (stage: string, status: string, safeSummary: string) => void;

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

async function withinTimeout<T>(
  operation: Promise<T>,
  timeoutMs: number,
  signal?: AbortSignal,
): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let removeAbortListener: (() => void) | undefined;
  try {
    const operations: Promise<T>[] = [
      operation,
      new Promise<T>((_, reject) => {
        timer = setTimeout(
          () => reject(new ExecutionTimeoutError(`Browser run exceeded ${timeoutMs}ms.`)),
          timeoutMs,
        );
      }),
    ];
    if (signal !== undefined) {
      if (signal.aborted) throw new ExecutionCancelledError("Browser run was cancelled.");
      operations.push(
        new Promise<T>((_, reject) => {
          const abort = () => reject(new ExecutionCancelledError("Browser run was cancelled."));
          signal.addEventListener("abort", abort, { once: true });
          removeAbortListener = () => signal.removeEventListener("abort", abort);
        }),
      );
    }
    return await Promise.race(operations);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
    removeAbortListener?.();
  }
}

function policyResult(request: ExecutionRequestV1, startedAt: string, reason: string): ExecutionResultV1 {
  return {
    contract_version: "v1", run_id: request.run_id, correlation_id: request.correlation_id,
    status: "errored", started_at: startedAt, completed_at: new Date().toISOString(),
    summary: "Generated source blocked by execution policy.", artifacts: [],
    runner_metadata: { browser: "chromium", source_hash: String(request.runner_config.source_hash ?? ""), policy_blocked: true, policy_reason: reason, evidence: {} },
  };
}

async function filesBelow(directory: string): Promise<string[]> {
  const entries = await readdir(directory, { withFileTypes: true }).catch(() => []);
  return (await Promise.all(entries.map(async (entry) => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? filesBelow(path) : [path];
  }))).flat();
}

async function executePlaywrightTestSource(
  request: ExecutionRequestV1, artifactRoot: string, signal?: AbortSignal,
): Promise<ExecutionResultV1> {
  const startedAt = new Date().toISOString();
  let config;
  try {
    config = validatePlaywrightTestSourceMode(request.runner_config);
  } catch (error) {
    return policyResult(request, startedAt, error instanceof Error ? error.message : String(error));
  }
  if (signal?.aborted) throw new ExecutionCancelledError("Browser run was cancelled.");
  const workspace = await mkdtemp(join(tmpdir(), "auto-at-generated-"));
  const artifacts: ExecutionResultV1["artifacts"] = [];
  const evidence: Record<string, { checksum: string; size: number }> = {};
  try {
    const resultDirectory = join(workspace, "test-results");
    const policyEvidence = join(workspace, "origin-policy.json");
    await writeFile(join(workspace, "generated.spec.ts"), config.playwright_test_source, { mode: 0o400 });
    await writeFile(join(workspace, "package.json"), "{\"type\":\"module\"}\n", { mode: 0o400 });
    await symlink("/worker/node_modules", join(workspace, "node_modules"), "junction");
    await writeFile(join(workspace, "playwright.config.ts"), `import { defineConfig } from '@playwright/test';\nexport default defineConfig({ testDir: '.', testMatch: 'generated.spec.ts', outputDir: ${JSON.stringify(resultDirectory)}, timeout: 60000, workers: 1, use: { trace: 'retain-on-failure', video: 'retain-on-failure', screenshot: 'only-on-failure', serviceWorkers: 'block' } });\n`, { mode: 0o400 });
    const runner = "/worker/node_modules/@playwright/test/cli.js";
    const guard = "/worker/src/origin-guard.cjs";
    const child = spawn(process.execPath, [runner, "test", "--config=playwright.config.ts", "--reporter=line"], {
      cwd: workspace,
      env: {
        PATH: process.env.PATH ?? "", HOME: workspace, TMPDIR: workspace,
        PLAYWRIGHT_ALLOWED_ORIGINS: JSON.stringify(config.allowed_origins),
        PLAYWRIGHT_POLICY_EVIDENCE: policyEvidence,
        NODE_OPTIONS: `--require ${guard}`,
      },
      stdio: ["ignore", "pipe", "pipe"],
    });
    const output: Buffer[] = [];
    child.stdout.on("data", (chunk: Buffer) => output.push(chunk));
    child.stderr.on("data", (chunk: Buffer) => output.push(chunk));
    const exit = await withinTimeout(new Promise<number | null>((resolveExit, reject) => {
      child.once("error", reject); child.once("exit", resolveExit);
    }), 65_000, signal).catch((error) => { child.kill("SIGKILL"); throw error; });
    const policy = await readFile(policyEvidence, "utf8").catch(() => "[]");
    const blocked = policy !== "[]";
    const result = blocked ? policyResult(request, startedAt, "origin outside project allowlist") : {
      contract_version: "v1" as const, run_id: request.run_id, correlation_id: request.correlation_id,
      status: exit === 0 ? "passed" as const : "failed" as const, started_at: startedAt,
      completed_at: new Date().toISOString(), summary: exit === 0 ? "Playwright Test passed." : "Playwright Test reported a failure.",
      artifacts, runner_metadata: { browser: "chromium", playwright_version: "1.50.1", source_hash: config.source_hash, policy_blocked: false, evidence },
    };
    await addEvidence(artifactRoot, request.run_id, "playwright-output", "txt", "text/plain", Buffer.concat(output), artifacts, evidence);
    await addEvidence(artifactRoot, request.run_id, "origin-policy", "json", "application/json", policy, artifacts, evidence);
    for (const file of await filesBelow(resultDirectory)) {
      const extension = file.split(".").pop() ?? "bin";
      await addEvidence(artifactRoot, request.run_id, `playwright-${artifacts.length}`, extension, "application/octet-stream", await readFile(file), artifacts, evidence);
    }
    result.artifacts = artifacts;
    result.runner_metadata.evidence = evidence;
    return result;
  } catch (error) {
    if (error instanceof ExecutionCancelledError) throw error;
    return policyResult(request, startedAt, error instanceof Error ? error.message : String(error));
  } finally {
    await rm(workspace, { recursive: true, force: true });
  }
}

export async function executeRequest(value: unknown, artifactRoot = process.env.ARTIFACT_ROOT ?? "/artifacts", signal?: AbortSignal, report?: ProgressReporter): Promise<ExecutionResultV1> {
  const request = validateExecutionRequestV1(value);
  if (request.runner_config.mode === "playwright_test_source") {
    return executePlaywrightTestSource(request, artifactRoot, signal);
  }
  const config = configOf(request);
  if (signal?.aborted) throw new ExecutionCancelledError("Browser run was cancelled.");
  const startedAt = new Date().toISOString();
  const artifacts: ExecutionResultV1["artifacts"] = [];
  const evidence: Record<string, { checksum: string; size: number }> = {};
  const steps: Array<{ step: Step; status: "passed" | "failed"; error?: string }> = [];
  const consoleErrors: string[] = [];
  const networkFailures: string[] = [];
  const browser = await chromium.launch({ headless: true });
  report?.("browser.launched", "running", "Browser launched.");
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
        for (const [index, step] of config.steps.entries()) {
          try {
            report?.(`browser.todo.${index + 1}`, "running", `Browser todo step ${index + 1} started.`);
            await performStep(page, step, config.step_timeout_ms);
            steps.push({ step, status: "passed" });
            report?.(`browser.todo.${index + 1}`, "passed", `Browser todo step ${index + 1} passed.`);
          } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            steps.push({ step, status: "failed", error: message });
            status = "failed";
            summary = `Browser step failed: ${step.action}.`;
            report?.(`browser.todo.${index + 1}`, "failed", `Browser todo step ${index + 1} failed.`);
            break;
          }
        }
      })(),
      config.timeout_ms, signal,
    );
  } catch (error) {
    if (error instanceof ExecutionCancelledError) {
      throw error;
    } else if (error instanceof ExecutionTimeoutError) {
      status = "failed";
      summary = error.message;
    } else {
      status = "errored";
      summary = error instanceof Error ? error.message : String(error);
    }
  } finally {
    report?.("evidence.collection", "running", "Collecting configured evidence.");
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
    report?.("evidence.collection", "passed", "Evidence collection completed.");
  }
  return { contract_version: "v1", run_id: request.run_id, correlation_id: request.correlation_id, status, started_at: startedAt, completed_at: new Date().toISOString(), summary, artifacts, runner_metadata: { browser: "chromium", playwright_version: "1.50.1", steps, console_errors: consoleErrors, network_failures: networkFailures, evidence } };
}
