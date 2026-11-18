# ADR 031: Explain checkpoint mismatches without changing restoration

Status: implemented; focused regressions passed, 2026-11-17.

Accuracy iteration 12 stopped at `unsafe_replay` after 35 clicks and 107 completed
operations. Back from the homepage's news-list link returned to the same visible
viewport, but the original checkpoint still failed comparison after two refreshes.
All 214 frames passed integrity checks. Screenshots alone cannot establish private
form or interaction equivalence. A separate saved-history-entry probe matched its
checkpoint and did not reproduce the full-session failure.

Emit `vision.checkpoint.mismatch` only when the existing full comparison is false.
Include session/checkpoint/state IDs and boolean differences for URL, interaction,
visual semantics, form presence, form values and scroll. Retain no values, labels,
URLs, form hashes or exceptions. HTTP logs identify checkpoint IDs as checkpoints,
not operation IDs. Logging failures cannot affect the comparison or history handle.

No checkpoint is replaced, no action is retried, and no restoration guard changes.
Passive visual differences alone remain nonfatal under the existing comparison.
This adds diagnostic evidence for the next loop; it does not establish the cause
of iteration 12 or claim an accuracy improvement. Execution v1, worker transport,
prompt v11, provider/model, permissions and budgets remain unchanged.

Focused red test: four missing-diagnostic failures and one passing passive-visual
case. Tests cover each mismatch category, immutable checkpoint metadata, no raw
data in logs, correct HTTP ID correlation and unavailable logging.

Final checkpoint/history/logging matrix: 51 passed; worker typecheck, Ruff and
changed-file whitespace checks passed. Portable validation is retained in
`benchmark/vision/accuracy/checkpoint-diagnostic-validation-20261117.json`.
