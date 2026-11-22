STATUS: PASS

# leader r3 - review of be-developer r7 (A1/A2/A3 flags, ADR-040)

VERDICT: PASS
CONVENTION: docs/code-standards.md -> AGENTS.md; khop (uv, one-way layering, config.py only env reader, contracts shared, behaviour change has test). docs/api-conventions.md khong ton tai, khong route doi.
GRAPH: developer co CONTEXT_CHECK + GRAPH_UPDATE. Toi khong chay lai hgraph; developer bao `hgraph check` sach, `--changed` exit 1 do tien to git-root (loi cong cu da biet).

BLOCKING: khong co.

Kiem trong tam
1. Co tat: `worker_capabilities` (vision_agent_loop.py:80-87) chi them capability khi co bat tuong ung; moi co doc lap. Worker: clickContext/agentDomPath chi true khi agent_mode va capability co mat (vision-operations.ts:215-216); observeDom tat = cung duong code (agentPaths false). `VisualExecutedClick` serializer wrap bo key None (contracts/vision.py) nen payload/`/trace`/hash khong doi. A3 `_save_inventory` return som khi co tat. Test: test_flags_default_to_off, test_capabilities_are_unchanged..., test_an_operation_dump_keeps_the_old_click_shape..., test_inventory_is_not_written_while_its_flag_is_off; spec worker "without the capabilities...".
2. Oracle/metrics: `git diff` metrics.py va oracle JSON rong. (sha256 cua file != 9242b33d vi hash la content_hash canonical, khong phai byte; metrics.py/oracle khong doi nen khong re-derive.) Khong dung prompt, policy, gate state_mismatch. Contract chi them optional; A3 ghi cot JSON `page_inventory` co san qua `uow.page_inventory`; khong migration.
3. Harness: `--sources none` bo contexts va inventory (run.py evaluate/detect) -> diem nhu truoc; thieu/hong du lieu -> fallback (click_context tra None neu thieu/sai; export_inventory allowlist, bo junk; check_grounding tu choi context cho op la). Cong chat hon, khong long hon: cong URL `off_page_url`, mo ho giua cac offset khong duoc credit, `role_targets` mot op/target, derive_detection tinh controls khong khop vao precision va bo qua trang khac. Mac dinh `--sources all` chi doi diem khi session co du lieu moi. Luu y (khong chan): "inventory_complete" can mot trang khong scrollable; role+ten duy nhat nhan dien ma khong kiem box, dung cho phat hien, khong cho credit click.
4. Worker cu: control plane kiem `required_capabilities <= capabilities` khi open (infrastructure/vision_worker.py:123) -> worker cu bi tu choi (fail closed), khong chay am tham thieu bang chung.
5. Nhay cam: them chi scroll int + SHA-256 URL; ten inventory la nhan control da qua bo loc sensitive cua worker; test co `typed text` khong duoc xuat hien.
6. Phu thuoc: harness khong import control-plane (descriptor_key viet lai, co test bang content_hash that); merge_inventory trong domain, khong nguoc tang.
7. Over-engineering: khong thay dependency moi. Ghi chu:
  - benchmark/vision/accuracy/evidence.py: shrink: `_unit/_pixels/_count` ba helper kiem kieu gan giong nhau; co the gop - chi goi y.
  - vision-dom.ts: dom_path v2/v3 sao chep khoi thuat toan anonymous-button (dev da ghi); co the rut thanh ham chung - chi goi y.

Rui ro chua xac minh (dev da neu): hanh vi live cua worker container, do on dinh dom_path tren carousel dots, `/result` observed_controls khi bat A3 voi dashboard, test DB-gated bi skip (153+81).

EVIDENCE
- `uv run ruff check .` -> All checks passed!
- `uv run pytest tests/test_vision_agent_evidence_flags.py tests/test_vision_accuracy_agent_evidence.py tests/test_vision_accuracy_*.py` -> 123 passed in 7.30s
- `workers/playwright: npx tsc --noEmit` -> exit 0
- `git diff --stat -- metrics.py oracle-*.json` -> rong
