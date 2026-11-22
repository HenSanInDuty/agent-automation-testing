STATUS: DONE

CONTEXT_CHECK
- conventions: docs/code-standards.md (hgraph brief), AGENTS.md, be-developer-r17.md (full); r14/r14b/ADR-042 read for the settle behaviour (kept as is). docs/api-conventions.md not applicable (no API change).
- graphs: playwright-vision-worker (brief for workers/playwright/src returned "no graph covers the directory"; per-file `hgraph which` maps all files to playwright-vision-worker).
- blast radius: brief on the directory gave 0 dependents; per-file: vision-checkpoints.ts is imported by vision-dom/history/operations (graph table), vision-observability.ts by http/operations/screen/dom/checkpoints.

Impact inventory: Database: không đụng. No contract, env var, API or event change. New log fields on 422 `unexpected_error` only (additive). Callers: `visionErrorDetails` is new (no signature change); `visionErrorType` untouched.

## Root cause (from r17, confirmed)
tsx/esbuild `keepNames` wraps the nested `const layoutBox = (el) => {...}` inside the `inspectState` evaluate callback as `__name(...)`; `__name` does not exist in the page -> `ReferenceError`, so `open()` (first `inspectState`) and every observe/navigate fail. Playwright's test transform does not inject `__name`, so no spec saw it.

## Red -> green
Red (before the fix, new spec, `npx playwright test vision-tsx-runtime.spec.ts --workers=1`):

    1 failed  src\vision-tsx-runtime.spec.ts:16:1 › open, inspect and close work under the tsx runtime used by `npm run start`
    +   "error": "Error: page.evaluate: ReferenceError: __name is not defined
    +     at eval (eval at evaluate (:234:30), <anonymous>:1:819)

Green (after): `1 passed (3.2s)`. The probe also inspects an animated page in a context WITHOUT the open() safety net (`inspect_without_guard`), so the test still proves the callbacks themselves are clean, not just masked by the guard.

Re-run command (workers/playwright): `npm test -- vision-tsx-runtime.spec.ts`. The spec spawns `node node_modules/tsx/dist/cli.mjs src/fixtures/vision-tsx-runtime-probe.ts` (same transform as `npm run start`/Dockerfile CMD), which does open -> setContent(pulsing fixture) -> inspectState (layoutBox branch runs, `animated` true) -> isPresentationOnlyAnimated -> close and prints one JSON line.

## Diff per file (all under auto-at-ui/)
- workers/playwright/src/vision-checkpoints.ts: `const layoutBox = (el) => {...}` -> `const geometry = { layoutBox(el) {...} }` (object method, same pattern as `traversal`), call site `geometry.layoutBox(el)`; comment with reason. Maths unchanged (ADR 042 behaviour identical; settle specs pass). `isPresentationOnlyAnimated` needed no change: it has no nested named function (verified by esbuild scan).
- workers/playwright/src/vision-operations.ts (only `open`): `await context.addInitScript("globalThis.__name = globalThis.__name || ((fn) => fn);")` right after `browser.newContext`, comment with reason and ADR.
- workers/playwright/src/vision-observability.ts: new `visionErrorDetails(error, type)`: only for `unexpected_error`; returns `error_name` (allow-list `^[A-Za-z]{1,40}$`, else `Error`), `error_origin` (fixed Playwright prefix regex, only if present), `error_digest` (sha256 first 8 hex). Never message/stack.
- workers/playwright/src/vision-http.ts: catch block stores `errorDetails`, spread into the `vision.request_rejected` fields.
- workers/playwright/src/vision-observability.spec.ts: new test (ReferenceError with URL/token/page text in message and stack -> log has name/origin/digest, no `private-`/`__name`/host text; categorised errors add no fields; bad name falls back to `Error`).
- workers/playwright/src/vision-tsx-runtime.spec.ts (new), workers/playwright/src/fixtures/vision-tsx-runtime-probe.ts (new): the tsx regression test.
- docs/adr/042-settle-geometry-tolerance.md: new section "Runtime: no named closures inside browser callbacks (r17/r18)".
- docs/vision-agent-operations.md: new "Smoke: open and close without a model" subsection.
- docs/graphs/playwright-vision-worker.md: 2 new files added; `sync --apply` regenerated the tables (it dropped 3 files without import links, I re-added the spec and the two Python files that were there before).
- .pytest-artifacts/r18-open-probe.mts (copy of the r17 probe).
- package.json: not changed (existing `npm test` runs the new spec).

