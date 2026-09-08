# Vision hỗ trợ locator cho Playwright và lưu vết khám phá

Trạng thái: **completed**. Tạo ngày 07/09/2026, giờ Asia/Saigon.
Các đường dẫn source trong tài liệu tính từ `auto-at-ui/`.
Đây là kế hoạch mới dựa trên working tree hiện tại, gồm cả thay đổi chưa commit của kế hoạch trajectory trước. Không đồng nghĩa những thay đổi trước đã được kiểm chứng đầy đủ.

## Mục tiêu và yêu cầu đã xác nhận

Vision quan sát ảnh để nhận diện phần tử cần thao tác; worker Playwright đối chiếu phần tử thật, kiểm chứng locator và thực hiện thao tác. Kết quả khám phá cung cấp locator và đường đi đã quan sát cho bước tạo test Playwright. Người dùng xem được ảnh, hành động, kết quả và việc quay lại state trong khi khám phá và sau khi kết thúc.

Yêu cầu từ hội thoại:

- Mỗi thao tác trên màn hình phải có frame và dấu vết.
- Click đổi trang phải quay lại hoặc khôi phục state trước để thử nhánh khác.
- Vision bổ trợ locator cho Playwright; kết quả Vision phải thật sự được bàn giao.
- Có nơi xem kết quả cuối và nguyên nhân khi chưa có draft/run/report.

Luồng dự kiến:

```text
frame → Vision chọn phần tử → worker kiểm chứng locator
      → lưu before → thao tác Playwright → lưu after
      → quan sát thay đổi → back/restore có kiểm chứng khi đổi nhánh
      → gói locator + đường đi + bằng chứng
      → tạo draft → duyệt theo cơ chế hiện có → Playwright run → report
```

Màn Vision luôn có kết quả khám phá và trace, kể cả khi generation lỗi.

## Tiêu chí nghiệm thu đo được

1. Mỗi thao tác browser thực sự, gồm click, nhập, cuộn, chờ, điều hướng ban đầu, back, đóng popup và từng bước replay phục hồi, có operation ID, thứ tự thực hiện và trạng thái. Before phải được lưu bền vững trước hành động; after được lưu khi browser còn chụp được. Capture lỗi, worker chết hoặc response mất phải có lý do rõ; không biến mất khỏi lịch sử.
2. Frame của operation là ảnh tại lần thực hiện đó. Không lấy ảnh cha từ một browser context khác rồi trình bày như before thật. Proposal chưa chạy và stop không tạo click giả.
3. Locator được bàn giao có chứng cứ: scope, descriptor có cấu trúc, đúng một phần tử, đúng phần tử Vision chỉ, kiểm tra khả năng thao tác, frame/state nguồn và thời điểm xác minh. Tất cả locator mơ hồ, cũ hoặc không đối chiếu được có lý do và không được gắn nhãn verified.
4. Fixture nhánh A điều hướng rồi quay lại thử B phải khôi phục đúng các invariant đã chọn (URL fingerprint, cấu trúc phần tử mục tiêu, form/scroll nếu liên quan); failure phải dừng nhánh phụ thuộc. URL giống nhau không đủ chứng minh state giống nhau.
5. Fixture modal/tab cùng URL phải được ghi là có thay đổi. `no_meaningful_change` không được suy ra chỉ từ URL; ảnh khác nhau cũng chưa chứng minh nghiệp vụ thành công.
6. Trong test integration, API bằng connection DB độc lập đọc được before/after đã commit khi lượt model tiếp theo còn chờ. UI hiển thị frame trong tối đa một chu kỳ polling hiện có (5 giây cộng thời gian request) sau commit trong môi trường local.
7. Draft có nguồn Vision phải sử dụng locator và thứ tự nhánh từ gói handoff đã xác minh. Không chỉ nhúng mô tả yêu cầu rồi để model tạo test độc lập; không nối các sibling thành một chuỗi hành động.
8. Refresh trang không mất trace/locator/kết quả; đổi nhánh hoạt động, ảnh thiếu/deleted/error có trạng thái kết thúc rõ; polling không reset bước người dùng đang xem.
9. Kết quả Vision nêu số proposal, thao tác thực hiện, locator verified/unresolved, nhánh explored/skipped/failed và lý do dừng. Hiển thị riêng trạng thái generation, draft, run, report cùng link; generation lỗi vẫn xem được kết quả Vision.
10. Giữ v1 `TestExecutionRequest/TestExecutionResult`, duyệt draft hiện có, tenant/project RBAC, screenshot consent và giới hạn hiện hành. Không phát sinh provider call trong fixture tests; không tự tăng budget.

## Quyết định, giả định và câu hỏi

### Confirmed revision — 2026-09-08, Phase 3 resumed

The user declined monetary cost reservations: “no, we dont need it”. Do not add per-request price configuration, monetary accounting, or a missing-price blocker. Preserve existing cost fields for compatibility without claiming dollar enforcement. Continue with cumulative model-step limits, rate limits, screenshot caps, state/hop/operation limits and the absolute session deadline. This resolves and supersedes the pricing blocker recorded below; Phase 3 is active and the full plan remains authorized.

Đã xác nhận: Vision hỗ trợ Playwright, phải có trace cho user, cần back/state, cần kết quả cuối rõ ràng.

Thiết kế đề xuất cho kế hoạch:

- Vision tiếp tục nhìn screenshot và trả target theo tọa độ chuẩn hóa. Screenshot không cung cấp DOM selector đáng tin cậy; trusted worker dùng DOM tại vùng target để tạo/kiểm chứng locator. Phần này được hiểu là bước triển khai yêu cầu locator, không thêm model hay nguồn dữ liệu bên ngoài.
- Ưu tiên role + accessible name / label / test ID, sau đó CSS attribute ổn định và duy nhất. Không suy ra accessible name chỉ từ innerText; dùng locator engine xác nhận lại.
- Giữ đồ thị khám phá và giới hạn BFS hiện có; bổ sung nhật ký theo thứ tự thực thi để user xem toàn bộ công việc, kể cả phục hồi. Đi qua một nhánh test không đồng nghĩa đi qua tất cả BFS nodes.
- Dùng browser session còn sống và checkpoint tạm trong bộ nhớ cho phiên mới. Back/đóng popup trước, replay đường đã xác minh khi cần; mọi bước phục hồi đều được ghi. Không coi ảnh, HTML hay storageState là bản sao toàn bộ browser/ứng dụng.
- v1 phạm vi là trang public theo policy hiện có, không có login/credential flow. Hỗ trợ DOM thường, open shadow root và iframe cùng origin bằng scope rõ; canvas/closed shadow/cross-origin frame không đối chiếu được được đánh dấu unsupported.
- Dữ liệu nhập phục vụ thử nghiệm giữ trong bộ nhớ phiên như hiện nay. Trace chỉ lưu nhãn che giá trị; handoff bước nhập dùng input reference chưa bind, chặn tạo test thực thi nhánh đó với lý do `input_binding_required`. Không âm thầm lưu text nhạy cảm vào gói bàn giao.
- Kết quả khám phá được tổng hợp xác định từ dữ liệu, có UI và JSON tải về; report Playwright dùng cơ chế run report hiện có.
- Giữ provider/model/runtime policy, RustFS, Google Drive và retention đang cấu hình. Không chọn chính sách production mới.

