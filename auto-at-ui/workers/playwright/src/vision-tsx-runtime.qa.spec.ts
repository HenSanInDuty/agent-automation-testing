import { execFile } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { expect, test } from "@playwright/test";

// QA r18: complete session flow under the tsx runtime (the `npm run start` transform), which Playwright's own
// transform cannot reproduce. One probe process, several assertions. Run: `npm test -- vision-tsx-runtime.qa.spec.ts`.
const here = dirname(fileURLToPath(import.meta.url));
const tsxCli = join(here, "..", "node_modules", "tsx", "dist", "cli.mjs");
const probe = join(here, "fixtures", "vision-tsx-runtime-flow-probe.ts");

type Flow = { nav: string; names: string[]; prepare: string; execute: string; outcome: string | null; text: string | null;
  shimType: string; shimName: string | null; closed: boolean };
let result: { pulse?: Flow; static?: Flow; own_name?: Flow; http?: { status: number; body: unknown };
  log?: Record<string, unknown>; error?: string } = {};
let diagnostics = "";

test.beforeAll(async () => {
  test.setTimeout(150_000);
  const run = await promisify(execFile)(process.execPath, [tsxCli, probe], { timeout: 140_000, windowsHide: true })
    .then(value => value, (error: { stdout?: string; stderr?: string }) => ({ stdout: error.stdout ?? "", stderr: error.stderr ?? "" }));
  diagnostics = run.stderr.slice(0, 500);
  result = JSON.parse(run.stdout.trim().split("\n").at(-1) || "{}");
});

for (const name of ["pulse", "static"] as const) {
  test(`${name} page: open, observe, prepare, execute click, close under tsx`, () => {
    expect(result.error, diagnostics).toBeUndefined();
    expect(result[name], diagnostics).toMatchObject({ nav: "completed", prepare: "prepared", execute: "completed", text: "đã bấm", closed: true });
    expect(result[name]!.names).toContain("Bấm thử");
  });
}

test("an evaluate failure becomes unexpected_error with name/origin/digest and no message", () => {
  expect(result.http, diagnostics).toEqual({ status: 422, body: { detail: "visual_request_rejected" } });
  expect(result.log).toEqual({ error_type: "unexpected_error", error_name: "ReferenceError", error_origin: "page.evaluate",
    error_digest: expect.stringMatching(/^[0-9a-f]{8}$/), leaked: false });
});

test("the __name shim is a no-op function and leaves a page-defined __name in place", () => {
  expect(result.static?.shimType).toBe("function");
  expect(result.own_name?.shimName).toBe("pageOwnName");
  expect(result.own_name?.execute).toBe("completed");
});
