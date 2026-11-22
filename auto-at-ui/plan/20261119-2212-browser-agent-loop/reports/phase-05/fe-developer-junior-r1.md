STATUS: FAIL
CONTEXT_CHECK: ok

# Phase 5 (Dashboard) — fe-developer-junior r1

## CONTEXT_CHECK
- conventions: `docs/code-standards.md` (chỉ là chỉ mục, trỏ tới `AGENTS.md`), `AGENTS.md` (TypeScript chỉ dashboard + worker; test kèm code; không convention UI riêng → bám pattern `vision-dashboard.tsx` / ledger hiện có)
- graphs: `vision-dashboard` (đọc `docs/graphs/vision-dashboard.md`, 25 file trước khi sửa)
- blast radius: hgraph brief báo 28 file phụ thuộc depth 2 (tổng 28 bị phụ thuộc, 19 nền). Phạm vi sửa thực tế: 6 file dashboard/worker + 1 file graph. Không đổi contract/schema/chữ ký BE.

## Kết quả nhanh
| Kiểm tra | Kết quả thật |
|---|---|
| `pnpm --filter @auto-at/dashboard test` | `ℹ tests 48 / pass 48 / fail 0` (gồm 4 test mới) |
| `pnpm --filter @auto-at/dashboard typecheck` | exit 0 (`tsc --noEmit`) |
| `pnpm --filter @auto-at/dashboard lint` | exit 0 (`eslint .`) |
| `pnpm --filter @auto-at/dashboard build` | exit 0 (dùng để dựng server e2e) |
| `pnpm --filter @auto-at/playwright-worker typecheck` | exit 0 |
| `pnpm --filter @auto-at/playwright-worker lint` | exit 1, 22 lỗi `no-explicit-any` ở file KHÔNG thuộc phase này (`fixtures/exploration-strategy-benchmark.ts`, `vision-outcome-capture.spec.ts`, ...). `vision-dashboard.spec.ts` không có lỗi lint. |
| e2e `vision-dashboard.spec.ts --workers=1` (full) | **55 passed, 2 failed** (57 test) |
| e2e rerun 2 test lỗi (`-g`) | vẫn 2 failed (ổn định, không phải flaky) |
| `hgraph check --changed` | exit 1 — xem mục GRAPH_UPDATE |

## E2E — 2 test thất bại (chưa xác nhận là sẵn có)
- `workers/playwright/src/vision-dashboard.spec.ts:238` — "Vision cards align on desktop, keep spacing and stack without mobile overflow": `expect(screen.getByRole("img")).toBeInViewport()` → `viewport ratio 0`.
- `workers/playwright/src/vision-dashboard.spec.ts:336` — "a saved session focuses the website and New opens a consent-gated form": `expect(getByRole('region', {name: 'Vision browser screen'})).toBeInViewport()` → `viewport ratio 0`.
- Phân tích: không có code scroll-to-focus nào trong dashboard (grep `scrollIntoView` chỉ có ở History/Open settings). Hai test này không bật `agent_loop_enabled`, nên select và khối hint mới không render; khối `Agent step` chỉ render khi operation có `agent_step` (fixture này không có). DOM của hai luồng này không đổi so với trước phase. Nguyên nhân gốc chưa tìm được (có thể layout/viewport); **chưa chạy baseline HEAD** để chứng minh sẵn có. Cần người có quyền chạy baseline trên HEAD hoặc xác nhận trên develop.
- Ba test mới của phase này đều xanh: dòng `[23/57]`, `[24/57]`, `[25/57]` trong `e2e.log`.

## Thay đổi file
| File | Thay đổi |
|---|---|
| `apps/dashboard/app/generation-types.ts` | `VisionPolicy.agent_loop_enabled?`, `VisualExploration.engine?`, type mới `VisualAgentStep` (shape khớp `read_trace` ở `vision_results.py`: `step_index`, `evaluation_previous_goal`, `memory`, `next_goal`, `skipped_actions[]`), `VisualOperation.agent_step?` |
| `apps/dashboard/app/generation-api.ts` | `submitVisualExploration` payload nhận `engine?: "planner" \| "agent_loop"` (body vẫn `JSON.stringify(payload)`, không đổi endpoint) |
| `apps/dashboard/app/components/vision-provider-model.ts` | +10 mã vào `failureMessages`; helper mới `explorationEngine`, `engineRequestFields`, `blockedReasonMessage`, `agentStepView` (+ type `ExplorationEngine`, `AgentStepView`) |
| `apps/dashboard/app/components/vision-provider-model.test.ts` | +4 test (mapping mã, fallback, agent step view, engine) |
| `apps/dashboard/app/components/vision-operation-ledger.tsx` | khối `aria-label="Agent step"` trong "Selected operation": 3 trường (Đánh giá bước trước / Memory / Mục tiêu kế) + dòng `Blocked` liệt kê `skipped_actions`; chỉ render khi có `agent_step`; `overflowWrap: anywhere` inline |
| `apps/dashboard/app/vision-dashboard.tsx` | state `engine` (mặc định planner); `<select id="vision-engine">` Planner / Agent loop chỉ hiện khi `savedPolicy.agent_loop_enabled === true`; hint text theo engine; `request` gắn `engine` chỉ khi Agent loop (planner giữ nguyên payload cũ). Gating `trace_version === "v4"` không đổi. |
| `workers/playwright/src/vision-dashboard.spec.ts` | fixture: `state.agentStep`, `engine` của sessionB, `agent_step` ở op 2 của sessionB; +3 e2e test (engine gating + payload, ledger agent step + planner không có khối, viewport 400px không tràn) |
| `docs/graphs/vision-dashboard.md` | `hgraph add` 2 file (`vision-provider-model.test.ts`, `vision-dashboard.spec.ts`), `hgraph sync --apply` (cập nhật import ledger → `vision-provider-model`) |