Không còn câu hỏi sản phẩm bắt buộc trước khi tạo kế hoạch. Các giới hạn trên phải hiện rõ khi triển khai, không được diễn giải thành cam kết phục hồi mọi ứng dụng hoặc test hoàn chỉnh cho mọi target.

## Bằng chứng từ source scout

| Source | Hiện trạng đã đọc | Hệ quả |
| --- | --- | --- |
| `workers/playwright/src/vision.ts` | `observeVisualTreeState` mở context mới, replay toàn bộ ancestor rồi chỉ chụp ảnh cuối; click bằng mouse coordinate. | Thiếu locator và frame cho các thao tác replay; không kiểm chứng state phục hồi. |
| `apps/control-plane/application/vision_events.py` | Hàng đợi ancestor nằm trong RAM; lưu frame theo node; suy ra no-change từ URL; handoff chỉ gửi intent. | Cần operation ledger, phân loại thay đổi và handoff có cấu trúc. |
| `apps/control-plane/infrastructure/workflows/temporal_worker.py`, `apps/control-plane/application/runs.py`, `apps/control-plane/infrastructure/persistence/session.py` | Publisher chờ processor bên trong transactional_session; commit sau toàn bộ xử lý. | Flush không đủ cho API đọc realtime. Cần transaction ngắn và claim/fencing riêng. |
| `packages/contracts/src/auto_at/contracts/vision.py` | Action chỉ có tọa độ/text; có state/frame/trajectory contract nhưng chưa có locator, restore, handoff. | Bổ sung contract có version; không thay runner v1. |
| `apps/control-plane/infrastructure/persistence/models.py`, `apps/control-plane/infrastructure/persistence/repositories.py` | Một replay frame trên mỗi state; edge proposal được finalize một lần. | Nhật ký operation và frame phải độc lập với gallery BFS cũ. |
| `apps/control-plane/application/generation_events.py`, `apps/control-plane/agents/generation/planner.py`, `packages/contracts/src/auto_at/contracts/generation.py` | Planner nhận URL/intent/hash; provenance chưa có session/handoff; output là source tự do. | Ràng buộc handoff và tạo source từ step/locator refs có kiểm chứng. |
| `apps/control-plane/agents/prompts/generation.py` | Prompt v5 yêu cầu loop qua controls, quay về target URL, source dưới 1.200 ký tự. | Dùng prompt/output riêng cho nhánh Vision; tránh constraint cũ làm mất đường đi. |
| `apps/control-plane/application/vision_replay.py`, `apps/control-plane/infrastructure/artifacts/rustfs.py` | Evidence private, checksum verification, READ theo project, tenant-admin deletion. | Tái dùng storage và quyền cho operation frames. |
| `apps/dashboard/app/vision-dashboard.tsx` | Frame refresh phụ thuộc selected; refreshSelected không fetch frames; tìm draft bằng correlation trong danh sách generation. | Cần snapshot cập nhật nhất quán và quan hệ IDs trực tiếp. |
| `apps/dashboard/app/components/vision-trajectory.tsx`, `apps/dashboard/app/components/vision-replay-model.ts` | Reset step khi snapshot đổi; sibling ngoài default path không chọn được; terminal child bị loại; lỗi ảnh thành loading vô hạn. | UI/test cần sửa hành vi thực tế, không chỉ text layout. |
| `apps/dashboard/app/runs/[id]/page.tsx`, `apps/control-plane/api/v1/routes/runs.py` | Đã có action ledger, artifacts, AI post-run review và GET run report. | Link đến kết quả hiện có thay vì tạo hệ report song song. |
| `tests/test_vision_event_processor.py`, worker `vision.spec.ts` | Chủ yếu mocks/parser; chưa chứng minh browser navigation, locator grounding hoặc DB visibility giữa phiên. | Bổ sung browser và DB integration bắt buộc. |

Kế hoạch trajectory cũ `plan/07092026211533-vision-trajectory-replay/README.md` được giữ nguyên làm lịch sử. Trạng thái completed ở đó không chứng minh các acceptance mới đã đạt.
Nhận xét trước đây rằng session 437e… “không thay đổi giao diện” chưa đủ cơ sở: classifier hiện chỉ so URL; cần đối chiếu ảnh trước/sau thật. Không sửa/backfill bằng chứng lịch sử để khớp thiết kế mới.

## Các ràng buộc pre-flight

- Kiến trúc: API chỉ HTTP; application điều phối qua domain ports; transaction/SQL/worker transport thuộc infrastructure. Prompt mới nằm trong `agents/prompts/`, cập nhật version và README.
- Execution: adapter Web UI hiện có, Playwright 1.50.1 và image v1.50.1-noble; không nâng phiên bản trong tính năng này. Contract execution v1 và giới hạn import source giữ nguyên. Test final vẫn phải được người dùng duyệt.
- Model/provider: giữ runtime đã chọn theo ADR-007 và tenant config; metadata phải ghi model/prompt thực dùng. Thiếu provider thì giữ trace và báo unavailable, không đổi model tự động.
- Dữ liệu: screenshot là private evidence có consent chuyển ảnh hiện hành; page text/attributes/locator là untrusted và có thể nhạy cảm. Chỉ descriptor đã sanitize mới được persist/hiện/chuyển planner. Nếu redaction làm đổi định danh, loại locator đó; không gọi nó là verified.
- Storage: không lưu cookies/localStorage/sessionStorage/raw DOM/typed values vào trace, report, logs hoặc handoff. State tạm hết khi session đóng/crash; không chọn thời hạn lưu credential mới.
- Retention: frame mới theo cơ chế private Vision evidence hiện có (user/admin deletion); không suy ra thời hạn từ ArtifactPolicy của run. Google Drive cleanup tuân cấu hình hiện hành: ADR-008 và runbook có đoạn mô tả không đồng nhất, cần chỉnh tài liệu theo config chứ không đổi retention.
- Quyền: mọi parent/frame/locator/handoff/request/draft/run lookup phải ràng tenant + project; correlation ID chỉ để truy vết. Giữ cookie/CSRF và quyền quyết định hiện có.
- Điều hành: deadline tính cho cả session, gồm model wait, restore và capture; giữ cost/rate/byte caps và giới hạn state/hop. Operation budget hữu hạn được suy từ state/hop hiện hành, không tăng quyền chạy.
- Retry: at-least-once delivery không đảm bảo exactly-once side effect browser. Lưu intent thao tác trước dispatch, dùng operation ID/fencing; trạng thái không biết đã chạy hay chưa phải báo unknown và không tự click lại.
- Thử nghiệm: synthetic local target và model fixtures; không thao tác target thật hay gọi provider trả phí để lập kế hoạch. Không đặt SLO production; chỉ đặt acceptance độ trễ local ở trên.

