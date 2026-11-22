STATUS: PASS

# Leader r2 - delta review (AgentRef, AGENT_REF_PATTERN, AGENT_REQUEST_MAX_BYTES)

BLOCKING: none.

- codex_bridge.py:375-376: AgentRef = str, min_length=1, max_length=24, no pattern. AGENT_REF_PATTERN exported at :374. Matches the approved decision.
- :265-266: valid_job rejects when is_agent and len(canonical_bytes(self)) > 131_072. canonical_bytes (:52-55) is json with ensure_ascii=False encoded UTF-8, so it counts real bytes. Correct measure. Only the agent branch, v4 untouched.
- v4 bytes/hash unchanged: model_serializer drops agent_context when None; test against tests/fixtures/v4_identity.json is in the 86 passing tests.
- Strict agent schema: ref has no pattern, anyOf {string, minLength 1, maxLength 24}; enforceable_schema test updated and green.
- min_length=1: reasonable, matches pm-r1 question 2 (empty ref still rejected at contract). Keep.
- Tests: 24/25 boundary, off-format refs parse, byte ceiling checked both sides (non-ASCII hosts exceed, ASCII hosts pass), v4 exempt.

Ponytail: nothing superfluous; minimal change.

OPTIONAL: none.

EVIDENCE:
- uv run pytest tests/test_agent_loop_contracts.py -q -> 86 passed
- plus tests/test_codex_bridge_contracts.py -> 174 passed; 6 errors in test_claude_bridge are PermissionError writing %TEMP%\pytest-of-hen (environment, not the diff)
- tests/test_vision_agent_engine_selection.py fails at collection: Settings reads local env with Codex bridge enabled (environment, not the diff)
- uv run ruff check packages/contracts tests/test_agent_loop_contracts.py -> All checks passed
- Excluded per instructions: hgraph --changed, 10 red tests in test_qa_phase01_edges.py.
