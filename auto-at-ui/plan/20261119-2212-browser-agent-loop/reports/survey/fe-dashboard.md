STATUS: DONE

CONTEXT_CHECK
- conventions: repo không có docs/code-standards.md / api-conventions.md; chỉ AGENTS.md (không có quy tắc riêng cho dashboard ngoài "TypeScript reserved for dashboard"). Bám pattern file cùng loại (model.ts thuần + .test.ts node:test + tsx mỏng).
- graphs: không graph nào phủ vùng này (docs/graphs có 0 graph). Đề xuất /h-graph (tên: `vision-dashboard`) nếu có sửa UI.
- blast radius: vision-dashboard.tsx bị 2 file phụ thuộc (generation-dashboard.tsx, agent/page.tsx); nó phụ thuộc 23 file (hgraph brief).

## Impact inventory (phạm vi nếu LÀM UI; không viết code ở khảo sát này)
- Route: /agent (qua generation-dashboard.tsx -> VisionDashboard), query `?vision=<id>`.
- Component sửa: vision-dashboard.tsx (form + chọn engine), vision-session-detail.tsx (cổng v4 -> engine mới), vision-operation-ledger.tsx (hiện reasoning/step).
- State/data: thêm 1 state `engine` trong VisionDashboard; không đụng store/query key nào (không có thư viện query, toàn useState + fetch).
- Contract BE FE phụ thuộc: POST /api/v1/vision/explorations (thêm `engine`, tùy chọn `allowed_domains`), VisualExploration (thêm field engine/trace_version), GET /trace (thêm per-step fields), /result.
- Token/style: globals.css class có sẵn (`form-grid`, `field`, `workspace-section`, `stack-list`, `vision-step`...). Không có design-guidelines.
- Trạng thái, responsive, a11y: xem mục 3.

## 1. Form tạo exploration
- Form: vision-dashboard.tsx:243-255 (section `#vision-new`), `<form onSubmit={requestExploration}>` dòng 246. Field: Project (247, select), Target URL (248), Exploration intent (249, textarea). KHÔNG có scope, limits, provider trong form.
- Provider/model/limits nằm trong Vision settings (policy tenant): vision-provider-settings.tsx:13-22; `max_steps`, `max_session_seconds`, ... ở generation-types.ts:49-62 (VisionPolicy). Scope "interaction_scope" chỉ là kết quả đọc (generation-types.ts:129,157), không phải input của form.
- Gửi: requestExploration (vision-dashboard.tsx:174-179) -> setConfirmation({kind:"new", request:{project_id,target_url,task_intent}}) -> submitExploration (185-204, dòng 193) gọi submitVisualExploration `{...request, use_vision:true, expected_provider, expected_model, expected_input_policy_fingerprint?}`. API: generation-api.ts:48-50 (POST /api/v1/vision/explorations, Idempotency-Key). Reload: generation-api.ts:51-52.
- Allowlist domain hiện có ở cấp PROJECT: `ProjectExecutionPolicy.allowed_origins` (generation-types.ts:63-67) hiển thị qua slot `projectPolicy` (vision-dashboard.tsx:264). Gợi ý: engine mới dùng lại allowed_origins của project (+ origin target_url), KHÔNG thêm ô allowlist vào form -> không cần UI allowlist.
- Chỗ thêm tối thiểu engine: (a) generation-api.ts:48 thêm `engine?: "v4" | "agent_loop"` vào payload type; (b) vision-dashboard.tsx: 1 `useState<"v4"|"agent_loop">("v4")` cạnh dòng 50, 1 `<label className="field">Engine<select>` sau dòng 248, thêm `engine` vào `request` tại dòng 22-23 và 178. Tổng ~6 dòng. Mặc định v4 = không đổi hành vi. Ghi chú: confirm dialog (271) mô tả "advisory exploration" — engine mới thực sự thao tác trình duyệt nên nên chỉnh câu mô tả; reload (requestReload 180) dùng lại engine của session phía BE.

