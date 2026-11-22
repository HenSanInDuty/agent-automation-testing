STATUS: PASS

# Phase 0 - review leader r1

VERDICT: PASS
CONVENTION: AGENTS.md (docs/code-standards.md chi la chi muc; khong co docs/api-conventions.md) - khop; phase khong sua code san pham.
GRAPH: `hgraph check --changed` -> "4 graph, 438 file source / File vua doi: 1 / Khong co van de", exit 0. File moi v4_identity.py da vao codex-bridge (phien chinh). Khong co file moi khac can graph.

BLOCKING: khong co.

## 1. Tieu chi xong
- Commit: user chon WIP -> a2e43d6, f85091a (phien chinh). OK.
- Log baseline: doi chieu log tho. G1 458p/1f/19s (pytest-B-g1-basetemp.log), G2 84p/1s, G3a 251p, G3b1-rest 236p, G3b2 182p, page_batch 3x7p. 458+84+251+236+60+182+21 = 1292 passed, 1 failed, 20 skipped: khop. Worker: locators 10, dom 38, history 8, operations 99 = 155 pass. Dashboard test 44 pass/0 fail; typecheck, lint, ruff exit 0 theo log. Alembic: toi chay lai `uv run alembic heads` = a4c6e8f01234 (head).
- Luu y: 60 test page_batch dau chi suy ra tu dau cham cua 2 log timeout (khong co ten test, khong co summary); suy luan 48+12 hop ly, 317 = 236+81 khop. Chap nhan, ghi la bang chung yeu.
- DB: ghi ro (.env co DATABASE_URL, 5432 LISTEN, 0 skip do DB, chua xac nhan ket noi that). Tong skip 20 la tren G1+G2; G3 khong skip. Moc "69 skip round 21" khong doi chieu duoc (DB-gated test khong chay o day) -> ghi vao no.
- r3 mo ta sai nhe assertion cua test do (noi live_canary); log that la lech hash manifest (`3b1c1ca0... != dfbd0cbf...`). r2 dung. Khong chan.

## 2. v4_identity
Chay lai `uv run python -I .../v4_identity.py` exit 0; sha256 + bytes cua codex_output_schema, prompt+schema, prompt_sha256, bridge_schema_sha256 khop JSON 100%.
- Hash 1 = sha256(json.dumps(TypeAdapter(CodexOutput).json_schema(), sort_keys, separators compact)) dung dinh nghia.
- Hash 2 = sha256(with_response_schema(build_prompt(req, canonical_bytes(obs)), output_schema(3))); UUID = UUID(int=n), NOW hang so, khong random/now/duong dan may (ROOT chi dung de sys.path). Deterministic. Phase 1/3 so sanh duoc, mien cung request mau. Luu y: request mau tu dung (khong phai fixture co san), da ghi trong JSON; phase sau phai dung lai chinh sample_request().

## 3. TS contract
sha256 26e0d39b...b211 cua reports/phase-00/vision-contract.generated.ts.txt = workers/playwright/src/vision-contract.generated.ts hien tai. Khop.

## 4. Kha nang chay lai
Cach chay ghi ro: CODEX_BRIDGE_ENABLED=false qua env, --basetemp, -p no:cacheprovider, corepack pnpm, worker chay tung spec (--workers=1). Test do co ten: test_codex_bridge_benchmark.py::test_offline_manifest_provenance_and_explicit_live_boundary. flow-result.json da khoi phuc (git status sach).

## 5. Ponytail (v4_identity.py, v4_identity.json)
Khong co delete/yagni/stdlib/native, khong dependency moi.
- v4_identity.py:L88-L108 shrink: chuoi "source"/"computation" dai lap voi _comment cua JSON. Co the cat bot; chi ghi chu.

## 6. Hgraph: exit 0 (xem tren).

## No / rui ro cho phase sau
- `.env` bat CODEX_BRIDGE_ENABLED=true nhung thieu CODEX_BRIDGE_EXECUTABLE (config.py:166-171 raise) -> 19 module loi collection neu khong override; moi lan chay phai override.
- test_vision_page_batch.py ghi de benchmark/vision/visual-buttons/flow-result.json trong repo (chay do dang giua chung de lai diff 99->96); chay het 81 test thi tro ve noi dung da commit. No co tu truoc.
- WinError 5/PermissionError o pytest-of-hen trong Temp mac dinh (83 error); phai dung --basetemp.
- Test do co tu truoc: test_codex_bridge_benchmark offline manifest hash lech; phase sau khong duoc quy cho thay doi cua minh.
- Tong pytest ~ 25 phut, can chia nhom <= 9 phut; vision-operations.spec 6.6 phut; page_batch ~15-19 s/test.
- Chua co bang chung ket noi PostgreSQL that cho test migration/fence (phase 1/4 can kiem lai).
