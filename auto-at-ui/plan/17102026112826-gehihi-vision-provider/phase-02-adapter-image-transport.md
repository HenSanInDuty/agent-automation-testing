# Phase 02 — Gehihi adapter và dispatch ảnh

## Execution status

Completed: 2026-10-17 17:42 +07:00 (started 17:36 +07:00).
The Gemini HTTP adapter, shared image dispatch, application callable protocol,
safe failure reasons and diagnostic redaction are implemented and tested offline.
Repository-wide Ruff passed; the planned focused suite passed **111 tests** and
diagnostic/legacy/benchmark/contract regressions passed **44 tests**, with no skips.
See the canonical README for exact paths, commands, initial resolved failures
and the phase 03 handoff.

An optional executor image-delivery context allows byte/consent/token/step checks
before any upload without consuming the session guard twice. Existing callers
remain compatible. Existing Drive tests were reused unchanged; new shared-dispatch
HF tests cover cleanup, provider failure, live-policy revocation and invalid_grant.
No prompt, contract, dependency or runtime orchestration change was needed here.

Phase 03 must replace the old publisher-local implementation and wire both
orchestrators to the shared adapter with remaining deadlines. Its dependencies
are now satisfied. This phase does not enable a tenant or validate a real model;
full integration, browser/persistence checks and rollout remain in later phases.

## Mục tiêu / prerequisites

Sau phase 01, triển khai model adapter và reusable dispatch có thể kiểm thử độc lập. Gehihi gửi screenshot inline trực tiếp Google; HF tiếp tục Drive. Chưa thay orchestration lifecycle.

## Files

Sửa:
- `apps/control-plane/agents/shared/openrouter.py` — Vision factory seam; giữ text factory.
- `apps/control-plane/agents/vision/executor.py`.
- `apps/control-plane/agents/vision/diagnostics.py`.
- `tests/test_agent_runtime.py`, `tests/test_vision_executor.py`, `tests/test_google_drive_temporary_images.py`.

Thêm:
- `apps/control-plane/agents/shared/gemini.py` — vision-specific HTTP adapter.
- `apps/control-plane/application/vision_model_batch.py` — callable protocol/input của application, không import infrastructure.
- `apps/control-plane/infrastructure/vision/__init__.py`.
- `apps/control-plane/infrastructure/vision/model_batch.py` — shared dispatch qua protocol.
- `tests/test_gemini_vision_model.py`, `tests/test_vision_model_batch.py`.

Tham chiếu existing `VisionModelBatch` ở `apps/control-plane/infrastructure/workflows/vision_publisher.py`; chuyển logic dùng chung vào file mới, wiring/import compatibility hoàn tất phase 03. Không copy hai bản dispatch lâu dài.

## Behavior / data flow

1. Gemini adapter dùng httpx hiện có, injected transport cho test. POST chính xác `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`, Bearer key từ Settings, model từ validated policy. Không cho payload/kwargs override model hoặc authorization/endpoint.
2. Payload giữ messages/prompt tập trung và schema batch hiện tại; `response_format={"type":"json_object"}`, bounded `max_tokens`, temperature theo executor, `reasoning_effort="low"`. Không dùng minimal/none hoặc bật tool/computer-use của provider. Chỉ request dữ liệu để worker hiện có thực thi.
3. Timeout request là min(30 giây, thời gian session còn lại), có cancellation; không request nếu deadline đã hết. Một call duy nhất, không retry/fallback trong SDK/adapter. Thiếu key trả failure trước network.
4. Shared callable nhận session context, screenshot bytes, task intent, policy, max_candidates, guard, sequence và callback kiểm tra live policy; dùng input độc lập với SQLAlchemy để legacy/v4 cùng gọi. Mang remaining deadline rõ ràng. Protocol là nội bộ application, không duplicate runner/agent wire contracts.
5. Branch HF: giữ delivery GoogleDriveTemporaryImageStore và cleanup/check_policy hiện có. Branch Gemini: không khởi tạo Drive store, không refresh OAuth, không lấy URL remote; kiểm tra bytes trước base64, truyền image_url=None vào executor đã hỗ trợ data URI.
6. Check live policy ngay trước external transfer và khi model trả về trước dùng proposals. Byte/token/action giới hạn hiện tại vẫn bắt buộc. Không tăng policy budget chỉ để provider trả output.
7. Bổ sung trường nội bộ safe failure reason cho batch outcome với default để giữ fake callers; phân loại deterministic: `provider_not_configured`, `provider_auth_failed` (401/403), `provider_billing_required` (402), `provider_rate_limited` (429), `provider_model_unavailable` (404), `provider_timeout`, `provider_unavailable` (5xx/transport/khác), `model_output_invalid`. 403/429 không suy đoán chính xác account billing từ body; message UI phải thận trọng.
8. Không lưu raw provider exception body. Giữ allowlisted status/category và diagnostic code. JSON không hợp lệ, refusal, thiếu choices/content, truncated output hoặc action sai phải fail closed theo validator; không dựng action mặc định.
9. Bổ sung redaction cho raw Gemini-key-like string và data:image base64 nếu model echo chúng vào output; request không được đưa vào debug capture. Tests phải kiểm tra log/audit/debug safe summary không chứa sentinel key/ảnh.

## Contract/prompt

Giữ `packages/contracts/src/auto_at/contracts/vision.py` và worker contract nguyên vẹn. Dùng `agents/prompts/vision.py` version v4 nguyên hành vi; adapter không hard-code prompt riêng. Không cần đổi pyproject/uv.lock khi chỉ dùng httpx. Provider response version metadata nếu có chỉ allowlist để đánh giá; không giả vờ có immutable snapshot pin.

## Tests / commands

- MockTransport assert exact URL, method, authorization, chosen model, supported parameters, PNG data URI decode đúng bytes; kwargs không override model.
- Gemini success không chạm Drive dù OAuth thiếu/hỏng. HF vẫn upload/cleanup đúng và invalid_grant giữ safe reason hiện có.
- Byte cap/disabled/missing consent/key/deadline reject trước HTTP. Một request khi 429/5xx, không sleep retry.
- Valid batch/custom clickable, malformed JSON, refusal/truncated, bounds và giới hạn candidates. Secrets/data URI bị loại khỏi diagnostic capture.
- Fake live-policy callback đổi provider trước/giữa call: không sử dụng kết quả sai policy.

```powershell
uv run ruff check apps/control-plane/agents/shared apps/control-plane/agents/vision apps/control-plane/application/vision_model_batch.py apps/control-plane/infrastructure/vision tests/test_gemini_vision_model.py tests/test_vision_model_batch.py
uv run pytest tests/test_agent_runtime.py tests/test_vision_executor.py tests/test_gemini_vision_model.py tests/test_vision_model_batch.py tests/test_google_drive_temporary_images.py
```

## Exit criteria / risks / non-goals

Payload contract và no-Drive được chứng minh bằng mocks; không khẳng định real model đã đạt evaluation. Google có thể đổi support/limits: đối chiếu official docs lúc triển khai, không đổi model đã chốt âm thầm. Không thêm Google Files API, SDK, stream response, OCR/redaction pipeline hoặc retry infrastructure.
