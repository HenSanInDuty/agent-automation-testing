# ADR 042: Geometry tolerance in page-state equivalence (settle and pre-dispatch)

Status: accepted by the user (plan option "A + limited B"); offline fix, round r14; not yet verified live

## Context

Round r12 live sessions hit `settle_timeout` on the home page. Round r13 traced it to an infinite CSS pulse
(`animate-play-now-pulse`, a scale animation) on the ancestor of a full-cover link: the scope-`all`
`interaction_fingerprint` hashes the rounded, clipped bounds, the five hit-test probes and the transparency of every
visible control, so the hash changed on almost every ~80 ms sample and the 800 ms quiet window was never reached.
`equivalentState` (`fingerprint` and form values equal) is the single comparison used by `settleState`, by the
prepare/dispatch gates in `vision-operations.ts`, by DOM observation and by history reuse, so the fix had to live in
that one function to keep settle and the pre-dispatch check consistent.

## Decision

`equivalentState` (in `vision-checkpoints.ts`) keeps the stored fingerprint comparison as a fast path and otherwise
compares the private interaction entries with a bounded tolerance.

A. Tolerant comparison. URL, form presence/values and scroll must be identical, the entry count must match, and per
entry (same position) the content digest (identity, labels, text, disabled, pointer-events, ...) must be identical and
the boxes must agree: centre offset at most `BOX_CENTER_TOLERANCE_PX` = 3 on each axis and IoU at least
`BOX_MIN_IOU` = 0.8 (about 10% size change). Entries without a box (anonymous `buttons` scope, landmarks,
`visual_buttons`) are compared exactly. Moved beyond tolerance, resized, appearing, disappearing or relabelled
controls remain changes.

B (limited). A control with itself or an ancestor under an infinite `CSSAnimation` whose keyframes touch only
`transform` (without translate/matrix/perspective), `scale`, `rotate`, `opacity` is measured by its untransformed
layout box (offset chain), not the transformed bounds. It is applied only when every transform on the ancestor chain
belongs to such an eligible animation, the control is in the main document (not in a frame or shadow tree), and the
chain has no fixed/sticky box. For those controls (and only when both states are "animated") transparency and the four
corner hit probes are exempt; the centre hit probe (the click point) must still agree.

Quiet window: `settleState` compares each sample with the state that opened the quiet window, not with the previous
sample, so a slow drift cannot slip under the tolerance in small steps.

Fingerprint comparison points (r14b, after review). The stored hash is an identity of the state the worker published,
not a fresh measurement, so a fresh inspection is never compared to the wire hash directly:
`observeDom` (`vision-dom.ts`) and prepare (`vision-operations.ts`) require `held.fingerprint === expected_state_fingerprint`
(expected must name the held `session.state`) AND `equivalentState(held, fresh)`; prepare then keeps `session.state` as
the baseline, so the published hash stays the operation's `state_fingerprint` and drift never accumulates across
rounds. The observation reports the held hash. Refresh (`vision-operations.ts`, `refresh_observation`) compares the
held hash exactly (no fresh inspection involved) and then settles against it. Remaining exact-hash gates, all held
vs held or wire vs held: the DOM snapshot hash check at prepare (`snapshot.state_fingerprint === expected`, both
published values) and the re-baseline after execute (`vision-operations.ts` post-click). No direct comparison of a
fresh inspection to a wire hash remains in `workers/playwright/src`.

