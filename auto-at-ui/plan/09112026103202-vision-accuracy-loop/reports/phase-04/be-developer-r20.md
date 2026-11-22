STATUS: DONE

CONTEXT_CHECK
- conventions: AGENTS.md, docs/code-standards.md (index only), docs/adr/042-settle-geometry-tolerance.md, be-developer-r19.md (full), be-developer-r13/r14b/r18 via ADR-042 and the r13 probe source; docs/api-conventions.md does not exist (no API change)
- graphs: playwright-vision-worker (hgraph brief said no graph covers `workers/playwright/src` as a folder; the file graph exists and was read)
- blast radius: no existing source touched; one new spec file, 0 dependents

# r20 (offline, read-only): why does the home page not settle on the scroll after the TOP button?

## Verdict
The TOP click is NOT the cause. The failing signature (about 52 state changes in 10 s, longest quiet 236-266 ms, geometry/hit-only drift of 1-3 of 18 controls) is the same in r12 (no TOP click) and r19. What I reproduced under the worker's own `inspectState` / `equivalentState` / `settleState` (tsx, Chromium headless 1280x720, `reducedMotion: "reduce"`, same context options as `vision-operations.ts:152`) is a page widget that produces exactly that signature:

- Mechanism: with the NHAN VAT / THU CUOI tabs active and the viewport on their panel (scroll y about 1200), the "switcher" widget (`div.mount-switcher`, and `div.character-switcher` + `a.video-frame` carousel without the tabs) churns the state for long bursts. Per sample (about 125 ms) one or more controls change: the five hit probes flip (overlapping cards re-stacked by the moving `.active` class) and/or the box moves 6-37 px (mount-switcher, `margin-left` animation) or 200-590 px (video-frame carousel, `translate` of an ancestor).
- Why ADR-042 does not absorb it: (A) allows 3 px / IoU 0.8 and requires equal hit tests; the hit flips and the box moves exceed it. (B) needs an INFINITE CSS animation with only scale/rotate/opacity; here the animations are finite (`iterations = 1`, `scale`, `margin-left`, `transform`, `width`), re-triggered by a timer, so `animated=false` for every moving entry (probe output: `animated: [false,false]` on all). Not smooth-scroll (see below), not header resize, not lazy-load, not hit-corner of the pulse.
- Burst shape measured (r20 `i3`, 5 tabs clicked, THU CUOI last, y=1200, 50 s window): burst of 145 changes lasting 25.5 s (one change per sample), then single ticks every 3.6 s, next burst at +36 s. Without the tabs (`h1`/`h3`, 130 s): 4.2 s burst every 14.5 s (24-26 changes per burst, max 33 changes in any 10 s window), settle always succeeds locally.
- A scroll whose 10 s settle window falls inside a long burst ends `state_kept_changing` (what r12 op 8 and r19 op 9 reported). Both failing runs had clicked NHAN VAT and THU CUOI beforehand (r12 seq 5-6, r19 seq 6-7).

## What is NOT established (honest limits)
1. The scroll position/delta of r19 seq 9 is not in any saved dump (`agent-loop-r19-trace.json` has no `delta_y`; the proposal rows are in the live DB, not read). After the TOP click the page is at y=0; a +600 wheel from there lands on y=600, which is calm in every replica (below). The widget needs the viewport near y 1000-2000, so seq 9 must have scrolled further than +600 for this to be the cause. Needed to close it: the `delta_y` of the r19 operation `cb145ad0` (read-only DB query or the worker log of that session).
2. I could NOT reproduce a full 10 s `settle_timeout` locally: the worst `settleState` time in 14+14 rounds was 4.2 s (normal CPU) and 6.6 s (CDP CPU throttle 4x), 8.4-8.6 s in the three r19-timeline replicas (`g1`, `g2`, `i1-i3`, always settled because the wheel landed before the burst began). The failure therefore needs the wheel to land inside a burst; the phase relation of the burst to page age / tab click time is not established (it differed between runs). The closest local approach is 8.5 s of the 10 s budget.
3. Linux container Chromium and the site's live content could differ from this Windows run (same engine family, same worker code).

## Runs (all under tsx, read-only: wheel, the fixed TOP button, optional tab clicks; no form, no login, no download)
Probe sources: `.pytest-artifacts/r20-top-probe.mts`, `.pytest-artifacts/r20-phase-sweep.mts`. Outputs: `.pytest-artifacts/r20-top-probe-{a1,b1,c1,d1,e1200,e2000,f600,f1200,g1,g2,h1,h2,h3,h4,i1,i2,i3}.json`, `r20-phase-sweep-{s1,s2}.json`.
TOP control: `button.absolute.inset-0.cursor-pointer` inside the fixed `div.fixed-menu`, box 1184,470,27x32 (at y=600). `html`/`body` `scroll-behavior: auto`.

