# Phase 05 — Regression, evaluation và rollout local

## Execution status

Completed: 2026-10-17 18:56 +07:00 (started 18:47 +07:00).
Added ADR-009, operator setup/failure/rollback guidance, a hashed synthetic
manifest and measured response-gate test. Added explicit div/span role=button
and offscreen-scroll browser evidence plus an isolated offline pytest harness.
No production benchmark or prompt changes were needed.

Final results: 560 Python tests, 31 dashboard unit tests, 10 dashboard browser
tests and 32 worker grounding/operation tests passed, with no skips. Three
configured-stack Compose tests excluded because they can invoke real providers.
Ruff, both typechecks, dashboard production build and diff checks passed.
See canonical README for exact commands/paths, warning details and cleanup.
All five phases are complete offline. Live canary remains not run.

## Mục tiêu / prerequisites

Sau phases 01–04, cung cấp bằng chứng fixture tái lập và runbook để bật/tắt Gehihi an toàn. Phân biệt integration tests offline với chất lượng provider thật; không dùng “free tier” như bảo đảm account không bị tính phí.

## Files

Sửa:
- `docs/vision-agent-operations.md`.
- `README.md` — setup Vision/provider và giới hạn.
- `tests/test_vision_benchmark.py`.
- `apps/control-plane/benchmark/vision.py` — chỉ thêm support manifest/evaluation fields nếu runner hiện tại cần.
- Các tests đã tạo ở phases trước nếu phát hiện regression.

Thêm:
- `docs/adr/009-gehihi-vision-provider.md`.
- `benchmark/vision/gehihi/manifest.json` — synthetic cases, expected invariants và nguồn fixture.
- `benchmark/vision/gehihi/README.md` — cách chạy, kết quả/skip và trạng thái canary.

Chỉ khi cần thay hành vi prompt sau evaluation: `apps/control-plane/agents/prompts/vision.py`, `apps/control-plane/agents/prompts/README.md` và tests executor/benchmark liên quan; bump version cùng lúc. Không sửa prompt ở caller.

## Evaluation offline bắt buộc

1. Manifest chỉ synthetic/local: native button, link, div/span role=button, disabled control, offscreen control cần scroll, nhiều sibling candidates, stop, invalid JSON, refusal, out-of-bounds, 429 và policy revoke. Tái sử dụng fixture locator/BFS hiện có; không scrape website bên ngoài.
2. Ghi provider/model, prompt version, transport, fixture hash/version, execution date; response giả được đánh dấu mocked. Đo schema validity, normalized coords, locator conversion và trace completeness riêng, không suy ra exhaustive coverage từ số click.
3. Regression phải chứng minh non-button click được chuyển thành deterministic worker operation và before/after lưu đúng; invalid output không tạo operation; lỗi provider giữ failure reason và không lặp unknown browser action.
4. Full Python baseline và TS/build, dùng fixtures cô lập/no real provider credentials. Ghi số pass/fail/skip thực tế; không báo kết quả dự kiến như đã chạy. Không phát sinh benchmark đụng app DB.
5. Nếu fixture cho thấy token budget hiện tại quá nhỏ cho real model, ghi hạn chế và chờ canary; không tự tăng guard hoặc đổi model. Mọi thay đổi prompt có version/evaluation riêng.

## Commands / acceptance

```powershell
uv run ruff check .
uv run pytest
pnpm --filter @auto-at/dashboard typecheck
pnpm --filter @auto-at/dashboard test
pnpm --filter @auto-at/dashboard build
pnpm --filter @auto-at/playwright-worker typecheck
pnpm --filter @auto-at/playwright-worker test src/vision-dashboard.spec.ts
```

Theo `docs/vision-agent-operations.md`, chuẩn bị disposable PostgreSQL fixture 127.0.0.1:55437 và dashboard fixture local trước chạy. Đảm bảo test settings không nạp provider credentials thật; không dùng raw .env để tạo test configuration. API network dùng mock transport. Full baseline có skip ngoài scope phải ghi rõ; provider/tenant/durable/browser scenarios của plan không được skip khi nghiệm thu.

## ADR/runbook cần ghi rõ

