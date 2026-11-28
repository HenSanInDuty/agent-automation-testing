# ADR 048: Stop the page clock between operations in agent-loop sessions

Status: accepted (direction 1 approved by the user 2026-11-26, h-fix gate 3); offline red/green; live pending

## Context

An `agent_loop` session opens the worker with `interaction_scope="all"` (`vision_agent_loop.py`). In that scope
`inspectState` puts the geometry and identity of every visible control into `equivalentState`
(`vision-checkpoints.ts`). mongchiton.vn has three Swiper autoplays (delay 3000 ms, speed 300-600 ms), so a state does
not last longer than about 2.9 s, while the agent keeps a state across a model call of about 9 s. Every gate that
compares the held state with a fresh one then refuses: observe start (`vision-operations.ts`), `dom_collection`
(`vision-dom.ts`), `prepare_start`, `prepare_end` and `before_dispatch`. `_observe` gives up after three attempts
(`vision_agent_loop.py`) and the session ends. ADR 042 made the comparison tolerant for CSS geometry; it cannot help
here, because the autoplay changes which control is on show, not only where it is.

Measurement (read-only probe on the public home page, `context.clock.install()` before the page, one scroll to 1440,
20 s of samples every 200 ms):

| Page clock | Samples | Not equivalent to the held state |
|---|---|---|
| running, at 1440 | 41 | 29 (70.7%), first difference after 3.3 s |
| stopped, at 1440 | 81 | 0 |
| stopped, after a second scroll to 2160 | 80 | 0 |
| running again after `resume`, at 2160 | 41 | 37 (90.2%), first difference after 1.2 s |

With the clock stopped, a screenshot took 300 ms, `waitForElementState("stable")` 60 ms and `settleState` 918 ms
(918 ms with the clock running), so the worker's own primitives keep working.

## Decision

New capability `agent-frozen-clock-v1`. It is requested only by the agent-loop open
(`worker_capabilities(..., frozen_clock=True)`, one call site) and honoured only when `agent_mode` is true. The
planner (v4) never asks for it, and a session that does not ask gets no fake clock: behaviour is unchanged.

`vision-operations.ts` (worker only; `equivalentState`, `settleState`, `inspectState`, `vision-dom.ts`, the prompt and
the error codes are untouched):

1. `open()` installs Playwright's `context.clock` before the first page exists, so every document and every popup
   of the context runs on the fake clock, then stops it after the first state is read (`setClock(session, false)`).
   `Session.frozenClock` and `Session.clockRunning` live in RAM only, like `pageText`.
2. Between operations the clock stands still: observe, `check_target`, prepare, the before-screenshot and every gate
   run on a page whose timers do not fire. A proposal rejected before dispatch never starts the clock.
3. `execute()` starts the clock once, after the `before_dispatch` gate and the target verification, immediately
   before the operation is marked `executing`. The page therefore has the whole operation (a click with its popup
   grace window, a navigation, a `wait`) to run its timers, so `setTimeout` effects of a click still appear.
4. After the usual post-operation settle the clock is stopped and `settleState` runs once more (quiet 160 ms, at most
   the operation's own settle budget, 10 s after a navigation or scroll and 1.5 s otherwise, capped by
   `session.deadline`, as the first settle) on the stopped page. That second sample absorbs CSS transitions still in flight, and the state that is
   published (`session.state`, `state_fingerprint`) is the one taken on the stopped page. If that settle fails the
   operation reports `settle_timeout`, as the first one does.
5. The `finally` block stops the clock again (a no-op when it is already stopped) before the after-capture, so every
   exit leaves the page stopped: an error, an unknown outcome, a refused download, a popup, a page change. The stop
   in step 4 runs inside the operation: if it cannot stop the page (after the retries of step 7), the operation ends
   `failed` / `settle_timeout` (its state is not a settled one) instead of being reported unknown, and the second settle
   is skipped. Either failure to stop is logged as `vision.clock.freeze_failed` with `error_type`, `error_name`,
   `error_origin` and `error_digest` (as the other `unexpected_error` rejections; never the message or stack). The
   flag `clockRunning` is set before the call that can start the clock and cleared only after a stop is known to
   have worked, so a failed start or stop leaves it on "running" and the next exit tries again; the session never
   goes on with a running clock marked as stopped.
6. A `wait` (also the observation refresh) runs with the clock started, so page time passes during it. This is the
   only way the agent can let a page "run on".