## 2. Trace / timeline
- Endpoint đang dùng: vision-session-detail.tsx:42-44 gọi song song getVisionResult (/result), getVisualTrace (/trace, phân trang, generation-api.ts:74-92), getVisualLocators (/locators, :93-96); poll 5s khi pending (:61); tiến trình live qua /activities + /activities/stream (generation-api.ts:66-67; component vision-progress-timeline.tsx, model vision-progress-timeline-model.ts, stage->nhãn map :10-49, unknown stage -> "Advisory progress updated" :97-99, nên engine mới không vỡ nếu thêm stage lạ nhưng nhãn chung chung).
- Kiểu TS: generation-types.ts: VisualExploration:68-84 (trace_version "legacy"|"v4" :70), VisualOperation:155 (purpose "setup"|"explore"|"restore"|"replay"), VisualLocator:156, VisualTrace:158, VisionResult:160, VisionProgressActivity:104-114 (metadata Record<string,string|number|boolean>).
- Gating: vision-session-detail.tsx:85 và :99 chỉ render live workspace + progress cho `trace_version === "v4"`; :100 locator catalog cho trace v4; vision-dashboard.tsx:258,269 render nhánh legacy (trajectory/replay/safe actions) cho `!== "v4"`. => session engine mới mà trace_version khác "v4" sẽ rơi vào nhánh LEGACY (sai, hiển thị trajectory rỗng). Rủi ro nhỏ nhưng thực: BE nên giữ trace_version="v4" cho agent_loop (evidence tương thích benchmark theo contract.md) hoặc FE sửa các 5 điểm gating trên.
- Tối thiểu để hiện evaluation_previous_goal/memory/next_goal + action results, tái dùng sẵn:
  - Ledger đã liệt kê operation theo sequence với trạng thái (vision-operation-ledger.tsx:29-30) và selected step panel (:30). Action results = VisualOperation.status/outcome_code (generation-types.ts:155) + operationLabel/operationStatus (vision-operation-model.ts) đã có -> action results KHÔNG cần UI mới nếu BE ghi mỗi action thành 1 operation (đúng yêu cầu benchmark collect).
  - Reasoning per-step: cách ít code nhất = (1) thêm field tùy chọn vào VisualOperation: `agent_step?: { step: number; evaluation_previous_goal: string; memory: string; next_goal: string } | null` (generation-types.ts:155) hoặc kiểu `VisualTrace.steps?`; (2) vision-operation-ledger.tsx:30 trong khối `vision-selected-step` thêm `<dl>`/3 dòng nếu `selected.agent_step` tồn tại (~5 dòng). Không tạo component mới; không tạo endpoint FE mới nếu BE nhúng vào /trace.
  - Lựa chọn thay thế (nếu BE đặt reasoning vào activities): metadata chỉ nhận string|number|boolean (types :112), nên chuỗi dài bị cắt/không phù hợp -> ưu tiên /trace.
  - Ledger đã lọc/hiện restore/replay (:15,:26,:29): engine mới không có -> ẩn tự nhiên, nhưng text "Returning to an earlier page" không xuất hiện.
  - Blocked actions (allowlist/stale ref): hiện qua status "rejected"->"Not executed" (vision-operation-model.ts) + outcome_code; nhãn thân thiện mã lỗi ở vision-provider-model.ts:~100 (visionFailureMessage map code->text). Mã mới (vd stale_ref, domain_blocked) cần thêm vào map này, nếu không hiện fallback chung; 1 dòng/mã + test ở vision-provider-model.test.ts.
- Ladder tái dùng cho mọi type/component mới: không tạo component mới (tái dùng VisionOperationLedger :30, VisionLiveScreen, VisionResultSummary, VisionProgressTimeline); không tạo type mới ngoài mở rộng VisualOperation (generation-types.ts:155) và VisualExploration (:68-84) với field tùy chọn; không tạo thư viện, không tạo endpoint client mới (getVisualTrace generation-api.ts:74). Không có file mới => không cần hgraph add.

