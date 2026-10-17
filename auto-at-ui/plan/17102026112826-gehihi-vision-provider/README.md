# Gehihi Vision provider trên dashboard

Ngày lập: 17/10/2026 (Asia/Saigon). Trạng thái: **completed — 5/5 phases; offline validated, live canary not run**.

## Mục tiêu và quyết định đã chốt

Thêm Google Gemini Vision với tên hiển thị **Gehihi**, model `gemini-3.8-flash`, để tenant admin chọn trên dashboard. Nhánh Gehihi nhận screenshot trực tiếp; không cần Google Drive để chuyển ảnh. Người dùng đã xác nhận provider và dashboard trong hội thoại. Đây là kế hoạch, không phải xác nhận hệ thống đã chạy thành công với API thật.

- UI dùng “Gehihi (Google Gemini)” tại phần cấu hình và consent để rõ bên nhận dữ liệu. ID kỹ thuật là `gemini`; không đổi tên model/API/env thành “gehihi”.
- Giữ Hugging Face và cấu hình tenant hiện có; không tự đổi provider, model hoặc bật Vision.
- Mỗi session giữ provider/model lúc tạo. Đổi cấu hình không được chuyển screenshot của session đang chạy sang provider mới.
- Scope gồm legacy và v4. Không đổi mặc định `vision_trace_v4_enabled`, không chuyển lịch sử sang v4.
- Dùng HTTP OpenAI-compatible của Google qua `httpx` đã có; không thêm SDK hoặc provider cho các text agent.
- Demo nhắm free tier, chỉ dữ liệu synthetic/local được phép gửi. Không bật billing, tự fallback, tự chọn model khác hoặc gọi API thật trong lúc lập plan.
- Không thêm monetary reservation/accounting. `max_cost_usd` vẫn là metadata tương thích như runbook hiện tại; giới hạn thực tế gồm request rate, bước, byte, token và thời gian. Free tier của tài khoản cần kiểm tra trước demo; metadata không bảo đảm chi phí bằng 0.

Không còn câu hỏi sản phẩm chặn triển khai. API key, quota tài khoản và URL demo an toàn là điều kiện vận hành cho canary, không phải lý do chặn coding/tests offline.

## Tiêu chí nghiệm thu

1. Tenant admin chọn Gehihi/model đã chốt, xác nhận gửi ảnh đến Google và lưu; tải lại trang vẫn đúng. Tenant khác không nhận cấu hình đó; người không có `MANAGE_TENANT` không sửa được.
2. Thiếu key vẫn khởi động ứng dụng được; dashboard báo chưa cấu hình. Không cho bật provider thiếu key; nếu key mất sau khi bật, session dừng bằng mã lỗi an toàn.
3. Mock HTTP chứng minh đúng endpoint/model, ảnh inline, không upload Drive hoặc dùng key Hugging Face. Hugging Face tiếp tục đi qua transport ảnh cũ.
4. Fixture browser có button và phần tử tương tác không phải button: sau navigate, response hợp lệ tạo candidate và thực hiện ít nhất một thao tác tiếp theo; before/after, proposal, replay vẫn liên kết. Đây là kiểm chứng integration, không phải tuyên bố chất lượng model thật.
5. Thiếu consent, đổi provider khi chạy, lỗi auth/quota/timeout, JSON sai, tọa độ sai đều dừng an toàn; giữ trace dở dang, không tự retry thao tác có kết quả chưa biết, không báo đã kiểm tra hết.
6. Dashboard dùng policy đã lưu để xác nhận lần chạy; thay đổi chưa lưu không làm sai bên nhận ảnh. Server từ chối xác nhận stale trước khi tạo session mới.
7. Không đổi `TestExecutionRequest/TestExecutionResult` v1, worker v4, quy trình duyệt draft hoặc verdict deterministic. Vision thành công không che lỗi bước sinh draft dùng text provider riêng.
8. Các kiểm thử bắt buộc ở từng phase chạy thật; ghi rõ skip vì thiếu PostgreSQL/browser fixture. Không tính skip là pass.

## Source scout: hiện trạng đã xác minh

