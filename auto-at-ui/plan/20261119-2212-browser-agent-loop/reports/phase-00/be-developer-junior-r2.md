STATUS: BLOCKED (hgraph check --changed exit 1: v4_identity.py chưa thuộc graph nào, cần user chọn graph; G3b còn 21 test page_batch chưa chạy vì timeout; bench artifact bị test đổi)

# Phase 0 — Ổn định nền — báo cáo be-developer-junior r2 (tổng hợp r1 + r2)

HEAD: f85091a (branch mantaray). Không commit. Không sửa code sản phẩm, không sửa test, không sửa `.env`.
Thay đổi do phiên này tạo ra: `reports/phase-00/` (log, script, bản sao TS, báo cáo), `tests/fixtures/v4_identity.json` (mới).
Ngoài ra `benchmark/vision/visual-buttons/flow-result.json` bị test ghi đè (xem mục "Side effect"), chưa khôi phục.

## CONTEXT_CHECK
- conventions: `AGENTS.md` (đã đọc ở r1: mục "Required checks before helping" và "Code organization rules"). `docs/api-conventions.md` không tồn tại (prompt xác nhận phase này không cần). `docs/code-standards.md` chỉ là chỉ mục trỏ về AGENTS.md.
- graphs: `playwright-vision-worker` (r1, brief cho `vision-contract.generated.ts`). r2 đụng vùng `codex-bridge` (script hash đọc `CodexOutput` và prompt `codex-dom-v11`), nhưng không sửa file sản phẩm nên không cần graph đó để làm việc. r2 không chạy lại `hgraph brief`.
- blast radius: 17 file phụ thuộc `vision-contract.generated.ts` (từ hgraph brief r1). Phase này không sửa file sản phẩm nên không tác động.

## Impact inventory
### Database
Không đụng. Không có migration, không có ALTER/DROP, không có backfill. Lệnh DB duy nhất là đọc `alembic heads` và probe cổng TCP (không ghi).

### File & contract
- `reports/phase-00/v4_identity.py` (mới): script tính hash đối chứng v4. Không được import bởi code nào khác. Lý do: bước 6 của phase yêu cầu script chạy lại được.
- `tests/fixtures/v4_identity.json` (mới): dữ liệu hash đối chứng, phase 1/3 sẽ đọc.
- `reports/phase-00/*` (mới, log và báo cáo).
- Caller: không có hàm nào đổi chữ ký.
- Test phủ vùng này: không có test nào đọc `v4_identity.json` (phase 1/3 sẽ thêm).

## Baseline (HEAD f85091a)

Cách chạy pytest đã chốt: `CODEX_BRIDGE_ENABLED=false` qua tiến trình (không ghi `.env`), `--basetemp` trong scratchpad, `-p no:cacheprovider -q -rfEs`. Bảng dưới là cấu hình có override + basetemp, trừ dòng (a) và dòng (b).

