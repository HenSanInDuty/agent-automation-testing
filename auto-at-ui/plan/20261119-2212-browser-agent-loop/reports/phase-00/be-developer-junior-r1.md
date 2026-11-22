STATUS: BLOCKED (hết trần 45 phút; chưa xong: pytest nhóm G3b, worker vitest có summary, dashboard test/typecheck/lint, v4 hash + script, tests/fixtures/v4_identity.json)

# Phase 0 — Ổn định nền — báo cáo be-developer-junior r1

HEAD: f85091a (branch mantaray). Cây làm việc sạch trước phiên; chỉ thêm thư mục `reports/phase-00/` (chưa track). Không commit, không sửa code sản phẩm, không tạo `tests/fixtures/v4_identity.json`.

## CONTEXT_CHECK
- conventions: `AGENTS.md` (đã đọc, mục "Required checks before helping" và "Code organization rules"); `docs/code-standards.md` (chỉ là chỉ mục, trỏ về AGENTS.md). `docs/api-conventions.md` KHÔNG tồn tại trong repo. Phase này không viết API nên không ảnh hưởng, nhưng brief hgraph nói phải đọc file đó trước: ghi nhận là thiếu.
- graphs: `playwright-vision-worker` (brief). `tests/fixtures` và `reports/phase-00` chưa thuộc graph nào.
- blast radius: hgraph brief cho `workers/playwright/src/vision-contract.generated.ts` → 17 file phụ thuộc (depth 2). Phase này không sửa file sản phẩm nên không tác động.

## Baseline (bảng)

| # | Lệnh | Kết quả | Log |
|---|---|---|---|
| 1 | `uv run ruff check .` | All checks passed! (exit 0) | `ruff-check.log` |
| 2 | `uv run pytest -p no:cacheprovider -q -rfEs` (cấu hình nguyên trạng, không override) | Collection lỗi: 19 module ERROR, 0 test chạy, exit 2 | `pytest-full.log` |
| 3 | Như #2 + `CODEX_BRIDGE_ENABLED=false` (override tiến trình, không ghi file), nhóm G1 `tests/test_[a-m]*.py`, basetemp mặc định | 1 failed, 375 passed, 19 skipped, 83 errors (toàn bộ ERROR là PermissionError, xem dưới) | `pytest-B-g1.log` |
| 4 | Như #3, G1 với `--basetemp` trong scratchpad | 1 failed, 458 passed, 19 skipped, 0 error | `pytest-B-g1-basetemp.log` |
| 5 | Như #3, G2 `tests/test_[n-z]*.py` trừ vision, basetemp scratchpad | 84 passed, 1 skipped, 0 fail | `pytest-B-g2-basetemp.log` |
| 6 | Như #3, G3a `tests/test_vision*.py` từ `test_vision_[a-l]`… (16 file, `< test_vision_m`) | 251 passed, 0 fail, 0 skip | `pytest-B-g3a-basetemp.log` |
| 7 | Như #3, G3 đầy đủ (45 file vision) | TIMEOUT 540s ở ~50% (exit 124), không có summary | `pytest-B-g3-basetemp.log` |
| 8 | G3b (`test_vision_[m-z]*` + `test_watch_vision_session.py`, 29 file) | CHƯA CHẠY (hết trần) | — |
| 9 | `npm.cmd run typecheck` (workers/playwright) | exit 0, `tsc --noEmit` không lỗi | `worker-typecheck.log` |
| 10 | `npm.cmd test -- src/vision-operations.spec.ts src/vision-dom.spec.ts src/vision-history.spec.ts src/vision-locators.spec.ts --workers=1` | TIMEOUT 400s (exit 124), chết giữa `vision-operations.spec.ts` (đang ở test 153, `state/hop and derived operation caps reject before another browser action`). Không có summary pass/fail/skip. Log rất dài (JSON log), không đủ số liệu | `worker-vision-tests.log` |
| 11 | `pnpm --filter @auto-at/dashboard test` | KHÔNG CHẠY: `pnpm.cmd` không có trên PATH của Git Bash (exit 1). `corepack.cmd pnpm --version` = 10.12.1 nên có thể chạy qua corepack; chưa làm vì hết giờ | `dashboard-test.log` |
| 12 | `pnpm --filter @auto-at/dashboard typecheck` / `lint` | CHƯA CHẠY | — |