| Đường dẫn | Bằng chứng và hệ quả |
| --- | --- |
| `apps/control-plane/config.py`, `pyproject.toml`, `uv.lock` | Settings tập trung env; có httpx, không cần dependency mới. Vision mặc định tắt/Hugging Face. |
| `apps/control-plane/agents/shared/runtime.py` | `VisionPolicy` chỉ cho Hugging Face; tenant override nằm trong `agent.runtime.v1`, extra fields bị cấm. Consent hiện chỉ là boolean. |
| `apps/control-plane/agents/shared/openrouter.py` | Có HTTP adapter OpenAI-compatible; `create_vision_language_model` chỉ hỗ trợ Hugging Face. General text factory là luồng riêng. |
| `apps/control-plane/agents/vision/executor.py` | Đã nhận ảnh inline khi không truyền image_url; validate candidate batch chặt, gọi một lần. Có metadata lỗi HTTP nhưng tầng orchestration còn mất chi tiết. |
| `apps/control-plane/infrastructure/workflows/vision_publisher.py` | `VisionModelBatch` v4 luôn tạo Google Drive store trước model call. |
| `apps/control-plane/application/vision_events.py`, `infrastructure/workflows/temporal_worker.py` trong control-plane | Legacy cũng dùng Drive trực tiếp; composition root là temporal_worker. Cần inject cùng transport với v4. |
| `apps/control-plane/application/vision_trace_events.py`, `infrastructure/persistence/vision_unit_of_work.py` | v4 có lease, short transaction, kiểm tra policy giữa các bước; lỗi model thường kết thúc bằng model_unavailable. |
| `apps/control-plane/application/vision.py` | Submit snapshot provider/model, guard và idempotency; prompt version lúc queued còn hard-code cũ. |
| `apps/control-plane/api/v1/routes/vision.py` | Có GET/PUT policy và POST explorations; PUT cần MANAGE_TENANT. Policy route còn chứa persistence orchestration; thay đổi mới phải đưa vào use case. |
| `apps/dashboard/app/vision-dashboard.tsx` | Provider/model chỉ đọc, consent hard-code Hugging Face; cùng state cho form và policy thực thi. |
| `apps/dashboard/app/components/vision-result-summary.tsx` | Thông báo lỗi chủ yếu generic, chỉ một số mã được dịch. |
| `apps/control-plane/agents/generation/vision_plan.py` | Sinh draft dùng general model riêng; thêm Vision provider không chuyển bước này. |
| `tests/test_vision_live_persistence.py`, `tests/vision_trace_fixtures.py` | Có test durable v4 bằng database fixture riêng tại 127.0.0.1:55437. |
| `workers/playwright/src/vision-dashboard.spec.ts` | Browser test dashboard có API fixture, cần VISION_DASHBOARD_URL. |

Các đường dẫn rút gọn ở cột đầu với “trong control-plane” có tiền tố đầy đủ `apps/control-plane/`. File mới được đánh dấu rõ trong từng phase; bảng này chỉ ghi hiện trạng.

## Thiết kế và ranh giới

Luồng dự kiến: dashboard đọc catalogue + saved policy → admin lưu consent gắn provider → submit kèm expected provider/model → server tạo snapshot → worker kiểm tra policy hiện hành → dispatch ảnh theo provider → executor validate JSON → worker deterministic thực hiện → lưu trace → đề xuất draft theo approval hiện có.

- **Data classification:** screenshot raw có thể chứa PII/secret; text redaction hiện có không che pixel. Chỉ dùng fixture/demo được phép gửi; không mô tả hệ thống như đã có screenshot redaction. Không log ảnh/base64/key, request body hoặc raw provider error. Giữ debug evidence redacted, encrypted và quyền đọc hiện có.
- **Consent:** thêm binding `raw_screenshot_transfer_provider` vào policy JSON; old HF consent chỉ tương thích HF. Chuyển sang Gehihi phải xác nhận mới; consent thuộc provider, không phải một checkbox dùng chung cho mọi nơi nhận ảnh.
- **Secret:** chỉ `config.py` đọc `GEMINI_API_KEY`, không gửi key ra dashboard, lưu DB, commit hoặc hiển thị repr. Đây là server key dùng chung như provider hiện có; authorization/config/trace vẫn tenant-scoped. Quota Google có thể dùng chung giữa tenant.
- **Audit:** lưu actor/tenant/correlation/provider/model và guard/consent trước–sau cho đổi policy, không lưu bí mật; session/event giữ snapshot và safe reason. Không audit nội dung ảnh.
- **Contract:** không tạo runner/worker contract mới. API policy/catalogue/submit thêm trường; giữ đọc lịch sử và HF client cũ. Không cần schema migration DB vì provider/model là string và overrides là JSON.
- **Execution:** giữ lease fencing, before-commit-before-dispatch, after-commit-before-ack, replay verification, limits và unknown-outcome stop. Không mở lại session terminal khi đổi provider.
- **Failure:** không tự fallback sang nhà cung cấp khác; không retry model trong adapter. Rate limiting cục bộ không đại diện quota Google toàn project.
- **Retention/deployment:** giữ RustFS durable policy và debug retention hiện tại theo runbook; không chọn production retention/cloud/auth. Scope local Compose, không đặt SLO production mới; tổng thời gian bị chặn bởi session deadline hiện có.
- **Prompt:** tiếp tục centralized `vision-exploration-v4`; chỉ sửa cách ghi provenance lúc queued cho session mới. Nếu evaluation buộc đổi hành vi prompt, phải sửa `agents/prompts/vision.py`, bump version và README, thêm regression trong phase 5.

## Phases và tiến độ chuẩn

Chỉ cập nhật tiến độ tại README này khi thực thi; không coi tài liệu phase là bằng chứng phase đã hoàn thành.

