# Phase 2 — Worker kiểm chứng locator, chụp thao tác và phục hồi state

Trạng thái: completed. Started: 2026-09-08 20:52 +07:00. Completed: 2026-09-08 21:29 +07:00. Phụ thuộc: Phase 1 contracts/fixtures. Phase 2 acceptance checks passed; the broader Python baseline has the external-service limitations recorded below.

## Source thêm/sửa

Sửa `workers/playwright/src/vision.ts`, `workers/playwright/src/server.ts`, `workers/playwright/src/vision.spec.ts`.
Thêm:
- `workers/playwright/src/vision-locators.ts`
- `workers/playwright/src/vision-operations.ts`
- `workers/playwright/src/vision-checkpoints.ts`
- `workers/playwright/src/vision-contract.ts`
- `workers/playwright/src/vision-locators.spec.ts`
- `workers/playwright/src/vision-operations.spec.ts`
- `workers/playwright/src/fixtures/vision-target.ts` — local HTTP fixture server.

## Protocol v4 và trình tự

Mở phiên có tenant/project/session identity, fencing token, allowed origins, absolute deadline và budget hiện hành. Thêm endpoint v4 rõ dưới `/visual-explorations/{session}/operations`:
- prepare: operation ID, expected state, action, checkpoint target; xác minh/resolve locator, chụp before, trả metadata verified và opaque handle.
- execute: operation ID + fencing token; chỉ chạy operation đã prepared và được caller acknowledge; trả operation result + after metadata.
- read result: tra operation đã thực hiện để reconciliation response thất lạc.
- acknowledge: control plane đã lưu evidence, worker có thể dọn staging thuộc operation.
Thêm checkpoint metadata read/restore preparation; mỗi primitive phục hồi đi qua cùng operation API. Đóng phiên huỷ worker state tạm. Giữ legacy v1/v3 reader cho rollout, không tự fallback phiên v4 sang replay legacy.

Đặt HTTP route cụ thể: POST `/visual-explorations` nhận version v4 để mở session; POST `/{session}/operations/prepare`; POST `/{session}/operations/{operation}/execute`; GET `/{session}/operations/{operation}`; POST `/{session}/operations/{operation}/ack`; GET `/{session}/checkpoints/{checkpoint}`; DELETE `/{session}`. Các path rút gọn đều dưới `/visual-explorations`. Restore được điều phối thành operation purpose=restore/replay, không có endpoint thực hiện âm thầm cả đường đi.

Mọi request v4 kiểm tra UUIDs, secret header, tenant/project/session identity, fencing token, expected state và cap payload trước parse sâu. Session ID không phải quyền truy cập. Setup bắt đầu từ trang trắng: capture before setup rồi mới goto target qua operation; trường hợp đóng popup dùng frame popup trước và frame parent sau, ghi rõ page refs.

1. DOM grounding chạy trước click/type, trên đúng screenshot/page state. Hit-test target normalized, đi lên interactive ancestor và xuống open shadow root phù hợp. Iframe cùng origin phải có frame scope và chuyển đổi tọa độ; iframe không hỗ trợ trả code, không đoán locator.
2. Tạo candidate role/name, label, test ID, CSS stable attribute theo thứ tự đã chốt. Chỉ nhận candidate khi count=1, resolve đúng element nguồn, visible/enabled và editable cho input; kiểm tra hit-test/overlay. Không dùng nth/first để che ambiguous.
3. Nếu DOM/hydration thay đổi giữa prepare và execute, revalidate; lệch state thì từ chối, chụp lại và yêu cầu proposal mới. Không blind click tại tọa độ cũ.
4. Click/type dùng locator Playwright đã resolve; với type ghi rõ thao tác append như hiện tại, không tự đổi sang fill/clear. Scroll/wait giữ schema bounded. Chụp trước và sau, ghi navigation/page creation/duration/action error.
5. Chờ ổn định có giới hạn: arm page/navigation events trước action, đợi DOM readiness và các mẫu trạng thái liên tiếp trong deadline; không đợi network-idle vô hạn. Timeout ghi `settle_timeout` kèm after best effort.
6. Thiết lập origin policy trên BrowserContext để bao cả popup và mọi page, trước action. Theo dõi tab mới đúng operation; lấy after ở tab mới nếu được phép. Link bị chặn, popup bị chặn, dialog/download không hỗ trợ đều có reason. Không tự thay target thành about:blank rồi ghi thành công.
7. Restoration: khi sibling cần parent, giữ parent page nếu popup, đóng popup qua operation có before/after; cùng-tab navigation thử back và kiểm tra invariant. Với state cùng URL hoặc back không khôi phục, tái dựng root + ancestor path từng bước bằng locator đã kiểm chứng.
8. State check dùng URL fingerprint + descriptor/semantic structure fingerprint + scroll/form invariants có liên quan. Form values và session runtime nếu cần chỉ trong RAM và không chứa credential flow. Không dùng screenshot hash làm bằng chứng duy nhất cho equivalence. Không phục hồi được thì `state_restore_failed`; không tiếp tục sibling trên state sai.
9. Replay không được tự lặp thao tác có kết quả unknown hoặc side effect không thể phục hồi. Back không rollback server data. Session/worker restart mất state RAM thì báo unavailable, không hứa retry trong suốt.
10. Duplicate execute ID trả kết quả đã có; ID khác payload bị từ chối. Per-session serialization/fencing chặn song song. Crash giữa action/result → unknown, không tự execute lại. Path artifact dùng UUID đã validate và kiểm tra nằm trong staging root.

## Frame và quyền

Before lấy từ browser tại thời điểm thao tác, không dùng ảnh historical parent thay thế. Control plane phải nhận và commit before trước execute; after bytes tồn tại đến ACK. Capture trước lỗi thì không action; capture sau lỗi vẫn giữ record action và before, báo evidence thiếu. Screenshot không phải browser checkpoint. Không persist raw DOM, browser storage hoặc typed text để phục hồi.

## Tests và validation

Fixture server gồm: hai link nội bộ, popup, SPA tabs/modal cùng URL, form/scroll, delayed hydration, duplicate accessible names, nested icon button, open shadow root, same-origin iframe, denied-origin popup, sensitive label, failed restore và no-op. Dùng browser thật của worker, model không tham gia.

Kiểm tra mỗi physical action có before/after hoặc failure code; thứ tự back/replay rõ; locator không trỏ sibling khác; không có additional click khi duplicate execute; deadline/bytes/origin guard giữ nguyên.
Tại `workers/playwright/`:
```text
npm.cmd run typecheck
npm.cmd test -- src/vision.spec.ts src/vision-locators.spec.ts src/vision-operations.spec.ts
```
Chạy trên Playwright 1.50.1/pinned container nếu browser local chưa có; không nâng dependency để bỏ qua lỗi.

## Nghiệm thu và non-goals

Fixture root → A → back/restore → B chạy và có ledger chính xác. Modal cùng URL có visual/semantic change. Locator unresolved được báo, không bàn giao verified. Không bổ sung canvas locator, auth, browser snapshot bền vững hay rollback target server.


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
