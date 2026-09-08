import { expect, test } from "@playwright/test";

import { visualTreeRequestOf } from "./vision.js";
import { readdir, readFile } from "node:fs/promises";
import { validateVision } from "./vision-contract.js";

const request = {
  contract_version: "v3", id: "session", node_id: "11111111-1111-4111-8111-111111111111",
  target_url: "https://example.test", allowed_origins: ["https://example.test"],
  max_hops: 2, max_states: 4, max_screenshot_bytes: 1024,
  max_session_seconds: 10, replay_path: [], parent_url_fingerprint: "a".repeat(64),
};

test("accepts v3 tree observations with only a parent URL fingerprint", () => {
  expect(visualTreeRequestOf(request).parent_url_fingerprint).toBe("a".repeat(64));
});

test("rejects raw parent URLs and the retired v2 tree contract", () => {
  expect(() => visualTreeRequestOf({ ...request, contract_version: "v2" })).toThrow();
  expect(() => visualTreeRequestOf({ ...request, parent_url_fingerprint: "https://secret.test" })).toThrow();
});

test("worker validates every shared Python locator/operation/handoff/v4 fixture", async () => {
  const directory = new URL("../../../packages/contracts/fixtures/vision-locator-v1/", import.meta.url);
  const files = (await readdir(directory)).filter((name) => name.endsWith(".json"));
  expect(files.length).toBeGreaterThanOrEqual(19);
  for (const file of files) {
    const fixture = JSON.parse(await readFile(new URL(file, directory), "utf8"));
    if (fixture.accepted) expect(() => validateVision(fixture.contract, fixture.payload), file).not.toThrow();
    else expect(() => validateVision(fixture.contract, fixture.payload), file).toThrow();
  }
});

test("private v4 transport shares accepted/rejected Python fixtures", async () => {
  const directory = new URL("../../../packages/contracts/fixtures/vision-worker-v4/", import.meta.url);
  const files = (await readdir(directory)).filter((name) => name.endsWith(".json"));
  expect(files.length).toBeGreaterThanOrEqual(9);
  for (const file of files) {
    const fixture = JSON.parse(await readFile(new URL(file, directory), "utf8"));
    if (fixture.accepted) expect(() => validateVision(fixture.contract, fixture.payload), file).not.toThrow();
    else expect(() => validateVision(fixture.contract, fixture.payload), file).toThrow();
  }
});
