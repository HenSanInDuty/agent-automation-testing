# Approved revision: local exploration capacity

Status: approved by the user ("duyệt, làm đi bạn"), 2026-11-09; implementation in progress.

Live iteration 05 completed 35 clicks and retained 42 states. Its active branch
reached hop 10 after selecting the Events news tab. That changed the local UI
without a new browser history entry. The live child cannot be expanded at the
configured depth; restoring an older sibling is unsafe and history selection
correctly rejected. Increasing states alone will not remove this depth boundary.

The baseline has already been reduced from 7 to 4 scrolls. Setup and independent
observations still consume at least 6 states, so 45 successful unique clicks
require at least 51 states. Do not discard those observations or change counting.

Proposed local project policy for `8f2d5531-f00d-4ce9-981e-f4b626657818`:

| Field | Current | Proposed |
|---|---:|---:|
| vision_max_states | 50 | 100 |
| vision_max_hops | 10 | 20 |

Allowed origins remain `https://mongchiton.vn`. Keep the existing provider/model,
20 model calls, 5 requests/minute, 120-second step deadline, screenshot limit,
cost cap, consent, approval boundary, oracle labels and >95% acceptance criteria.
Apply only after the current run is terminal; new sessions snapshot the policy.
Old runs remain immutable and ineligible to be combined across configurations.

Implementation after approval must expand the supported hop range consistently:
private worker open schema, visual state hop validation, project policy API
validation and dashboard numeric input. Regenerate worker schema, test 10/20/21
boundaries and cap enforcement, and deploy matching services. Defaults remain 5
hops and 50 states. The execution v1 request/result contract does not change.
Inspect all downstream handoff/trajectory limits before editing; do not silently
truncate states. No database column migration is currently indicated (integers
without a <=10 constraint), but verify the full migration head before rollout.

Read-only downstream audit: DOM snapshot capacity already follows max_states;
checkpoint ancestry and handoff steps permit 100 entries. Handoff branch export
still has a separate 50-branch limit, which must remain explicit if reached rather
than silently truncating. The main hop range declarations are
`packages/contracts/src/auto_at/contracts/vision_worker.py`,
`packages/contracts/src/auto_at/contracts/vision.py`,
`apps/control-plane/api/v1/routes/generation.py`, and the numeric input in
`apps/dashboard/app/generation-dashboard.tsx`. The worker enforces the requested
limit dynamically. No fixed <=10 database constraint was found in the original
tree-limit migration. Existing runtime sessions must not have limits rewritten.

The alternative is to keep existing caps and report the unmet coverage limit.
Do not split runs and combine their coverage as if one run passed. Any additional
safe optimization must retain state/hop accounting and independent evidence.