| # | Lệnh | Kết quả | Log |
|---|---|---|---|
| 1 | `uv run ruff check .` | All checks passed, exit 0 (r1) | `ruff-check.log` |
| 2a | pytest nguyên trạng `.env` (không override) | Collection lỗi: 19 module ERROR, 0 test chạy, exit 2 (r1). Nguyên nhân: `.env` có `CODEX_BRIDGE_ENABLED=true` nhưng thiếu `CODEX_BRIDGE_EXECUTABLE`, `config.py:166-171` raise | `pytest-full.log` |
| 2b | pytest với override `CODEX_BRIDGE_ENABLED=false`, basetemp mặc định | G1: 1 failed, 375 passed, 19 skipped, 83 errors (PermissionError `pytest-of-hen`, môi trường) | `pytest-B-g1.log` |
| 3 | G1 `tests/test_[a-m]*.py`, basetemp scratchpad | 1 failed, 458 passed, 19 skipped, 0 error | `pytest-B-g1-basetemp.log` |
| 4 | G2 `tests/test_[n-z]*.py` trừ vision, basetemp scratchpad | 84 passed, 1 skipped, 0 failed | `pytest-B-g2-basetemp.log` |
| 5 | G3a `tests/test_vision_[a-l]*.py` (16 file) | 251 passed, 0 failed, 0 skipped | `pytest-B-g3a-basetemp.log` |
| 6 | G3 đầy đủ 45 file (r1) | Timeout 540 s ở ~50%, exit 124, không summary. Bỏ, chia nhóm | `pytest-B-g3-basetemp.log` |
| 7 | G3b1: 15 file `test_vision_[m-r]*` (gồm `test_vision_page_batch.py`), 317 test | Lần 1: 125/317 xong, không F/E, timeout 540 s, exit 124 (`pytest-B-g3b1-basetemp.log`). Đoạn tiếp theo test #126-190: 12 xong, không F/E, timeout 530 s, exit 124 (`pytest-B-g3b1-pieceA.log`). Xem chi tiết dưới | 3 log trên |
| 8 | G3b1 phần còn lại: 14 file không phải page_batch (`test_vision_page_inventory` … `test_vision_reload`) | 236 passed, 0 failed, 0 skipped, 179.6 s, exit 0 | `pytest-B-g3b1-rest.log` |
| 9 | G3b2: 14 file `test_vision_replay` … `test_vision_worker_observability` + `test_watch_vision_session.py` | 182 passed, 0 failed, 0 skipped, 211.9 s, exit 0 | `pytest-B-g3b2-basetemp.log` |
| 10 | `npm.cmd run typecheck` (workers/playwright) | exit 0, `tsc --noEmit` sạch (r1) | `worker-typecheck.log` |
| 11 | Worker `src/vision-locators.spec.ts --workers=1` | 10 passed, 0 failed, exit 0, 4.9 s | `worker-vision-locators-r2.log` |
| 12 | Worker `src/vision-dom.spec.ts --workers=1` | 38 passed, 0 failed, exit 0, 21.5 s | `worker-vision-dom-r2.log` |
| 13 | Worker `src/vision-history.spec.ts --workers=1` | 8 passed, 0 failed, exit 0, 3.0 s | `worker-vision-history-r2.log` |
| 14 | Worker `src/vision-operations.spec.ts --workers=1` | 99 passed, 0 failed, exit 0, 6.6 min | `worker-vision-operations-r2.log` |
| 15 | Worker gộp 4 spec chạy một lệnh (r1) | Timeout 400 s, exit 124, không summary. Thay bằng 4 lệnh riêng ở dòng 11-14 | `worker-vision-tests.log` |
| 16 | `corepack.cmd pnpm --filter @auto-at/dashboard test` | 44 pass, 0 fail, 0 skip, exit 0 | `dashboard-test-r2.log` |
| 17 | `corepack.cmd pnpm --filter @auto-at/dashboard typecheck` | `tsc --noEmit`, exit 0 | `dashboard-typecheck-r2.log` |
| 18 | `corepack.cmd pnpm --filter @auto-at/dashboard lint` | `eslint .`, exit 0, không cảnh báo | `dashboard-lint-r2.log` |

### Tổng pytest (có số liệu đầy đủ)
- G1 + G2 + G3a + G3b1 (non-page_batch + 60 page_batch) + G3b2: **1271 passed, 1 failed, 20 skipped**; **21 test chưa chạy** (xem dưới).
  - Phép cộng: G1 458 + G2 84 + G3a 251 + G3b1-rest 236 + G3b1 page_batch đã chạy 60 + G3b2 182 = 1271 passed. Skip: G1 19 + G2 1 = 20.
- Test đỏ (1, có sẵn ở baseline, không sửa): `tests/test_codex_bridge_benchmark.py::test_offline_manifest_provenance_and_explicit_live_boundary` — `assert '3b1c1ca08a19...' == 'dfbd0cbfd5d0...'` (hash manifest `benchmark/vision/codex/manifest.json`). Thuộc G1.
- Chưa chạy: 21 test của `tests/test_vision_page_batch.py` (xem dưới). Không có test nào trong 21 này thấy là đỏ, nhưng cũng không có số liệu.

