STATUS: PASS

VERDICT: PASS
CONVENTION: AGENTS.md, docs/code-standards.md, prompts/README.md - khop (README row bumped, graph text updated).
GRAPH: hgraph check -> "6 graph, 460 file source - Khong co van de." Khong co file moi.

BLOCKING: khong co.

Kiem 1 (prompt): tong quat (khong ten site/URL/so nut/oracle; test no-mongchiton/http). Khop tin hieu that: render_snapshot (vision_agent_loop.py:100-117) phat "more below: yes|no" va dong "N control ngoai snapshot" dung chuoi prompt trich. Khong mau thuan an toan: off-origin van chi close_popup/back (Boundaries giu nguyen); caps 20 calls va policy khong doi. Dieu kien dung: "until more below is no or scrolling reveals nothing new" + 20-step cap + no_safe_action; khong vo han. Rui ro: skipped_count co the khong het do control bi bo (khong phai do fold) -> "scroll first" khong lam no ve 0, nhung dieu kien "scrolling reveals nothing new" cho phep complete; xau nhat la dung o cap 20 (da neu o r11 Risks).
Kiem 2: PROMPT_VERSION v2 la nguon duy nhat; vision_agent_loop.py:297,515 import hang so (provenance/bridge job theo); build_prompt tu choi version khac; contract pattern ^agent-loop-v[1-9][0-9]*$ chap nhan v2. codex-bridge.md:92 va codex_service.py:63 docstring con v1: chi cosmetic, ngoai pham vi, khong chan (goi y doi nhan khi tien hanh).
Kiem 4 over-engineering: khong co delete/yagni/stdlib/native/dependency moi. shrink: agent_loop.py (Finishing, doan "After scrolling no longer reveals new controls, that is covered.") lap y voi "Repeat until..." o muc Covering. Giu mot cho. Ghi chu, khong chan.

OPTIONAL:
- agent_loop.py "Covering the starting page first": "return with navigate (or back)" khi dang o trang off-origin; navigate khong duoc chap nhan o trang off-origin (chi close_popup/back). Nen noi "back" truoc cho off-origin. Khong mau thuan voi Boundaries ("Return to an allowed page") nen khong chan.
- Cap nhat docs/graphs/codex-bridge.md:92 va codex_service.py:63 sang v2 khi tien hanh.

EVIDENCE:
- uv run ruff check . -> All checks passed!
- uv run pytest tests/test_agent_loop_prompt.py tests/test_agent_loop_bridge.py tests/test_vision_agent_loop.py -q --basetemp=.pytest-artifacts/leader-r5tmp -> 51 passed, 48 skipped, 1 warning in 81.31s (skips co san, dieu kien; khong dieu tra them).
- hgraph check -> Khong co van de.
- Test benchmark manifest co san failing (hash drift) khong thuoc pham vi r11; khong chay lai.