| Phase | Mục tiêu | Trạng thái | Phụ thuộc | Validation |
| --- | --- | --- | --- | --- |
| [01 — Policy và catalogue](phase-01-policy-catalogue.md) | Settings, consent binding, API, audit | completed | Không | 100 focused tests passed, including PostgreSQL; Ruff passed |
| [02 — Adapter và ảnh](phase-02-adapter-image-transport.md) | HTTP Gehihi, shared dispatch, lỗi an toàn | completed | 01 | 111 focused + 44 regression tests passed; Ruff passed |
| [03 — Orchestration](phase-03-execution-integration.md) | Legacy/v4, stale policy, trace/provenance | completed | 01, 02 | 178 phase + 68 regression tests passed; Ruff passed |
| [04 — Dashboard](phase-04-dashboard.md) | Provider selector, saved/draft, consent/errors | completed | 01, 03 | 31 unit + 10 browser tests passed; typecheck/build passed |
| [05 — Evaluation và rollout](phase-05-evaluation-rollout.md) | Fixture evidence, ADR/runbook, rollback | completed | 01–04 | 560 Python + 31 unit + 42 browser tests passed; Ruff/TS/build passed |

Triển khai theo thứ tự; các phase đầu chưa phải bản phát hành hoàn chỉnh để bật Gehihi cho tenant.

Current progress: **5/5 completed**. Legacy/v4 execution, dashboard configuration/
confirmation and synthetic evaluation are validated. ADR/runbook and binary
rollback guidance are complete. No phase remains. Live canary is deliberately
not run and no tenant has been enabled; deployment and real quota/model quality
are not certified by offline acceptance.

### Phase 05 completion — 2026-10-17 18:56 +07:00

- Added the hashed, synthetic Gehihi manifest and adapter-backed response gate:
  8/12 mocked batches validate, 6/7 supplied coordinate candidates are in range,
  and all four intentional invalid/refusal/quota cases reject safely without
  candidates or retries. These fixture distributions are not model-quality rates.
- Reused actual legacy/v4 browser/SQL integration for non-button links, retained
  frames, proposal linkage, safe failures, policy revocation and approval boundaries.
  Added div/span role=button and offscreen-scroll deterministic worker cases with
  before/after evidence. Existing native/disabled/ambiguous/sibling/unknown-action
  regressions passed. Locator conversion and frame completeness stay separate.
- Added ADR-009, setup/secret/consent instructions, safe-error table, explicit
  canary limits and schema-aware disable/drain/backup/downgrade instructions.
  Official Google model, compatibility, pricing and rate-limit pages rechecked
  on 2026-10-17. Key presence does not validate account quota or real model quality.
- Exact changed paths for phase 05: `README.md`, `docs/vision-agent-operations.md`,
  `docs/adr/009-gehihi-vision-provider.md`, `benchmark/vision/gehihi/manifest.json`,
  `benchmark/vision/gehihi/README.md`, `benchmark/vision/gehihi/run_offline.py`,
  `tests/test_vision_benchmark.py`, `workers/playwright/src/fixtures/vision-target.ts`,
  `workers/playwright/src/vision-operations.spec.ts`, this README and
  `phase-05-evaluation-rollout.md`.
- Validation actually run:
  - `uv run ruff check .` — passed (initial new closure-binding warning fixed).
  - `uv run python benchmark/vision/gehihi/run_offline.py -q --tb=short` —
    **560 passed, no skips**, 282.65 seconds, 11 existing collection/deprecation
    warnings. This runs pytest with dotenv/inherited app settings removed, a
    migrated disposable UUID database and loopback socket restrictions, adding
    `--ignore=tests/test_playwright_worker_compose.py` and a unique workspace
    basetemp. The three excluded configured-stack tests are not counted as passes.
  - `corepack pnpm --filter @auto-at/dashboard typecheck` — passed.
  - `corepack pnpm --filter @auto-at/dashboard test` — **31 passed, no skips**.
  - `corepack pnpm --filter @auto-at/dashboard build` — passed with the fixture
    API URL `http://127.0.0.1:3107`; final build includes unknown-label hardening.
  - `corepack pnpm --filter @auto-at/playwright-worker typecheck` — passed.
  - `$env:VISION_DASHBOARD_URL='http://127.0.0.1:3107'; corepack pnpm --filter @auto-at/playwright-worker test src/vision-dashboard.spec.ts --workers=1`
    — **10 passed, no skips**, 14.4 seconds against the final production build.
  - `corepack pnpm --filter @auto-at/playwright-worker test src/vision-locators.spec.ts src/vision-operations.spec.ts --workers=1`
    — **32 passed, no skips**, 59.6 seconds.
  - `git diff --check` — passed; Windows line-ending warnings only.
- Deviations: added the small reproducible offline test harness because plain
  pytest can load real `.env` and target the application database; added the two
  existing worker fixture/test files for explicit custom-role/offscreen evidence.
  `apps/control-plane/benchmark/vision.py` needed no changes. No dependency,
  prompt, guard, execution v1 or worker v4 contract changes.
- Cleanup: database query confirmed no owned suite/trace UUID databases remained;
  stopped/auto-removed `gehihi-phase05-postgres` on 127.0.0.1:55437 and stopped
  the owned dashboard on 127.0.0.1:3107. Disposable RustFS/browser fixtures cleaned
  themselves. Existing application services and all prior changes were preserved.
- Deferred deliberately: real-provider canary, tenant enablement, deployment and
  real quota/token-sufficiency assessment. No `.env` edits, billing enablement,
  real provider calls or application migrations/restarts occurred in phases 04–05.
  Existing Next root/ESLint-plugin and Node module-type warnings remain nonblocking.

