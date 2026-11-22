# Mongchiton stale-result diagnosis

The live page's character carousel reproduces checkpoint drift in the same worker
image and browser configuration used by session
`95c8129e-f321-4f4f-9c28-378c34806b83`.

## Application failure path

1. The third Codex exchange completed at 15:20:01.459750 UTC.
2. The worker received a checkpoint read at 15:20:01.532 UTC.
3. The controller stopped with `bridge_stale_result` at 15:20:01.735175 UTC.

`CodexCandidateService._propose()` checks state immediately after the exchange
(`apps/control-plane/application/codex_candidates.py`, line 198). The controller's
callback combines checkpoint equality, `matches_current`, and the observation
fingerprint. The worker computes `matches_current` by comparing the checkpoint
with a fresh `inspectState()` result. The interaction hash includes rounded
geometry and hit-test results for visible interactive elements throughout the
viewport, and private form state is checked separately in memory.

The refresh loop requires no consumed call/reservation. A stale post-response
result therefore stops the session rather than triggering a new observation.
These checks explain the reported failure; the provider exchange itself succeeded.

## Reproduction without model calls or clicks

An independent disposable browser used the deployed worker image
`sha256:e0ba86e8b16127050996f179563094fac0d633dce3385cc5c2ddaba0f5d8bab7`.
The actual deployed `vision-checkpoints.ts` SHA-256 is
`780f399eefd1c2f05ed4650a0c2e51413284637b861f58fff0ef2ca0c6b4aad0`.
Configuration: 1280x720, `reducedMotion=reduce`, service workers blocked,
downloads disabled. No app volume, credential, provider or application service
was connected to the diagnostic container.

| Requested vertical scroll | Consecutive state mismatches, 12 one-second samples |
|---|---:|
| 0 px | 0/12 |
| 560 px | 0/12 |
| 1136 px | 8/12 |
| 1136 px, separate focused confirmation | 8/12 |
| 1136 px, only character autoplay stopped locally | 0/12 |

1136 px corresponds to the observed first 560 px scroll plus the controller's
576 px next-viewport step. This reconstructs that viewport; it is not a replay
of every preceding click or the historical browser's exact state.

At the unstable viewport, URL, scroll and form-state comparisons stayed equal.
The changed fields were interaction geometry and hit tests. Identified nodes:

- `div.character-switcher`, whose `active` selection rotates automatically;
- `a.video-frame.group.z-10` and its `svg.play-icon` / descendant path as the slide moves.

For example, a switcher changed from bounds `[137,273,242,374]` to
`[139,275,239,372]`, with a changed hit-test result, while its identity hash and
label hash remained equal. Passive semantic changes alone at 560 px did not
invalidate the interaction checkpoint.

The website's public [JavaScript bundle](https://mongchiton.vn/_next/static/chunks/3144b5357y7dm.js)
configures `.character-mount-swiper` with a 3000 ms autoplay delay, 600 ms transition,
and an `onSlideChange` callback that updates the selected character. Its
[stylesheet](https://mongchiton.vn/_next/static/chunks/0j5d4dcl6r293.css)
scales `.character-switcher.active` to 105 percent. Reduced-motion preference does
not stop this JavaScript-driven autoplay in the observed page.

The diagnostic intervention called only that carousel's `autoplay.stop()` in the
disposable browser. With the same fingerprint code and no weakened comparisons,
all 12 subsequent samples matched. Nothing was paused or changed in the deployed
application or on the website server.

## Additional mismatch between observation and invalidation scope

In the deployed version, DOM candidate extraction accepts semantic controls such
as buttons, links, inputs and explicit roles. The tested character switchers are
plain DIVs with no role. The checkpoint extractor additionally includes elements
with `cursor:pointer`, including these DIVs and inherited-pointer descendants.
Consequently, elements that do not appear as model-addressable candidates can
still invalidate the entire model observation.

## Conclusion and limit

The experiment isolates an actual source of drift on Mongchiton: automatic
character changes alter the broad viewport interaction hash during model latency.
The 9.99-second third exchange spans multiple 3-second autoplay periods.
This strongly explains the live session's post-response stale stop. The original
checkpoint endpoint did not retain field-level differences, so the exact historical
DOM delta cannot be proven retrospectively from that session alone.

The fix should preserve exact target identity, context and actionability checks,
while allowing a fresh observation to assess whether a change affects the proposed
target. Simply ignoring `bridge_stale_result`, extending the timeout, or treating
model availability as the issue would not resolve this mechanism. Pausing the
carousel was a diagnostic intervention, not a proposed production workaround.

Evidence:

- [Reduced-motion samples](mongchiton-state-drift-20261105.json)
- [Focused node identification](mongchiton-state-drift-focus-20261105.json)
- [Carousel-stopped counterfactual](mongchiton-state-drift-paused-carousel-20261105.json)
- [Public script/CSS excerpts and script hash](mongchiton-carousel-source-20261105.json)
- [Probe source](diagnose_live_state.mjs)

The normal-motion control in `mongchiton-state-drift-normal-motion-20261105.json`
does not match the deployed motion setting and is not used for the conclusion above.
