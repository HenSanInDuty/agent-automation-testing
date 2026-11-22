STATUS: DONE

# Phase 2 — Worker agent mode (be-developer r1)

CONTEXT_CHECK
- conventions: `docs/code-standards.md` (chỉ mục trỏ về `AGENTS.md`) và `AGENTS.md` đã đọc nguyên văn. Repo không có `docs/api-conventions.md` (brief chỉ liệt kê `code-standards.md`). Quy tắc áp dụng cho phase này: TypeScript chỉ cho dashboard + worker; contract sinh từ Python (không sửa tay `vision-contract.generated.ts`); thay đổi hành vi phải kèm test. Phần còn lại của `AGENTS.md` nói về control-plane Python, không liên quan phase này; code bám khuôn các file `vision-*.ts` hiện có.
- graphs: `playwright-vision-worker` (đọc nguyên văn), `hgraph brief workers/playwright/src/vision-operations.ts workers/playwright/src/vision-dom.ts`
- blast radius: 15 file bị phụ thuộc / 11 file phụ thuộc (từ hgraph brief; depth 2)

## Impact inventory

### Database
Database: không đụng (worker giữ state trong RAM; không migration, không backfill).

### File và contract
| File | Tạo/Sửa | Lý do |
|---|---|---|
| `workers/playwright/src/vision-operations.ts` | sửa | toàn bộ agent mode, mọi nhánh sau `session.agentMode` |
| `workers/playwright/src/vision-agent-mode.spec.ts` | tạo | 23 test Chromium thật (plan liệt kê) |
| `workers/playwright/src/fixtures/agent-loop-target.ts` | tạo | fixture loopback 2 origin (plan liệt kê) |
| `workers/playwright/src/vision-dom.ts` | KHÔNG sửa | plan cho phép sửa chỉ nếu bước 1 cần; `skipped_count` có sẵn, eviction làm ở `vision-operations.ts` |
| `docs/graphs/playwright-vision-worker.md` | sửa (hgraph add/sync) | thêm 2 file mới |

- Caller của hàm đổi chữ ký: không đổi chữ ký hàm/method public nào. `Session` (type nội bộ, không export) thêm 4 field: `agentMode`, `blockedTerms`, `latestSnapshotId`, `recovered`. Chỉ `open()` dựng `Session` (grep `domSnapshots: new Map()` = 1 chỗ).
- Public contract: không đổi. Worker đọc `VisualWorkerOpen.agent_mode` / `blocked_action_terms` (đã có từ phase 1; schema có `default: false` / `[]`; worker dùng `=== true` / `?? []`). Capabilities, `operation_budget` (`1 + max_states*(2*max_hops+3)`), mã lỗi HTTP không đổi. Mã outcome mới trong agent mode: `origin_blocked`, `sensitive_action_blocked` (cùng tập mã `stale_dom_snapshot`, `dialog_unsupported`, `download_unsupported` đã có).
- Test hiện có phủ vùng: `vision-operations.spec.ts` (99), `vision-dom.spec.ts`, `vision-history`, `vision-locators`, `vision-target-preflight`, `vision-visual-buttons`, `vision-readiness`, `vision-outcome-capture`, `contract`, `vision`, `vision-observability`, `vision-click-evidence`, `vision-sample-guard`, `vision-settle-observability`. Chưa có test trước phase này cho: eviction snapshot, allowlist enforce, blocklist hành động, re-baseline form, dialog/download hồi phục — nay đã có trong spec mới.

## Cái đã làm (theo bước plan)
Mọi thay đổi nằm sau `session.agentMode`; v4 chạy cùng code path cũ.
1. `observeDom`: agent mode bỏ chặn `dom_snapshot_limit`; sau khi snapshot mới thành công (và sau `revalidateDom`) gọi `evictSnapshots` (xoá map, dispose `document` + từng handle `anonymousTargets`), đặt `latestSnapshotId`. Observe lỗi thì snapshot cũ giữ nguyên. Evict chỉ chạy khi không có op pending (observeDom đã `operation_pending`).
2. `prepare`: agent mode, `dom_snapshot_id !== latestSnapshotId` ⇒ `rejected stale_dom_snapshot` (kiểm trước `unknown_dom_snapshot`, vì snapshot cũ đã bị xoá khỏi map).
3. Tuần tự (`sequential = agentMode && purpose === "explore"`): bỏ `hop_limit`/`state_limit`, không `exploredStates++`, không push/đặt `ancestry`; cho `navigate` (về `target_url`), `back`, `close_popup` với purpose `explore`. v4 giữ `invalid_navigation_purpose` / `invalid_restore_purpose`.
4. Allowlist K3: kiểm tại `prepare` bằng URL hiện tại của page (`allowedOrigin`, `vision-contract.ts:178`): page `http(s)` ngoài `allowed_origins` ⇒ mọi kind trừ `close_popup`/`back` bị `rejected origin_blocked`. `context.route` không đổi (không abort sub-resource; ảnh origin khác vẫn tải). Page `about:blank` không bị coi là origin ngoài (nếu không, `navigate` đầu tiên bị chặn).
5. Hành động nhạy cảm: sau ground, `ground.target.evaluate(sensitiveFacts)` ⇒ `sensitive_action_blocked` khi: `type=submit|reset`, nút trong `form` không `type` (property `type === "submit"` và `.form`), `input[type=image]` trong form, `a[download]`, hoặc tên (aria-label, aria-labelledby, label, title, value của nút, textContent) khớp `blocked_action_terms` sau chuẩn hoá NFC + chữ thường (so khớp "chứa"). Worker không giữ danh sách riêng (`blockedTerms` chỉ từ `VisualWorkerOpen`).
6. Re-baseline: sau `type` thành công mà `fingerprint` (url + interaction + form presence + scroll) trước/sau bằng nhau, `snapshot.state = captured` cho snapshot của op.
7. K4: dialog / download không-chủ trong lúc op đang chạy ⇒ `session.recovered`; cuối op throw cùng mã v4 (`dialog_unsupported`, `download_unsupported`) nhưng không set `policyFailure`. Ngoài op đang chạy, `action_outcome_unknown`, và mọi thứ ở v4 ⇒ khoá như cũ. Download do click (owner) vốn không khoá ở v4 (outcome `download_started`, status completed); giữ nguyên.