- Lý do chọn Gehihi do user xác nhận, official model ID và ngày kiểm tra docs; bổ sung ADR-007/008, không rewrite quyết định lịch sử.
- Settings key server-only; các service control-plane và temporal-worker cùng nhận env_file Compose hiện có. Chỉ thêm placeholder .env.example, không đưa key vào docs.
- Catalogue configured chỉ là có key; không chứng minh credential/quota. Nếu thay key môi trường, cần recreate/restart đúng services để đọc Settings mới; hướng dẫn chứ không chạy production.
- Tenant admin: chọn Gehihi, model, consent, guards, enable/save; submit xác nhận recipient. Tenant override ưu tiên hơn env; không hướng dẫn chỉ đổi VISION_PROVIDER rồi tưởng tenant đã đổi.
- Screenshot raw có thể chứa PII và free-tier Google có điều kiện sử dụng dữ liệu; synthetic demo only. HF vẫn có đường Drive riêng; Gemini không yêu cầu OAuth Drive.
- Giữ durable RustFS retention hiện tại, encrypted debug retention hiện tại, RBAC/audit/correlation; không chọn production SLO/retention mới.
- General text model/draft không đổi; nếu draft gặp HF402, đó là bước riêng cần xử lý riêng, không tự fallback.
- Các safe reason, chỗ xem trace đã lưu, quota ở Google AI Studio và cách tắt tenant; không log request/key/body.
- Giới hạn hiện tại: local rate/step/time guards không đảm bảo quota chung toàn Google project hoặc kiểm soát tiền; max_cost_usd chỉ metadata.

## Rollout và canary

1. Merge/deploy chỉ sau offline acceptance; giữ defaults HF/disabled và flag v4 hiện tại.
2. Operator tự cấp GEMINI_API_KEY từ project free tier, xác nhận quota và phạm vi dữ liệu; không bật billing. Không yêu cầu người dùng dán key vào chat.
3. Admin của tenant demo lưu consent/provider/model; không sửa tenant khác. Deploy cả API và worker trước enable để tránh worker cũ đọc config mới.
4. Canary API thật chỉ chạy khi user yêu cầu demo và đã có safe target/key/quota. Giới hạn 1 session synthetic, max_steps=3, max_requests_per_minute=5, max_session_seconds=120, không retry tự động. Không cho phép fallback.
5. Kiểm tra đúng recipient/model, không có Drive call, có thao tác sau navigate nếu model sinh candidate, before/after, failure reason, draft boundary và audit. Kết quả canary có thể fail quota/output; ghi trung thực, không đổi verdict.
6. Nếu chưa được yêu cầu/thiếu readiness, đánh dấu canary “not run” riêng; offline implementation có thể complete nhưng chưa được coi live-demo validated. Không cần chạy canary để chứng minh mock integration.

## Rollback

- Dừng nhận session mới bằng disable policy cho tenant bị ảnh hưởng; drain hoặc stop session đang chạy theo cơ chế hiện có, không replay thao tác chưa biết kết quả.
- Sao lưu non-secret overrides và kiểm tra tenant scopes. Nếu chỉ tắt Gehihi trên binary mới: chọn HF với consent HF được xác nhận và model cũ, hoặc giữ disabled; không tự chuyển session.
- Nếu hạ binary cũ: trước downgrade, chuẩn bị override tương thích schema cũ cho từng tenant bị sửa. Xóa field raw_screenshot_transfer_provider khỏi vision JSON, chuyển gemini sang disabled HF/model trước đó, giữ các section runtime khác. Làm tương tự env provider/binding mới nếu có; không enable HF bằng consent Google.
- API/worker cũ không được đọc override Gemini/field mới vì extra=forbid. Verify runtime deserialize bằng fixture trước hạ phiên bản; không cần SQL migration hoặc xóa lịch sử.
- Giữ sessions/actions/artifacts/audit; historical provider string gemini vẫn phải đọc được. Lưu dấu vết rollback, không xóa evidence.

## Exit criteria / non-goals

Tất cả tiêu chí README có offline evidence; ADR/runbook và rollback được review; canonical phase statuses phản ánh đúng tests đã chạy. Không tự triển khai production, bật paid tier, đổi model, chỉnh retention, xóa dữ liệu hoặc hứa free-tier availability.