### Phase 04 completion — 2026-10-17 18:47 +07:00

- Implemented catalogue-driven admin controls, custom HF model preservation,
  provider-bound consent reset, missing-key state and read-only nonadmin settings.
  Separate saved/draft policies block unsaved runs and preserve saved recipient
  after failed saves. Confirmation freezes provider/model; safe 409 refreshes
  settings and requires a new confirmation without automatic resubmission.
- Historical session provider/model labels use the session snapshot. Safe provider,
  policy and Drive failures retain partial evidence and distinguish text draft failure.
- Exact changed paths: `apps/dashboard/app/vision-dashboard.tsx`,
  `apps/dashboard/app/generation-types.ts`, `apps/dashboard/app/generation-api.ts`,
  `apps/dashboard/app/generation-api.test.ts`, `apps/dashboard/app/api-client.ts`,
  `apps/dashboard/app/components/vision-provider-settings.tsx`,
  `apps/dashboard/app/components/vision-provider-model.ts`,
  `apps/dashboard/app/components/vision-provider-model.test.ts`,
  `apps/dashboard/app/components/vision-result-summary.tsx`,
  `apps/dashboard/app/components/vision-session-detail.tsx`,
  `workers/playwright/src/vision-dashboard.spec.ts`, this README and phase 04 file.
- Validation: `corepack pnpm --filter @auto-at/dashboard typecheck` passed;
  `corepack pnpm --filter @auto-at/dashboard test` **31 passed, no skips**;
  `corepack pnpm --filter @auto-at/dashboard build` passed;
  `corepack pnpm --filter @auto-at/playwright-worker typecheck` passed;
  `$env:VISION_DASHBOARD_URL='http://127.0.0.1:3107'; corepack pnpm --filter @auto-at/playwright-worker test src/vision-dashboard.spec.ts --workers=1`
  **10 passed, no skips**, 12.8 seconds. `git diff --check` passed.
- Initial browser 7-pass/3-fail result resolved by explicit select accessible labels.
  Existing Node module-type and Next lockfile-root/ESLint-plugin warnings remain.
- Deviation: extended shared API error parsing plus its API tests to retain the
  backend's structured safe code (needed for stale confirmation and missing key).
  No dependency, prompt, execution/worker contract, server policy or tenant changes.
- Phase 05 unlocked. Production build will be refreshed in final validation after
  the small unknown-label helper hardening, already covered by passing unit tests.

### Execution record — phase 05

- Started: 2026-10-17 18:47 +07:00 (Asia/Saigon).
- Scope: synthetic evaluation manifest/evidence, provider ADR and operator rollout/
  rollback instructions, final Python/TypeScript/browser validation.
- Validation will exclude the three configured-stack Compose tests, which can
  invoke a real reporting provider. Use isolated PostgreSQL on port 55437,
  disabled dotenv, synthetic credentials and loopback-only fixture network.
- Canary remains not run; no live provider call, enablement or application restart.

### Execution record — phase 04

- Started: 2026-10-17 18:37 +07:00 (Asia/Saigon).
- Scope: catalogue-driven provider settings, separate saved/draft policy,
  provider-bound consent, frozen confirmation and stale-policy recovery,
  session snapshot labels and safe failure explanations.
- Existing phase 01–03 changes are preserved. Validation will use a local
  dashboard with mocked APIs; no real provider calls or tenant enablement.
- Validation pending. Phase 05 remains not started.
- Initial checks: dashboard/worker typecheck, 31 dashboard unit tests and production
  build passed. Browser suite: 7 passed, 3 failed because wrapped select labels
  included option text in their accessible names. Explicit labels added; rerun pending.
- Tooling: `pnpm` has no PATH shim here; use the repository-pinned version through
  `corepack pnpm`. No dependency or lockfile changes.

### Execution record — phase 03

- Started: 2026-10-17 18:07 +07:00 (Asia/Saigon).
- Scope: shared legacy/v4 dispatch, fresh provider-bound policy checks,
  submission confirmation/idempotency, prompt provenance and safe failure traces.
- Preserved existing phase 01/02 changes. Validation uses synthetic providers
  and isolated PostgreSQL/browser fixtures; configured-stack Compose tests remain excluded.
- Validation pending; phases 04–05 have not started.
- Initial legacy/progress run: 48 passed, 5 failed because the new synthetic model
  fixture returned `actions` instead of the contract's `candidates`; corrected,
  then 53 passed. Initial Ruff line-length/import findings are being resolved.
- Initial database validation encountered skipped tests because the isolated
  PostgreSQL fixture was absent. Started owned disposable container
  `gehihi-phase03-postgres` (`postgres:17-alpine`) on `127.0.0.1:55437` for reruns.
  Skipped tests do not establish acceptance; application services were not changed.
- Database rerun: 50 passed, no skips. First new provider/browser integration run:
  26 passed, 2 failed. One test used `kind` instead of locator `strategy`; the other
  exposed v4 mapping an emptied origin allowlist to a generic failure rather than
  `policy_disabled`. Both fixes are applied; final phase validation remains pending.
