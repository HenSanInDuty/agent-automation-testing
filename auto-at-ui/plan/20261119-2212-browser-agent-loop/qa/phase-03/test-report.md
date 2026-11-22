# Test report - Phase 3 (QA r1)

QA VERDICT: PASS

Moi truong: Windows 11 (uv, pytest) cho phan portable; Linux that cho test process/service: `docker run --rm --network none --entrypoint /app/.venv/bin/python` tren image local `auto-at-ui-temporal-worker:latest`, repo mount `:ro`, pytest lay tu `.venv/Lib/site-packages` host (pure python, `sys.path.append`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 -p pytest_asyncio.plugin`), khong ghi vao repo. `CODEX_BRIDGE_ENABLED=false`. KHONG goi Codex/Claude that.

## Output that
Windows, test moi (QA + dev):
```
59 passed, 13 skipped in 2.22s   (13 skip = test process Linux-only)
```
Windows, 7 file checklist + 3 file moi:
```
171 passed, 28 skipped, 13 warnings in 166.34s (0:02:46)
```
Linux docker (3 file moi + process, claude_bridge, spool, service, end_to_end, contracts, agent_loop_contracts, model_batch, candidate_service):
```
367 passed, 2 skipped, 2 warnings in 61.27s (0:01:01)
```
(Lan dau co 1 fail la loi cua test QA r03 - dung model claude voi service codex; da sua test, khong phai bug san pham.)
`uv run ruff check .` -> `All checks passed!`
Test do baseline phase 0 (`test_codex_bridge_benchmark::test_offline_manifest_provenance_and_explicit_live_boundary`): khong thuoc nhom da chay, khong tinh.
`test_codex_exploration_integration.py` chi chay tren Windows (xanh).

## Coverage theo yeu cau
- Thu tu 5 khoi + tien to chung khi chi snapshot doi (P01-P03), delimiter chong injection (P04, P05).
- Dispatch builder/parser theo prompt_version qua fake Codex + fake Claude (dev, Linux docker) + QA-R03.
- v4 `codex-dom-v11` byte-identical theo `tests/fixtures/v4_identity.json` (QA-V401, doc fixture truc tiep).
- Output agent sai schema bi bac (QA-O01 x9, dev bad_kind/candidates cho ca hai provider).
- Spool: round-trip 24 000 ky tu Viet (S04, dev); bien REQUEST_MAX_BYTES 131 072 vao / 131 073 bi bac (S01); dom/schema van 65 536 (S03).
- Prompt ~100 KB qua fake process (dev), bien 131 072/131 073 cua process (R02).
- Hoi quy 7 file checklist: xanh.

## Hanh vi can leader biet (khong FAIL)
1. Contract tran request o 126 288 byte thuc te (moi truong toi da) < 131 072, nen "131 072 vao" chi kiem duoc o duong doc `load()`; duong `publish` kiem voi request hop le lon nhat. Khong the tao request hop le 131 072 byte.
2. Parser agent chap nhan ref sai dinh dang (`abc`) va action thieu field null; chi schema provider (strict) ep field day du, ref kiem snapshot o phase 4. Test QA-O01b ghim hanh vi nay - phase 4 phai kiem ref.
3. Request lon nhat (126 KB) cho prompt > 131 072 -> process fail-closed `bridge_output_limit` (dev da nhan dien; phase 4 nen gioi han allowed_hosts).
4. Van de Codex dung file instructions v4 (dev, muc "Van de" 1) chua the kiem neu khong goi model that - chuyen phase 6.

## Chua test duoc
- Chay job agent that qua bridge host (Claude/Codex that): chuyen phase 6 (can user cho phep goi model that; giong checklist phase).
- Gioi han stdin cua `claude` that voi prompt ~100 KB (stdin JSON ensure_ascii ~2x): chi kiem duoc voi fake; phase 6.
- Chat luong prompt (model co theo INSTRUCTIONS hay khong): can model that.
- Stress test: khong can - khong co vong lap tren tap lon, query, lock, job hang loat moi.

## Cong graph
`hgraph add codex-bridge tests/test_agent_loop_bridge_qa.py` + `hgraph sync codex-bridge --apply`. `hgraph check`: `4 graph, 449 file source / Khong co van de`. `hgraph check --changed` van exit 1 do loi tien to `auto-at-ui/` (git toplevel la thu muc cha; cung tinh trang phase 1-2, user chap nhan); khong con file `tests/test_agent_loop_*` hay file phase 3 nao bi bao thieu graph.

Tai lieu: `plan/20261119-2212-browser-agent-loop/qa/phase-03/test-cases.md`, file nay, automation `tests/test_agent_loop_bridge_qa.py`.