| Run | Shape | Result |
| --- | --- | --- |
| a1 | open, scroll 600, TOP, +600 (no reduce, no tabs), 15 s | TOP scroll finished in 9 ms (instant, not smooth); settle after TOP ok (1.0 s); 1 change in 15 s (the scroll itself), longest quiet 14.8 s |
| b1 | same + 5 tab clicks (Su Kien, Cam Nang, Tin Tuc, Nhan Vat, Thu Cuoi) | each click settled about 1 s; TOP ok; +600: 1 change, quiet 14.6 s |
| c1 | b1 on the r19 wall-clock timeline (clicks at +22..64 s, TOP +67.5 s, scroll +77.8 s), 40 s window, reduced motion | 1 change in 40 s |
| d1 | a1 with reducedMotion + context route as the worker | 1 change, quiet 14.9 s |
| e1200 / e2000 | TOP then wheel +1200 / +2000 (no tabs) | 36 / 14 changes in 15 s; movers: `a.video-frame` (translate carousel, 212 px), `div.character-switcher` (hit flips), lazy count change; longest quiet 3.1 s; settle ok |
| f600 / f1200 | 5 tabs, r19 timeline, NO TOP, second wheel +600 / +1200 | 43 / 13 changes; f600 mover `div.mount-switcher.ml-2` hit x41, margin-left/scale animations (finite); settle ok |
| g1, g2 | f600 with a real `settleState(10 s, 800)` right after the wheel, then 15 s measure | op settle 8.58 s / 8.52 s (settled); burst of hit-only changes every 120-130 ms from +9.9 s, still running at the 15 s end |
| h1, h3 (no tabs, no TOP, y=1200, 60 s / 130 s) | | 142 / 321 changes; burst 4.2 s every 14.5 s; longest quiet 3.1 s; op settle 4.3 / 4.5 s |
| h2 / h4 | h1 with CDP CPU throttle 4x / 10x, 40 s | 49 / 14 changes; op settle 5.4 / 5.3 s |
| i1, i2, i3 | r19 replica (5 tabs, TOP, wheel +1200), op settle then 15 / 15 / 50 s measure | op settle 8.43 / 8.59 / 8.55 s; mount-switcher hit-only churn every sample; i3: one burst 9.97 s to 35.46 s (145 changes), ticks 2.7, 6.4, 39.0, 42.7 s, next burst from 46.3 s |
| s1 / s2 | 14 rounds each of wheel y 600 to 1200, `settleState`, back, vary the wait (CPU 1x / 4x) | 0 failures; ms 981-4245 (s1), 1060-6555 (s2) |