- Broader validation exposed existing clients retrying without `correlation_id`.
  Preserve the original server-generated identity on omission; explicitly supplied
  mismatching correlation IDs still fail. This retains the existing optional-field
  HTTP schema and old HF compatibility. Regression added for both providers.
- The first combined phase run finished with 174 passed and that one correlation
  compatibility failure (no skips). After the fix, submission/migration tests
  passed 20/20; adapter, Drive, diagnostics and policy persistence regressions
  passed 68/68. A final combined run includes the new interruption/identity tests.

### Phase 03 completion — 2026-10-17 18:28 +07:00

- Both composition roots now inject the same provider-aware model batch. Legacy
  reads detached current tenant/project policies through a separate short read
  transaction; v4 retains its fenced commit-per-operation lifecycle. Provider/model
  snapshots and provider-bound consent are checked before transfer and after response.
  Revocation or changed origins stops further actions with `policy_disabled`.
- Legacy now shares one cumulative step guard, bounds worker/model waits by the
  session deadline, respects saved/live traversal and rate limits, and refuses to
  replay an interrupted running session. V4 keeps durable before/after commit and
  acknowledgment order, lease fencing, unknown-outcome reconciliation and replay rules.
- Submission accepts an optional expected provider/model pair, requires it for new
  Gemini sessions, and returns safe 409 for stale confirmation without writes.
  Retries verify tenant/project/target/intent and explicitly supplied correlation;
  omitted correlation reuses the original generated identity. Policy/flag changes
  do not create another session. New sessions record centralized prompt provenance;
  starting old sessions preserves their recorded metadata.
- Safe provider reasons survive terminal persistence, result APIs and allowlisted
  progress metadata. HTTP 401/402/429, timeout, missing key, invalid JSON/coordinates,
  provider switches and consent/origin changes retain partial evidence. HF keeps its
  Drive/OAuth path. Existing draft-generation failures remain independent of Vision
  completion, and approval/runner verdict contracts are unchanged.
- Exact changed paths for this phase:
  `apps/control-plane/application/vision.py`,
  `apps/control-plane/application/vision_events.py`,
  `apps/control-plane/application/vision_trace_events.py`,
  `apps/control-plane/api/v1/routes/vision.py`,
  `apps/control-plane/domain/activity.py`, `apps/control-plane/domain/vision.py`,
  `apps/control-plane/infrastructure/persistence/vision_unit_of_work.py`,
  `apps/control-plane/infrastructure/workflows/temporal_worker.py`,
  `apps/control-plane/infrastructure/workflows/vision_publisher.py`,
  `tests/test_vision_event_processor.py`, `tests/test_vision_provider_submission.py`,
  `tests/test_vision_provider_integration.py`, this README and
  `phase-03-execution-integration.md`.
- Final validation actually run:
  - `uv run ruff check .` — passed.
  - `uv run pytest tests/test_vision_provider_submission.py tests/test_vision_policy_routes.py tests/test_vision_event_processor.py tests/test_vision_live_persistence.py tests/test_vision_results.py tests/test_vision_locator_pipeline.py tests/test_vision_migration_compatibility.py tests/test_vision_worker_contracts.py tests/test_execution_contract_fixtures.py tests/test_agent_boundaries.py tests/test_vision_provider_integration.py tests/test_vision_progress.py -q --basetemp=.pytest_cache/gehihi-phase03-verified --tb=short`
    — **178 passed, no skips**, 230.05 seconds; three existing Starlette/Alembic warnings.
  - `uv run pytest tests/test_vision_model_batch.py tests/test_gemini_vision_model.py tests/test_google_drive_temporary_images.py tests/test_vision_debug_evidence.py tests/test_vision_debug_access.py tests/test_vision_policy_persistence.py -q --basetemp=.pytest_cache/gehihi-phase03-adapter --tb=short`
    — **68 passed, no skips**, 6.94 seconds; one existing Starlette warning.
  - `git diff --check` — passed (Windows line-ending warnings only).
- Browser evidence includes Gemini inline HTTP through `MockTransport`, navigation
  and a subsequent non-button link click for both legacy/v4, SQL-linked proposals
  and retained images, and authorized result/progress reads. V4 readers see committed
  navigation while the model call is pending. Existing browser tests cover sibling
  restore/replay, generation failure, explicit approval and deterministic v1 execution.
- Deviations: added the dedicated provider integration module instead of duplicating
  existing persistence/result fixtures; added domain allowlists for safe progress
  reasons; wired the existing CSRF dependency on submission. Optional correlation
  compatibility was retained after the existing migration regression exposed it.
  No new SQL schema, dependency, worker contract, prompt text or model choice.
- Environment/limits: all database tests used disposable UUID databases on the owned
  PostgreSQL fixture at `127.0.0.1:55437`. The fixture container was stopped and
  auto-removed after validation. Browser targets were owned loopback fixtures;
  provider HTTP was mocked. No real provider request, `.env` edit, tenant enablement,
  application database migration or application-stack restart was performed.
  Full-suite/dashboard validation remains for phases 04–05; configured-stack Compose
  tests were not run. These tests do not certify real-provider quality or free quota.
