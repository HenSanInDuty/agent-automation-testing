STATUS: DONE

CONTEXT_CHECK
- conventions: AGENTS.md (read via hook), docs/code-standards.md (index only), docs/adr/042-settle-geometry-tolerance.md, be-developer-r20.md (full), be-developer-r18.md (tsx pitfall); docs/api-conventions.md does not exist (no API change)
- graphs: playwright-vision-worker (brief: `workers/playwright/src` as a folder is in no graph, the file graph exists and was read)
- blast radius: no existing source touched; one new spec, 0 dependents (hgraph brief: 0 files depend on the r20 spec)

# r21 (offline, animation suppression probe): can the worker calm `mount-switcher` while it settles?

No source change, no live session, no bridge/model, no docker, no commit. Chromium headless 1280x720, `reducedMotion: "reduce"` + passthrough route (as `vision-operations.ts:152`), worker `inspectState`/`equivalentState`/`settleState` under tsx (`node node_modules/tsx/dist/cli.mjs`, r18 pitfall respected: the in-page code is evaluated without nested named functions the probe cannot serialise; `window.__name` init script as the worker).

## Verdict
1. A page-wide CSS rule that shortens every animation/transition to 1 ms (`b2`) makes the site settle reliably inside a burst: 1-2 state changes in 5 s instead of 22-30, longest quiet 3.8-4.3 s, `settleState(3 s, 800 ms)` ok in 0.9 s (control: `settleState` fails in 2.9 s, 28 changes). It is reversible, fires `transitionend`/`animationend`, ends every animation at its true end state and does not mutate page DOM except one `<style>`. Reproduced 2 of 2.
2. `transition:none` + `animation-play-state:paused` (`b`) and a looping `Animation.pause()` (`a2`) also stabilise (1-2 changes) but change page semantics: they swallow `transitionend`/`animationend`, and `a2` freezes an intermediate frame (box 31 px off the end state, scale 1.039) that a later `play()` moves again. Rejected as the primary measure.
3. One-shot pause (`a1`), `finish()` (`c1`, `c2`), scoped pause/CSS on the running-animation subtree (`d1`, `d2`) and CDP `Animation.setPlaybackRate(100)` do NOT help (17-30 changes in 5 s).
4. Suppression is not sufficient alone: (i) the page's own JS timers keep writing the DOM during suppression (class/style/childList, 21-47 mutations in 5 s, the carousel keeps hopping, 1-2 hops per 5 s, each is one state change), so a hop between `settle` and `prepare_end` / `before_dispatch` still gives `state_mismatch`; (ii) once the calming style is removed the churn returns at baseline level at once (20-23 changes per 4 s), so it must stay on until the post-click capture, not only during settle; (iii) a timer that moves controls itself is not stopped (fixture). Recommendation: B2 as a settle assist for viewport ops, combined with A-lite (settle again once before `prepare` when `state_mismatch` is a single hop) or B (ADR scoped equivalence) for the residual hop mismatch. Details in "Design".

## Method
Probe `.pytest-artifacts/r21-suppress-probe.mts` (read-only: wheel, the five tab clicks of r12/r19/r20, no other click, no form). Shape = r20 i3: open, wheel 600, tabs Su Kien / Cam Nang / Tin Tuc / Nhan Vat / Thu Cuoi, wheel to y=1200 (`scroll_y` 1200 in all runs). Then wait for the start of a burst (at least 5 non-equivalent samples within 2 s; found at 6.6-6.9 s in every run), and inside the SAME burst: phase 1 baseline (4 s), apply measure, `settleState(3 s, 800 ms)`, phase 2 measured (5 s), screenshot, restore, phase 3 restored (4 s). A MutationObserver (attributes, childList, characterData, subtree) runs for the whole page; swiper wrapper transforms and screenshot hashes are sampled (`snaps`, runs `s2`-`s4`). Using one burst for control and treatment removes the burst-phase uncertainty of r20.
Metrics per phase: `state_changes` (samples not `equivalentState` to the reference), `longest_quiet_ms`, reasons (hit / bounds / content / count), `document.getAnimations()` census.
Mutation counts are labelled by the phase flag, which is set when a `measure()` starts, so the 3 s `settleState` is attributed to the preceding phase; compare shapes, not exact numbers.

