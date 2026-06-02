# Simplify End-User Pipeline Run UX

**Date**: 2026-06-02 05:42  
**Severity**: Medium  
**Component**: user-app / shared PipelineRunPage  
**Status**: Resolved

## What Happened

Shipped a UX simplification for end-users (non-admin) running pipelines. Goal: remove all technical choices (LLM profile selection, pause/cancel controls, pipeline search) so the flow is: upload document → run → see results inline, no decisions.

Two commits landed on `develop`:
1. `1842778` — feat: add 3 optional props to shared PipelineRunPage, user-app enables all 3, removed search from pipeline list
2. `0be5f53` — fix: corrected TypeScript ignoreDeprecations from "6.0" (invalid for TS 5.9.3) to "5.0"

## The Brutal Truth

The real issue was hidden technical debt, not UX complexity. We had a pre-existing tsconfig bug (`ignoreDeprecations: "6.0"` is not valid in TS 5.9.3) that broke the entire `next build` type-check phase, which we only surfaced while testing the new UX code. The user had to approve a breaking fix to an unrelated config file just to verify the new feature compiled. That's sloppy — we should have caught and fixed the tsconfig days ago, not during feature work. The simplification itself was straightforward.

## Technical Details

**User-app run page** (`apps/user-app/src/app/pipelines/[id]/run/page.tsx`):
```tsx
<PipelineRunPage
  templateId={templateId}
  hideLlmProfile       // User always gets System Default profile
  hideRunControls      // No pause/cancel buttons visible
  showResultsInline    // Full ResultsViewer renders on terminal state
/>
```

**Shared component** added opt-in props (all default `false`, backward-compatible):
- `hideLlmProfile?: boolean` — hides LLMProfileSelector when true
- `hideRunControls?: boolean` — hides PipelineControls (pause/cancel) when true  
- `showResultsInline?: boolean` — renders full <ResultsViewer> inline post-run instead of link-only

**Pipeline list** (`apps/user-app/src/app/pipelines/page.tsx`): removed Search input + query/filtered state + unused Search/React imports. Saves 27 lines, no filtering logic lost (never used in user flow).

**tsconfig.base.json** breaking fix:
- Changed `"ignoreDeprecations": "6.0"` → `"5.0"`
- "6.0" is a TypeScript 6.x suppression value, invalid for installed TS 5.9.3
- Made `next build` type-check fail repo-wide with cryptic "invalid ignoreDeprecations" error
- Only discovered while testing new code in user-app

## What We Tried

1. **Props-on-shared vs. fork component** — User decided (via explicit Q&A) to extend shared component with opt-in props (default false) rather than fork. Reasoning: KISS, zero admin-app impact, shared codebase stays dry.

2. **Document upload stays** — User confirmed keeping the document upload input; only removing the "choices" (profile, controls, search).

3. **tsconfig fix depth** — User explicitly approved the value change from "6.0" to "5.0" after we surfaced the pre-existing bug and explained the impact on build verification.

## Root Cause Analysis

**For UX simplification:** no real root cause — this was a straightforward feature request. Design was sound: opt-in props with safe defaults.

**For tsconfig bug:** institutional neglect. Likely set to "6.0" as a forward-looking config (in anticipation of upgrading to TS 6.x in the future) but never tested against the actual installed version (5.9.3). This should have been caught in a `next build` verification step the moment someone ran a fresh `npm install` on the repo.

## Lessons Learned

1. **Configuration drift is silent until you touch adjacent code.** Pre-existing config bugs stay dormant until you run a full build on unrelated work. Add a `npm run type-check` + `next build --debug` step to the PR gate for non-chore commits.

2. **Version-forward config is a liability.** Setting `ignoreDeprecations: "6.0"` for TS 5.9.3 is aspirational, not safe. Lock config values to what you currently use; bump in explicit, tested commits, not preemptively.

3. **Opt-in props are the right choice for shared components.** Extending with defaults=false means legacy code is unaffected; new consumers can opt in to simplified behavior. Much safer than forking or refactoring shared code.

4. **Document upload was the right keeper.** It's actual user input, not a technical configuration choice. Stripping LLM profile + pause/cancel was the right call; document input stays.

## Next Steps

1. Manual smoke test on live backend with the new simplified UX (pending).
2. Verify admin-app still renders full controls (code review DONE, but functional test skipped).
3. Land on develop once manual smoke test passes.
4. Consider adding `npm run build` (full type-check + next build) to pre-push or CI gate to catch config drift earlier.

---

**Status**: DONE  
**Summary**: End-user run UX simplified by hiding technical choices (LLM profile, pause/cancel, search); shared component extended with opt-in props (backward-compatible). Pre-existing tsconfig bug ("6.0" invalid for TS 5.9.3) was surfaced and fixed as a blocker to feature verification.

**Unresolved Questions:**
- Manual smoke test with live backend still pending — is the inline ResultsViewer stable under real load?
- Should we add a dedicated pre-push build verification hook, or rely on CI?

---

## Follow-up — Hide Per-Node Results

**Date**: 2026-06-02 05:55  
**Change**: Commit `534ac57` "feat(user-app): hide per-node results from end-user views"

User clarified: end-users don't need to see per-node execution results. Decision: hide the "Nodes" tab everywhere in user-app (both inline run results + run-detail page).

**Scope:**
- `packages/shared/src/components/pipeline/ResultsViewer.tsx` — added `hideNodeResults?: boolean` prop (default false). When true: remove "Nodes" from visibleTabs; default activeTab falls back to "testcases" (not "nodes").
- `packages/shared/src/components/pipeline/PipelineRunPage.tsx` — threaded `hideNodeResults` prop to ResultsViewer.
- `packages/shared/src/components/pipeline/PipelineRunDetailPage.tsx` — threaded `hideNodeResults` prop to ResultsViewer.
- `apps/user-app/src/app/pipelines/[id]/run/page.tsx` and `apps/user-app/src/app/pipelines/[id]/runs/[runId]/page.tsx` — enable `hideNodeResults={true}` on both user surfaces.

**Kept:** aggregate "X completed / Y failed" summary counts (user explicitly chose not to hide); admin-app unchanged (opt-in default-false pattern).

**Verification:** `next build` user-app PASS (6 routes); `tsc` admin-app clean. Self-reviewed (small, consistent with existing pattern). Manual smoke test with live backend still pending.

**Status**: DONE_WITH_CONCERNS  
**Summary**: Per-node results hidden from both user-app surfaces via opt-in prop; aggregate summary counts retained per user choice. Manual backend smoke test + code review not yet completed (3 commits not pushed).  
**Concerns**: Not pushed; functional test on live backend required before full completion.