- Dependencies unlocked: phase 04 dashboard provider selection, saved-policy consent
  and stale-confirmation UX. Phase 05 remains pending; overall plan stays in progress.

### Execution record — phase 01

- Started: 2026-10-17 11:35 +07:00 (Asia/Saigon).
- Scope: settings, pure provider catalogue, provider-bound consent, policy use case,
  transaction dependencies, authenticated API and focused offline tests.
- Pre-flight: only this untracked plan directory existed in the working tree.
  Existing architecture, runtime, configuration and policy route inspected.
- Progress: 0/5 phases completed. No provider calls or tenant enablement authorized
  by this phase; next dependency is phase 02 after phase 01 validation.
- Blocker discovered: `domain.runs.AuditEvent` and `AuditEventModel` have no
  detail/payload field. They cannot persist the required before/after provider,
  model, consent and guard values. Decision needed for phase 01: permit an
  additive audit JSON migration, or keep the no-migration constraint by storing
  versioned policy snapshots in `configs` referenced by audit entity IDs.
  Safe work continues on settings, consent, catalogue and policy validation;
  no later phase will begin before this audit-storage decision is resolved.
- Safe implementation completed while awaiting that decision:
  optional secret-safe Gemini setting and example placeholder; pure provider
  catalogue; HF-compatible provider-bound consent and override normalization;
  read/catalogue/validation use case; authenticated policy/catalogue GET routes;
  dependency composition and focused runtime/read HTTP tests.
- Changed paths so far:
  `.env.example`, `apps/control-plane/config.py`,
  `apps/control-plane/agents/shared/runtime.py`,
  `apps/control-plane/agents/shared/vision_providers.py`,
  `apps/control-plane/application/vision_policy.py`,
  `apps/control-plane/api/v1/dependencies/vision.py`,
  `apps/control-plane/api/v1/routes/vision.py`, `tests/test_config.py`,
  `tests/test_agent_runtime.py`, `tests/test_vision_policy.py`,
  `tests/test_vision_policy_routes.py`, `tests/test_dashboard_route_contracts.py`,
  this README and `phase-01-policy-catalogue.md`.
- Validation actually run:
  - `uv run ruff check apps/control-plane/config.py apps/control-plane/agents/shared apps/control-plane/application/vision_policy.py apps/control-plane/api/v1 tests/test_config.py tests/test_agent_runtime.py tests/test_vision_policy.py tests/test_vision_policy_routes.py tests/test_dashboard_route_contracts.py` — passed.
  - `uv run pytest tests/test_config.py tests/test_agent_runtime.py tests/test_vision_policy.py tests/test_vision_policy_routes.py tests/test_dashboard_route_contracts.py -q` — **70 passed**, no skips; one existing Starlette/httpx deprecation warning.
  - `git diff --check` — passed.
  - Initial Ruff run found one line-length violation; fixed before the passing run.
- Not complete: PUT use-case wiring, atomic config/audit write and audit persistence;
  write HTTP/RBAC/CSRF, tenant-isolation and rollback tests still required after
  the storage decision. Passing tests above do not establish phase acceptance.
- No live provider call, real `.env` edit, tenant enablement, migration, production
  access or execution-contract change. Phases 02–05 have not started.

### Resume verification — 2026-10-17 11:58 +07:00

- Preserved the existing partial implementation and untracked plan/tests.
- Re-ran the exact focused Ruff and pytest commands listed above: Ruff passed;
  **70 tests passed**, no skips, one Starlette/httpx deprecation warning.
- Confirmed the audit-storage blocker against the domain model, SQL model and
  repository: the SQL audit table has neither policy detail nor before/after
  hash columns; the domain hash fields are not persisted by the repository.
- Phase 01 remains in progress (0/5 complete). The pending decision is whether
  to keep the no-migration constraint using tenant-scoped versioned policy
  snapshots in `configs`, linked through audit entity IDs (recommended), or
  revise scope to add a JSON detail column through a migration.
- No implementation changes were made during this verification. PUT wiring,
  atomic config/audit persistence and write-path tests await that decision;
  phases 02–05 remain not started.

### Approved execution revision — audit storage

- Resumed: 2026-10-17 12:23 +07:00. User approved the recommended no-migration
  option. The earlier audit-storage blocker is resolved; phase 01 is in progress.
- Store each before/after Vision policy snapshot at
  `vision.policy.audit.v1.<audit-entity-uuid>` in tenant-scoped `configs`.
  Each update generates a new entity UUID; prior snapshots are not overwritten.
  The audit event uses entity type `vision_policy_snapshot` and that UUID.
- Snapshot JSON contains schema version, actor, tenant, correlation ID, timestamp
  and validated before/after Vision fields (provider/model/consent/guards), never
  credentials, screenshots or the general runtime configuration.
- Active override, snapshot and audit event must commit or roll back together.
  Resume scope: PUT use-case wiring, existing CSRF enforcement, isolated writes,
  persistence/rollback tests. No SQL schema migration is needed.

### Phase 01 completion — 2026-10-17 12:30 +07:00