### Tổng số liệu pytest đã có (chỉ các nhóm đã có summary, cấu hình #3 + basetemp)
- G1 + G2 + G3a: **793 passed, 1 failed, 20 skipped**. G3b chưa chạy nên tổng chưa đủ toàn suite.
- Test đỏ (1): `tests/test_codex_bridge_benchmark.py::test_offline_manifest_provenance_and_explicit_live_boundary` — `assert '3b1c1ca08a19...' == 'dfbd0cbfd5d0...'` (hash manifest `benchmark/vision/codex/manifest.json` khác giá trị kỳ vọng). Chỉ ghi lại, không sửa.
- Test skip có lý do ghi trong log: `test_codex_bridge_spool.py:240` "symlink adversary checked in Linux image" (1 skip ở G2/G1 khác: 19 ở G1 là skip DB-gated/có điều kiện, số chi tiết trong `pytest-B-g1-basetemp.log`).

## Lỗi môi trường và nguyên nhân gốc

1. **Collection pytest đỏ (cấu hình nguyên trạng, #2):** 19 module (`test_catalog_routes`, `test_codex_bridge_end_to_end`, `test_health`, `test_vision_*`, …) lỗi khi import `main` vì `apps/control-plane/main.py:19` gọi `get_settings()` → `config.py:179` → `validate_codex_bridge` (`config.py:166-171`): ném `enabled Codex bridge requires explicit local tenant, ID and paths`. Nguyên nhân: `.env` có `CODEX_BRIDGE_ENABLED`, `CODEX_BRIDGE_ID`, `CODEX_BRIDGE_ALLOWED_TENANT`, `CODEX_BRIDGE_HOST_SPOOL`, `CODEX_BRIDGE_AUTH_FILE` (đều có giá trị), nhưng **thiếu `CODEX_BRIDGE_EXECUTABLE`**, và validator bắt buộc `executable` khi bridge bật. Không sửa `.env` (file nhạy cảm, nằm ngoài quyền của phase). Đây là vấn đề cấu hình local cần user quyết: thêm `CODEX_BRIDGE_EXECUTABLE` vào `.env` hoặc tắt bridge local.
2. **PermissionError trên pytest basetemp mặc định (#3):** 83 ERROR với `PermissionError: [WinError 5] Access is denied: 'C:\Users\hen\AppData\Local\Temp\pytest-of-hen'`. Đây là thư mục tạm của pytest không ghi được trên máy này (không phải lỗi sản phẩm). Cách vượt chỉ để chạy baseline: `--basetemp` trỏ vào scratchpad (đã làm ở #4–#6). Cần user/ môi trường dọn `pytest-of-hen` nếu muốn chạy mặc định.
3. **Timeout:** nhóm vision chậm (G3 cả nhóm >540s; G3a 181s/16 file). Worker vitest >400s cho 4 spec với `--workers=1`.

## Alembic
`uv run alembic heads` → `a4c6e8f01234 (head)`. Khớp kỳ vọng.

## Môi trường DB
- `DATABASE_URL` trong tiến trình shell: **không set**. `.env` có khoá `DATABASE_URL` (giá trị không ghi vào báo cáo).
- PostgreSQL test: **chưa kiểm tra** (không probe, không start/stop docker — theo prompt). Nên hiểu là chưa xác nhận đang chạy.
- Số test DB-gated bị skip: G1 19 skip + G2 1 skip + G3a 0 skip = 20 skip đã thấy. Chưa có số tổng toàn suite (G3b thiếu). Mốc "69 skip ở round 21" trong phase chưa đối chiếu được.

## Hash đối chứng v4 (mục 6)
**CHƯA LÀM.** Không tạo `reports/phase-00/v4_identity.py`, không tạo `tests/fixtures/v4_identity.json`. Nguồn đã tìm thấy để làm tiếp:
- `CodexOutput` dùng ở `apps/control-plane/agents/vision/codex_service.py:8` và `:33` (`TypeAdapter(CodexOutput).json_schema()`), và `apps/control-plane/domain/codex_bridge.py:12`.
- `prompt_version == "codex-dom-v11"` ở `tests/test_codex_model_batch.py:85`, và `tests/test_vision_provider_submission.py` (cùng chuỗi). Request mẫu cố định chưa chọn.

## Bản sao contract TS
`workers/playwright/src/vision-contract.generated.ts` đã copy sang `reports/phase-00/vision-contract.generated.ts.txt` (đổi đuôi `.txt` để không lọt vào graph và gây `uncovered-changed`). sha256 = `26e0d39b1fc79a6f458181bc58a5fc26efc5a03732fbe7269528e3d0c6f9b211`. Phase 1 cần copy lại thành `.ts` khi so diff, hoặc so trực tiếp với file gốc.

## Checklist "Tiêu chí xong" (phase-00-baseline.md)
- [ ] User đã quyết commit/để nguyên cho các file đang sửa dở — CHƯA: WIP đã commit ở `a2e43d6` và `f85091a` theo prompt, cây sạch; chưa có xác nhận riêng nào khác. Coi như đã quyết theo prompt.
- [ ] Log baseline ruff/pytest/worker/dashboard có số pass/fail/skip — **MỘT PHẦN**: ruff đủ; pytest G1/G2/G3a đủ, G3b thiếu; worker typecheck đủ, vitest thiếu summary; dashboard thiếu.
- [x] Alembic head ghi lại (`a4c6e8f01234`).
- [ ] `tests/fixtures/v4_identity.json` có 2 hash, script chạy lại cho cùng kết quả — CHƯA. Bản sao TS đã có.
- [x] Môi trường DB ghi rõ (có/không, số skip) — ghi rõ "chưa kiểm PostgreSQL", DATABASE_URL không set trong shell, 20 skip đã thấy.

Phần đã làm xong ở checklist: alembic, bản sao TS, môi trường DB (một phần). Các mục còn lại cần một lượt tiếp.

## Việc còn lại (để phiên tiếp theo làm)
1. Chạy G3b: `CODEX_BRIDGE_ENABLED=false uv run pytest -p no:cacheprovider -q -rfEs --basetemp=<scratch>/pytest-tmp-g3b $(ls tests/test_vision*.py tests/test_watch_vision_session.py | awk '$0 >= "tests/test_vision_m"')` (chia nhỏ nếu >9 phút).
2. Worker vitest: chạy từng spec file (4 file), ghi summary riêng cho từng file, tránh một lệnh 400s+.
3. Dashboard: `corepack.cmd pnpm --filter @auto-at/dashboard test` / `typecheck` / `lint`.
4. Viết `reports/phase-00/v4_identity.py` (canonical JSON `sort_keys=True, separators=(",",":")`) và `tests/fixtures/v4_identity.json`; chọn request mẫu từ `tests/test_codex_model_batch.py` hoặc `tests/test_vision_provider_submission.py`, ghi nguồn; chạy 2 lần.
5. Quyết định user: thêm `CODEX_BRIDGE_EXECUTABLE` vào `.env` local (để 19 module collect được) hoặc tắt bridge local; dọn thư mục `pytest-of-hen` nếu muốn chạy basetemp mặc định.
6. Kiểm PostgreSQL (không start/stop) và số skip DB-gated toàn suite.

## Tiến trình và dọn dẹp
- Không mở stack docker, server hay worker nào. Vitest bị timeout nên đã kết thúc; không còn vitest trong danh sách tiến trình.
- Các tiến trình `vite --port 5173` (PID 2704), `vite --port 5199` (PID 12252), `next start -p 3210` (PID 19804/30280/23560, worktree `agent-at-admin-ui-rework`) và nhiều `claude.exe` **không phải của phiên này**. Không kill.

## hgraph
Lần đầu `hgraph check --changed` lỗi `uncovered-changed` vì file copy `.ts` trong `reports/phase-00/`. Đã đổi sang `.txt` và chạy lại:

```
hgraph check — 4 graph, 437 file source
✔ Không có vấn đề.
exit=0
```

## GRAPH_UPDATE
- graph đã cập nhật: không cần — không thêm file vào graph, không đổi import.
- file mới đã đưa vào graph: không có. `tests/fixtures/` và `reports/phase-00/` vẫn chưa thuộc graph nào (chưa tạo file `.ts`/`.py` trong các thư mục này nên không lỗi; sẽ cần `hgraph add` khi tạo `v4_identity.py`/`.json` nếu hgraph yêu cầu).
- hgraph check --changed: exit 0 (xem trên).

## Ghi chú
- Trong phiên: pytest chỉ chạy bằng `--basetemp` trong scratchpad và `CODEX_BRIDGE_ENABLED=false` qua tiến trình; không đổi file cấu hình.
- Log thô tất cả trong `reports/phase-00/` (`*.log`).