### Chi tiết page_batch (G3b1)
- `test_vision_page_batch.py` có 81 test. Chạy được 60 (test 78-137 trong thứ tự collect của chunk), không F/E. Chưa chạy 21 (test 138-158).
- Lý do: test page_batch chậm, ~30-40 s mỗi test (ví dụ `test_restored_tabs_and_viewport_coverage_keep_verified_targets[popup_refresh]` chạy riêng: 1 passed, 30.8 s). Ba lần chạy đều timeout ở giới hạn 540 s.
- Các phần khác của G3b1 đã xong (dòng 8).

### Side effect: artifact benchmark bị đổi
- `git status` cuối phiên: ` M benchmark/vision/visual-buttons/flow-result.json` (2 dòng đổi). Trước phiên chỉ có `reports/phase-00/` chưa track.
- Diff: `"operations": 99 → 96`, `"model_batches": 6 → 5`. Nguồn ghi: `tests/test_vision_page_batch.py` (test ghi file này). Do chạy page_batch bị dừng giữa chừng nên số liệu có thể là kết quả dở.
- Chưa khôi phục vì nằm ngoài phạm vi file của phase này. Đề xuất: sau khi user đồng ý, `git checkout -- benchmark/vision/visual-buttons/flow-result.json`. Chạy lại `test_vision_page_batch.py` sẽ ghi lại file này.

### Alembic
`uv run alembic heads` → `a4c6e8f01234 (head)`. Khớp kỳ vọng (r1).

### Môi trường DB
- `DATABASE_URL` có trong `.env` (host:port `127.0.0.1:5432`; mật khẩu không ghi). Biến này không set trong shell.
- Cổng 5432 đang LISTEN (kiểm bằng TCP connect, không ghi, không start/stop docker). Tiến trình giữ cổng là `com.docker.backend.exe` (PID 9896), không phải của phiên này.
- Chưa xác nhận test có kết nối PostgreSQL thật hay không; không có test nào bị skip với lý do DB. Các lý do skip đã thấy: "run in offline harness image", "bridge process runs in the Linux container", "Linux Compose producer flock contention", "symlink adversary checked in Linux image", "set RUSTFS_STRESS=1 …". Tổng 20 skip (G1 19 + G2 1), 0 skip do DB. G3b chưa tổng đủ skip.
- Mốc "69 skip ở round 21" chưa đối chiếu được vì chưa có số skip toàn suite.

## Hash đối chứng v4

Script: `reports/phase-00/v4_identity.py` (chạy từ gốc repo: `uv run python -I plan/20261119-2212-browser-agent-loop/reports/phase-00/v4_identity.py`). Chạy 2 lần: exit 0 cả hai, `cmp` báo IDENTICAL.

