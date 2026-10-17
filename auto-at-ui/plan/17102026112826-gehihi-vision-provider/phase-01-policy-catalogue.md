# Phase 01 — Runtime policy, catalogue và consent

## Execution status

Completed: 2026-10-17 12:30 +07:00 (started 11:35 +07:00).
Settings, catalogue, provider-bound consent and policy read/write use cases are
implemented. The approved config snapshots and audit event commit atomically
with the active override; PUT enforces tenant management permission and CSRF.
Repository-wide Ruff and 100 focused tests passed, including real PostgreSQL
commit/rollback checks, with no skips. The canonical README contains the exact
changed paths, commands, broader-validation limitations and phase 02 handoff.
The broader suite passed 416 tests with no skips using a workspace basetemp;
the three existing Compose tests were excluded because they target the running
stack and can invoke its reporting provider. See README for the initial
interrupted run's local fixture-data side effects.

Audit storage resolved by user on 2026-10-17: use versioned tenant-scoped config
snapshots linked by audit entity ID, with no migration. Implementation resumed
at 12:23 +07:00; PUT use-case wiring and atomic audit write validation are complete.
No later phase has begun.

Resume verification at 2026-10-17 11:58 +07:00 re-ran the focused checks:
Ruff passed and 70 tests passed without skips. The audit-storage decision
was pending at that point; see the canonical README for the approved resolution.

## Mục tiêu / prerequisites

Cho phép mô tả và lưu Vision provider Gehihi một cách tenant-scoped, không rò key và không kế thừa consent HF. Đọc README của plan, runtime/config và ADR-003/007/008. Chưa bật cho tenant hoặc gọi provider.

## Files

Sửa:
- `apps/control-plane/config.py`, `.env.example`.
- `apps/control-plane/agents/shared/runtime.py`.
- `apps/control-plane/api/v1/routes/vision.py` — chỉ các endpoint policy/catalogue trong phase này.
- `tests/test_config.py`, `tests/test_agent_runtime.py`, `tests/test_dashboard_route_contracts.py`.

Thêm:
- `apps/control-plane/agents/shared/vision_providers.py` — catalogue/capability thuần, không network/env.
- `apps/control-plane/application/vision_policy.py` — read/update policy và catalogue qua ports.
- `apps/control-plane/api/v1/dependencies/vision.py` — composition/transaction dependencies.
- `tests/test_vision_policy.py`, `tests/test_vision_policy_routes.py`.
- `tests/test_vision_policy_persistence.py` — execution addition for real SQL
  snapshot/audit commits, rollback and persisted tenant isolation.

Tái sử dụng, chỉ sửa nếu interface hiện tại thiếu cho use case: `apps/control-plane/domain/ports.py`, `apps/control-plane/infrastructure/persistence/repositories.py`. Dùng ConfigurationRepository và AuditEventRepository hiện có; không tạo DB table.

## Thiết kế phải triển khai