Không đụng: `globals.css` (ngoài "File liên quan", nên không thêm CSS mới; dùng class sẵn + inline style), `vision-conclusion.tsx` (không mở trong phase này, nên không xác nhận lỗi encoding ở file đó), contract, BE, DB.

## Ladder cho helper/file mới
- File mới: **không tạo file mới nào**. Mọi helper nằm trong `vision-provider-model.ts` (file đã có trong "File liên quan"), để không phải thêm file ngoài danh sách.
- Helper mới và lý do:
  - `explorationEngine(value)`: chuẩn hoá engine, giá trị lạ → planner. Tái dùng nothing vì chưa có.
  - `engineRequestFields(engine)`: planner không gửi key `engine` (payload cũ giữ nguyên).
  - `blockedReasonMessage(reason)`: tái dùng `visionFailureMessage`; chỉ thêm fallback có giới hạn độ dài.
  - `agentStepView(item)`: gom logic null/rỗng/cắt 600 ký tự/giới hạn 20 dòng blocked/kind 40 ký tự để test được (ledger là `.tsx`, node test không import được JSX).
- Dependency mới: không.

## Chi tiết quyết định
- Mã lỗi: ngoài 6 mã trong phase, thêm `invalid_ref`, `action_kind_blocked`, `ineligible_target`, `batch_stopped` (đều là `skipped_reason` / mã allow-list của BE phase 4), để không rơi vào fallback.
- Nhãn: giữ nguyên nhãn trong phase ("Đánh giá bước trước", "Memory", "Mục tiêu kế"); dòng bị chặn đặt nhãn `Blocked` (tiếng Anh, giống UI còn lại). Option select: "Planner" / "Agent loop". Lưu ý UI đang trộn Anh/Việt, cần user chốt.
- Không mở rộng `VisionPolicy` gửi đi: `agent_loop_enabled` chỉ đọc (BE bỏ qua khi PUT).

## Rủi ro đã biết (không thuộc phần FE)
- Từ báo cáo phase 4 (`reports/phase-04/be-developer-r1.md` mục 1): `/trace` chưa trả `agent_step` ở production vì `routes/vision.py::_results` không có `agent_steps(scope)` trên repository. FE đã xử lý vắng field (không hiện khối), nhưng **UI sẽ không thấy khối agent cho tới khi BE nối thêm**.

## GRAPH_UPDATE
- graph đã cập nhật: `vision-dashboard` (`hgraph add` 2 file, `hgraph sync --apply`)
- file mới đã đưa vào graph: không có file mới; thêm vào graph hiện có: `apps/dashboard/app/components/vision-provider-model.test.ts`, `workers/playwright/src/vision-dashboard.spec.ts`
- `hgraph check --changed`: exit 1. Output thật:
  ```
  ✖ [uncovered-changed] file vừa đổi/mới nhưng chưa thuộc graph nào
    apps/control-plane/... (17 file: phase BE, không thuộc phase 5)
    apps/dashboard/app/components/vision-operation-ledger.tsx
    apps/dashboard/app/components/vision-provider-model.test.ts
    apps/dashboard/app/components/vision-provider-model.ts
    apps/dashboard/app/generation-api.ts
    apps/dashboard/app/generation-types.ts
    apps/dashboard/app/vision-dashboard.tsx
    packages/contracts/... (2), tests/test_vision_*.py (3), workers/playwright/src/vision-contract.generated.ts
    workers/playwright/src/vision-dashboard.spec.ts
    … +1 file nữa
  ```
  - Phần lớn là file của phase khác (control-plane, contracts, tests Python, `vision-contract.generated.ts`) — ngoài phạm vi, không tự thêm vào graph.
  - Các file dashboard của phase này vẫn bị báo "uncovered" dù `hgraph which` trả `→ vision-dashboard` và `hgraph check <file>` cho `vision-dashboard.tsx` trả "✔ Không có vấn đề". Đây là lệch giữa `--changed` và `which`; chưa điều tra sâu. Cần leader/hgraph xem.
- `hgraph check <file phase 5>`: `✔ Không có vấn đề.`

## Đã dừng tiến trình
- Server e2e (`next start` port 3107) chạy trong tiến trình bao bởi wrapper foreground có `timeout`, được tắt bằng `taskkill /T` sau khi test xong; đã kiểm tra không còn listener trên 3107.
- Lưu ý quy trình: để chạy e2e phải có server, và repo không có `playwright.config` với `webServer`. Tôi dùng một script Node foreground bị giới hạn thời gian (`scratchpad/e2e-run.mjs`) thay vì nền. Nếu quy định coi việc này là tiến trình nền, cần user xác nhận.

## Log
- `plan/20261119-2212-browser-agent-loop/reports/phase-05/fe-developer-junior-r1.md.log`
- Output thô: `scratchpad` `dash-test.log`, `dash-typecheck.log`, `dash-lint.log`, `dash-build.log`, `e2e.log`, `e2e-rerun.log`, `worker-lint.log`, `hgraph-check2.log`

## Việc còn lại / đề xuất
1. Chạy baseline HEAD cho 2 test `:238` và `:336` để xác nhận sẵn có (hoặc sửa nếu do phase này).
2. Quyết định nhãn tiếng Anh / tiếng Việt cho khối agent và select engine.
3. Leader xử lý `hgraph check --changed` cho file phase khác và điều tra lệch `--changed` với `which`.
4. BE nối `agent_steps` vào `/trace` (phase 4, mục 1) để khối agent hiện được.