Per-change attribution (from the worker's `privateInteractions`, index-aligned with a name list built by the same traversal; entries without a stable alignment are marked `idxN`): kinds counted `hit` 83 and `bounds` 156 (h1), `hit` 170 / `bounds` 26 (i3). Controls: `div.mount-switcher.lg:-ml-35.ml-2` (hit only, maxdc 0), `div.mount-switcher.lg:-ml-5.ml-14` (bounds maxdc up to 37.5 px, IoU 0.42-0.87), `div.character-switcher...` (hit only), `a.video-frame.group.z-10` + `svg.play-icon` + `path` (translate carousel, maxdc 589 px, IoU 0), page-numbering `button.h-[7px]...` (width animation, 8 px, IoU 0.375). A pop-in on the fixed menu (`a.absolute.inset-0`, opacity animation, `iterations=1`) and the one scroll event account for the single change seen in the TOP+600 replicas (count/content only at the scroll itself).

## Reproduction spec (mechanism only, not the site)
New `workers/playwright/src/vision-settle-switcher.spec.ts` (inline fixture, no new fixture file): four overlapping cards, a 100 ms timer moves `.active` (z-index) and restarts a finite `scale`/`margin-left` animation. Not runtime-dependent, so no tsx twin is needed.
1. mechanism (passes): at least 10 state changes in 30 samples, geometry/hit-only (no content added/removed), and every running animation is finite (so ADR-042 B cannot apply).
2. negative control (passes): the same page settles once the churn stops (1.5 s).
3. `test.fail()` (passes as expected failure): a 5 s settle inside a long burst does not settle.

```
$ npx playwright test src/vision-settle-switcher.spec.ts --reporter=line   (workers/playwright)
{"event":"vision.state.settle_timeout","message":"Page did not stay stable for 800 ms within 5000 ms: state_kept_changing. Observed 51 state changes (51 visible DOM/layout, 0 form values, 0 URL).","longest_observed_stable_ms":96,"samples":53,"state_changes":51,...}
  3 passed (12.6s)
$ npx tsc --noEmit   (workers/playwright)  -> exit 0, no output
```
The `settle_timeout` log line above is the expected output of test 3 (51 changes, 0 URL, same shape as r19: 52 changes, 0 URL).

## Proposals (not implemented)
| # | Idea | Gate | Pros | Cons / risks | Files / tests |
| --- | --- | --- | --- | --- | --- |
| A | Longer settle budget for viewport-changing ops and recovery (now fixed `10_000`, `vision-operations.ts` about line 887): e.g. `min(session.deadline, 40 s)`, same 800 ms quiet and tolerance, early return at the first quiet window | unchanged | Smallest change; with burst 25.5 s per 36 s period (and 3.6 s tick gaps) a 40 s window contains a quiet gap; no page mutation | Does not fix the next failure: a burst starting after the settle makes `prepare` (`equivalentState(held, fresh)`) reject `state_mismatch` (r19 seq 12/13); costs session time (120 s total); a longer burst than assumed still fails | `vision-operations.ts` (+ constant), spec: switcher fixture with a 12 s burst settles within 20 s; update `vision-settle-switcher.spec.ts` test 3 |
| B | Scoped equivalence ("ambient motion", ADR-043 candidate): `settleState` and `prepare` ignore changes confined to hit tests/box drift of controls that do not overlap the proposal's target, provided content digests, count, URL, forms, scroll are identical; dispatch keeps exact-node + centre hit + target preflight | relaxes (needs your ADR decision; this is NOT a no-gate-change option) | Directly removes both failure modes (settle and prepare) for ambient widgets; safe click is still guaranteed by exact-node + centre hit probe | Weakens the "whole page unchanged" guarantee: an unrelated moving card could cover the target without being flagged except by the centre hit probe; needs reviewer sign-off and an overlap test | `vision-checkpoints.ts` (`equivalentState` target-scoped variant), `vision-operations.ts` callers (`prepare`, `observeDom`), ADR-043, specs for covering/non-covering movers |
| C | Worker calms the page while it settles (inject `* { animation: none !important; transition: none !important }` during its own scroll settle, remove after) | unchanged | Cheap to try | Mutates the page and screenshots; my fixture shows timer re-stacking (`z-index`) still flips the hit probes with animations off, so it may not help at all; needs a live-site probe first | `vision-operations.ts`; probe `r20-top-probe.mts` variant before any decision |
| not recommended | Prompt/policy to avoid the TOP control | n/a | | TOP is incidental; the targets of interest (mct-30/31 tabs, panels below them) are what start/show the widget | - |

My recommendation: close open item 1 (read the r19 seq 9 `delta_y`), then probe C offline (10 minutes, no gate change) and decide between A (alone, then re-measure) and B (ADR). I did not run a live session and did not touch the gate.

## Risks
- The cause is established as a mechanism class (finite timer-driven animations on the switcher widget during a long burst), not as the exact r19 event, because open items 1 and 2 remain.
- Hit-only churn is invisible in the worker's public logs (controls are not named); the spec and probes name them only locally.
- The real site can change at any time; r13's probe (`r13-settle-probe.json`) saw 79 changes in 15 s at y=600 before ADR-042, consistent with the pulse, which ADR-042 fixed (all TOP+600 replicas here are calm).

## Files
- created: `workers/playwright/src/vision-settle-switcher.spec.ts`
- artifacts: `.pytest-artifacts/r20-*` (probes and JSON above)
- appended: `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md` (r20 section), `plan/09112026103202-vision-accuracy-loop/README.md` (r20 handoff)
- graph: `docs/graphs/playwright-vision-worker.md` (+1 file via hgraph)
- no source change, no commit, no live session, no bridge/model call, no docker action. Processes: every probe closed its browser; no process left.

GRAPH_UPDATE
- graph đã cập nhật: playwright-vision-worker
- file mới đã đưa vào graph: workers/playwright/src/vision-settle-switcher.spec.ts
- hgraph check: `hgraph check — 6 graph, 469 file source` / `✔ Không có vấn đề.`