1. Thêm `gemini_api_key` vào Settings, default rỗng, secret-safe repr; env `GEMINI_API_KEY`. Endpoint Google là constant server-trusted trong adapter phase 02, không cho tenant tùy ý nhập URL. Thêm optional `VISION_RAW_SCREENSHOT_TRANSFER_PROVIDER` để cấu hình môi trường không thể dùng consent boolean cũ cho Gemini.
2. Catalogue có hai ID `huggingface` và `gemini`. Label Gemini là “Gehihi (Google Gemini)”; Gemini chỉ nhận model `gemini-3.8-flash` đã chốt. HF giữ model hiện tại và quy tắc non-empty, không đổi custom model hợp lệ. General AgentRuntimeConfig.provider vẫn chỉ các provider đã hỗ trợ cho text.
3. VisionPolicy thêm `raw_screenshot_transfer_provider: Literal["huggingface", "gemini"] | None = None`. Khi enabled, accepted phải true và binding phải khớp provider. Khi accepted=false, normalize binding=None. Cho lưu disabled policy chưa consent để cấu hình từng bước.
4. Tương thích: dữ liệu HF cũ accepted=true/binding thiếu được normalize sang HF. Không áp dụng phép suy diễn này cho Gemini. Merge env/override không được mang binding HF sang Gemini rồi coi là consent hợp lệ. Model/provider unknown trả validation có kiểm soát.
5. Use case update đọc override tenant, merge riêng vision giữ nguyên text/evidence/guard khác, validate, kiểm tra readiness khi enabled và ghi configuration + audit cùng transaction. Không chỉ trả lỗi 500 từ Pydantic. Audit không chứa key; ghi thay đổi consent/provider/model và guards với actor/correlation.
6. `GET /api/v1/vision/providers` cần principal/tenant hợp lệ, không gọi Google. Response `{items:[{id, display_name, models, configured, supports_inline_images}]}`; models là các lựa chọn `{id, display_name}`. HF catalogue không làm mất custom model đã lưu; Gemini chỉ một model. configured chỉ nghĩa server có key, không cam kết key hợp lệ/quota còn.
7. GET/PUT `/api/v1/vision/policy` thêm consent binding. PUT tiếp tục yêu cầu MANAGE_TENANT và CSRF hiện có. Vi phạm quyền=403, payload/policy sai=422, bật khi thiếu key=409 với code `provider_not_configured`. GET vẫn đọc được disabled policy khi chưa có key.
8. Giữ cấu hình runtime mặc định và VISION_ENABLED false. `.env.example` chỉ thêm placeholder/chú thích; không đọc/sửa .env thật. Không thêm key vào API, OpenAPI examples, logs hoặc JSON DB.

Approved audit design: store versioned before/after policy JSON under
`vision.policy.audit.v1.<entity-uuid>` in tenant-scoped `configs`; the audit event
uses `vision_policy_snapshot` and the same entity UUID. Each update allocates a
new UUID. Snapshot metadata includes actor, tenant, correlation and timestamp;
only validated Vision fields enter before/after. All three writes share the
dependency transaction, which commits before HTTP success.

## API/schema/compatibility

Đây là mở rộng policy API và JSON `agent.runtime.v1`, không đổi shared execution/action contracts. Không cần migration SQL. Consumer cũ HF không gửi binding vẫn hợp lệ theo quy tắc compatibility. Binary cũ không đọc được field mới: ghi chú rollback tại phase 05.

## Tests và commands

- Default unchanged; env Gemini với consent thiếu/sai bị từ chối; disabled+missing key được load; general text provider không được mở rộng vô tình.
- Policy update tenant A không ảnh hưởng B; không ghi đè text config; unauthorized/CSRF không có write/audit; success một audit không chứa key.
- HF old JSON normalize; đổi HF→Gemini với accepted cũ bị từ chối; explicit new binding thành công; malformed model/provider trả 422.
- Catalogue có key thì configured=true, không network; không key thì false. Bật thiếu key trả safe409.
- Cập nhật OpenAPI route inventory cho endpoint mới.

```powershell
uv run ruff check apps/control-plane/config.py apps/control-plane/agents/shared apps/control-plane/application/vision_policy.py apps/control-plane/api/v1 tests/test_config.py tests/test_agent_runtime.py tests/test_vision_policy.py tests/test_vision_policy_routes.py tests/test_dashboard_route_contracts.py
uv run pytest tests/test_config.py tests/test_agent_runtime.py tests/test_vision_policy.py tests/test_vision_policy_routes.py tests/test_vision_policy_persistence.py tests/test_dashboard_route_contracts.py -q
```

## Exit criteria / risks / non-goals

Tests trên pass bằng fake key/config repo, không external request; HF configuration regression pass. Chưa cho coi Gehihi có thể thực thi trước phase 02–03. Không chọn auth mới, per-tenant secret vault, generic provider marketplace hoặc refactor toàn bộ routes.