## Phases

| # | Mục tiêu | Trạng thái | Phụ thuộc | Validation |
| --- | --- | --- | --- | --- |
| 1 | Contract, operation/frame/locator/handoff persistence | completed | Scout hiện tại | Contract + repository + migration tests |
| 2 | Worker grounding locator, capture từng thao tác, back/restore | completed | 1 | 31 focused browser/contract tests passed; pinned Playwright 1.50.1 |
| 3 | Orchestration với commit theo thao tác, giới hạn và retry | completed | 1, 2 | Processor + independent DB-reader integration |
| 4 | Handoff tới generation và draft dùng locator thật | completed | 1, 3 | Planner, renderer, provenance, approval regression |
| 5 | API trace/locator/kết quả và liên kết report | completed | 1, 3, 4 | RBAC + API contracts + deletion tests |
| 6 | Dashboard live trace, branch/state và kết quả cuối | completed | 5 | UI behavior + browser integration |
| 7 | Kiểm chứng end-to-end và rollout local | completed | 1–6 | Full focused pipeline + migration compatibility |

## Rủi ro, rollout và ngoài phạm vi

### Execution progress

Current state: all seven phases are completed. Earlier dated checkpoints below are retained as history; they do not represent current blockers. The user declined monetary cost accounting/reservations/missing-price gating. The compatible fields remain metadata only; step, rate, byte, deadline and traversal limits remain enforced.

- Historical Phase 3 checkpoint (2026-09-08 21:42 +07:00; resolved by the user: no cost accounting required): `VisionPolicy.max_cost_usd` and session `max_cost_usd` are stored, but no Vision caller or shared guard accounts for monetary cost. The shared guard limits steps and per-request tokens/bytes only. Enforcing the planned cumulative dollar cap requires an approved cost reservation source; adding a new configurable reservation changes runtime policy shape. Asked whether to add an administrator-configured conservative reservation per request and block live calls when missing, or keep live calls disabled pending pricing direction. Safe independent work underway: typed transport, operation commit/capture/ACK/reconciliation, immutable RustFS storage and disposable-PostgreSQL tests. No live v4 model writer enabled; later phases remain not started until this decision is resolved.

- Phase 3 started 2026-09-08 21:34 +07:00: implement short-transaction operation orchestration, typed v4 transport, durable RustFS evidence/ACK and retry reconciliation. Existing uncommitted changes preserved. Docker daemon is currently stopped; checking local startup for required disposable PostgreSQL validation.

- Phase 2 started 2026-09-08 20:52 +07:00: resume from completed Phase 1; implement v4 worker transport, grounded locators, capture/ACK operation lifecycle and checkpoint primitives. Preserve all existing uncommitted changes. Docker is unavailable; install the browser matching the existing Playwright 1.50.1 dependency for local fixture validation.
- Phase 2 validation checkpoint 2026-09-08 21:17 +07:00: `npm.cmd run typecheck` passed; initial locator/shared-fixture suite **11 passed**. First operation suite **13 passed, 1 failed** because click resolved before popup creation was observed; fixed by arming page events before dispatch and bounding the popup wait. Operation rerun **14 passed**. Python contract/execution fixture suite **33 passed**. Expanded lifecycle/limit/HTTP checks and baseline regressions remain underway; Phase 2 remains in progress.

- Phase 1 started 2026-09-07 23:27 +07:00: additive contracts, scoped operation/frame/locator/handoff persistence, and short-transaction UoW. Current Alembic head is `f8a9b0c1d2e3`; the proposed revision is available.
- Existing uncommitted trajectory implementation and unrelated workspace edits are preserved. No new writer is enabled in this phase.
- Overall: **7/7 phases completed** at 2026-09-08 23:43 +0700. Full synthetic pipeline and isolated baseline passed. Deployment and real-provider canary remain deliberately gated; see Phase 7 completion below.
- Validation checkpoint 2026-09-07 23:45 +07:00: focused Phase 1 suite **50 passed**; `uv run ruff check .` passed; Alembic has one head `f9a0b1c2d3e4`. Full `uv run pytest -q`: **258 passed, 1 failed, 4 errors**. Four errors are Windows default pytest temp-folder access; the unrelated triage missing-key test loaded local `.env` Hugging Face settings, made one unintended provider request (HTTP 200), and failed its unavailable expectation. No new trace fixture called a provider. Remediation: rerun in a process with dotenv loading disabled, provider-key environment variables removed, outbound sockets blocked except loopback, and a fresh workspace basetemp. No provider configuration or unrelated triage test is being changed.

Browser Back không rollback dữ liệu server. Nếu không thể phục hồi invariant, dừng nhánh; không tái thử thao tác chưa biết kết quả. Screenshot cũng không lưu JS heap, listener hay toàn bộ state. Duplicate labels, overlay và hydration có thể làm locator sai; bắt buộc kiểm chứng lại ngay trước thao tác.

Rollout theo thứ tự migration additive → worker đọc protocol cũ/mới → orchestration mới → generation/API → dashboard. Ghi version phiên để session cũ tiếp tục reader cũ; drain phiên worker đang chạy trước thay process. Chưa bật writer mới khi thiếu schema/worker capability. Rollback writer về phiên legacy cho phiên mới, giữ các bảng evidence và reader tương thích; không downgrade xoá lịch sử.

Ngoài phạm vi: thay model/cloud/auth/retention, login tự động, phục hồi server DB tổng quát, canvas-to-DOM giả, healing tự động trong run đang chạy, approve test tự động, video liên tục, xuất PDF/DOCX mới, backfill locator từ ảnh lịch sử, sửa lỗi provider `generation unavailable` bằng thay cấu hình nhà cung cấp.

## Tài liệu phase

- [Phase 1 — Contract và persistence](phase-01-contracts-persistence.md)
- [Phase 2 — Worker locator và state](phase-02-worker-locators-state.md)
- [Phase 3 — Orchestration và live persistence](phase-03-orchestration-live-trace.md)
- [Phase 4 — Bàn giao cho generation](phase-04-locator-handoff-generation.md)
- [Phase 5 — API kết quả và trace](phase-05-trace-result-api.md)
- [Phase 6 — Dashboard](phase-06-dashboard-trace-results.md)
- [Phase 7 — Integration và rollout](phase-07-validation-rollout.md)

## Tham chiếu kỹ thuật

Source trong repo là cơ sở về phiên bản. Tài liệu Playwright hiện hành được dùng để đối chiếu khái niệm; mọi API phải compile/test trên 1.50.1:

