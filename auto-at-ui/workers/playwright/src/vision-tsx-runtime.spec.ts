import { execFile } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { expect, test } from "@playwright/test";

// r18 (regression of r16/r17): the worker runs through `tsx` (esbuild keepNames) which rewrites every named closure
// to `__name(fn, "name")`. A browser callback that carries such a closure throws `__name is not defined` in the page.
// Playwright's own test transform does not inject `__name`, so every other spec passes while `open` is dead in the
// container. This spec spawns the real production transform (the `start` script uses `tsx`) and drives open ->
// inspect (animated control) -> close. Run: `npm test -- vision-tsx-runtime.spec.ts` in workers/playwright.
const here = dirname(fileURLToPath(import.meta.url));
const tsxCli = join(here, "..", "node_modules", "tsx", "dist", "cli.mjs");
const probe = join(here, "fixtures", "vision-tsx-runtime-probe.ts");

test("open, inspect and close work under the tsx runtime used by `npm run start`", async () => {
  test.setTimeout(90_000);
  const run = await promisify(execFile)(process.execPath, [tsxCli, probe], { timeout: 80_000, windowsHide: true })
    .then(result => ({ ...result, code: 0 }), (error: { stdout?: string; stderr?: string; code?: number }) =>
      ({ stdout: error.stdout ?? "", stderr: error.stderr ?? "", code: error.code ?? 1 }));
  const line = run.stdout.trim().split("\n").at(-1) ?? "";
  expect(JSON.parse(line || "{}"), run.stderr.slice(0, 500)).toEqual(
    { open: true, inspect_animated: true, inspect_without_guard: true, presentation_only: true, close: true });
  expect(run.code).toBe(0);
});
