# Round 17: qualification attempt 1 failed

Iteration: `56e50d4d-2be0-433b-98ad-2eab68d7773f`.
Session: `c2cb227d-6c27-4323-971d-da27bbe67fcc`.
Candidate: `qualification-candidate-20261117.json`; source, config, oracle, images,
model `gpt-6-luna`, prompt `codex-dom-v11` and limits unchanged from round 16.

The frozen oracle requires carousel indicator 4 and its matching slide for
`mct-54`. Operation 26 has a verified locator for button 4; its before-frame shows
slide 4 (Thu Cuoi Kinh Dien), but its after-frame shows slide 5 (Vo Lam Chan Menh).
This cannot receive credit. Autoplay between click and capture is a hypothesis;
the evidence does not establish that the physical click hit a wrong target.

There were 47 explore click attempts: 45 completed positive bindings, one
unmatched completed click and one rejected unmatched click. Removing operation
26 from possible positive outcomes leaves an **available-evidence accuracy ceiling
of 44/47 = 93.6170%**, below the strict >95% gate. This is not a measured true
accuracy. Five positive outcomes were reviewed independently; the saved score
5/47 is a conservative lower bound. Remaining eligible outcomes were left
unreviewed once qualification was impossible with the retained evidence. All
raw evidence remains available; no attempt was dropped from the denominator.

- Detection: precision 47/48 (97.9167%), recall 47/47 (100%); complete inventory.
- Runtime: unavailable / unsafe_replay; final restore Back rejected with
  history_checkpoint_unavailable. No pending/unknown operations in the export.
- 145 operations; 286 retained frames verified, four unavailable frames belonging
  to two rejected operations. Operation window: 742.937198 seconds.
- 12 bridge model jobs completed; reported usage 66,038 input and 4,551 output
  tokens. Monetary cost is not reported. These are bridge-job counters, not the
  coding assistant conversation's token usage.
- No runtime code, prompt, policy, oracle or execution verdict changed this round.

Evidence lives in `runs/56e50d4d-2be0-433b-98ad-2eab68d7773f/`: manifest,
provenance, evidence, timing, usage, inventory, state and download evidence,
checkpoint diagnostics, five content-addressed reviews, assessments, score and
`carousel-outcome-mismatch.json` with operation/frame identities and checksums.
`manual-findings.json` records only the five positively reviewed operations.

Offline gates: `qualification-offline-complete-20261117.json` retains 1151 passed,
two explained isolated RustFS skips and separate host tests, including the initial
connection failure and successful repeats. The prior 102-case worker regression
is retained in `retained-target-stability-validation-20261117.json`; full Ruff
passed on resume. No unchanged full suite was rerun.

Qualification streak: **0/3**. Return to phase 04 to reproduce click/after-frame
timing on a synthetic autoplay carousel before changing code. Preserve original
node/form/checkpoint guards, side-effect rules and strict outcome scoring. Stop
at this round boundary; resume from the canonical plan README in a fresh session.