Dispatch (r14b). Playwright's click waits for the target to be "stable", which an infinite animation never is, so a
pulsing control ended `action_outcome_unknown`. Only a target under an eligible infinite animation (same rule as the
`animated` flag: CSS scale/rotate/opacity only, nothing blocked, no foreign transform, main document) is clicked with
`force: true`, and only when `isPresentationOnlyAnimated` also finds that the click point resolves to the target or
its descendant at that moment (force skips Playwright's own hit-target check). The preceding exact-node and scope
verification is unchanged. Chosen over pausing the target's animation: force changes nothing on the page, whereas
pausing mutates animation state and needs restoring on every failure path. Every other target keeps full
Playwright actionability. DOM mode grounds the click by coordinates (existing behaviour), so a control that visibly
covers the pulsing one receives the click, never the covered link through it.

Unchanged: the stored `fingerprint`, `interaction_fingerprint`, `semantic_fingerprint`, wire contract and persisted
checkpoint metadata (values and hashing); hit test, scope check and exact-node verification at dispatch.

## Limits

- Not exempt: marquee/carousel translate (CSS `translate*`/`matrix`, script-driven wrapper transforms), animations of
  `left`/`top`/`width`/`height`, `Element.animate` and any other script-driven animation, finite animations and
  transitions. A page dominated by those still ends in `state_kept_changing`.
- Controls inside iframes or shadow trees are never layout-boxed (tolerance A only).
- The layout box carries a constant bias on odd layouts (body margin quirks); only equality across samples matters.
- Settle returns the last sample (within 3 px of its reference); with the dispatch tolerance a control can be up to
  ~6 px from where the model saw it.
- A control may now be 3 px / 10% away from where the model saw it when the gate passes.

## Safety risk

Small drift passes the gate that previously failed on a 1 px change. The click lands on a freshly measured box and
still needs the fresh hit test, scope check and exact-node verification, so a control moved more than the tolerance,
covered or replaced still cancels the click. Stricter than the plan text: transparency and corner hit probes are
exempt only under an eligible infinite animation; elsewhere they must match.

## Tests

`workers/playwright/src/vision-settle-animation.qa.spec.ts` (r14b): observe -> prepare -> execute on the strong
pulse (3 rounds, no `state_mismatch`, forced click lands), `isPresentationOnlyAnimated` true/false matrix (pulse,
spin, static, marquee, left, width, carousel, covered point), covered pulse not clicked through, marquee never clicked.
`workers/playwright/src/vision-settle-animation.spec.ts` (14 tests): static, pulse, strong pulse, rotate+fade settle;
pulse phases equal; drift beyond tolerance, relabel/aria/disabled, appear/disappear, opaque and control overlays,
carousel translate (next to an eligible pulse), marquee/left/width animations, `state_kept_changing` for a moving
animation and for slow drift. Regression: operations, agent-mode, agent-evidence, outcome-capture, dom, history,
readiness, preflight, sample-guard, visual-buttons, observability, locators and `vision.spec`.

## Runtime: no named closures inside browser callbacks (r17/r18)

The worker runs through `tsx` (`npm run start`), whose esbuild uses `keepNames`: every named function or arrow
(`const layoutBox = (el) => {...}`) becomes `__name(fn, "layoutBox")`. Playwright serialises a `page.evaluate` callback
with `toString()`, so the page sees `__name` and throws `ReferenceError: __name is not defined`. The Playwright test
transform does not inject `__name`, so the specs passed while every `open` failed in the container (r16 live session,
`unexpected_error`, 422 `visual_request_rejected`). The r14 `layoutBox` closure in `inspectState` was the only browser-side
case. Rules since r18:

- Browser callbacks (`page.evaluate`, `evaluateHandle`, `addInitScript`, `locator.evaluate`) define helpers as object
  methods (`const geometry = { layoutBox(el) {...} }`, like `traversal`) or inline them, never as `const f = () => {}`
  or nested `function f() {}`. The decision of ADR 042 (what counts as eligible, the layout box maths) is unchanged.
- Safety net: `open()` adds `globalThis.__name = globalThis.__name || (fn => fn)` as a context init script, so a future
  slip degrades to a no-op instead of killing every session.
- `vision-tsx-runtime.spec.ts` runs the real tsx transform (`fixtures/vision-tsx-runtime-probe.ts`): open, inspect an
  animated page in a context WITHOUT the safety net, `isPresentationOnlyAnimated`, close.
- `unexpected_error` rejections now log `error_name`, `error_origin` (Playwright API prefix, e.g. `page.evaluate`) and
  `error_digest` (first 8 hex of sha256 of the message); never the message or stack.

## Rollback

Restore `equivalentState` to `a.fingerprint === b.fingerprint && a.privateForms === b.privateForms` and compare
against `previous` in `settleState`; the extra private fields are unused then. Rebuild `playwright-worker`.