## Ladder cho mọi file/helper mới mà plan chưa ghi lý do
| Thứ mới | Đã tìm chỗ tái dùng | Vì sao chưa đủ |
|---|---|---|
| `evictSnapshots` (method) | `expire()` (`:99-111`) clear map nhưng không dispose handle, và đóng cả browser | cần dispose có chọn lọc, giữ browser sống |
| `sensitiveFacts` + `normalizeTerm` | `visualButtonSemantics` (chỉ cho scope visual_buttons), regex nhạy cảm `vision-dom.ts:126` (lọc control khỏi snapshot, không phân biệt submit/download) | không có sẵn kiểm submit/download/tên theo từ khoá cho control đã ground |
| field `Session.recovered` | `policyFailure` (dính vĩnh viễn) | cần trạng thái "ghi nhận mà không khoá" (K4) |
| origin_blocked bằng URL page tại prepare (thay vì đánh dấu trong route handler) | `observeOrigin` / `context.route` (chỉ ghi nhận) | URL page sống bao phủ redirect + popup + điều hướng cùng tab, không cần thêm state; route handler giữ nguyên |
| spec + fixture mới | `vision-target.ts` dùng chung (nhồi route agent vào sẽ ảnh hưởng spec v4) | cần 2 origin loopback + form/dialog/download riêng; plan đã liệt kê |
| dependency mới | — | không thêm |

## Lệch / ghi chú so với plan (cần leader biết)
1. **Test 25 vòng → 20 vòng.** Plan ghi 25 observe + 25 click với `max_states/max_hops` ví dụ 3/2, nhưng `operation_budget = 1 + 3*(2*2+3) = 22` (công thức giữ nguyên theo "Sửa sau review") nên op thứ 23 sẽ dính `operation_budget_exhausted`. Spec dùng 3/2 + 1 setup + 20 vòng observe/click = 21 op, vẫn gấp nhiều lần `max_states=3`, `max_hops=2`; đối chứng v4 cùng cấu hình chạm limit.
2. Bước 4 làm bằng kiểm URL live ở prepare, không đánh dấu page trong route handler (xem ladder). Hành vi theo K3 như plan.
3. Thêm (không có trong bước plan, theo AC3 "type không gửi Enter"): agent mode `type` với `text` chứa `\r`/`\n` ⇒ `sensitive_action_blocked`, vì `pressSequentially("\n")` bấm Enter và submit form.
4. `close_popup` được phép với purpose `explore` ở agent mode (plan bước 3 chỉ nêu back/navigate; test plan yêu cầu "close_popup chạy").
5. Từ khoá khớp theo "chứa" + NFC + lowercase đúng plan bước 5; **không** bỏ dấu. Phase 4 test ghi "có dấu/không dấu": nếu Python muốn cả "xoa tai khoan" bị chặn thì danh sách `blocked_action_terms` phải chứa cả hai dạng (hoặc worker phải bỏ dấu, đề nghị quyết ở phase 4, không làm ở phase này).
6. `hgraph check --changed` exit 1 — xem GRAPH_UPDATE (lỗi do repo git gốc là thư mục cha, file phase 1 chưa thuộc graph; không phải do phase 2).
7. `npm run lint` của worker đỏ ở baseline: 22 lỗi (`no-explicit-any`, `no-require-imports`) trong 6 file **không phải của phase này** (`exploration-strategy-benchmark.ts`, `vision-integration-server.ts`, `origin-guard.cjs`, `vision-contract.ts`, `vision-dom.spec.ts`, `vision-outcome-capture.spec.ts`; `git status` xác nhận chưa file nào trong số đó bị sửa). File phase này đụng lint sạch.

## Kiểm chứng (output thật)
Ghi chú: `npm.cmd test -- <spec> --workers=1` (không có `playwright.config`, timeout mặc định 30s/test).

