# Phase 7 — Kiểm chứng end-to-end và rollout local

Trạng thái: completed. Phụ thuộc: Phases 1–6.

## Source thêm/sửa

Thêm:
- `tests/test_vision_locator_pipeline.py`
- `tests/test_vision_migration_compatibility.py`
- `benchmark/vision/v2/manifest.json`

Sửa:
- `apps/control-plane/benchmark/vision.py`
- `tests/test_vision_benchmark.py`
- `tests/test_playwright_worker_compose.py`
- `docs/vision-agent-operations.md`
- `docs/architecture.md`
- `README.md`

Dùng lại fixture server `workers/playwright/src/fixtures/vision-target.ts` và browser specs Phases 2/6. Thêm test-only fixture wiring bằng setup test; không trỏ fixture model sang endpoint thật. Không đổi cấu hình production để chạy test.

## Scenario bắt buộc

1. Vision fake model chọn link A rồi sibling B. Worker thật xác minh role/test ID, lưu before, click A, lưu after, back/restore được kiểm chứng rồi B. API đọc được từng bước khi phiên chưa kết thúc.
2. Modal/tab cùng URL, form/scroll restore và popup: phân biệt page change, same-page change, no-change; không chụp nhầm parent của tab mới.
3. Duplicate element/overlay/stale DOM, unsupported frame/shadow/canvas, sensitive locator: unresolved có bằng chứng, không sinh locator verified giả.
4. Capture-before lỗi không thao tác; after lỗi giữ attempt; worker crash/response lost giữ unknown, duplicate event không tự click lại; restore failure chặn dependent branch.
5. Budget/deadline/policy disable giữa phiên dừng đúng và giữ partial trace. Không tăng max state/hop/rate/token để pass test.
6. Handoff được commit, generation mock chọn branch/ref, renderer sinh source dùng locator thật, draft pending; explicit test approval qua API tạo đúng một run. Chạy local target bằng pinned Playwright, report flow qua fixture reporting model. Assert session → handoff → request → draft → run → report là cùng provenance.
7. Generation provider fake lỗi `generation unavailable`: session vẫn có kết quả khám phá/trace/catalog và failure reason; UI không nói toàn bộ pipeline hoàn tất.
8. Hai tenants/projects, revoked permission, deleted frame, export: quyền đúng, audit safe, no private data leak. Reconnect/polling/refresh không lẫn state.
9. Legacy session 7-frame/6-sibling synthetic tái hiện hình dạng session người dùng, không copy ảnh/payload thật vào fixture. Hiện legacy evidence rõ, không gán locator mới cho session cũ.

## Đo lường

Ghi aggregate fixture metrics:
- verified locator grounding rate và wrong-target count;
- operation frame completeness (cả numerator/denominator và lý do ảnh thiếu);
- restore verified/failure count;
- partial progress visibility latency sau commit;
- handoff branch eligibility và deterministic rerun result;
- số duplicate physical action do redelivery (phải bằng 0 cho completed operations).
Bộ synthetic dương tính phải đúng target 100%; ca không hỗ trợ phải từ chối thay vì cải thiện tỷ lệ bằng đoán. Tách tỷ lệ fixture và giới hạn target thực; không coi benchmark local là cam kết production.

## Validation commands

Tại root, khi DB test/fixture services sẵn sàng:
```text
uv run ruff check .
uv run pytest tests/test_vision_contracts.py tests/test_vision_operation_repository.py tests/test_vision_handoff_repository.py tests/test_vision_event_processor.py tests/test_vision_live_persistence.py tests/test_vision_handoff.py tests/test_vision_source_renderer.py tests/test_vision_results.py tests/test_vision_locator_pipeline.py tests/test_vision_migration_compatibility.py tests/test_vision_replay.py tests/test_vision_routes.py tests/test_generation_event_processor.py tests/test_generation_preflight.py tests/test_outbox_publishing.py tests/test_execution_contract_fixtures.py tests/test_reporting_routes.py tests/test_vision_benchmark.py
uv run alembic heads
```
Sau focused suite, chạy baseline `uv run pytest`; phân loại skipped Compose checks rõ, không báo e2e pass khi skip. Dashboard typecheck/test/build và worker typecheck/browser specs theo Phase 6. `git diff --check` trước handoff.

## Migration, deploy và rollback

- Recheck dirty tree, dependency versions và migration head. Không commit/reset các sửa trước của user.
- Upgrade additive trên DB test có legacy fixture; kiểm tra count, refs, tombstones và reader tương thích. Backup DB theo quy trình local trước migration local thật; không restore/overwrite volume trong validation.
- Build worker hỗ trợ legacy và v4; drain session trước restart; deploy writer mới sau schema, rồi generation/API và dashboard. Phiên đang chạy gắn version, không đổi protocol giữa chừng.
- Không tự enable tenant Vision hoặc thay provider/consent cho canary. Synthetic local test không cần trả phí. Canary target thật chỉ khi scope user đã cho phép; thiếu thì ghi chưa chạy.
- Quan sát operation_unknown, restore_failed, orphan staged frames, handoff failures, DB commit latency và per-session deadline enforcement bằng safe enums/counts. Không log locator values/page text/URL.
- Rollback writer cho new sessions về version cũ, giữ evidence tables/reader mới đủ để xem trace đã có. Không downgrade xóa operation history; hoàn tất/đánh dấu interrupted trước khi drain worker.
- Sửa runbook về provider-image retention cho đúng ADR-008/config hiện hành; không thay retention bằng việc sửa docs.

## Nghiệm thu cuối và giới hạn

Tài liệu hướng dẫn chính xác: mở session Vision để xem kết quả/trace/locator; bấm draft để duyệt; mở run để xem verdict/report. End-to-end synthetic xác minh locator từ Vision thực sự được Playwright dùng. Các hạn chế input binding, unsupported targets, state restore và provider failure phải nhìn thấy trên UI.

Không tự chứng nhận production-ready, đổi cloud/model, sửa lỗi credential provider hoặc backfill session cũ. Sau mỗi phase người thực hiện cập nhật trạng thái, bằng chứng test và deviations trong README canonical của kế hoạch này.


Execution started 2026-09-08 23:25 +07:00. All prior phase checks passed; validating the synthetic approval/execution/report chain and new-session rollout gate.

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