- Completed the approved no-migration audit design, preserving all prior work.
  `VisionPolicies.update` validates authorization, provider consent and readiness;
  preserves non-Vision overrides; writes a new scoped before/after snapshot and
  one correlated audit event together with the active override.
- Policy PUT now delegates to the application use case and the existing CSRF
  dependency. Returns 403 for unauthorized writes, safe 422 for invalid policy,
  and 409 `provider_not_configured` when enablement lacks a credential.
  Dependency transaction commits before the success response is sent.
- Final changed paths for phase 01:
  `.env.example`, `apps/control-plane/config.py`,
  `apps/control-plane/agents/shared/runtime.py`,
  `apps/control-plane/agents/shared/vision_providers.py`,
  `apps/control-plane/application/vision_policy.py`,
  `apps/control-plane/api/v1/dependencies/vision.py`,
  `apps/control-plane/api/v1/routes/vision.py`, `tests/test_config.py`,
  `tests/test_agent_runtime.py`, `tests/test_vision_policy.py`,
  `tests/test_vision_policy_routes.py`, `tests/test_vision_policy_persistence.py`,
  `tests/test_dashboard_route_contracts.py`, this README and
  `phase-01-policy-catalogue.md`.
- Validation actually run:
  - `uv run ruff check .` — passed.
  - `uv run pytest tests/test_config.py tests/test_agent_runtime.py tests/test_vision_policy.py tests/test_vision_policy_routes.py tests/test_vision_policy_persistence.py tests/test_dashboard_route_contracts.py -q`
    — **100 passed, no skips**, one existing Starlette/httpx deprecation warning.
  - PostgreSQL tests used the disposable fixture on `127.0.0.1:55437`, with real
    repositories/dependency composition. They verified committed snapshots,
    tenant scoping, correlation and rollback on snapshot, audit and commit failure.
  - `uv run pytest` — interrupted; two deterministic Compose worker tests had
    passed. The Compose dashboard test can mutate the running stack and trigger
    its reporting provider, so that module is excluded from further validation.
    This interrupted command is not a full-suite pass.
    Read-only verification confirmed that it had already created one synthetic
    Compose dashboard tenant and two local runs; both persisted reports are
    `unavailable`. Those test records were preserved. Reporting-provider attempts
    cannot be ruled out, so this invocation is not described as wholly offline.
  - `uv run pytest --ignore=tests/test_playwright_worker_compose.py` — interrupted
    after fixture setup errors from Windows access denial on the default pytest
    temporary directory. A targeted reproduction in `tests/test_verified_artifacts.py`
    confirmed the `tmp_path` setup error.
  - `uv run pytest --ignore=tests/test_playwright_worker_compose.py --basetemp=.pytest_cache/gehihi-phase01-20261017-1230`
    — **416 passed, no skips**, 11 collection/deprecation warnings, 169.97 seconds.
    Three Compose tests were excluded by the command; exclusions are not passes.
    Real PostgreSQL, RustFS and browser-fixture checks ran successfully.
  - `git diff --check` — passed (Windows line-ending warnings only).
- Deviations: added `tests/test_vision_policy_persistence.py` to verify real SQL
  transactions beyond the planned fake-repository tests; explicitly wired the
  existing CSRF guard because the original PUT route did not invoke it.
  The approved config-snapshot solution needs no domain port or SQL schema change.
- Follow-up: phase 02 provides HTTP/image transport; phases 03–05 integrate
  execution, UI and evaluation. No production deployment or tenant enablement
  was performed by this phase. Runner contracts and prompts are unchanged.

### Execution record — phase 02

- Started: 2026-10-17 17:36 +07:00 (Asia/Saigon).
- Scope: Gemini vision-only HTTP adapter, provider-aware shared image dispatch,
  bounded deadline, safe failure classification/redaction and offline tests.
- Preserved all existing phase 01 changes and untracked files. No orchestration
  lifecycle changes, tenant enablement, real provider calls or `.env` edits.
- Official Google model and OpenAI-compatibility documentation rechecked; the
  approved model, fixed endpoint, inline images and low reasoning remain the plan.
- Validation pending. Phase 03 wiring remains the next dependency after acceptance.
- First focused pytest run: 107 passed, 4 failed. The HF dispatch test settings
  used field names for OAuth fields that require their existing validation aliases;
  fixture correction underway. No provider network requests were made.
  Initial Ruff found two long lines; fixed, and `uv run ruff check .` passed.

### Phase 02 completion — 2026-10-17 17:42 +07:00

- Implemented the vision-only Gemini adapter with a fixed Google endpoint,
  approved model, explicit payload fields, inline images, low reasoning and
  JSON-object response format. Caller kwargs cannot override transport identity.
  Requests are bounded by 30 seconds and the remaining deadline, cancellation
  propagates, and no retry, redirect-following or fallback is performed.
- Added a persistence-independent session input and callable protocol, plus shared
  provider dispatch. Gemini never constructs a Drive store. HF retains existing
  upload/cleanup and safe OAuth reauthorization behavior. Executor checks bytes,
  consent, token/candidate caps and the shared step guard before entering image
  delivery; dispatch checks the live policy before transfer and before returning.