## 3. Trạng thái & a11y/responsive hiện có
- Loading: LoadingState (components/states.tsx), "Loading exploration result…" (session-detail:84), "Loading vision policy" (dashboard:232). Empty: EmptyState "No visual explorations" (dashboard:267), "No browser action has been recorded yet." (ledger:29). Error: notice role="alert" (dashboard:256), settings error + Retry (229-230), session-detail error (:89) với tách 401/403/404 (:46-47,:59). Không quyền: canManage/role==="tenant_admin" (dashboard:66,168,227), nút xóa evidence ẩn khi !canDelete; policy disabled message (:250). Offline: SSE fallback polling label (visionConnectionLabel :101-106). Disabled gating khi dirty/saving/submitting (:251).
- A11y: ledger section tabIndex=0 + phím Arrow/Home/End (ledger:19-23), aria-current="step", range "Trace position", aria-label trên nút operation, ConfirmDialog. Form dùng `<label className="field">` bọc control (select Engine phải theo cùng cách để có label). Layout dùng `vision-live-workspace`/`form-grid` (globals.css); chưa kiểm tra breakpoint bằng browser (không yêu cầu). Lưu ý: vision-conclusion.tsx có chuỗi tiếng Việt lẫn ký tự hỏng (dòng 8, 18, 22 hiển thị `?`) — lỗi encoding sẵn có, ngoài phạm vi, nên báo user.

## 4. Test / lệnh
- Dashboard test: node:test, `*.test.ts` thuần model, import `.ts` thẳng (vd components/vision-operation-model.test.ts:1-3). Không vitest, không test render React. apps/dashboard/package.json scripts: `test` = `node --experimental-strip-types --test`, `typecheck` = `tsc --noEmit`, `lint` = `eslint .` (cấu hình ở root eslint.config.mjs; eslint là devDependency root, package dashboard không khai báo). Chạy: `pnpm --filter @auto-at/dashboard test|typecheck|lint` (hoặc cd apps/dashboard). Tôi chưa chạy các lệnh này (khảo sát).
- Test hiện có liên quan: vision-operation-model.test.ts, vision-progress-timeline-model.test.ts, vision-provider-model.test.ts, vision-click-model.test.ts, vision-replay-model.test.ts, generation-api.test.ts (kiểm payload API: thêm case engine vào đây).
- Logic mới nên đặt trong *-model.ts thuần (vd hàm format agent_step) để test được bằng node:test.

## 5. Có thể hoãn UI cho phase đầu?
Có, khuyến nghị HOÃN phần hiển thị reasoning; chỉ cần 2 điều kiện:
- (a) BE giữ `trace_version` = "v4" (hoặc FE sửa 5 điểm gating) để session agent_loop không rơi vào nhánh legacy; ops đã ghi đủ operation/locator/frames như contract.md nên ledger/live screen hiện sẵn, bỏ qua per-step reasoning.
- (b) Chọn engine per session vào lúc phase đầu: qua API (field `engine` trong POST) / script benchmark `run.py`; mặc định v4 nên dashboard hiện tại không đổi và không gửi engine.
Rủi ro khi hoãn: không thấy evaluation/memory/next_goal trên UI (debug phải đọc /trace JSON hoặc evidence benchmark); dashboard vẫn hiển thị session mới với nhãn "advisory" gây hiểu nhầm ("model proposals only, not executed" dashboard:269, ConfirmDialog :271) dù engine mới thực thi thật; mã lỗi mới hiện thông báo generic; nếu BE đổi shape /trace (thêm field) FE vẫn ổn vì types tùy chọn, nhưng nếu đổi `purpose`/`trace_version` thành giá trị mới thì ledger/session-detail có thể lọc nhầm hoặc rơi nhánh legacy. Chi phí làm UI tối thiểu sau đó: ~15-25 dòng (select engine + 3 dòng reasoning trong ledger + vài map mã lỗi + test generation-api/ model), 0 file mới.

GRAPH_UPDATE
- graph đã cập nhật: không cần — khảo sát, không đổi file
- file mới đã đưa vào graph: không
- hgraph check --changed: không chạy (không sửa code)