Typecheck:
```
> @auto-at/playwright-worker@0.1.0 typecheck
> tsc --noEmit
(exit 0, không output lỗi)
```
Lint file phase này: `npx eslint src/vision-operations.ts src/vision-agent-mode.spec.ts src/fixtures/agent-loop-target.ts` → exit 0, không output.
Lint toàn worker (`npm run lint`): `✖ 22 problems (22 errors, 0 warnings)`, toàn bộ nằm trong 6 file không đụng (danh sách ở mục 7); không lỗi nào ở file phase này.

Spec mới `vision-agent-mode.spec.ts`, 3 lần chạy liên tiếp (cấu hình code cuối):
```
run 1: 23 passed (2.3m)
run 2: 23 passed (2.3m)
run 3: 23 passed (2.3m)
```
Danh sách (run 1): snapshot cũ bị evict + `stale_dom_snapshot` không click; 20 vòng observe/click với max_states 3 / max_hops 2 (handle cũ đã dispose); v4 cùng limit chạm `dom_snapshot_limit`/`hop_limit`/`state_limit`; back/navigate explore (agent) vs `invalid_restore_purpose`/`invalid_navigation_purpose` (v4); popup ngoài allowlist mở, `origin_blocked` cho click/type/scroll/navigate, `close_popup` chạy, ảnh origin khác tải (`GET /pixel.png`, naturalWidth 1); blocklist: "Gửi đi", "Tiếp tục" (nút không type trong form), "Tải về" (`a[download]`), "Xoá tài khoản", "XOÁ" (NFD) ⇒ `sensitive_action_blocked`, không có request submit/file.bin; "NẠP THẺ", "ĐĂNG KÝ" chạy; type vào ô không submit; `type` có `\n` bị chặn; v4 không áp blocklist; batch type A/B/C cùng snapshot chạy cả ba (v4: `stale_dom_snapshot`); confirm/alert/prompt/beforeunload ⇒ `dialog_unsupported`, `policyFailure=null`, op kế chạy (v4: `policyFailure="dialog_unsupported"`, `observeDom` bị từ chối); download do click ⇒ `download_started`, op kế chạy; download trong op `wait` đang chạy hồi phục ở agent, khoá ở v4; download ngoài op và `action_outcome_unknown` khoá cả hai chế độ.

Hồi quy v4 (không sửa spec v4 nào):
```
vision-operations.spec.ts                        99 passed (6.2m)
vision-dom, vision-history, vision-locators, vision-target-preflight, vision-visual-buttons,
  vision-readiness, vision-outcome-capture, contract   110 passed, 1 skipped (1.3m)
    (skip = contract.spec.ts:120 "runs generated source with the browser bundled in the worker image", chỉ chạy trong image)
vision, vision-observability, vision-click-evidence, vision-sample-guard,
  vision-settle-observability                    26 passed (8.0s)
```
Cả ba lệnh exit 0. Log tô ở scratchpad: `...\scratchpad\reg-operations.log`, `reg-rest.log`, `reg-other.log`, `agent-run2.log`, `agent-run3.log`.

Không chạy: `vision-dashboard.spec.ts` (không import `vision-operations`, không thuộc danh sách hồi quy của phase), pytest (phase này không đụng Python).

## Chưa có test / rủi ro còn lại
- Chưa thử trên target mongchiton thật (phase 6): rủi ro "chặn nhầm" từ khoá chỉ kiểm bằng fixture ("ĐĂNG KÝ", "NẠP THẺ" không bị chặn khi danh sách không chứa chúng). Kết quả thực phụ thuộc danh sách của `domain/vision_agent_safety.py` (phase 4).
- Từ khoá "chứa" có thể chặn quá tay (ví dụ "xoá" trong "Xoá bộ lọc"); đó là quyết định danh sách ở phase 4.

GRAPH_UPDATE
- graph đã cập nhật: `playwright-vision-worker` (hgraph add + `sync --apply`; cập nhật quan hệ import của hai file mới)
- file mới đã đưa vào graph: `workers/playwright/src/vision-agent-mode.spec.ts`, `workers/playwright/src/fixtures/agent-loop-target.ts`
- `hgraph check` (toàn bộ): `hgraph check — 4 graph, 444 file source / ✔ Không có vấn đề.` exit 0
- `hgraph check --changed`: **exit 1** `✖ [uncovered-changed]` liệt kê 14 file, gồm cả `workers/playwright/src/vision-operations.ts` và `vision-contract.generated.ts` dù `hgraph which` xác nhận hai file này thuộc `playwright-vision-worker`. Nguyên nhân: thư mục git gốc là `D:/Person/CaoHoc/KhoaLuanTotNghiep/agent-at` (cha của `auto-at-ui`), `--changed` so đường dẫn có tiền tố `auto-at-ui/` với đường dẫn graph không tiền tố. Các file còn lại trong danh sách là file phase 1 (Python control-plane + contracts + tests) chưa thuộc graph nào, ngoài phạm vi phase 2. Không có file nào do phase 2 tạo/sửa bị báo thiếu graph (hai file mới đã nằm trong graph). Đề nghị leader xử lý khi gộp (lập graph cho `vision.py`/`codex_bridge.py` phase 1, hoặc chạy hgraph từ git root).
