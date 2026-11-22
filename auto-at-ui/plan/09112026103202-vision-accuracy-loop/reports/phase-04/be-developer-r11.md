STATUS: DONE

CONTEXT_CHECK
- conventions: AGENTS.md, docs/code-standards.md (hgraph brief), prompts/README.md, be-developer-r10.md
- graphs: vision-agent-loop, codex-bridge, vision-exploration (hgraph brief)
- blast radius: 10 file depend on agent_loop.py (publisher, 7 tests, temporal_worker, live_persistence test) / 15 deps

# r11 - agent_loop prompt v1 -> v2 (offline)

## Evidence (step 2)
- `render_snapshot` (application/vision_agent_loop.py:100-117) sends the model a header `viewport: WxH; more below: yes|no` and a final line `N control ngoài snapshot` when `skipped_count>0`. No observation change needed.
- r10 result (`.pytest-artifacts/agent-loop-r10-result.json`): homepage `scrollable=true, skipped_count=9`; /su-kien, /tin-tuc, /cam-nang `scrollable=true, skipped_count=2`. So the model received both signals and ignored them. The v1 prompt only said "a note says how many controls fall outside it" (vague, no rule to return to the starting page, no ban on `complete`). Prompt-only fix justified; loop code not touched. Actions scroll/back/navigate already exist (navigate = return to session start page).
- Not verifiable offline: the exact snapshot text the model saw in r10 (not stored in trace); inferred from code + result pages.

## Diff
- `apps/control-plane/agents/prompts/agent_loop.py`: PROMPT_VERSION `agent-loop-v1` -> `agent-loop-v2`; failure bullet now names the two signals ("more below: yes", "N control ngoài snapshot"); new section "Covering the starting page first" (finish the starting page before external/shared header links; return via navigate/back, then scroll while "more below: yes"/controls outside snapshot); Finishing: no `complete` while those signals persist on the starting page, until scrolling reveals nothing new. Generic: no site names/URLs/counts.
- `apps/control-plane/agents/prompts/README.md`: row bumped to v2 + changelog sentence.
- `tests/test_agent_loop_prompt.py`: version/README test -> v2; new `test_v2_instructs_covering_the_starting_page_before_complete` (includes no mongchiton/http check); the "refused other version" case keeps v1 as the now-refused version.
- `tests/test_agent_loop_bridge.py`, `tests/test_vision_agent_loop.py`: v1 -> v2 (PROMPT_BUILDERS set, request fixtures, call assertion). `tests/test_agent_loop_bridge_qa.py:90`: v1 stays as the refused version (no diff needed beyond that).
- `docs/graphs/vision-agent-loop.md:74`: v2.
- Manifest: `benchmark/vision/codex/manifest.json` covers only codex-dom-v11 (`codex_exploration.py`); agent_loop.py is not in its sources -> not regenerated. `test_offline_manifest_provenance_and_explicit_live_boundary` stays failing exactly as before (pre-existing hash drift, e.g. `contracts/codex_bridge.py`); no state change.
- Left stale (out of scope, cosmetic): `docs/graphs/codex-bridge.md:92` and `agents/vision/codex_service.py:63` docstring still say `agent-loop-v1`; `test_agent_loop_contracts.py` uses v1 only as a regex-valid fixture string.

## Tests (real output)
- `uv run ruff check .` -> All checks passed!
- pytest (prompt, bridge, bridge_qa, contracts, vision_agent_loop, loop_qa, evidence_flags, qa_r8, codex_bridge_benchmark): `1 failed, 362 passed, 67 skipped` (110 s). The 1 failure is the known `test_codex_bridge_benchmark.py::test_offline_manifest_provenance_and_explicit_live_boundary`. 67 skips are pre-existing (conditional skips in the suites). run_offline.py not run: manifest/fixtures concern codex-dom-v11 only.
- `hgraph check` -> "Không có vấn đề." (no file added/removed, no import change; hgraph add/sync not needed).

## Before live
Rebuild/restart control-plane, temporal-worker (import prompt via vision_agent_loop) and claude-bridge (codex_bridge_cli PROMPT_BUILDERS builds the prompt text). playwright-worker not needed. `agent_loop_round.py check` should then show identical hashes.

## Risks
- More model calls (scroll steps, returning to start page): each ~40 s; the 20-step cap may bind before full coverage. Policy caps unchanged.
- The model can still ignore the instruction (it ignored the v1 hint); the rule is prompt-only with no loop guard. If r12 still stops early, next option is a small guard in vision_agent_loop.py rejecting `complete` while the start page has skipped controls (needs new decision).
- Scroll previously caused homepage `state_mismatch` in r6; expect it to recur (gate unchanged).
- Longer instructions: prefix cache invalidated once.

GRAPH_UPDATE
- graph đã cập nhật: vision-agent-loop (text version only); no file added/removed
- file mới đã đưa vào graph: không có
- hgraph check: "✔ Không có vấn đề." (full `hgraph check`, not `--changed`)