Output (lần 1 = lần 2):
```
"codex_output_schema": sha256 572143fe7414be16b23706eeb7b666cd1c2dc73108dc46a36763d27a26f93ef9 (3797 bytes)
"codex_dom_v11_prompt_plus_schema": sha256 cc45b11674650ed8232f4cdbb643524de8ec08a760738aeacd36ff6519f29259 (9269 bytes)
    prompt_sha256 b1ef50be24b5f4f95063a512e900e93d7fc7cfd1a59e71b4de6e2ac3b93259a7
    bridge_schema_sha256 6ef40dd1f7c5e26c8bc04b03859a02a893969eea19845cf33cf5ef55f7a60368
```
- Hash 1: `TypeAdapter(CodexOutput).json_schema()` dạng `json.dumps(..., sort_keys=True, separators=(",",":"))`, mã hoá UTF-8 (`CodexOutput` tại `packages/contracts/src/auto_at/contracts/codex_bridge.py`).
- Hash 2: `with_response_schema(build_prompt(req, canonical_bytes(obs)), output_schema(3))` với `PROMPT_VERSION = "codex-dom-v11"` (`apps/control-plane/agents/prompts/codex_exploration.py`, `apps/control-plane/agents/vision/codex_service.py`).
- Nguồn request mẫu: không có fixture sẵn trong `tests/` chứa đúng một request đầy đủ. Script dựng request từ helper `observation()`/`request()` trong `tests/test_codex_bridge_contracts.py` và `task_context()`/prompt test trong `tests/test_codex_candidate_service.py`, thay UUID và thời điểm bằng hằng số (`UUID(int=1..7)`, `NOW = 2026-10-23T12:00Z`), `stage="dom"`, `candidate_limit=3`, task `"Check buttons on the fixture page"`. Đây là lệch nhỏ so với bước 6 ("dùng fixture có sẵn") và được ghi trong JSON.
- Chi tiết nằm trong `tests/fixtures/v4_identity.json`.

## Bản sao contract TS
`reports/phase-00/vision-contract.generated.ts.txt` (đuôi `.txt` để không vào graph). sha256 `26e0d39b1fc79a6f458181bc58a5fc26efc5a03732fbe7269528e3d0c6f9b211`. Phase 1 cần copy lại thành `.ts` (vào thư mục tạm, không vào graph) để so diff.

## hgraph check --changed
```
hgraph check — 4 graph, 438 file source
File vừa đổi: 1

✖ [uncovered-changed] file vừa đổi/mới nhưng chưa thuộc graph nào
  plan/20261119-2212-browser-agent-loop/reports/phase-00/v4_identity.py

Cách xử lý:  drift/stale-file → `hgraph sync <slug> --apply`
             uncovered-changed → `hgraph add <slug> <file...>` hoặc lập graph mới bằng /h-graph
exit=1
```
- Không có graph hiện tại nào phủ `reports/phase-00/` (4 graph: `codex-bridge`, `playwright-vision-worker`, `vision-dashboard`, `vision-exploration`). `hgraph add` cần sửa `docs/graphs/`, nằm ngoài phạm vi file của phase này, nên phiên không tự làm.
- Lựa chọn cho user: (a) `hgraph add codex-bridge plan/.../reports/phase-00/v4_identity.py` (vì script hash đọc contract bridge); (b) chuyển script sang thư mục khác có graph phù hợp; (c) lập graph mới cho công cụ kiểm tra plan (`/h-graph`). Phase 0 không tuyên bố xong khi check còn exit 1.

## Checklist "Tiêu chí xong" (phase-00-baseline.md)
- [ ] User đã quyết commit/để nguyên cho các file đang sửa dở. Chưa có quyết định riêng; không commit trong phiên này. Đã có WIP commit `a2e43d6` và `f85091a` theo prompt.
- [ ] Log baseline ruff/pytest/worker/dashboard có số pass/fail/skip. **Gần đủ**: ruff, G1, G2, G3a, G3b1 (phần còn lại), G3b2, worker 4 spec, dashboard test/typecheck/lint đều có số liệu. **Thiếu**: 21 test page_batch chưa chạy; worker vitest gộp (r1) không có summary, đã thay bằng 4 lệnh riêng.
- [x] Alembic head ghi lại (`a4c6e8f01234`).
- [x] `tests/fixtures/v4_identity.json` có 2 hash; script chạy 2 lần cho cùng kết quả; bản sao TS nằm ở `reports/phase-00/`.
- [x] Môi trường DB ghi rõ: `DATABASE_URL` có trong `.env`, cổng 5432 LISTEN, 0 skip do DB, chưa xác nhận kết nối thật.

Ghi chú: checklist ô 1 và ô 2 chưa tick, nên phase chưa xong. Phase 1 chỉ nên bắt đầu sau khi user chọn cách xử lý `uncovered-changed` và quyết định chạy nốt 21 test page_batch.

