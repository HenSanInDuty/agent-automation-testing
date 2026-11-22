STATUS: DONE

CONTEXT_CHECK
- conventions: docs/code-standards.md (via hgraph brief), AGENTS.md, be-developer-r16.md (read in full). docs/api-conventions.md not read: diagnosis only, no API change. ADR-042 not re-read (only the code).
- graphs: playwright-vision-worker (hgraph brief for server.ts; 32 files). Graph body not re-read beyond the brief (read-only diagnosis).
- blast radius: not applicable (no source changed). Brief for server.ts: 0 dependents, 8 dependencies.

# r17 - Why the r16 live session was rejected at session_open

## Root cause (reproduced, deterministic)
`session_open` fails because `inspectState()` (called by `open()` right after the blank page is created) throws inside the browser:

    page.evaluate: ReferenceError: __name is not defined
        at inspectState (workers/playwright/src/vision-checkpoints.ts:30)   <- page.evaluate call
        at VisualOperationWorker.open (workers/playwright/src/vision-operations.ts:209)

The worker container runs the source through **tsx** (`workers/playwright/Dockerfile` `CMD npm run start` -> `package.json` `"start": "tsx src/server.ts"`). tsx 4.19.2 transforms with esbuild 0.23.1 `keepNames: true` (grep of `node_modules/tsx/dist/index-*.cjs` shows `keepNames:!0`). With keepNames, esbuild rewrites every named function/arrow to `__name(fn, "name")`. A callback passed to `page.evaluate` is serialized with `toString()` and runs in the page, where the helper `__name` does not exist -> ReferenceError.

The trigger is the **r14/r14b** code: the evaluate callback of `inspectState` gained a nested named arrow, `const layoutBox = (el: Element): number[] | null => {...}` (vision-checkpoints.ts ~line 40). esbuild output for it: `const layoutBox = /* @__PURE__ */ __name((el) => {`. The HEAD version of the file has no nested named function in that callback.