7. A popup or a new document gets the fake clock from the context init script that Playwright replays from its call
   log, and is stopped by the same context-wide call (`pauseAt` reaches every frame of every page). The stop time is
   read from the page itself (`Date.now()` plus 1 ms). Cause found by measurement in round 2 (live: 1 session in 15
   ended `initial_capture_failed`): on a page with a child frame (srcdoc, `about:blank`, cross-origin) the child's
   clock is 3-96 ms ahead of the main frame's, so `pauseAt` throws "Cannot fast-forward to the past" for that frame,
   but only after it has stopped every frame (6 of 6 local pages with a child frame document threw; an empty script-created iframe did not; on every one all frames
   were frozen afterwards). The
   worker accepts that error only when it then reads `Date.now()` of every frame twice, 250 ms apart, and all values
   are equal (`pageClockStopped`). Any other error (for example a late navigation destroying the execution context
   the time was read from) is retried up to four attempts, 100 ms apart, within `session.deadline`, and then thrown.
   A fake stop time far enough ahead for every frame was rejected: it would fire timers of the frames that are behind.

Contract: `required_capabilities` of `VisualWorkerOpen` accepts the new literal (`max_length` 12); the TypeScript
contract is regenerated, not edited. `open` returns the capability in `capabilities`.

## Limits

- An infinite CSS animation that moves a control (translate, marquee) and video are not stopped by the page clock.
  They still end in `state_kept_changing` / `settle_timeout` as ADR 042 describes; this ADR does not change that.
- The clock runs for the whole operation, so a timer with a period under the 160 ms quiet window, or an endless
  `requestAnimationFrame` loop that moves a control, never settles inside an operation: the operation ends
  `settle_timeout` (QA cases C06 and C08). The page stays stopped afterwards. On such a page the first navigation of
  `open` fails as it did before this ADR.
- Content that appears after a timer without any operation shows up only when the agent runs its next operation,
  `wait` included. The model does not see it earlier. The prompt `agent-loop-v4` is unchanged and does not tell the
  model that the page is stopped; a model that expects a banner "after a few seconds" must call `wait`.
- The page's `Date.now()` falls behind real time by the total time spent stopped. A site that compares it with a
  server time (token expiry, countdown) can see an unusual clock. Accepted: a session lasts minutes.
- Out of scope, existing bug: a read-only observation refresh that ends `settle_timeout` does not update the state the
  worker holds, so the next observe is `state_mismatch`. With the clock stopped the refresh settles at once, which
  makes it rarer but does not fix it.
- Every start/stop adds an entry to Playwright's clock log and an init script to the context, replayed on each new
  document. A session of a few hundred operations is small; there is no cap.
- Playwright pinned at 1.50.1 (`Clock` API); a major upgrade must re-run the specs below.

## Safety risk

Low. The clock only changes when page timers fire; no click, navigation or type is added, and every gate of
prepare/execute runs before the clock starts. If stopping the clock fails, the operation says so (step 5) and the next
gate sees a changed state and refuses, as before this ADR. The capability is requested by one call site; rollback is removing the
`frozen_clock=True` argument there (the worker then never installs the clock).

## Tests

`workers/playwright/src/vision-agent-mode.spec.ts`, on a fixture page with a timer-driven carousel
(`/carousel`, `/carousel-late` in `fixtures/agent-loop-target.ts`):

- Without the capability: observe, wait past one period, prepare is `state_mismatch` at `prepare_start` (pins the old
  behaviour). With the capability the same flow, with eight periods of waiting, prepares and executes `completed`
  twice with no `vision.state.mismatch` line (red before the worker change: `round 1: state_mismatch`).
- `wait` 1000 ms moves the carousel and changes the state, then the page stands still; the refresh wait works.
- Click (with a 50 ms `setTimeout` effect), type, scroll and the screenshot work on a stopped page.
- A popup (page time stopped, `close_popup` back to a stopped parent) and a navigation to a document whose timer
  starts 4 s after load (still `Slide 0` 4.5 s later).
- A proposal rejected at prepare, a proposal rejected at `before_dispatch` (page time does not move), and an
  unknown outcome after dispatch all leave the clock stopped.
- No capability: `Date.now()` advances while idle; v4 mode that asks for it gets the capability reported and no clock.
- Round 2: a page with srcdoc, `about:blank` and cross-origin child frames (`/carousel-frames`) opens, runs click and
  `wait`, and every frame's `Date.now()` stands still after each operation, with no `freeze_failed` and no
  `vision.state.mismatch` line (red before the fix: the first navigate ended `action_outcome_unknown`). With `pauseAt`
  made to throw, the operation ends `failed` / `settle_timeout`, `clockRunning` stays true, the log carries
  `error_name` and `error_digest` and no message text, and once the stop works again the next operation stops the page.
- The existing cases that must keep failing (relabelled target, replaced control, modal, URL, scroll, form value) are
  unchanged and green.

Python: `worker_capabilities()` default, order and agent-loop call (`tests/test_vision_agent_loop.py`), the contract
(`tests/test_vision_worker_contracts.py`). Manifest hashes were regenerated (`tests/test_codex_bridge_benchmark.py`).
The live gate is one agent session on the real site; it has not run yet.

## Rollback

Remove `frozen_clock=True` at the call in `vision_agent_loop.py`; the worker and the contract can stay.