## Results (all in a burst, y=1200)
| Variant | What | Baseline chg / quiet | Mitigated chg (5 s) / longest quiet | `settleState` 3 s | Restored chg (4 s) | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| none (control, 2 runs) | nothing applied | 24/327 ms, 23/342 | 28/345 ms, 28/345 | FAIL 3.0 s, FAIL 2.9 s (16 changes, quiet 244 ms) | 22, 24 | burst reproduced, 100% hit churn (hit 24-28, box 6) |
| a1 | `getAnimations()` pause once, `play()` after | 20/352 | 18/1605 | ok 0.84 s (fluke: gap right after apply) | 21 | no: new transitions start after the pause |
| a2 | pause every 40 ms (new animations too), `play()` after | 23/273 | 2/3701 | ok 0.84 s | 21 | stabilises, but frozen mid-frame (below) |
| b (3 runs) | style `animation-play-state:paused; transition:none` | 20-24/295-350 | 1/3735, 1/4255, 1/4233 | ok 0.84 / 0.93 / 0.85 s | 20-23 | stabilises; swallows end events |
| b2 (2 runs) | style `animation-duration/transition-duration:1ms; delay:0; animation-iteration-count:1` (site probe form; the spec's `FAST_CSS` omits the iteration count) | 23/329, 21/353 | 2/4215, 2/3767 | ok 0.95 / 0.91 s | 23, 23 | stabilises, keeps semantics |
| c1, c2 | `finish()` finite running animations (once, every 40 ms) | 23/276, 23/351 | 30/361, 27/362 | FAIL 2.9 s, FAIL 3.0 s | 23, 20 | no (0 running finite animations at the first call, `n0=0`) |
| d1 | pause (every 40 ms) only the LCA subtree of the running animations = one `div.mount-switcher` | 22/344 | 22/1102 | ok 0.96 s | 21 | no: churn comes from other elements |
| d2 | same scope with scoped CSS rule | 23/297 | 30/384 | FAIL 2.95 s | 23 | no |
| cdp | CDP `Animation.setPlaybackRate(100)` (2 runs) | 22/330, 22/369 | 22/698, 17/1382 | FAIL 2.9 s, FAIL 2.9 s | 22, 21 | no |

Notes on the table.
- b2 note: the first run of the variant used `animation-iteration-count:1!important` as well (probe text `b2`); the product-worthy form is the duration-only one in `vision-settle-suppression.spec.ts` (`FAST_CSS`). The site probe used the iteration-count form; both runs gave 2 changes. Not measured: the duration-only form on the live site (spec fixture only). Treat as a residual difference to verify live.
- Reasons in the mitigated phase: b `{hit:1}`, b2 `{bounds 4, hit 2}`, a2 `{bounds 5, hit 1}`, controls `{hit 28, bounds 6}`. Hit probes of `mount-switcher` are the churn; they quiet down with b/b2/a2.
- a1/c/d/cdp fail because the culprit transitions are created repeatedly after any one-shot action, and the censuses (`anim_during`) show at most 1 animation (the infinite pulse) at a random instant: the churn is a stream of short-lived CSS transitions that appear and die between probes, plus JS style writes (`div.swiper-slide...before` and `div.swiper-wrapper` attr:style, `div.swiper-slide.flex.justify-center` attr:class). Only a rule that applies to every future element (b, b2) or a loop that pauses everything every 40 ms (a2) removes them; scoped subtrees chosen from the running animations at one instant miss them (d).
- Why CDP rate 100 failed while 1 ms durations worked is NOT established (CDP rate scales the document timeline, the churn did not go away; possibly the writes are rAF/JS driven from the timeline, not from transitions). I report it as observed.

## What the page does while suppressed (attributes, timers, frozen state, restore)
- JS timers keep changing the DOM. During b (5 s): 21-25 mutations (`attr:class` 13, `attr:style` 5-9, `childList` 3), top target `div.swiper-slide.flex.justify-center` class (7): the Swiper autoplay keeps advancing. During b2: 47 mutations, class 26, style 16, childList 5. Baseline in the same unit: about 80 per 4 s. So suppression removes the per-frame writes, not the page's own timers.
- Carousel hops continue: wrapper `translateX` of the 2nd swiper -5850 (slide 3) -> -7800 (4) in b, -> -9750 (5) in b2 over 5 s, restored run -> -11700 (6). Each hop is instantaneous under b/b2 and is one state change (hit flip), which is what `longest quiet 3.7-4.3 s` with 1-2 changes shows.
- b: transitions are cancelled to their end state (`transition-property: none` visible in `snaps`: tp `none` while applied), pulse (the single infinite animation) is paused, not ended: `anim_during` = 1 paused infinite. `transitionend` never fires (fixture, below). After restore `transition-duration` is 0.6 s / 0.3 s again and `leftover_style_nodes` = 0.
- b2: no `transitionend` swallowing (fixture); after restore the same durations return; `leftover_style_nodes` = 0.
- a2: 15 paused animations (14 finite) at the end of the window; sampled style at that moment `margin-left -113.5 px` (rest -20), `scale 1.039`, one `mount-switcher` box at x 112 vs 143 at rest (31 px, over the 3 px / IoU 0.8 tolerance), another at -58.9 px vs -140 px. That is an intermediate frame; `play()` restored the rest values (`style_after` equals `style_before`).
- Screenshots: during b the screenshot hash changes only when a hop lands (`snaps`: before 8b30be214c, mit+3 s e0225e6dd4 (equal hop index 3, different hash because of the pulse frozen at another phase), mit+8 s e15c8da553 (hop 4)); the frame shows true end states, not mid-frames. Under a2 the paused screenshot (`r21-a2-paused.png`) shows the frozen mid-frame (fixture proves the same: frozen frame != end-state frame). Images: `.pytest-artifacts/r21-*-paused.png` (8 files, 1 per variant), not reloaded for review (no image review required by the conclusion, which rests on the numbers and fixture).
- Restore: after removing the style or playing the animations the churn returns at the baseline level in every run (phase 3: 20-23 changes per 4 s). Therefore the worker would have to keep the page calm from `settle` through `prepare` (held vs fresh `equivalentState`), `dispatch` and the after-capture, otherwise `held` (calm) and `fresh` (not calm) disagree at once. I did not run a held-vs-fresh comparison across an unsuppress on the live site; this follows from phase 3 and from the equivalence rule, not from a direct measurement.

## Safe-click and screenshot side effects (local fixture, not the site)
New spec `workers/playwright/src/vision-settle-suppression.spec.ts` (6 tests, all pass). Fixture: 3-slide carousel hopping every 1000 ms by a 600 ms CSS transition (quiet gap 400 ms < 800 ms), `transitionend` increments a counter; a second fixture where a JS timer moves a card via inline `left`.
| Test | Result |
| --- | --- |
| baseline hop every 1000 ms never settles (after the first hop) | passes (settle false) |
| `transition:none` + paused: settles, JS timer still ran (`__n` > 0), `transitionend` count stays 0 | passes (semantic change documented) |
| 1 ms durations: settles, `transitionend` fires, suppressed screenshot (timer stopped) byte-equal to the real end-state screenshot after the style is removed, `translateX` equals `-300*n` | passes |
| `pause()` of running animations: frozen transform between -300 and 0, unchanged after 700 ms, end state -300 after `play()`, frozen screenshot != end-state screenshot, `equivalentState(held frozen, fresh after resume)` false | passes (frozen-intermediate hazard documented) |
| JS timer moving a card by inline `left`: not settled under `PAUSE`, `NONE` (`transition/animation:none`) and `1ms` | passes |
| after resume (1 ms rule removed, timer stopped): `elementFromPoint` at the centre of slide n is that exact node and `mouse.click` there is received by it | passes |
Not tested on the real site: clicks (no click beyond the five tab clicks of r12/r19/r20). The click-safety statement is the fixture's only.
Finding while writing the fixture: a plain z-index re-stacking timer with the animation removed did NOT flip the five hit probes in my fixture (the r20 fixture's churn came from its `scale`/`margin-left` animation, not from the class toggle). This weakens the r20 "z-index timer" wording; on the real site the hit churn follows the CSS/JS motion and disappears under b/b2, which fits.
Fixture lesson: `setContent` on the same page re-runs scripts in one window, `const` re-declarations throw (the second fixture iteration silently ran no timer); the spec wraps the timer script in an IIFE.

## Design (best option: B2 "calm motion", not implemented)
Choice: B2 = a `<style data-auto-at-calm>` with `*,*::before,*::after{animation-duration:1ms!important;animation-delay:0s!important;transition-duration:1ms!important;transition-delay:0s!important}`.
Why not b / a2: they swallow `transitionend`/`animationend` (menus, modals, carousels waiting for the event stall) or freeze mid-frame. Why not scoped (d): the culprit set is not the set of running animations at one instant. Infinite animations (the pulse) run 1 ms iterations forever with B2 (duration only, iteration count untouched), so ADR-042 B still applies to them and nothing is hidden; to be verified live.
1. New file `workers/playwright/src/vision-calm.ts` (small module, no abstraction beyond three functions): `enableCalm(page)`, `disableCalm(page)` (idempotent, tolerate closed page/detached frames), `withCalm(page, fn)` (try/finally). Injection by `page.evaluate` of a string-built function (r18: no nested named helpers inside evaluate callbacks; `window.__name` init script is already in the context). Style node id fixed, so a second `enableCalm` is a no-op and `disableCalm` removes by id. Main frame only (the worker's `inspectState` reads the main document; iframes keep the real timing, a documented limit).
2. Where it is called (`workers/playwright/src/vision-operations.ts`):
   - `~887`, the settle after a viewport-changing action (`viewportChanged` = scroll/navigate/back/close_popup): `enableCalm(afterPage)` before `settleState(... 10_000, 800)`; keep it through the after-capture and outcome screenshot; `disableCalm` in the operation's `finally`.
   - `~552`, refresh settle (`refresh_observation`): same pair.
   - `prepare` / `observeDom` compare (`~328`, `~557-561`, `~655`, `~729`): `session.state` must be measured under the same regime as the fresh inspection. The simplest consistent policy is session-level: enable on the page when the op that scrolls/navigates starts, keep it until the operation (including the click and post-click capture) ends or `close`. A per-settle on/off is rejected by phase 3 above.
   - Feature flag: worker env var (default off until a live run shows it works); no contract field change.
3. Restore on every path: `finally` in the operation wrapper for success, `settle_timeout`, thrown errors, `navigated`/popup (the new `afterPage`), target page closed (swallow `TargetClosedError`), session close, worker shutdown. After a navigation the style is gone with the old document, the call re-applies on the new document before its settle.
4. Residual hop mismatch: with calm on, 1-2 hops per 5 s remain. A hop between settle and `prepare_end` / `before_dispatch` gives `state_mismatch` (r19 seq 12/13 shape). Combine with A-lite: on `state_mismatch` at prepare, run one more `settleState` and re-compare once (bounded by `session.deadline`), or B (ADR scoped equivalence for non-overlapping movers). That choice is the user's.
5. Tests to add (new spec `vision-calm.spec.ts`, plus a tsx twin because the evaluate code is in the worker bundle): (a) enable/disable idempotent and removes the node; (b) disabled on thrown error, closed page, navigation; (c) the carousel fixture settles with calm and does not without; (d) `transitionend` fires; (e) the calm frame equals the real end-state frame; (f) JS-timer fixture still fails (documents the limit, `test.fail()`); (g) the r18 tsx runtime check (`vision-tsx-runtime.spec.ts` shape) with the calm code path; (h) click lands on the exact node after calm.
6. ADRs: a new ADR 043 "Calm motion during settle" (status proposed): decision, rejected alternatives (a/b/c/d/cdp with the numbers above), the held/fresh same-regime rule, the residual hop, the flag, and the "what the worker may do to the page" statement (a style node only, no DOM, no events). Add a short cross-reference line in ADR 042 (B animated path unchanged). Update `docs/graphs/playwright-vision-worker.md` (new file via hgraph) and the worker README if it lists env flags.
7. Cost/risk of the design: the agent sees calm frames (transitions skipped) and any test that asserts timing sees a changed page, so the flag stays Vision-agent-only; the live site can change; only 2 runs of the exact B2 form on the real site (plus 3 of b).

## Honest limits
- 1 site, one burst per run, 2-3 runs per promising variant, 1 run for the rest; the Windows Chromium run may differ from the Linux container (same engine family).
- The B2 site probe used a slightly stronger rule (`iteration-count:1`) than the one in the spec; the duration-only form is unproven on the live site.
- The r19 seq 9 `delta_y` is still unread (r20 open item 1). This probe shows the calm measure removes burst churn at y=1200; it does not prove r19 seq 9 was a burst.
- The mechanism of `mount-switcher` hit churn is partly unexplained (cdp rate vs 1 ms; why finish() at 40 ms does not help).
- Held-vs-fresh across unsuppress was inferred, not measured on the site.

## Checks (real output)
```
$ npx playwright test src/vision-settle-suppression.spec.ts --reporter=list --workers=1    (workers/playwright)
  6 passed (28.0s)
$ npx tsc --noEmit        -> no output (clean)
$ npx eslint src/vision-settle-suppression.spec.ts   -> no output (clean)
```
Site probe output lines (one per run, `"ph"` = [phase, state_changes, longest_quiet_ms]):
```
none  settle {"settled":false,"ms":3014}  [["1_baseline",24,327],["2_mitigated",28,348],["3_restored",22,330]]
a2    settle {"settled":true,"ms":838}    [["1_baseline",23,273],["2_mitigated",2,3701],["3_restored",21,396]]
b     settle {"settled":true,"ms":844}    [["1_baseline",20,295],["2_mitigated",1,3735],["3_restored",22,366]]
b2    settle {"settled":true,"ms":946}    [["1_baseline",23,329],["2_mitigated",2,4215],["3_restored",23,404]]
b2    settle {"settled":true,"ms":911}    [["1_baseline",21,353],["2_mitigated",2,3767],["3_restored",23,360]]
c2    settle {"settled":false,"ms":3020}  [["1_baseline",23,351],["2_mitigated",27,362],["3_restored",20,408]]
d1    settle {"settled":true,"ms":961}    [["1_baseline",22,344],["2_mitigated",22,1102],["3_restored",21,359]]
cdp   settle {"settled":false,"ms":2945}  [["1_baseline",22,330],["2_mitigated",22,698],["3_restored",22,358]]
```
Artifacts: `.pytest-artifacts/r21-suppress-probe.mts`; `r21-{none,a1,a2,b,c1,c2,d1,d2}.json`, `r21-s2-{none,b}.json`, `r21-s3-b2-*.json`, `r21-s3-b-*.json`, `r21-s4-cdp-{1,2}.json`, `r21-*-paused.png`.

## Files
- created: `workers/playwright/src/vision-settle-suppression.spec.ts` (new spec, fixture inline)
- artifacts: `.pytest-artifacts/r21-*`
- appended: `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md` (r21 section), `plan/09112026103202-vision-accuracy-loop/README.md` (r21 handoff)
- graph: `docs/graphs/playwright-vision-worker.md` (+1 file via hgraph, total 38)
- no source change, no commit, no live session, no bridge/model call, no docker action. Every probe closed its browser; no process left.

GRAPH_UPDATE
- graph đã cập nhật: playwright-vision-worker
- file mới đã đưa vào graph: workers/playwright/src/vision-settle-suppression.spec.ts
- hgraph check: `hgraph check` -> `hgraph check — 6 graph, 470 file source` / `✔ Không có vấn đề.`; `hgraph check --changed` still lists 70+ files from other uncommitted work (control-plane Python, dashboard, docs) as `uncovered-changed`; none belong to this phase and none are mine (the only file I created is covered)
