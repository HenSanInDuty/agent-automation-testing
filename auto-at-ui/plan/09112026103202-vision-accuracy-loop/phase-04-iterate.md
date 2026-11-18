# Phase 04 — Chạy, phân tích, sửa, chạy tiếp

## Mục tiêu và prerequisites

Phase 01–03 có oracle/harness/fix đã kiểm chứng. Codex thực hiện vòng cải thiện
trong workspace, cập nhật README chuẩn sau từng vòng; không cần hỏi lại cho mỗi
test/fix/rebuild local/live run nằm trong quyền đã có khi người dùng yêu cầu execute.

## Source/artifact scope

- `benchmark/vision/accuracy/run.py`, `evidence.py`, `metrics.py`.
- `benchmark/vision/accuracy/runs/<iteration-id>/`: provenance, hypothesis, score.
- Các file sửa theo loại lỗi: `application/vision_trace_events.py` (orchestration),
  `domain/vision_coverage.py` (identity/inventory), `infrastructure/vision_worker.py`
  (transport), worker `vision-dom.ts`, `vision-revalidation.ts`,
  `vision-operations.ts`; matching tests phải đi cùng.
- Nếu lỗi planner được chứng minh: `apps/control-plane/agents/prompts/codex_exploration.py`
  và prompt `README.md`; tăng version, chạy fixtures/eval tương ứng.
- `benchmark/vision/codex/manifest.json` cho provenance; README kế hoạch cho tiến độ.
  Không sửa mọi file kể trên nếu chưa có evidence.

## Một vòng cụ thể

1. Chọn đúng một giả thuyết từ lượt terminal gần nhất, nêu evidence và dự đoán.
2. Tạo test tái hiện cô lập, xác nhận fail đúng lý do. Đánh giá tác động tới
   mục tiêu chưa bao phủ và chi phí; ưu tiên lỗi chặn nhiều nút.
3. Sửa tối thiểu; test lỗi và adverse cases phải qua. Nếu regression fail thì
   chưa triển khai và chưa dùng live làm debugger cho lỗi đã tái hiện được.
4. Ghi source/config/oracle hashes. Drain; build/redeploy services có thay đổi
   qua `docker-compose.yml` + `docker-compose.codex.yml`, giữ volume và mount.
   Kiểm health và mã deploy khớp workspace.
5. Chạy một reload bằng harness. Không chạy regression browser song song.
   Đợi terminal, thu evidence, chấm độc lập; run không terminal chưa có final score.
6. So với baseline và vòng trước: missing IDs, exact wrong targets, drift stage,
   các budget dùng, calls, thời gian, reject/unknown/missing frames.
7. Nếu chưa >95%: viết nguyên nhân kế tiếp và quay bước 1. Nếu đạt, chuyển phase 05.
   Nếu phase 05 fail, quay đây, giữ toàn bộ qualification thất bại.
8. Sau 5 vòng không cải thiện, tổng hợp failure clusters và thay giả thuyết/fixture;
   không chỉ bơm thêm timeout/calls hoặc reload may rủi. Không dừng ở một bản fix
   khi vẫn có thể tiến bộ trong quyền hiện tại.

Unknown physical action: reconcile cùng operation, không retry side effect.
Quota/provider outage: ghi sự cố, chỉ retry theo policy hiện hữu, không đổi model/
bật billing. Giới hạn cấu trúc 50 states: đo và giảm redundant work trước;
nếu vẫn cần tăng policy thì đưa số liệu và xin user direction, không lách cap.

## Contract, validation, acceptance

Giữ execution v1. Prompt/private transport đổi thì cập nhật manifest, version,
compatibility tests và rollout tương ứng. Không migration trừ phát hiện có lý do,
lúc đó cập nhật plan trước khi làm.

Mỗi vòng chạy `uv run ruff check .` + focused `uv run pytest ...` hoặc isolated
`uv run python benchmark/vision/codex/run_offline.py ...` theo fixture dependencies.
Worker đổi thì typecheck + spec liên quan; dashboard chỉ kiểm khi thực sự đổi.
Không cần full suite mỗi vòng khi focused đã đủ; phase 05 chạy broad suite cuối.

Acceptance phase: có ít nhất một lượt đạt toàn bộ metric/safety gates, hypothesis
và fix có red→green evidence, không pending operations, score reproducible.
Đây chưa phải hoàn thành toàn kế hoạch. Ngoài phạm vi: UI redesign, provider
migration, website mutation, tự approve generated suites.


## Completion 2026-11-17

Round 16 (`fd3ddda4-ca69-4abb-818b-a8ac1ad594d8`) passes all independent metric/safety gates: C=46/47, A=46/48, detection P=46/48, R=46/47, complete inventory, no unsafe/unsettled operations. ADR-031/032/033 preserve original checkpoint/node/form guards; red/green and regression artifacts are linked in canonical README. Runtime remains unavailable/unsafe_replay. Phase 05 is unlocked; no final qualification claim yet.

## Reopened after round 17, 2026-11-17

First fresh qualification attempt `56e50d4d-2be0-433b-98ad-2eab68d7773f`
failed. Operation 26 binds carousel indicator 4 but its retained after-frame shows
indicator/slide 5. Autoplay during click-to-capture is a hypothesis, not proof of
a wrong physical target. With this outcome unverified and two other noncreditable
attempts, the maximum credit supported by available evidence is 44/47 (93.62%).
Reproduce this timing boundary locally before a scoped fix and negative tests;
do not disable site autoplay, alter oracle labels or infer success from completed.
Keep the separate final history_checkpoint_unavailable/unsafe_replay failure in
scope for diagnosis. The user requested a fresh-session handoff after each round,
so no new implementation or live run begins in the round 17 conversation.


## Pre-round-20 remediation completed, 2026-11-18

The three retrospective priorities are implemented and validated offline: current target/proposal identity, bounded representative outcome capture, and the unified restoration evidence matrix. See ADR-036 and `benchmark/vision/accuracy/pre-round20-validation-20261118.json` for source provenance, red/green results and negative guards. The canonical README records the handoff. No deployment or round 20 occurred. This implementation unit is complete; phase 04 remains open pending live outcome review and qualification. Do not infer that mct-47 or live accuracy is repaired.


## Round 20 failed, 2026-11-18

ADR-036 candidate deployed and one live round completed. Coverage ceiling 31/47 fails; operation 85 has an unknown controller outcome after worker success and an orphan after-image in RustFS. Six early carousel images were retained within 500 ms. See canonical README and ROUND20-20261118.md for bounded evidence and the after-frame commit diagnostic handoff. Phase remains open; no round 21 started.