## Số liệu r1 giữ lại
- G1 + G2 + G3a (r1, cấu hình override + basetemp): 793 passed, 1 failed, 20 skipped. r2 cộng G3b: 1271 passed, 1 failed, 20 skipped.
- Collection lỗi (2a) gây ra bởi `CODEX_BRIDGE_EXECUTABLE` thiếu trong `.env`. Không sửa `.env` (file nhạy cảm). Cần user quyết: thêm biến vào `.env` cục bộ hoặc tắt bridge cục bộ.
- PermissionError ở basetemp mặc định (`C:\Users\hen\AppData\Local\Temp\pytest-of-hen`). Môi trường, không phải sản phẩm. Đã vượt bằng `--basetemp` trong scratchpad.

## Timeout và cách chạy
- Lệnh G3b1 lần đầu bị harness chuyển sang nền khi chạm 540 s (`exit=124` trong log, tiến trình đã kết thúc). Không chạy bản sao thứ hai.
- Các lệnh còn lại đều có `timeout` ≤ 530 s, không chạy nền.

## Side effect và tiến trình
- Không có stack docker, server hay worker nào do phiên này mở. Playwright của 4 spec đã kết thúc (exit 0).
- Không kill tiến trình nào. Các tiến trình khác trong máy (vite PID 2704 và 12252, next, nhiều `claude.exe`, `com.docker.backend.exe` PID 9896, python PID 24052 và 15212 khởi động trước phiên) không thuộc phiên này.

## GRAPH_UPDATE
- graph đã cập nhật: không. (`hgraph check` còn exit 1, xem trên.)
- file mới cần đưa vào graph: `plan/20261119-2212-browser-agent-loop/reports/phase-00/v4_identity.py`. Chờ user chọn.
- hgraph check --changed: exit 1 (output thật ở trên).

## File trong phạm vi và log
- Mới: `tests/fixtures/v4_identity.json`, `reports/phase-00/v4_identity.py`, `reports/phase-00/be-developer-junior-r2.md`, `be-developer-junior-r2.md.log`, `dashboard-test-r2.log`, `dashboard-typecheck-r2.log`, `dashboard-lint-r2.log`, `pytest-B-g3b1-basetemp.log`, `pytest-B-g3b1-pieceA.log`, `pytest-B-g3b1-rest.log`, `pytest-B-g3b2-basetemp.log`, `worker-vision-locators-r2.log`, `worker-vision-dom-r2.log`, `worker-vision-history-r2.log`, `worker-vision-operations-r2.log`, `hgraph-check-r2.log`.
- Từ r1: `be-developer-junior-r1.md`, các log `ruff-check.log`, `pytest-full.log`, `pytest-B-g1.log`, `pytest-B-g1-basetemp.log`, `pytest-B-g2-basetemp.log`, `pytest-B-g3a-basetemp.log`, `pytest-B-g3-basetemp.log`, `pytest-override-codex-off.log`, `worker-typecheck.log`, `worker-vision-tests.log`, `dashboard-test.log` (r1, lỗi `pnpm.cmd`, đã thay bằng `dashboard-test-r2.log`), `vision-contract.generated.ts.txt`.
- Không sửa code sản phẩm, test, `.env`, graph.

## Việc cần user quyết (ESCALATE)
1. Graph cho `v4_identity.py` (hoặc đổi vị trí script).
2. Khôi phục `benchmark/vision/visual-buttons/flow-result.json` về HEAD (`git checkout -- ...`).
3. Chạy nốt 21 test page_batch (138-158 trong chunk) với thời gian dài hơn, hoặc chấp nhận là chưa chạy.
4. Cấu hình `.env`: thêm `CODEX_BRIDGE_EXECUTABLE` hoặc tắt bridge cục bộ để collection chạy nguyên trạng; dọn `pytest-of-hen` nếu muốn basetemp mặc định.
5. Quyết định commit/để nguyên các file WIP.
