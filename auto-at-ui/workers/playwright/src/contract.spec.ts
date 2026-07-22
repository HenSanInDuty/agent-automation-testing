import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

import { validateExecutionRequestV1, validateExecutionResultV1 } from "./contract.js";
import { configOf } from "./execute.js";

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
