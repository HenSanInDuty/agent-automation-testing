import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { expect, test } from "@playwright/test";

import {
  validateExecutionRequestV1,
  validatePlaywrightTestSourceMode,
  validateExecutionResultV1,
} from "./contract.js";
import { configOf, executeRequest, ExecutionCancelledError, preflightPlaywrightTestSource } from "./execute.js";

const fixtures = new URL("../../../packages/contracts/fixtures/execution-v1/", import.meta.url);

async function fixture(name: string): Promise<unknown> {
  return JSON.parse(await readFile(fileURLToPath(new URL(name, fixtures)), "utf8"));
}

test("accepts the shared web UI request fixture", async () => {
  const request = validateExecutionRequestV1(await fixture("request.web-ui.json"));

  expect(request.target_type).toBe("web_ui");
  expect(request.runner_config.browser).toBe("chromium");
});

test("accepts the shared passed result fixture", async () => {
  const result = validateExecutionResultV1(await fixture("result.passed.json"));

  expect(result.status).toBe("passed");
  expect(result.artifacts[0]?.content_type).toBe("application/zip");
});

test("rejects a request with an unsupported contract version", () => {
  expect(() => validateExecutionRequestV1({ contract_version: "v2" })).toThrow(
    "invalid TestExecutionRequest v1",
  );
});

test("normalizes the supported Web UI configuration", async () => {
  const request = validateExecutionRequestV1(await fixture("request.web-ui.json"));

  expect(configOf(request)).toMatchObject({
    browser: "chromium",
    step_timeout_ms: 10_000,
    timeout_ms: 60_000,
  });
});

test("rejects an unsafe or malformed Web UI step", async () => {
  const request = validateExecutionRequestV1(await fixture("request.web-ui.json"));
  request.runner_config.steps = [{ action: "goto", url: "file:///etc/passwd" }];

  expect(() => configOf(request)).toThrow("goto step url must use http or https");
});

test("accepts the shared v1 generated Playwright source request fixture", async () => {
  const request = validateExecutionRequestV1(await fixture("request.playwright-test-source.json"));
  const config = validatePlaywrightTestSourceMode(request.runner_config);

  expect(config.mode).toBe("playwright_test_source");
});

test("rejects an invalid generated-source mode", () => {
  expect(() => validatePlaywrightTestSourceMode({ mode: "shell", source_hash: "a".repeat(64) }))
    .toThrow("invalid playwright_test_source runner configuration");
});

test("rejects generated source with a mismatched hash or prohibited import", () => {
  expect(() => validatePlaywrightTestSourceMode({
    mode: "playwright_test_source",
    playwright_test_source: "import { readFile } from 'node:fs';",
    source_hash: "a".repeat(64),
  })).toThrow("invalid playwright_test_source runner configuration");
});

test("uses the TypeScript AST to reject direct network APIs", () => {
  const source = "import { test } from '@playwright/test'; test('x', async ({ request }) => request.get('https://example.test'));";
  expect(() => validatePlaywrightTestSourceMode({
    mode: "playwright_test_source", playwright_test_source: source,
    source_hash: createHash("sha256").update(source).digest("hex"),
    allowed_origins: ["https://example.test"],
  })).toThrow("direct network request APIs");
});

test("returns a normal v1 policy-blocked result before browser startup", async () => {
  const request = await fixture("request.playwright-test-source.json") as Record<string, unknown>;
  const config = request.runner_config as Record<string, unknown>;
  config.source_hash = "a".repeat(64);

  const result = await executeRequest(request, "/tmp/worker-contract-artifacts");
  expect(result).toMatchObject({ status: "errored", summary: "Generated source blocked by execution policy." });
  expect(result.runner_metadata).toMatchObject({ policy_blocked: true });
});

test("preflights generated source without launching a browser or producing a verdict", async () => {
  const request = await fixture("request.playwright-test-source.json");

  await expect(preflightPlaywrightTestSource(request)).resolves.toEqual({ accepted: true });
});

test("preflight rejects TypeScript that the pinned runner cannot load", async () => {
  const request = await fixture("request.playwright-test-source.json") as Record<string, unknown>;
  const config = request.runner_config as Record<string, unknown>;
  const source = "import { test } from '@playwright/test'; test('broken', async ({ page }) => {";
  config.playwright_test_source = source;
  config.source_hash = createHash("sha256").update(source).digest("hex");

  await expect(preflightPlaywrightTestSource(request)).resolves.toMatchObject({ accepted: false });
});

test("runs generated source with the browser bundled in the worker image", async () => {
  test.skip(!existsSync("/ms-playwright"), "requires the pinned Playwright worker image");
  const source = [
    "import { test, expect } from '@playwright/test';",
    "test('bundled browser', async ({ page }) => {",
    "  await page.setContent('<button>Save</button>');",
    "  await expect(page.getByRole('button', { name: 'Save' })).toBeEnabled();",
    "});",
  ].join("\n");
  const request = {
    contract_version: "v1", run_id: "11111111-1111-4111-8111-111111111111",
    correlation_id: "22222222-2222-4222-8222-222222222222",
    project_id: "33333333-3333-4333-8333-333333333333", test_case_id: "generated-browser",
    target_type: "web_ui", revision: "a".repeat(40),
    runner_config: {
      mode: "playwright_test_source", playwright_test_source: source,
      source_hash: createHash("sha256").update(source).digest("hex"),
      allowed_origins: ["https://example.test"],
    },
    artifact_policy: {
      trace_on_failure: true, video_on_failure: true, screenshot_on_failure: true, retain_days: 30,
    },
  };

  const result = await executeRequest(request, "/tmp/worker-contract-artifacts");

  expect(result).toMatchObject({ status: "passed", runner_metadata: { policy_blocked: false } });
});

test("stops before launching a browser when the run was already cancelled", async () => {
  const request = await fixture("request.web-ui.json");
  const controller = new AbortController();
  controller.abort();

  await expect(executeRequest(request, "/artifacts", controller.signal)).rejects.toBeInstanceOf(
    ExecutionCancelledError,
  );
});