Why nothing caught it earlier: the Playwright test runner (45/45 specs pass locally, and r16's own local run) uses its own Babel transform, which does not inject `__name`. Only the production entry point (tsx) does. So fixtures/specs pass, the container fails, on any page (the failure happens on the blank page before any navigation, so it is NOT specific to mongchiton.vn).

Consequence: not only `open`. `inspectState` is also used by navigate/observe/check-target, so no session can work in the current build, in the container or under `npm run start`. r12 (pre r14) worked because that callback had no nested named function.

## Suspicions ruled out
| Suspicion | Verdict | Evidence |
| --- | --- | --- |
| (a) Python/TS contract drift after r15 shelve (capabilities, frames maxItems) | Ruled out | The exact control-plane payload (built with the real `VisualWorkerOpen` model, caps `dom-observation-v1, step-timeout-v1, click-context-v1`, 1280x720, agent_mode, blocked terms) passed `validateVision("VisualWorkerOpen")`; the failure is at vision-operations.ts:209, after validation. A contract failure would also be logged `contract_rejection` (VisionWorkerError), not `unexpected_error`. |
| (b) r14 code throws only on the real mongchiton page | Partly right on cause (r14 code), wrong on trigger | It is r14 code, but it throws on the blank `about:blank` page too; the real site is irrelevant. |
| (c) Chromium cold start | Ruled out | Launch works: local open takes ~0.3 s, container 0.8-1.1 s on repeats. The 3,787 ms in r16 was the first cold launch before the same ReferenceError. |
| r15 shelve | Not involved | The offending hunk is the r14 `layoutBox` closure (also present in HEAD+r14 only); the shelve touched contracts/generated file. |

## Reproduction (no LLM, no bridge, no control-plane session)
1. Payload: `.pytest-artifacts/r17-make-payload.py` -> `.pytest-artifacts/r17-open-payload.json` (run: `PYTHONPATH="apps/control-plane;packages/contracts/src" uv run python .pytest-artifacts/r17-make-payload.py <out>`; note `;` separator on Windows). Flags A1+A3 equivalent: `click-context-v1` on, `agent-dom-path-v1` off (A2 is a different flag).
2. Local, direct call of `VisualOperationWorker.open` under tsx, 3 attempts (`.pytest-artifacts/r17-open-probe.mts`):

       attempt 1: FAIL 335 ms type=unexpected_error name=Error code=undefined
       page.evaluate: ReferenceError: __name is not defined
           at inspectState (...vision-checkpoints.ts:30:31)
           at VisualOperationWorker.open (...vision-operations.ts:209:27)
       attempt 2: FAIL 303 ms ... attempt 3: FAIL 308 ms ... (identical)
   `visionErrorType` classifies it `unexpected_error`, matching the r16 log exactly.
3. Container `auto-at-ui-playwright-worker-1` (port 7100 is not published, so `docker exec -i ... node -e <r17-container-open.cjs>` posts to 127.0.0.1:7100 with the container's own secret; open + DELETE, no click, no control-plane session), 2 attempts:

       open 422 1086 ms {"detail":"visual_request_rejected"}
       delete 422 {"detail":"session_unavailable"}
       open 422 801 ms {"detail":"visual_request_rejected"}
       delete 422 {"detail":"session_unavailable"}
   Same outcome as r16 (422 `visual_request_rejected`; DELETE `session_unavailable` because no session opened). No session or process left in the container.
4. Which construct: `.pytest-artifacts/r17-keepnames2.cjs` (esbuild 0.23.1 keepNames transform, count `__name(` inside the `inspectState` evaluate callback): HEAD 0, tree 1 (`layoutBox`). `r17-nested-names.cjs` over vision-checkpoints/vision-dom/vision-operations: all other nested `__name` sites (vision-dom skip/ground/groundCandidate, vision-operations onFrameNavigated/onNavigation/onPage) are Node-side closures and exist in HEAD at the same count, so they are harmless. layoutBox is the only new browser-side one.
5. Fix check without editing source: `.pytest-artifacts/r17-open-probe-fixed.mts` passes a `launch` wrapper (constructor arg of `VisualOperationWorker`) that calls `context.addInitScript("globalThis.__name = globalThis.__name || ((f) => f);")`. Result: `attempt 1: OK 451 ms caps=9 budget=1001`, `attempt 2: OK 420 ms` (opens, and the 9 capabilities incl. `click-context-v1` are returned).

## Proposed minimal fix (not implemented)
1. In `VisualOperationWorker.open` (vision-operations.ts ~152, right after `browser.newContext(...)`), add
   `await context.addInitScript("globalThis.__name = globalThis.__name || ((fn) => fn);")` with a comment explaining tsx keepNames. One line; covers every current and future named closure inside `page.evaluate` callbacks for sessions. Other contexts created by legacy `openVisualSession`/tree-state paths (vision.ts) should get the same line only if their callbacks gain nested named functions (a quick check of their callbacks shows none today); a shared helper `newVisionContext` is optional and not needed for this fix.
   Alternative (not preferred): remove the nested arrow (inline `layoutBox` as an expression-free structure); fragile, the next closure re-breaks it.
2. Regression test that fails today: a spec that spawns the real entry transform. For example `execFile("npx", ["tsx", "-e", "<import open, open against a data: URL fixture, print ok>"])`, or one test that compiles `vision-checkpoints.ts` with esbuild `keepNames:true`, `page.evaluate`s `inspectState`'s callback against the existing fixture page. Must run under tsx, not the Playwright transform, otherwise it cannot see the bug. Also add the same check as a CI/pre-live smoke: `r17-open-probe.mts` (3 attempts) is a ready-made probe.
3. Process: run one no-LLM open+close against the rebuilt container before any further paid live session (rebuild/recreate of `playwright-worker` is required; the container FS is read-only and the source is baked into the image).

## Proposed safe log for `unexpected_error` (not implemented)
`visionErrorType` deliberately never logs the message (page text, URLs, credentials). Add fields, in `vision-http.ts` catch (line ~137) and `vision-observability.ts`:
- `error_name`: `error.name` (e.g. `ReferenceError`, `TypeError`), allow-listed against `^[A-Za-z]{1,40}$`.
- `error_origin`: the Playwright API prefix if the message starts with `/^(page|locator|frame|browserType|browserContext|browser|elementHandle|jsHandle)\.[A-Za-z]+/` (e.g. `page.evaluate`), else omitted.
- `error_digest`: first 8 hex chars of `sha256(message)`; lets repeated failures be correlated without exposing text.
- `error_frame`: first stack frame `file:line` inside `workers/playwright/src` only (repo path, no user data), e.g. `vision-checkpoints.ts:30`.
Test: unit test in `vision-observability.spec.ts` that a plain Error with a URL/credential in the message yields `error_name`/`error_digest` and the log line does not contain the message text.
With these, the r16 log would have said `error_name=ReferenceError error_origin=page.evaluate error_frame=vision-checkpoints.ts:30`, diagnosable without a retry.

## Impact inventory for the proposed fix (not applied)
- Database: không đụng.
- Files: `workers/playwright/src/vision-operations.ts` (one line in `open`), `workers/playwright/src/vision-http.ts` + `vision-observability.ts` (log fields), new spec for tsx smoke, `vision-observability.spec.ts`. No contract, env or API change. Callers of `visionErrorType`: grep before changing its signature (prefer adding a new helper).
- Existing tests: 45 vision specs (Playwright transform) cover open but cannot catch tsx-only failures; no test covers the tsx entry.

## Findings (file:line)
- `workers/playwright/src/vision-checkpoints.ts:~40` (nested `const layoutBox = (el) => {...}` inside the `page.evaluate` callback begun at :30) - breaks under tsx keepNames: `__name is not defined` on every `inspectState`; entire worker is unusable in the container since r14.
- `workers/playwright/Dockerfile` CMD / `package.json` `start` - production runs through tsx while tests run through Playwright's transform (transform mismatch, the reason specs missed it).
- `workers/playwright/src/vision-http.ts:137-139` + `vision-observability.ts:15-24` - `unexpected_error` carries no name/origin, hid this for a whole live session.

## Commands run (all with timeouts, none interactive)
- `hgraph brief workers/playwright/src/server.ts ...`; `uv run python r17-make-payload.py`; `npx tsx r17-open-probe.mts payload 3` (3 FAIL); `docker exec -i auto-at-ui-playwright-worker-1 node -e ...` x2 (2 x 422); esbuild keepNames scripts; `npx tsx r17-open-probe-fixed.mts payload 2` (2 OK).
- Not run: no rebuild/restart/stop of any container, no control-plane session, no bridge/model call, no source edit, no commit.

## Processes
All scripts exited by themselves (`process.exit(0)` / end of command). Local Chromium instances closed with the worker `close`/exit; no node, tsx or chrome process left. Docker stack untouched (container only received two `docker exec` calls that finished).

## Files written (only .pytest-artifacts/r17-* and this report)
`.pytest-artifacts/r17-make-payload.py`, `r17-open-payload.json`, `r17-open-probe.mts`, `r17-open-probe-fixed.mts`, `r17-container-open.cjs`, `r17-keepnames.cjs`, `r17-keepnames2.cjs`, `r17-nested-names.cjs`, `r17-head-vision-{checkpoints,dom,operations}.ts` (copies of HEAD for comparison), this report and `.log`.

GRAPH_UPDATE
- graph đã cập nhật: không cần — không thêm/xoá file source, không đổi import (chỉ file trong .pytest-artifacts)
- file mới đã đưa vào graph: không có
- hgraph check --changed: not run (no source change)
