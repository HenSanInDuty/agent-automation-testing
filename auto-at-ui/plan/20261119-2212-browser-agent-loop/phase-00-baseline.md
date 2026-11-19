---
phase: 0
title: "Ổn định nền"
status: in_progress
cook_step: B1
priority: P1
owner: be-developer-junior
qa: skip
dependencies: []
---
## Mục tiêu
Có baseline sạch trước khi sửa: ~55 file đang sửa dở trên nhánh `mantaray` (Claude bridge, RustFS read-after-write,
round 21, dashboard provider settings) nằm đúng trên đường đi của plan. Ghi lại baseline test để các phase sau so sánh.

## Database Impact
Không đụng.

## File liên quan
- Không tạo/sửa file sản phẩm. Chỉ đọc `git status`, chạy test, ghi báo cáo.
- Tạo: `tests/fixtures/v4_identity.json` (dữ liệu đối chứng, không phải code sản phẩm).
- Commit chỉ khi user chỉ định rõ (AGENTS.md / quy tắc git của phiên). Không tự commit.

## Luồng dữ liệu của phase này
Không có.

## Convention áp dụng
`AGENTS.md` mục "Required checks before helping" (git status, uv, ruff, pytest).

## Graph liên quan
Không. (Graph `vision-agent-loop`, `playwright-vision-worker` lập ở phase 1 / phase 2.)

## Các bước thực hiện
1. `git status --short` → liệt kê file đã sửa/chưa track trong vùng: `apps/control-plane/{application,infrastructure,agents,domain,api}/**vision*`,
   `**codex*`, `packages/contracts/**`, `workers/playwright/src/**`, `apps/dashboard/app/**`, `migrations/`.
2. Báo user danh sách và hỏi qua phiên chính: commit (message do user duyệt) hay để nguyên. Phase dừng ở đây nếu
   user chưa quyết.
3. Chạy baseline, lưu log vào `reports/phase-00/`:
   - `uv run ruff check .`
   - `uv run pytest` (chia nhóm ≤ 9 phút nếu cần; danh sách hồi quy vision ở `reports/survey/be-control-plane.md` §7.1)
   - `cd workers/playwright && npm.cmd run typecheck && npm.cmd test -- src/vision-operations.spec.ts src/vision-dom.spec.ts src/vision-history.spec.ts src/vision-locators.spec.ts --workers=1`
   - `pnpm --filter @auto-at/dashboard test`, `typecheck`, `lint`
4. Ghi `uv run alembic heads` (kỳ vọng `a4c6e8f01234`).
5. Ghi môi trường: PostgreSQL test có chạy không (`DATABASE_URL`), số test DB-gated bị skip — phase 1/4 cần DB thật để
   chứng minh migration và fence.
6. Ghi hash đối chứng v4 vào `tests/fixtures/v4_identity.json` (file test, tạo mới ở phase này, phase 1/3 đọc):
   sha256 `TypeAdapter(CodexOutput).json_schema()` (canonical JSON), sha256 prompt + schema `codex-dom-v11` cho một
   request mẫu cố định (dùng fixture có sẵn trong `tests/`). Lưu bản sao `vision-contract.generated.ts` hiện tại vào
   `reports/phase-00/` để phase 1 so diff. Script tạo hash lưu ở `reports/phase-00/v4_identity.py` để chạy lại được.

## Unit test phải viết
Không.

## Tiêu chí xong (checklist)
- [ ] User đã quyết commit/để nguyên cho các file đang sửa dở.
- [ ] Log baseline ruff/pytest/worker/dashboard nằm ở `reports/phase-00/` kèm số pass/fail/skip.
- [ ] Alembic head ghi lại.
- [ ] `tests/fixtures/v4_identity.json` có 2 hash; chạy lại script cho cùng kết quả; bản sao TS contract nằm ở `reports/phase-00/`.
- [ ] Môi trường DB ghi rõ (có/không, số skip).

## Rủi ro & tín hiệu nhận biết hỏng
- Baseline đã đỏ sẵn → ghi rõ test nào đỏ trước khi đụng code, để phase sau không bị đổ lỗi.
- Test DB-gated bị skip (69 skip ở round 21) → ghi số skip làm mốc.
