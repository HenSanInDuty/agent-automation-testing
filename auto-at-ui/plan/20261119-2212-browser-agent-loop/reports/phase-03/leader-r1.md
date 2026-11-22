STATUS: PASS

# Phase 3 leader review r1

CONVENTION: AGENTS.md (Prompt management, layering) - khop: prompt o agents/prompts/, README co dong agent-loop-v1, caller import prompt. docs/code-standards.md chi la muc luc; docs/api-conventions.md khong co.
GRAPH: dev bao `hgraph check` exit 0; `--changed` exit 1 chi do lech tien to auto-at-ui/ (git root la thu muc cha). File moi da vao codex-bridge: co. CONTEXT_CHECK/GRAPH_UPDATE day du.

BLOCKING: khong co.

Kiem trong tam
- v4 byte-identical: codex_exploration.py khong doi (git diff rong); output_schema() khong doi, chi them agent_output_schema() (codex_service.py:62); codex_batch.py mac dinh prompt_version=PROMPT_VERSION, schema=output_schema(max_candidates), stage cu. test_agent_loop_bridge.py:176-177 so sha256 prompt + schema voi tests/fixtures/v4_identity.json (fixture la file moi chua track, can commit cung phase).
- Dispatch: codex_bridge_cli.py PROMPT_BUILDERS theo prompt_version, version la -> ValueError. Parser o process.py:228 / claude_process.py:321 chon theo request.agent_context is not None (contract bao dam tuong duong prompt_version agent-loop-vN); generation_process van truyen parser rieng. application/codex_bridge.py:61 bo with_response_schema cho agent (builder nhung schema o khoi 2); v4 van qua with_response_schema.
- spool.py:38 REQUEST_MAX_BYTES = AGENT_REQUEST_MAX_BYTES import tu contract, dung o doc (:249) va ghi (:298); dom/schema 65 536, screenshot 5 000 000 giu. Diff spool dung (heredoc la vi pham quy trinh, khong phai loi code).
- 5 khoi: agent_loop.py:110-121 dung thu tu instructions, schema, task/limits, memory/history, page (cuoi). Gia tri doi theo lan goi chi o khoi 5. Delimiter UNTRUSTED_PAGE_DATA, token trong snapshot bi trung hoa (:107); task/memory/history redact.
- Test: du cac muc "Unit test phai viet" (31 test ham trong 2 file; 10 skip la test process Linux-only, dev chay 24/24 trong docker Linux).

(a) Codex dung instructions v4 co dinh (process.py:62): chap nhan. Khong chan phase 3 vi sua triet de can file ngoai pham vi (catalogue/doctor/Dockerfile); cau "These instructions replace..." (agent_loop.py:32) la giam nhe hop ly. Rui ro that: chat luong engine Codex -> do o QA that phase 6; neu lech thi mo phase nho tao AGENT_INSTRUCTIONS_PATH. Claude khong bi anh huong.
(b) Prompt > 131 072 byte bi bridge_output_limit o ca cuc doan (100 host x 255 ky tu): fail-closed, chap nhan. Phase 4 nen gioi han so/do dai allowed_hosts. Ca thuc te ~106-110 KB qua.

Ponytail over-engineering (diff phase)
- codex_batch.py:L50 shrink: tham so `stage` du (contract buoc stage == "image" iff co anh). Plan liet ke nen giu; bo o phase sau.
- agent_loop.py:L91 shrink: `_redact` trung logic task_context.redact (dev da neu no). Gop mot nguon trong agents/shared sau.
- Khong co delete/yagni/stdlib/native, khong dependency moi.

OPTIONAL
- Stdin Claude dung json.dumps ensure_ascii -> ~2x byte voi tieng Viet; kiem gioi han that o phase 6.
- "done kem ly do" chi la enum CodexStop.reason (khong co text); ngoai phase.
- QA goi model that chuyen sang phase 6 (can user cho phep), chap nhan theo plan.

EVIDENCE
- uv run pytest tests/test_agent_loop_prompt.py tests/test_agent_loop_bridge.py tests/test_agent_loop_contracts.py -q --basetemp <scratchpad> (CODEX_BRIDGE_ENABLED=false): 115 passed, 10 skipped. (Lan dau khong --basetemp: 11 error PermissionError tmp_path, do moi truong.)
- uv run ruff check .: All checks passed!
- Hoi quy 7 file checklist + Linux docker: theo bao cao dev (112 passed/15 skipped Windows; 291 passed Linux), toi khong chay lai. 1 do test_codex_bridge_benchmark co tu baseline phase 0.
