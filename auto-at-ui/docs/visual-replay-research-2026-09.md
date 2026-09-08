# Visual Replay: research and product assessment

Date: 2026-09-07

## Conclusion

Implementation update (2026-09-07): the product now calls this surface **Exploration
evidence**. New sessions expose a redacted trajectory graph and render one selected
transition at a time; historical edge-less sessions retain a clearly labelled legacy
gallery. Operators should verify that the activity connection displays its polling
fallback when SSE reconnects, and that deleting a frame makes its private bytes
unavailable without inventing a branch outcome. Deploy additively: migration, worker
writes, trajectory API, dashboard, then tenant display; readers may be rolled back
independently of the additive edge data.

The current **Visual replay** is a private screenshot gallery of BFS exploration
states, not a replay a human can follow.  It is safe and auditable, but it does
not answer the debugging questions that a replay should answer: *which branch
was taken, what action caused the next state, did it succeed, and why did the
agent stop?*

Do not present it as an execution replay until the product has a first-class
trajectory model.  A more accurate interim name is **Exploration evidence**.

## Evidence from the current implementation

`VisionEventProcessor` persists one screenshot before asking the model for a
batch of candidate actions.  Every non-stop candidate is then queued as a new
independent BFS branch.  `observeVisualTreeState` recreates a fresh browser
context, navigates from the target URL, and replays its ancestor action path.
This protects sibling isolation, but a retained frame is consequently a *node*
in a search tree, not the next moment of one linear browser session.

The dashboard lists only `State N / checksum / retained`.  Selecting a state
loads one image and paints the entire batch of candidate coordinates with the
same `model proposal` label.  It shows neither parent state, child state,
selected branch, action outcome, URL/title, viewport, nor an action label that
identifies an individual marker.  The separate action list is global and does
not make the tree readable.  Screenshot selection also requires loading a
separate blob one frame at a time.

The result is especially confusing when one model call returns several
candidates: the overlapping markers look like simultaneous actions although
they are alternative branches.  Treating model proposals as though they were
executed steps is the central UX error.

Relevant code:

- `apps/control-plane/application/vision_events.py`
- `workers/playwright/src/vision.ts`
- `apps/dashboard/app/vision-dashboard.tsx`
- `apps/dashboard/app/components/vision-replay-model.ts`

## What mature workflows make visible

| Product | Useful workflow pattern | Application here |
| --- | --- | --- |
| Browserbase / Stagehand | Keep a session identity and a shareable session/dashboard link; retain operation history, structured logs, metrics, and a debugger URL for inspection. | Keep the private-frame access policy, but expose a session summary plus a per-step event stream.  For a live run, show current state and connection state; for a completed run, show a deterministic trace. |
| Browser Use | A trajectory is a sequence of page states, model actions, action results/errors, visited URLs, screenshots, final result, and independent judgement.  Its history helpers return these together; its cloud also supplies a live session URL. | Persist a redacted action-result record for every branch edge, and distinguish model proposal, attempted action, observed result, failure, and terminal reason.  Show judgement/verification separately from agent self-report. |
| Midscene Test | A local interactive HTML report connects detailed steps, screenshots, AI decision trace, element-location result, and full screenshot history.  Its workflow model has named cases and explicit lifecycle steps. | Report a narrative: intent → state → candidate → branch → observation → stop/draft handoff.  Allow a compact timeline, expandable step details, and a failure-first view. |

Sources:

- [Stagehand reference: history, session URL, debugger URL, metrics and structured logging](https://github.com/browserbase/stagehand/blob/main/packages/docs/v3/references/stagehand.mdx)
- [Browserbase Node SDK: sessions expose recordings, logs and replays](https://github.com/browserbase/sdk-node/blob/main/src/resources/sessions/sessions.ts)
- [Browser Use: complete agent history fields and generated action GIF](https://github.com/browser-use/browser-use/blob/main/AGENTS.md)
- [Browser Use Cloud: step loop, live session view, and independent judge](https://github.com/browser-use/browser-use/blob/main/CLOUD.md)
- [Midscene Test: visual report contains steps, screenshots, AI decision process and element location](https://midscenejs.com/midscene-test/use)

## Recommended product shape

Maintain the existing privacy boundary: frames remain private evidence, typed
text and raw model reasoning remain absent, and the replay must never change a
deterministic verdict.  Build a **redacted trajectory graph** on top of it.

```text
Session / intent / limits / outcome
  └─ State 01 (image, URL fingerprint, hop 0)
       ├─ Candidate A: click @ 42%, 61%, confidence 0.91
       │    └─ State 02: observed / URL changed / screenshot
       └─ Candidate B: scroll +640, confidence 0.64
            └─ State 03: observed / no meaningful change
```

The primary view should be a linearized selected path with Previous/Next,
keyboard navigation, thumbnails, and a scrubber.  Each step should show
`before image → labelled action → after image`, branch status, capture time,
hop, confidence, and a safe result.  A secondary tree/minimap should reveal
siblings and let the reviewer switch branch.  Do not draw every proposal at
once; show one selected action with a numbered marker and reveal alternatives
on demand.

## Delivery order

1. **Correct the language and navigation.** Rename the current section to
   Exploration evidence; show state hop and parent/child counts; make a selected
   state visually distinct; add next/previous controls and thumbnail strip.
2. **Persist edge outcomes.** Add a redacted, immutable action-edge record
   (`parent_state_id`, `child_state_id`, proposal ID, action summary,
   confidence, observed status, URL fingerprint, duration, safe error/stop
   code).  Capture enough metadata to explain a transition without storing
   typed values, raw prompt/model output, cookies, or storage URLs.
3. **Render trajectory first.** Select the highest-confidence completed path by
   default; render one annotated transition at a time; offer the branch tree
   only as a secondary diagnostic.
4. **Make failure diagnosable.** Surface limits, policy blocks, navigation
   failure, screenshot failure, candidate rejection, and draft-handoff result
   at the affected step.  Retain the existing admin-only encrypted diagnostic
   details.
5. **Verify with real fixtures.** Add visual/UI tests for: alternative sibling
   candidates; an action without coordinates; branch navigation; missing image;
   terminal limit; and failed candidate call.  Seed a representative replay
   fixture so the dashboard can be judged without calling the vision provider.

## Non-goals

- Do not simulate a continuous video: each BFS node intentionally runs in a
  new isolated context, so interpolating frames would be misleading.
- Do not expose the worker's raw screenshot URL, browser CDP endpoint, typed
  text, cookies, model chain-of-thought, or provider response.
- Do not make replay evidence a test verdict or an automatic code-change path.