- Added optional safe batch failure reasons, HTTP/transport classification,
  rejection of refusal/truncation, and redaction of echoed Gemini keys/data URIs
  from diagnostic capture. Prompts and shared runner/worker contracts are unchanged.
- Exact changed paths for phase 02:
  `apps/control-plane/agents/shared/gemini.py`,
  `apps/control-plane/agents/shared/openrouter.py`,
  `apps/control-plane/agents/vision/executor.py`,
  `apps/control-plane/agents/vision/diagnostics.py`,
  `apps/control-plane/application/vision_model_batch.py`,
  `apps/control-plane/infrastructure/vision/__init__.py`,
  `apps/control-plane/infrastructure/vision/model_batch.py`,
  `tests/test_agent_runtime.py`, `tests/test_vision_executor.py`,
  `tests/test_gemini_vision_model.py`, `tests/test_vision_model_batch.py`,
  this README and `phase-02-adapter-image-transport.md`.
- Validation actually run after fixes:
  - `uv run ruff check .` — passed.
  - `uv run pytest tests/test_agent_runtime.py tests/test_vision_executor.py tests/test_gemini_vision_model.py tests/test_vision_model_batch.py tests/test_google_drive_temporary_images.py -q`
    — **111 passed, no skips**, 1.86 seconds.
  - `uv run pytest tests/test_vision_debug_evidence.py tests/test_vision_debug_access.py tests/test_vision_event_processor.py tests/test_vision_benchmark.py tests/test_vision_contracts.py tests/test_vision_worker_contracts.py tests/test_execution_contract_fixtures.py -q --basetemp=.pytest_cache/gehihi-phase02-20261017-1741`
    — **44 passed, no skips**, 2.82 seconds.
  - `git diff --check` — passed (Windows line-ending warnings only).
- Earlier failures are resolved: two Ruff line lengths and four new HF tests
  whose synthetic OAuth values needed existing Settings validation aliases.
- Implementation detail: an optional executor image-delivery context keeps guard
  reservation before external transfer without charging the step twice. Existing
  callers remain compatible. Existing Drive tests were reused unchanged, with new
  shared-dispatch HF regressions in `tests/test_vision_model_batch.py`.
- Follow-up/limits: phase 03 must replace the old publisher-local dispatch with
  the shared adapter, wire legacy/v4 callers with remaining deadlines and live
  policy callbacks, and persist safe completion reasons. Old orchestration is
  intentionally unchanged at this phase boundary; do not enable Gehihi yet.
  Phases 03–05 remain not started. Full-suite, browser and persistence validation
  belong to subsequent integration/evaluation phases and were not rerun here.
  No live provider calls, tenant enablement, `.env` changes or stack changes.

## Rủi ro và rollout

- Free-tier quota có thể hết hoặc tài khoản không đủ điều kiện; không hứa miễn phí vô hạn. Dùng account/project free tier và xác minh quota trước canary, không tự bật paid tier.
- Output/thinking có thể tiêu hết token budget và trả JSON thiếu; trả lỗi validation, không tăng budget âm thầm. ID stable không có nghĩa là Google cung cấp snapshot trọng số bất biến như một commit HF.
- UI/server policy có thể đổi giữa confirmation và submit hoặc trong call; kiểm tra snapshot trước external call và trước hành động tiếp theo. Call đã gửi không thể thu hồi.
- Consent field mới làm binary cũ với `extra=forbid` không đọc được override mới. Rollback phải disable/drain, backup non-secret config và chuyển overrides về schema/provider cũ trước khi hạ backend.
- Text draft vẫn có thể bị HF 402 dù Vision dùng Gehihi thành công; UI cần phân biệt hai kết quả.
- Mốc rollout: test offline → local fixture → cấu hình key server và consent tenant → canary synthetic có giới hạn khi được yêu cầu → kiểm tra trace/quota. Không tự restart stack, sửa .env hoặc gọi API thật trong planning.

## Ngoài phạm vi

Stream/video màn hình trực tiếp, thay text generation provider, tự chứng nhận “mọi nút đều hoạt động”, sửa hook/agentmemory, auto-healing, production deployment, thay auth, runner mới, monetary accounting và xóa dữ liệu lịch sử.

## Tài liệu nền và nguồn provider

Ràng buộc repository: `AGENTS.md`, `docs/architecture.md`, `docs/adr/001-platform-architecture.md`, `docs/adr/003-governed-openrouter-agent-configuration.md`, `docs/adr/007-vision-model-selection.md`, `docs/adr/008-vision-temporary-image-delivery.md`, `docs/vision-agent-operations.md`.

Đối chiếu ngày 17/10/2026: model hỗ trợ ảnh và structured output; OpenAI-compatible endpoint hỗ trợ ảnh inline. Nguồn: [model](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash), [OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai). Free tier có điều kiện dữ liệu dùng để cải thiện sản phẩm; quota thực tế theo project/tài khoản: [pricing](https://ai.google.dev/gemini-api/docs/pricing), [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits). Kiểm tra lại trước canary; không suy ra availability của key từ trang tài liệu.

Thực thi tiếp bằng `$feature-plan-execution` với đường dẫn thư mục này.
