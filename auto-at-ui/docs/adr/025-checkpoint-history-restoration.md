# ADR 025: Select the original browser history entry during restoration

Status: offline validated; live qualification in progress, 2026-11-09.

The third accuracy-loop run stopped after Events navigation. A separate public,
read-only browser probe demonstrated that one click creates two history entries.
One Back therefore remains on Events; additional observation cannot restore Home.
Evidence: `benchmark/vision/accuracy/history-probe-20261109.json`.

The Chromium worker privately saves the current CDP history entry ID, complete
URL hash, and original Page with each checkpoint when it has observed a GET
navigation. Unknown methods and form-submit entries supply no capability. History
IDs and complete URLs never enter the model, API result, database, or audit export.
The private v4 result adds an optional boolean capability, default false. A restore
Back can reference the existing checkpoint UUID through an optional private field.
Responses without the capability retain single-Back behavior in the controller.
Deploy controller and worker together: strict private schemas do not support a
mixed-version rollout. The target-neutral execution v1 contract is unchanged.

Before prepare and dispatch the worker requires the same Page, a still-present
earlier entry with the original URL hash, and the same current history entry as
at prepare. It selects that entry once using CDP Page.navigateToHistoryEntry.
It neither retries Back nor reconstructs a navigation URL. Missing, replaced, or
mutated entries reject; an uncertain dispatched action is never replayed.
The existing step deadline bounds selection and observation.

Selecting an entry does not certify restoration. Existing URL, interaction, form,
scroll and checkpoint verification remains authoritative, including bounded
read-only observation recovery. Prefix clicks and form effects are never replayed.

Regression fixtures cover duplicate entries, delayed hydration, permanent drift,
hidden-form drift, replaced entries, Page mismatch, removed entries, and history
mutation between prepare and dispatch. Raw CDP history stays in worker RAM.

A self-link navigation can replace an entry ID even when the original checkpoint
still matches exactly. When the normal checkpoint verification succeeds on the
same Page, refresh its private GET history handle using a second full state/form
comparison. The persisted checkpoint, saved state and ancestry remain unchanged.
No handle is refreshed on form/state drift or missing GET proof. This is required
by the sibling-navigation regression: otherwise a safe Home self-link makes the
old history handle unavailable on the next branch return.