## Callback inventory (grep of evaluate/evaluateHandle/addInitScript in src, non-spec)
Method: esbuild 0.23 `keepNames` transform of every src/*.ts, list of indented `__name(` sites, matched to evaluate callback line ranges.
- Browser-side, was broken: vision-checkpoints.ts `layoutBox` (inspectState callback). FIXED.
- Browser-side, clean (no nested named function): vision-checkpoints.ts isPresentationOnlyAnimated + readiness callback (~351); vision-button-semantics.ts (self-contained top-level function); vision-dom.ts:41-156 callback; vision-click-evidence.ts:6 evaluateHandle; vision-locators.ts:32, 56, 111, 167; vision-revalidation.ts:7, 17, 34, 53, 63; vision-operations.ts 263-299, 632-646, 735-774, 920; execute.ts:401; trivial `el => ...` callbacks.
- Node-side named closures that the scan flagged (harmless, never serialised): vision-dom.ts skip/ground/groundCandidate (176-199, after the callback ends at 156), vision-locators.ts `candidate` (141, after callback ends at 137), vision-operations.ts onFrameNavigated/onNavigation/onPage (788-827), execute.ts abort/removeAbortListener, class constructors.
- addInitScript: only the new one in open(). No other contexts get it (other contexts' callbacks have no named closures; the guard is a safety net, add it to `vision.ts` only if that changes).

## Test output (real, --workers=1)
- tsx spec: `1 passed (3.2s)`.
- `npx tsc --noEmit`: exit 0, no output.
- eslint (vision-checkpoints, vision-operations, vision-http, vision-observability, vision-observability.spec, vision-tsx-runtime.spec, probe): exit 0, no output.
- vision-observability.spec: `10 passed (3.0s)` (includes the new log test).
- Group A (settle dev + QA + settle-observability + operations): `140 passed (7.1m)`.
- Group B (agent-mode, agent-mode.qa, agent-evidence, outcome-capture, dom, history, readiness, tsx-runtime, observability): `140 passed (5.8m)`.
- r17 script, local worker under tsx (`node node_modules/tsx/dist/cli.mjs ../../.pytest-artifacts/r18-open-probe.mts ../../.pytest-artifacts/r17-open-payload.json 3`, open + close, mongchiton payload, no navigation/click):

      attempt 1: OK 289 ms caps=9 budget=1001
      attempt 2: OK 266 ms caps=9 budget=1001
      attempt 3: OK 263 ms caps=9 budget=1001
  (r17 before the fix: 3 x FAIL `__name is not defined`.)
Not rerun (outside the requested list): vision-target-preflight, sample-guard, visual-buttons, locators, vision.spec, click-evidence.

## Service to rebuild and live check for the main session
Rebuild/recreate: `playwright-worker` only (source is baked in the image, FS read-only). Not done by me (forbidden). After the rebuild, no-LLM check:
`docker exec -i auto-at-ui-playwright-worker-1 node -e "$(cat .pytest-artifacts/r17-container-open.cjs)"` (posts open + DELETE to 127.0.0.1:7100 with the container secret, no click, no control-plane session). Expect open 200, delete 200 (r17 saw 422 twice). If it still returns 422, Loki `event="vision.request_rejected"` now shows `error_name`, `error_origin`, `error_digest`.

## Findings / caveats
- `hgraph check` (full) exit 0, "Không có vấn đề". `hgraph check --changed` exit 1: it lists 70 changed files as uncovered, with paths prefixed `auto-at-ui/` (git root is one level up, so the path match fails, including for files that `hgraph which` maps to playwright-vision-worker) plus other phases' Python/dashboard files I may not touch. No file of mine is truly unmapped.
- The graph file diff is large because `sync --apply` regenerated the tables on top of earlier uncommitted edits.
- The open() guard only covers the context from `open()`; legacy `openVisualSession` in vision.ts is untouched (no named closures in its callbacks today).

## Processes
All scripts exited themselves; no chrome/node left (checked `ps`). Docker untouched, no commit, no bridge/model call.

GRAPH_UPDATE
- graph đã cập nhật: playwright-vision-worker
- file mới đã đưa vào graph: workers/playwright/src/vision-tsx-runtime.spec.ts, workers/playwright/src/fixtures/vision-tsx-runtime-probe.ts
- hgraph check --changed: exit 1 (path-prefix `auto-at-ui/` mismatch + files of other phases, see Findings); `hgraph check`: "✔ Không có vấn đề."