- [Locators](https://playwright.dev/docs/locators): locator engine, role/label/test ID, strict matching và tái resolve.
- [Pages](https://playwright.dev/docs/pages): page/popup là đối tượng riêng, cần theo dõi khi click mở tab.
- [Authentication](https://playwright.dev/docs/auth): trạng thái auth được tái sử dụng có phạm vi lưu trữ riêng; không mặc định đó là toàn bộ state ứng dụng.


## Phase 1 implementation record - completed 2026-09-07 23:49 +07:00

Implemented versioned, bounded locator/operation/frame/checkpoint/handoff contracts and 19 Python-validated parity fixtures. Evidence requires unique target grounding and actionability; sensitive locator identities are rejected. Added four additive tables, legacy session defaults, generation linkage, immutable checkpoint invariants, conditional leases/fencing, serialized sequences, and commit-per-call UoW. Private frame writes verify size/checksum and durable read-back before metadata commit; tombstones preserve history. Handoffs validate complete branch paths, executed locator identity and immutable hashes; generation keys bind the handoff identity/hash. Runner execution v1 and human approval remain unchanged.

Validation:

- `uv run ruff check .` - passed.
- `uv run pytest tests/test_vision_contracts.py tests/test_generation_contracts.py tests/test_persistence_schema.py tests/test_vision_operation_repository.py tests/test_vision_handoff_repository.py tests/test_execution_contract_fixtures.py -q` - **53 passed**, including real PostgreSQL competing claims/prepares, independent reader visibility, fencing, immutable finalization, scope/FK rejection, frame tombstones, checkpoint/branch rules and migration upgrade.
- `uv run alembic heads` - one head, `f9a0b1c2d3e4`.
- Full Python suite in an isolated `uv run --no-sync python -` process (dotenv disabled, provider-key env removed, outbound sockets restricted to loopback, fresh `.pytest-tmp/locator-phase1-<uuid>` basetemp): **263 passed**. The final three concurrency/checkpoint/DB constraint tests were added afterward and passed in the focused 53-test rerun; the full suite was not repeated unnecessarily.
- Migration test upgraded a new UUID-named PostgreSQL database through `f8a9b0c1d2e3`, seeded legacy session/generation rows, upgraded to head and verified data and nullable/default compatibility. Tests use the disposable `vision-locator-phase1-test` container on localhost:55437; they explicitly skip if that fixture is absent. No application DB migration was performed.

Implementation details/deviations: non-indexed operation/evidence/handoff contract fields are retained in validated JSON payloads; query/reference fields have explicit columns and scoped FKs. Checkpoint metadata is a nullable JSON column on existing states, with raw browser state still memory-only. Migration downgrade refuses destructive evidence deletion, following the plan's rollback-writer policy. The private storage port is defined and tested using an immutable in-memory fixture store; the RustFS adapter and worker transport integration remain Phase 3/2 responsibilities. The existing unrestricted full-suite invocation made one unintended Hugging Face call through an unrelated triage test; its failure and the successful isolated rerun are documented above. No local provider settings or unrelated tests were changed.

Exact implementation paths (relative to `auto-at-ui/`):

- `packages/contracts/src/auto_at/contracts/vision.py`
- `packages/contracts/src/auto_at/contracts/generation.py`
- `packages/contracts/src/auto_at/contracts/__init__.py`
- `apps/control-plane/domain/entities.py`
- `apps/control-plane/domain/ports.py`
- `apps/control-plane/domain/vision.py`
- `apps/control-plane/infrastructure/persistence/models.py`
- `apps/control-plane/infrastructure/persistence/repositories.py`
- `apps/control-plane/infrastructure/persistence/vision_unit_of_work.py`
- `migrations/versions/f9a0b1c2d3e4_add_vision_locator_operations.py`
- `tests/test_vision_contracts.py`
- `tests/test_generation_contracts.py`
- `tests/test_persistence_schema.py`
- `tests/test_vision_operation_repository.py`
- `tests/test_vision_handoff_repository.py`
- `tests/vision_trace_fixtures.py`
- `packages/contracts/fixtures/vision-locator-v1/descriptor.accepted.json`
- `packages/contracts/fixtures/vision-locator-v1/descriptor.rejected-scope.json`
- `packages/contracts/fixtures/vision-locator-v1/descriptor.rejected-sensitive.json`
- `packages/contracts/fixtures/vision-locator-v1/handoff.accepted-branch.json`
- `packages/contracts/fixtures/vision-locator-v1/handoff.accepted-empty.json`
- `packages/contracts/fixtures/vision-locator-v1/handoff.rejected-hash.json`
- `packages/contracts/fixtures/vision-locator-v1/handoff.rejected-unbound-input.json`
- `packages/contracts/fixtures/vision-locator-v1/locator.accepted-redacted.json`
- `packages/contracts/fixtures/vision-locator-v1/locator.accepted-verified.json`
- `packages/contracts/fixtures/vision-locator-v1/locator.rejected-ambiguous-verified.json`
- `packages/contracts/fixtures/vision-locator-v1/locator.rejected-not-actionable.json`
- `packages/contracts/fixtures/vision-locator-v1/locator.rejected-wrong-target.json`
- `packages/contracts/fixtures/vision-locator-v1/operation.accepted-prepared.json`
- `packages/contracts/fixtures/vision-locator-v1/operation.accepted-unknown.json`
- `packages/contracts/fixtures/vision-locator-v1/operation.rejected-executing-no-before.json`
- `packages/contracts/fixtures/vision-locator-v1/operation.rejected-missing-reason.json`
- `packages/contracts/fixtures/vision-locator-v1/operation.rejected-stop.json`
- `packages/contracts/fixtures/vision-locator-v1/worker.accepted-v4.json`
- `packages/contracts/fixtures/vision-locator-v1/worker.rejected-missing-scope.json`

Canonical documentation updated: this README and `phase-01-contracts-persistence.md`. Next: Phase 2 browser locator grounding, per-operation capture, and checkpoint restoration. No new writer or browser feature is enabled by Phase 1 alone.

Validation cleanup: the owned disposable PostgreSQL container was stopped and automatically removed after the checks. `git diff --check` passed for modified tracked Phase 1 source/test files.


## Phase 2 implementation record - completed 2026-09-08 21:29 +07:00

Implemented the opt-in v4 browser worker with Python-owned transport schemas and generated TypeScript types/validation schemas. The existing 19 locator fixtures and nine new transport fixtures exercise both Python and worker validation. Legacy v1/v3 readers remain available; an active or closed v4 identity cannot fall back to legacy worker routes.

The worker opens on a blank page, records each setup/explore/restore/replay primitive in chronological order, and stages actual before bytes before accepting execute. Execute requires the prepared handle and acknowledgement of the exact persisted before frame ID/checksum. Results, private frame reads and ACK cleanup support lost-response reconciliation without repeating an action. Scoped identities, strict payload/UUID checks, fencing, per-session serialization, deadlines, screenshot/state/hop caps and the derived finite operation budget are enforced. Expiry destroys browser RAM while keeping safe operation results; unknown browser outcomes block dependent work.

Locator candidates are verified against the exact hit-tested interactive element using Playwright's role/name, label, test ID and stable CSS engines. Same-origin iframe coordinate conversion and open-shadow scopes are explicit. Ambiguous, sensitive, unsupported, covered, disabled and stale/replaced targets remain unresolved or rejected. Input uses append semantics, including end-of-content positioning; values stay in RAM and are omitted from result/checkpoint JSON. Bounded settling observes semantic changes independently from URL and image changes. Dialogs, downloads, denied popups and failed capture have explicit outcomes. Popup closure captures the popup before and its original parent after. Back/replay primitives compare URL, semantic, scroll and form invariants; a failed final restore blocks siblings. Replay requires the original completed, replayable action/locator, and cannot replay unknown outcomes or arbitrary button/type side effects.

Validation evidence:

- `npm.cmd run typecheck` (worker directory) - passed, including the final append-key change.
- `npm.cmd test -- src/vision.spec.ts src/vision-locators.spec.ts src/vision-operations.spec.ts --workers=1` - **31 passed** on local Chromium 133.0.6943.16, Playwright browser build 1155, matching Playwright **1.50.1**. Covers root -> A -> verified back -> B, popup close, same-URL modal/no-op, scoped grounding, failed restoration, stale hydration, before ACK, duplicate execution, lost browser result, capture failures, deadline/bytes/state budget, live form invariants, settle timeout, denied origins, dialog/download and HTTP identity/payload checks. No model/provider is involved.
- `npm.cmd test -- --workers=1` - **49 passed, 1 skipped**. The existing generated-source bundled-image browser test requires `/ms-playwright` and was skipped on Windows; the new browser fixture tests actually ran locally. Execution v1 contract, source preflight and observability regression tests passed.
- Final targeted `npm.cmd test -- src/vision-operations.spec.ts --grep 'input appends|state/hop' --workers=1` - **2 passed** after adding explicit hop-cap coverage and changing append positioning to `ControlOrMeta+End`. The preceding full worker suite was not unnecessarily repeated.
- `uv run pytest tests/test_vision_worker_contracts.py tests/test_vision_contracts.py tests/test_execution_contract_fixtures.py -q` - **33 passed**.
- `uv run ruff check .` - passed. `uv run python packages/contracts/export_vision_worker.py --check` - passed. Scoped `git diff --check` - passed.
- Broader Python baseline in an isolated `uv run --no-sync python -` process: dotenv loading disabled, provider-key environment removed, outbound Python sockets/DNS restricted to loopback, `PGCONNECT_TIMEOUT=2`, fresh `.pytest-tmp/locator-phase2-<uuid>` basetemp. **253 passed, 22 skipped, 1 failed**. Failure: existing `tests/test_operations_routes.py::test_operations_summary_is_authorized_and_returns_every_dashboard_count` returns HTTP 500 because its PostgreSQL dependency is unavailable. Docker's daemon is unavailable and a direct TCP probe confirmed localhost:5432 is not accepting connections. Six existing application-DB tests were explicitly skipped by the temporary invocation plugin; 13 Phase 1 disposable-DB tests and three Compose tests skipped through their existing availability guards. No test source, application DB, provider settings or verdict was changed to hide this limitation. The first baseline attempt was stopped after 37 tests when the catalog DB test waited on the absent database; the bounded rerun above supplies the recorded results. Database/Compose baseline revalidation remains a Phase 3/7 environment prerequisite, not a claim that the full suite passed.

Deviations and implementation details:

- Added `vision_worker.py`, a generator and generated schema/types in Phase 2 because Phase 1's generic command envelope did not define open/prepare/execute/ACK payload details. This implements the planned private v4 transport; execution v1 remains unchanged. Added a dedicated HTTP helper to keep worker lifecycle/transport concerns separate.
- Added an authenticated frame-byte GET under the operation route so the control plane can verify/persist evidence without receiving a filesystem path. Result metadata is also a Python-owned shared contract.
- Restoration stays primitive-by-primitive. There is no hidden full-path replay endpoint and no general server/application rollback guarantee. The Phase 3 orchestrator must read a checkpoint after a tentative back, trace any replay fallback, and assert the final restored checkpoint before exploring a sibling.
- ACK evidence before closing a session: unacknowledged staging bytes survive close, but browser/runtime state and HTTP access to the closed session do not. Staging cleanup only removes the exact validated operation directory after matching frame ACKs. Restart reconciliation and durable before commits belong to Phase 3.
- Used the matching local browser because Docker is unavailable. The standard Playwright install initially timed out on one CDN and succeeded via its fallback. Its automatic cache GC also removed the previously cached `chromium-1234` and `chromium_headless_shell-1234` directories; these are not repository dependencies. The worker README documents `PLAYWRIGHT_SKIP_BROWSER_GC=1` for subsequent installs. No Playwright package or image pin changed.

Exact changed implementation paths (relative to `auto-at-ui/`):

- `workers/playwright/README.md`
- `workers/playwright/src/server.ts`
- `workers/playwright/src/vision.ts`
- `workers/playwright/src/vision.spec.ts`
- `workers/playwright/src/vision-contract.ts`
- `workers/playwright/src/vision-contract.generated.ts`
- `workers/playwright/src/vision-locators.ts`
- `workers/playwright/src/vision-locators.spec.ts`
- `workers/playwright/src/vision-checkpoints.ts`
- `workers/playwright/src/vision-operations.ts`
- `workers/playwright/src/vision-operations.spec.ts`
- `workers/playwright/src/vision-http.ts`
- `workers/playwright/src/fixtures/vision-target.ts`
- `packages/contracts/src/auto_at/contracts/vision_worker.py`
- `packages/contracts/export_vision_worker.py`
- `tests/test_vision_worker_contracts.py`
- `packages/contracts/fixtures/vision-worker-v4/open.accepted.json`
- `packages/contracts/fixtures/vision-worker-v4/open.rejected-traversal.json`
- `packages/contracts/fixtures/vision-worker-v4/prepare.accepted.json`
- `packages/contracts/fixtures/vision-worker-v4/prepare.rejected-stop.json`
- `packages/contracts/fixtures/vision-worker-v4/prepare.rejected-replay.json`
- `packages/contracts/fixtures/vision-worker-v4/execute.accepted.json`
- `packages/contracts/fixtures/vision-worker-v4/execute.rejected-no-ack.json`
- `packages/contracts/fixtures/vision-worker-v4/ack.accepted.json`
- `packages/contracts/fixtures/vision-worker-v4/ack.rejected-frames.json`

Canonical documents updated: this plan README and `phase-02-worker-locators-state.md`. Existing uncommitted Phase 1, trajectory and unrelated workspace changes are preserved. Next: Phase 3 short-transaction orchestration, durable frame commit/ACK integration and independent DB-reader validation. The feature is not yet enabled end to end; phases 3-7 remain not started.

## Phase 3 implementation checkpoint — 2026-09-08 21:47 +07:00

Status: **in progress, awaiting a material runtime-policy decision**. Phase 3 is not complete; phases 4–7 have not started.

Implemented and independently validated the operation foundation:
- Typed bounded HTTP transport for v4 open/prepare/execute/read/frame/checkpoint/ACK/close, private identity headers, response identity checks, frame signatures/checksums/byte caps, and safe transport failures.
- Persist operation intent before prepare, persist verified before bytes before execute, commit executing before dispatch, persist final evidence before ACK, and read the same operation after a lost execute response. Unknown operations block subsequent work. Duplicate final delivery retries ACK only. Per-call deadline handling renews the lease during pending async work.
- Conditional S3 create-only operation-frame writes using IfNoneMatch, bounded checksum/type-verified read-back, closed response bodies, and operation-frame deletion.
- Permit a worker rejection after persisted dispatch intent (executing does not prove an action occurred). Retain unresolved locator evidence on prepared/rejected operations while still requiring verified grounding for executing/completed target actions.

Exact implementation paths changed in this session (relative to auto-at-ui/):
- apps/control-plane/application/vision_operations.py (new)
- apps/control-plane/infrastructure/vision_worker.py (new)
- apps/control-plane/infrastructure/artifacts/rustfs.py
- apps/control-plane/domain/ports.py
- apps/control-plane/domain/vision.py
- apps/control-plane/infrastructure/persistence/repositories.py
- tests/test_vision_live_persistence.py (new)
- tests/test_vision_operation_transport.py (new; focused adapter tests split from the planned integration file)

Validation:
- `uv run ruff check .` — passed after final changes.
- `uv run pytest tests/test_vision_live_persistence.py tests/test_vision_operation_transport.py -q` — **19 passed**, including 10 actual disposable-PostgreSQL tests and 9 synthetic HTTP/S3 checks. An independent DB connection sees executing + before before dispatch and completed + both frames while the next fixture model coroutine waits. Covers lost response, browser loss, redelivery, upload/capture failures, policy disable, deadlines, operation caps, mismatched identity and failed ACK.
- `uv run pytest tests/test_vision_live_persistence.py tests/test_vision_operation_transport.py tests/test_vision_operation_repository.py tests/test_vision_handoff_repository.py tests/test_vision_event_processor.py tests/test_vision_progress.py tests/test_outbox_publishing.py tests/test_transaction_boundary.py tests/test_vision_replay.py tests/test_rustfs_artifacts.py tests/test_execution_contract_fixtures.py -q` — **69 passed, 1 setup error** at the existing Windows default pytest temp directory. Reran `uv run pytest tests/test_vision_event_processor.py --basetemp <fresh .pytest-tmp/locator-phase3-UUID> -q` — **3 passed**. The two final unknown-dependency/ACK tests were added afterward and are included in the 19-test rerun above.
- `uv run python packages/contracts/export_vision_worker.py --check` — passed.
- `uv run alembic heads` — one head, f9a0b1c2d3e4. The existing migration regression ran against a disposable database in the focused selection.
- Scoped `git diff --check` — passed.
- Full Python, browser and dashboard suites were not rerun for this partial checkpoint; the full plan's final validation remains outstanding. No provider/model/Drive calls were made by the fixture tests.

Environment: started the existing local Docker Desktop daemon after confirming it was stopped. Docker's existing restart policies also restarted pre-existing local containers. Created only the owned postgres:17-alpine container vision-locator-phase3-test on 127.0.0.1:55437, with UUID-named disposable databases; no application database migration or deployment was performed. The owned test container was stopped and auto-removed after validation; the pre-existing local services were left running.

Decision needed: the current VisionPolicy and session record expose max_cost_usd, but neither Vision executor nor shared AgentStepGuard implements dollar accounting. Add an explicit administrator-configured conservative per-request reservation and fail closed when absent, or leave live calls disabled pending a pricing source? This changes runtime-policy shape and cannot be silently inferred from a stored dollar limit. No cost/model/provider policy has been changed.

Remaining Phase 3 work: publisher separation and session running/final commits; graph/proposal/checkpoint persistence and BFS restoration integration; atomic operation/frame/state/edge/activity commits; closed progress stages; cumulative model guards and approved cost reservation; centralized batch prompt correction/versioning; full startup takeover reconciliation including evidence under an older fence; cancellation/failure finalization of queued edges; processor/independent-reader tests through the actual publisher wiring. The tested operation service is not yet wired into VisionEventProcessor or temporal_worker. No new v4 writer is enabled. Current reconciliation covers same-owner lost responses and fails closed on worker loss; it does not yet implement recovery of an expired owner's completed evidence.

Canonical documentation: this checkpoint is recorded in both README.md and phase-03-orchestration-live-trace.md. Overall progress remains **2/7 completed**; no later dependency is unlocked.

## Phase 3 completion ? 2026-09-08 22:28 +07:00

Status: **completed**. This record supersedes the historical partial checkpoint and its resolved pricing question.

Implemented the v4 publisher outside the outbox transaction, fenced session lifecycle, durable operation/frame/locator/checkpoint/state/edge/activity commits, independent BFS branches and traced checkpoint restoration/replay. Recovery reads an expired owner's final evidence without dispatching another action; lost browser state ends unavailable with preserved evidence. Cancellation, provider failure and failed restoration finalize pending proposals. Cumulative model steps, live consent/policy checks, rate/byte/traversal caps and the absolute deadline remain enforced. The centralized batch prompt is version v3. Cost accounting was omitted as the user requested.

Validation:
- Focused Python regression command selecting test_vision_event_processor, test_vision_progress, test_vision_executor, test_outbox_publishing, test_transaction_boundary, test_vision_live_persistence, test_vision_replay, test_vision_operation_repository, test_vision_handoff_repository and test_vision_operation_transport with a fresh workspace basetemp: **99 passed**.
- After adding the restore-failure activity emission: `uv run pytest tests/test_vision_live_persistence.py -k 'publisher_browser and restore_failed' -q --tb=short`: **1 passed**.
- `uv run ruff check .`: passed.
- Worker `npm.cmd run typecheck`: passed; `npm.cmd test -- src/vision.spec.ts src/vision-locators.spec.ts src/vision-operations.spec.ts --workers=1`: **31 passed**.
- Five real Chromium/PostgreSQL publisher cases cover A/B branching, same-URL modal/replay, failed restoration, cancellation and model failure. A separate DB reader sees committed frames while the next fixture model waits. Two takeover cases cover retained/lost worker evidence. No model/provider/Drive calls were made.

Exact Phase 3 paths (relative to auto-at-ui):
- apps/control-plane/application/vision_operations.py
- apps/control-plane/application/vision_trace_events.py
- apps/control-plane/application/vision_events.py
- apps/control-plane/application/runs.py
- apps/control-plane/domain/ports.py
- apps/control-plane/domain/vision.py
- apps/control-plane/domain/activity.py
- apps/control-plane/infrastructure/vision_worker.py
- apps/control-plane/infrastructure/artifacts/rustfs.py
- apps/control-plane/infrastructure/persistence/vision_unit_of_work.py
- apps/control-plane/infrastructure/persistence/repositories.py
- apps/control-plane/infrastructure/workflows/vision_publisher.py
- apps/control-plane/infrastructure/workflows/temporal_worker.py
- apps/control-plane/agents/vision/executor.py
- apps/control-plane/agents/prompts/vision.py
- apps/control-plane/agents/prompts/README.md
- workers/playwright/src/vision-checkpoints.ts
- workers/playwright/src/vision-locators.ts
- workers/playwright/src/vision-operations.ts
- workers/playwright/src/fixtures/vision-integration-server.ts
- tests/test_vision_live_persistence.py
- tests/test_vision_operation_transport.py
- tests/test_vision_executor.py
- tests/test_vision_progress.py
- tests/test_outbox_publishing.py

Deviations: separate v4 processor/publisher modules preserve legacy behavior and transaction ownership. The operation cap matches Phase 2's bounded restoration budget, 1 + max_states * (2 * max_hops + 3). Real HTTP testing exposed tsx-injected function-name helpers inside page.evaluate; object methods fix the serialization issue. Replay checkpoint references are scoped to the destination checkpoint, which may differ from the original proposal's source state. Navigation starts a new branch ancestry. No v4 submission writer is enabled yet; rollout remains Phase 7.

The owned disposable PostgreSQL container is running for subsequent plan validation. UUID databases are removed by fixtures; application databases were not migrated. Full Python/dashboard/Compose validation remains Phase 7. Phase 4 is unlocked.

## Phase 4 completion ? 2026-09-08 22:46 +07:00

Status: **completed**. Built immutable root-to-leaf handoffs from committed operations. Siblings remain separate; restoration is excluded from business paths. Unknown/failed actions and unbound typed inputs have blocked reasons. More than 50 branches rejects the whole handoff with a recorded limit reason, without silently truncating coverage.

Generation submission resolves the handoff in tenant/project scope, binds idempotency to its hash and checks the original target. Session completion, handoff, accepted generation request and outbox commit together; a rejected generation request preserves the bundle. A separate centralized v1 prompt selects branch/assertion IDs only. The deterministic renderer validates ancestry and evidence, emits role/label/test-ID/CSS scopes with JSON escaping, bounded scroll/wait, popup handling and separate tests. All ready branches are required in order. Visibility/actionability assertions are explicitly pre-action observations, not business-success claims. Draft provenance contains source session/handoff/hash, selected branches and operation refs.

Validation:
- Focused Phase 4 suite (handoff, renderer, generation contracts/planner/event/preflight, execution v1 fixtures, live persistence, handoff repository, progress), fresh workspace basetemp: **87 passed**.
- Final scoped submission/target/idempotency test: **1 passed**.
- Final browser publisher -> immutable handoff -> structured model fixture -> deterministic source -> pending-review draft after target/provenance checks: **1 passed**.
- `uv run ruff check .`: passed.
- Renderer suite includes loading two escaped test paths with the installed Playwright 1.50.1 CLI. Extended real-browser integration verifies same-URL modal branches and generation failure retaining the identical trace/bundle. No real provider calls.

Exact changed paths:
- apps/control-plane/application/vision_handoff.py (new)
- apps/control-plane/application/vision_source_renderer.py (new)
- apps/control-plane/application/vision_trace_events.py
- apps/control-plane/application/generation.py
- apps/control-plane/application/generation_events.py
- apps/control-plane/agents/generation/vision_plan.py (new)
- apps/control-plane/agents/prompts/vision_generation.py (new)
- apps/control-plane/agents/prompts/README.md
- apps/control-plane/domain/ports.py
- apps/control-plane/domain/activity.py
- apps/control-plane/infrastructure/persistence/vision_unit_of_work.py
- apps/control-plane/infrastructure/persistence/repositories.py
- packages/contracts/src/auto_at/contracts/generation.py
- tests/test_vision_handoff.py (new)
- tests/test_vision_source_renderer.py (new)
- tests/test_vision_handoff_repository.py
- tests/test_vision_live_persistence.py
- tests/test_generation_preflight.py

Deviations: existing generation repository injection supplies the scoped handoff reader, so Temporal wiring and the legacy planner/prompt require no changes. Handoff stores immutable locator references; renderer resolves their already-immutable descriptors. Blocked branches may retain failed operations, while ready branches still require completed grounded operations. A Vision preflight failure preserves pending review and raises a safe error instead of invoking the legacy freeform repair path, which would discard grounding. The first extended integration run hit a missing UUID import in test code (3 failed, 3 passed); the import was fixed and the 87-test suite passed. Production rollout and full baseline validation remain Phase 7. Phase 5 is unlocked.

## Phase 5 completion ? 2026-09-08 22:58 +07:00

Status: **completed**. Added authorized trace pagination, locator catalog, private operation-frame reads/deletions and deterministic result/JSON export endpoints. Reads use repeatable-read snapshots; a changed trace revision rejects continued pagination so clients can restart. Frame metadata includes retained/deleted/missing states and never storage keys. Byte reads verify size/checksum. Deletion is byte-first, retains tombstones, and commits failure audits and prior successful deletions for retry.

Results separate exploration, handoff, generation, draft, run and report states through explicit scoped references. Queued report events remain pending; terminal runs without reports are unavailable. Legacy sessions are labeled evidence-only and use only the exact scoped legacy generation key, never ambiguous correlation lookup. Generation responses expose the optional handoff ID; draft provenance already exposes the validated Phase 4 source.

Validation:
- `uv run pytest tests/test_vision_results.py tests/test_vision_routes.py tests/test_vision_replay.py tests/test_dashboard_route_contracts.py --basetemp <fresh workspace directory> -q --tb=short`: **47 passed**.
- Final result suite after adding queued-report handling: **14 passed**.
- Existing `tests/test_reporting_routes.py` against a UUID disposable PostgreSQL schema with dotenv disabled and process-local DATABASE_URL: **1 passed**. Initial isolated runner omitted the contracts import path and exited before creating a database; corrected invocation passed.
- `uv run ruff check .`: passed.
- Tests cover independent append/revision changes, service/foreign-project/foreign-tenant denial, project-reader deletion denial, corrupted/missing/deleted frame responses, deletion failure audit retention, exports, legacy evidence, exact draft/run/report links and missing/failed/pending reports. No provider calls.

Exact changed paths:
- apps/control-plane/application/vision_results.py (new)
- apps/control-plane/api/v1/routes/vision.py
- apps/control-plane/api/v1/routes/generation.py
- apps/control-plane/infrastructure/persistence/repositories.py
- tests/test_vision_results.py (new)
- tests/test_dashboard_route_contracts.py

Deviations: reused the existing replay authorization boundary and verified operation store without changing their legacy behavior. New reads are application methods with repository adapters; no domain or transport rewrite was needed. The export is JSON metadata only, without screenshot bytes or signed URLs. Real object absence is reported when the selected frame is fetched; metadata reads do not issue storage requests for every retained frame. Phase 6 is unlocked.

## Phase 6 completion ? 2026-09-08 23:25 +07:00

Status: **completed**. Selected-session results precede collapsed creation/settings. Added the chronological operation ledger, immutable branch navigation, before/after frames with independent error states, locator catalog, safe JSON export and explicit downstream links. Stable operation IDs survive polling; follow mode is optional. Deep links, stale-response guards, abortable image requests, object URL cleanup, terminal progress cleanup and conditional downstream polling are implemented. Legacy sibling selection now rebuilds the path with cycle guards; historical frame selection says ?View this frame?. Keyboard navigation is confined to the focused trace and ignores form controls.

Validation: dashboard typecheck passed; dashboard unit/API tests **27 passed**; three intercepted-API Chromium dashboard scenarios **3 passed** (13.4s), including delayed session switches, image 404 with retained before image, polling/follow/keyboard, deep links and the legacy seven-frame/six-sibling case. Worker typecheck passed with the browser fixture. Production `npm.cmd run build` passed with all nine pages generated; existing workspace-root and ESLint-plugin configuration warnings remain. The first build found two unused variables; fixed the legacy compatibility argument and wired independent frame error copy, then rebuilt successfully. No provider calls.

Changed paths: `apps/dashboard/app/{vision-dashboard.tsx,generation-api.ts,generation-api.test.ts,generation-types.ts,generation-dashboard.tsx,globals.css}`; `apps/dashboard/app/components/{vision-operation-ledger.tsx,vision-operation-model.ts,vision-operation-model.test.ts,vision-locator-catalog.tsx,vision-result-summary.tsx,vision-session-detail.tsx,vision-trajectory.tsx,vision-replay-model.ts,vision-replay-model.test.ts,vision-progress-timeline.tsx,vision-progress-timeline-model.ts,fixtures/vision-trajectory.ts}`; `workers/playwright/src/vision-dashboard.spec.ts`.

Deviations: no React test dependency was added; behavior is covered by existing Node tests and actual Chromium. Polling uses revision-aware metadata requests and fetches only selected frame bytes. The new session-detail component isolates request ownership. Phase 7 is unlocked; production deployment and real-provider canary have not run.

## Phase 7 completion ? 2026-09-08 23:43 +0700

Status: **completed**. The full synthetic chain now verifies a fake Vision selection against the actual pinned browser, reads before/after commits through the authorized API while exploration is still running, persists the immutable handoff and grounded draft, explicitly approves through the API, executes its source with Playwright 1.50.1, and persists a fixture-model report. Scoped result links agree on session ? handoff ? request ? draft ? run ? report. Duplicate event delivery performs no extra target visits; repeated approval creates no second run. The test found and fixed an existing duplicate-decision response bug (two values returned where the route requires three); the same immutable decision now returns the same run successfully. Deterministic verdicts were not changed.

New-session writer rollout is controlled by `VISION_TRACE_V4_ENABLED=false` by default. Enabling it binds v4 and its prompt version at acceptance. Turning it off affects only new submissions; idempotent resubmission preserves the prior version. Additive migration tests retain legacy records, and rollback tests preserve v4 frame tombstones. The runbook documents schema/worker ordering, draining, evidence-preserving rollback, user-visible results, input/target limitations and safe diagnostics. Its provider-image retention description now matches ADR-008 and the existing default (Drive deletion disabled); actual retention, provider and consent settings were not changed. Monetary cost accounting/reservations/missing-price gating remain excluded per the user's correction.

Validation:
- Focused pipeline and migration suite: `uv run pytest tests/test_vision_locator_pipeline.py tests/test_vision_migration_compatibility.py -q --tb=short --show-capture=no --basetemp .pytest-tmp/locator-pipeline-3`: **3 passed** (30.50s).
- Full Python baseline: `uv run python .pytest-tmp/run_isolated_locator_baseline.py`: **354 passed, 3 skipped** (146.56s). This fresh process disabled dotenv, removed provider credentials, blocked non-loopback Python sockets/DNS, used an owned UUID PostgreSQL database, and supplied a fresh workspace basetemp. The three configured-stack Compose tests were explicitly skipped because that existing deployment is not fixture-isolated and its workflow can trigger configured providers. They are not claimed as passing. The initial runner script had an unmatched parenthesis and exited before database creation; the corrected invocation above passed.
- Worker `npm.cmd run typecheck`: passed. `npm.cmd test -- --workers=2`, with `VISION_DASHBOARD_URL=http://127.0.0.1:7317` pointing at the production dashboard build: **52 passed, 1 skipped** (49.7s). The one skipped test requires the Docker image's `/ms-playwright`; actual local generated-source execution was independently exercised by the Python pipeline. All three dashboard Chromium scenarios passed.
- Dashboard `npm.cmd run typecheck`, `npm.cmd test`: passed, **27 tests**. Phase 6's production `npm.cmd run build` passed and that build served the final browser suite. Existing workspace-root/ESLint-plugin and Node module-type warnings remain.
- `uv run ruff check .`: passed. `uv run python packages/contracts/export_vision_worker.py --check`: passed. `uv run alembic heads`: one head, **f9a0b1c2d3e4**. `git diff --check`: passed (existing LF/CRLF notices only).
- Aggregate fixture output saved at `benchmark/vision/v2/validation.json`: grounded locators **2/2**, wrong targets **0**, retained operation frames **10/10**, missing reasons **none**, verified restores **1**, restore failures **0**, eligible branches **2/2**, deterministic rerun **passed**, duplicate physical actions **0**. Authorized API read after the known commit took **0.032365s** in the final baseline. This is a local API read measurement, not provider latency or a production SLO.

Exact Phase 7 changed paths:
- apps/control-plane/config.py
- apps/control-plane/application/vision.py
- apps/control-plane/application/generation.py
- apps/control-plane/api/v1/routes/vision.py
- apps/control-plane/benchmark/vision.py
- workers/playwright/src/fixtures/vision-integration-server.ts
- tests/test_vision_live_persistence.py
- tests/test_vision_locator_pipeline.py (new)
- tests/test_vision_migration_compatibility.py (new)
- tests/test_vision_benchmark.py
- tests/test_playwright_worker_compose.py (isolation documentation only; existing verdict checks unchanged)
- benchmark/vision/v2/manifest.json (new)
- benchmark/vision/v2/validation.json (new)
- docs/vision-agent-operations.md
- docs/architecture.md
- README.md
- plan/07092026231342-vision-playwright-locator-trace/README.md and phase progress records

Deviations and remaining deployment boundary: no application database was migrated, no application deployment was restarted, and no real-provider/Drive or production-target canary was run. The local rollout deliverable is the tested writer gate plus the documented deployment sequence; a deployed-v4 Compose acceptance result is not claimed. The worker fixture bridges the existing Windows browser cache through an owned test junction; production execution code is unchanged. Fixture reports use the actual recorded run verdict and metadata with an injected model, without remote artifact/provider delivery. The owned dashboard server and disposable PostgreSQL container have been stopped; UUID test databases and worker temp roots were removed by fixtures. Existing user modifications remain uncommitted and preserved.

Overall: **7/7 phases completed**. No implementation phase remains. Deliberately gated follow-up: deployment/schema upgrade and an authorized real-target/provider canary.

Final housekeeping: the exact isolated baseline runner was archived as `.pytest-tmp/run_isolated_locator_baseline.txt` after execution. A final Ruff invocation initially included that temporary script and reported style issues; archiving it outside Python source discovery restores the clean source check. The original validation script and aggregate JSON remain available for review. The disposable PostgreSQL container used auto-removal on stop.
