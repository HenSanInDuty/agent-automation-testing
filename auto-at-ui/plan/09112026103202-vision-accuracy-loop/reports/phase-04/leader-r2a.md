STATUS: PASS

# Leader r2a - direction A (harness role binding)

Verified: oracle JSON and metrics.py git diff empty (exit 0). pyproject/uv.lock unchanged (no new dependency).
Binding (evidence.py _role_binding_error, binding_error): path rule untouched for any locator with a path; role rule reachable only when path is None (before: unconditional failure), so old scores cannot change. Checks present: verified status, binding_reference, grounding for same operation, complete facts, viewport == oracle viewport, before_page_id == root tab, role by tag (a/button only), normalized non-empty equal name, IoU>=0.8, exactly one candidate == reviewer target_id, click inside oracle box, one credit per target (run.py evaluate). Missing grounding -> no_role_grounding, no credit. Outcome review, frame checksums, metrics.score still required. Invalid exported facts become None and only remove credit.
Page-identity risk (header link clicked on /cam-nang binds like homepage): real but bounded; credit still needs reviewer outcome verdict + frames, the old path rule has the same property, dev documented it. Not blocking; fix = export url fingerprint (already in ESCALATE).
Tests: ruff "All checks passed!"; pytest 3 files "57 passed in 2.51s". Negative cases cover each condition; old-run test re-scores retained runs.
Over-engineering: no delete/yagni/stdlib/native findings. shrink note: run.py ground CLI + check_grounding backfill old runs; justified, keep.
Graph: hgraph check -> "6 graph, 455 file source, no issues" exit 0. hgraph check --changed lists 53 files with auto-at-ui/ prefix as uncovered, including codex_service.py which hgraph which maps to codex-bridge, vision-agent-loop; git toplevel is agent-at/, hgraph root auto-at-ui/. Confirmed tooling prefix mismatch, not a graph gap. New files are in vision-accuracy-harness.
Scope: only direction A files reviewed.
Note: oracle sha256 on this checkout differs from dev's (CRLF autocrlf); git diff empty so content unchanged.

BLOCKING: none
OPTIONAL: export url fingerprint/scroll in /trace (user decision per ESCALATE).
