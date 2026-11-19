STATUS: FAIL

# Plan review (leader) — browser-agent-loop
Convention: AGENTS.md (repo không có docs/code-standards.md). K1–K5 và impact.html không bị lật lại.

## BLOCKING
1. `total_candidates` không có phase nào sở hữu contract. Phase 2 bước 8 bắt worker trả nó, phase 4 dùng nó dựng marker `[refs a-b trimmed]` (AC5),
   nhưng phase 1 không thêm field vào `CodexDomObservation`/`CodexBoundObservation`/`VisualWorkerDomObservation`
   (`packages/contracts/.../codex_bridge.py:123-160`, `vision_worker.py:91-102`, closed model) và grep toàn repo không có `total_candidates`.
   Cách gọn: dùng field sẵn có `skipped_count` (codex_bridge.py:133, le=5000) + `truncated` → tổng = `len(elements)+skipped_count`; xác minh ngữ nghĩa
   `skipped_count` ở worker rồi bỏ bước 8. Hoặc giao field mới cho phase 1 và regenerate TS.
2. Test phase 4 "snapshot 300 element" không dựng được: `elements` max_length=100 (codex_bridge.py:130), `max_elements` le=100 (vision_worker.py:70).
   Trần 24 000 ký tự vẫn cắt được trong 100 phần tử; sửa số 300 và khoảng marker theo giới hạn 100 (+ `skipped_count`).
3. Ngân sách operation của worker không được xử lý: `budget() = 1 + max_states*(2*max_hops+3)` (vision-operations.ts:189), chặn
   `operation_budget_exhausted` ở :449; control-plane đối chiếu đúng công thức trong `HttpVisualWorker.open` (infrastructure/vision_worker.py:118-135, file không thuộc phase nào).
   Agent loop 20 lần gọi × tới 10 action có thể vượt budget do `max_states/max_hops` của policy. Phase 2 chỉ test "25 click không chạm hop/state limit".
   Plan phải chọn: agent mode đặt budget theo max_steps×10+overhead (sửa worker :189 và vision_worker.py:118-135, giao cho phase 2/1), hoặc ghi rõ policy
   bắt buộc cho session agent_loop. Thiếu bước này AC6 có thể chết bằng `operation_budget_exhausted`.

## SHOULD-FIX
- Trần 20 lần gọi (K1) nằm ở `min(max_calls, policy.max_steps)` (codex_candidates.py:103,114); `vision_max_steps` mặc định 3, le=20 (config.py:79).
  Phase 4 nói "hết 20 lần gọi → agent_step_limit" mà không nói 20 lấy từ đâu. Nêu rõ: dùng `policy.max_steps` (user đặt 20) hay ép khi tạo session agent_loop.
- Phase 5: "chỉ hiện khi API báo cờ bật" nhưng không endpoint nào trả cờ `vision_agent_loop_enabled`; phase 1 chỉ thêm `engine` vào `ExplorationResponse`
  (routes/vision.py:142-157). Thêm field vào `VisionPolicyReadResponse` (routes/vision.py:95) hoặc `VisionProvidersResponse` ở phase 1, hoặc bỏ gating (API trả 4xx).
- Phase 4 gọi `worker.open(agent_mode=True, ...)` nhưng không nói chỗ dựng `VisualWorkerOpen` (`vision_trace_events.py:218` là v4, cấm sửa theo AC7). Ghi rõ nằm trong `vision_agent_loop.py`.
- Phase 4 "repositories.py hoặc vision_unit_of_work.py": chốt `vision_unit_of_work.py` (phase 1 đã sửa file này), không đụng repositories.py.
- Phase 3: bridge đã có `dom` qua `spool.verify_inputs` (application/codex_bridge.py:60) và snapshot text trong `agent_context` → hai nguồn cho cùng snapshot.
  Nói rõ `build_prompt` dùng nguồn nào để ref `version:n` không lệch element id.
- Phase 6 `run.py`: engine được truyền qua `.pytest-artifacts/accuracy_round.py` (untracked), `run.py start` ít khả năng cần sửa; ghi nơi truyền engine thật để tránh sửa thừa.
- Phase 1 "nới enum nếu cần" cho back/navigate explore: `VisualWorkerPrepare.references` (vision_worker.py:177-200) không cấm back/navigate explore, nên không cần nới → bỏ để khỏi sinh diff TS thừa.
- AC5 nói trần "cấu hình" (24 000 ký tự, K=5) nhưng phase 1 chỉ thêm một cờ vào `config.py`. Thêm `vision_agent_snapshot_chars` ở config.py hoặc ghi hằng ở domain (AGENTS.md: config.py là nơi duy nhất đọc env).

## NIT
- Phase 1 `origin_policy ... (tên chốt khi làm)` còn mở — chốt hoặc bỏ (xem yagni).
- Danh sách từ khoá nhạy cảm nằm ở hai nơi (TS worker, Py domain): thêm test đối chiếu hoặc một nguồn truyền qua `VisualWorkerOpen`.
- Không phát hiện file trùng giữa các phase; `vision-provider-model.ts`/`generation-types.ts` đang `M` ở phase 0 nhưng chỉ phase 5 sửa → ổn nếu phase 0 chốt commit/để nguyên.
- Phase 6 phụ thuộc phase 5 (P2) dù AC6 không cần UI; chấp nhận được.

## Ponytail (over-engineering)
- yagni: phase 1 `VisualWorkerOpen.origin_policy` → `agent_mode` đủ (K3 chỉ có một chính sách ở agent mode); bỏ field + phần TS regenerate.
- yagni: phase 1 cột `visual_agent_steps.job_id`, `stop_reason` → đã có ở session/activity; giữ `snapshot_version`. Đụng schema đã duyệt trong impact.html — để user quyết.
- shrink: phase 1 `AgentLoopContext` history "≤ 5 bước × giới hạn byte" → `tuple[str, ...]` max_length=5 đã render sẵn; bỏ validator byte tự viết.
- shrink: phase 4 `OperationRunner`/`SnapshotRenderer` là hàm thuần trong cùng file, chỉ tách lớp khi file > ~400 dòng.
- shrink: phase 2 bước 6 (re-baseline form) → nếu bỏ batch `type A→B` thì bỏ được; đụng thiết kế bulk-action đã duyệt, để user quyết.
- delete: phase 6 `AGENT-LOOP-01-<date>.md` trùng nội dung với handoff README + ADR-038; giữ handoff một dòng (AGENTS.md bắt buộc), gộp số liệu vào ADR hoặc một báo cáo.
- native: phase 5 ảnh chụp 400px là việc của QA, không phải tiêu chí xong của dev.

## AGENTS.md
- Tầng (domain thuần, application điều phối): khớp. Prompt management (AGENTS.md:31): khớp (agents/prompts + README + version). Contract chung: khớp.
- config.py: lệch nhẹ ở trần snapshot/K (xem SHOULD-FIX cuối).
- Không có CONVENTION_CHANGE.
