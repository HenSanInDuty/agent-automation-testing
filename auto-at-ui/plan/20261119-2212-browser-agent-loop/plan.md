---
title: "Engine agent loop cho Vision (browser-agent closed loop)"
status: pending
created: 2026-11-19
slug: browser-agent-loop
auto_continue: false
progress_url: ""
---

# Engine agent loop cho Vision

Artifact phạm vi & luồng (đã duyệt 2026-11-19, theo mọi đề xuất mục K/L): https://claude.ai/artifact/BCxug7E5uWx9zym2wxfZLd
(file nguồn: `impact.html`). Khảo sát: `reports/survey/*.md`. Paper: `../../../docs/Ref/Building-Browser-Agent.pdf`.

## Contract

**Outcome.** Chọn `engine=agent_loop` khi tạo session Vision. Mỗi bước: worker trả snapshot mới (ref `version:n`),
model trả `evaluation_previous_goal`, `memory`, `next_goal` và 1..N action (hoặc done/stop/need_screenshot).
Control-plane kiểm an toàn bằng code, chạy từng action qua `ExecuteVisualOperation` (frame before/after), dừng batch
khi trang đổi, ghi step log, lặp. Không restore/replay: agent đi tiếp từ trang hiện tại; `back` và `navigate` (về
target) là action của model. Engine planner (v4) giữ nguyên và là mặc định. Test case "click hết control" mongchiton
chạy như một task bình thường, chấm bằng benchmark độc lập như cũ.

**Constraints.** Quy tắc tầng `AGENTS.md`; prompt chỉ ở `apps/control-plane/agents/prompts/` có version + README;
contract chung ở `packages/contracts`; Python qua `uv`. v4 không đổi hành vi và không đổi schema hash `codex-dom-v11`;
mọi nới guard ở worker đặt sau cờ agent mode. Provider giữ nguyên (`codex_cli`, `claude_cli`). Evidence tương thích
`benchmark/vision/accuracy/run.py collect/evaluate`; `metrics.py` + oracle không đổi. Ngân sách: tối đa 20 lần gọi
model/session (giữ trần hiện tại), rate/phút, thời gian session, trần ký tự snapshot.

**Quyết định đã chốt (Gate 2, mục K).**
- K1: giữ trần 20 lần gọi model; đo ở phase 6, nếu thiếu thì lập plan riêng nâng trần cho agent loop.
- K2: đợt đầu chỉ dùng action kind có sẵn: click, type, scroll, wait, back, close_popup, navigate (về target_url).
- K3: allowlist = `allowed_origins` của project. Điều hướng/popup ngoài allowlist được mở để quan sát; mọi action
  trên trang ngoài allowlist bị chặn trừ `close_popup`/`back`; sub-resource (ảnh, CDN, XHR) không chặn.
- K4: ở agent mode, dialog/download do chính action gây ra được ghi lại, huỷ và báo model; `action_outcome_unknown`
  vẫn khoá session như v4.
- K5: step log theo `intent_retention_until` của session; reload giữ engine của session gốc.

**Non-goals.** Model nhẹ cắt snapshot; endpoint snapshot-range/batch ở worker; `ariaSnapshot()` làm ref; giữ phiên CLI
sống; multi-tab; cột allowlist theo session; tool hover/press_key/select_option/wait_for text/navigate URL tuỳ ý;
nâng trần 20 lần gọi; đổi metrics/oracle; bỏ hay viết lại v4; cam kết miễn nhiễm prompt injection.

**Ngân sách gọi model.** Trần = `min(policy.max_steps, 20)` (tenant policy `vision_max_steps`, le=20, mặc định 3 —
chạy benchmark đặt 20). Mỗi lần gọi bridge đều tính vào trần, kể cả lần retry do sai schema và lần gọi stage image
(`need_screenshot`), giống v4 và khớp CHECK `ck_codex_job_sequence BETWEEN 1 AND 20`.

**Acceptance criteria.**
1. Session `agent_loop` chạy vòng lặp; mỗi lần gọi model chỉ nhận snapshot mới nhất + memory + K bước gần nhất
   (K = 5); step log lưu `step_index`, evaluation/memory/next_goal, `actions` (mỗi action có `result` hoặc
   `skipped_reason`) và `operation_ids`; action bị chặn/bỏ qua có trong `actions`, không có trong `operation_ids`
   (`len(operation_ids) <= len(actions)`).
2. Ref sai regex ⇒ `invalid_ref`; ref có version ≠ snapshot hiện tại hoặc không có trong map ⇒ `stale_ref`; với các
   action đó số request prepare/execute tới worker = 0.
3. Chặn bằng code, ghi lý do vào step log, số hành động trình duyệt = 0:
   - control-plane (`domain/vision_agent_safety.py`): kind ngoài 7 kind; mọi kind trừ `close_popup`/`back` khi trang hiện
     tại ngoài allowlist (`origin_blocked`); `input_type ∈ {submit, reset}` hoặc tên khớp từ khoá (`sensitive_action_blocked`);
   - worker (agent mode, lớp hai): như trên, cộng `a[download]` và nút submit của form (thông tin control-plane không có).
   Danh sách từ khoá có một nguồn (domain Python) truyền xuống worker qua `VisualWorkerOpen`. Không có action nhấn phím
   (K2) nên `type` không gửi Enter/submit form.
4. Với mỗi điều kiện trong {`url_change`, `state_fingerprint` đổi không do re-baseline form, popup mới, download,
   op status ≠ `completed`}: các action sau trong batch có 0 request tới worker và bước kế gọi `observe_dom` đúng 1 lần.
   Batch `type A` rồi `type B` trên cùng form (chỉ giá trị form đổi) chạy cả hai.
5. Phần snapshot trong prompt ≤ `vision_agent_snapshot_chars` (config, mặc định 24 000, đo bằng `len(str)`); khi cắt có
   marker `[refs a-b trimmed]` với a, b đúng ref bị cắt, và `skipped_count` của worker được báo thành "N control ngoài
   snapshot". Phần lịch sử có độ dài ≤ hằng số cố định (memory ≤ 2 000 ký tự + 5 dòng lịch sử đã giới hạn), không phụ
   thuộc số bước đã chạy.
6. Task click-hết-control mongchiton chạy trên `agent_loop`: session terminal với reason ∈ {`agent_done`,
   `agent_stopped`, `agent_step_limit`, `session_timeout`} (≠ `unsafe_replay`); `run.py collect` + `evaluate` thoát 0 và
   sinh `score.json`; `git diff --exit-code -- benchmark/vision/accuracy/metrics.py benchmark/vision/accuracy/oracle-mongchiton-1280-v1.json`
   thoát 0; không target oracle nào bị `sensitive_action_blocked`. Điểm C/A được báo cáo, không đặt ngưỡng.
7. Bộ test hồi quy v4 (Python + worker + dashboard) xanh hoặc chỉ đỏ đúng các test đã đỏ ở baseline phase 0;
   request không có `engine` tạo session planner như trước; sha256 schema `CodexOutput` và prompt + schema
   `codex-dom-v11` cho request mẫu khớp giá trị ghi ở phase 0; diff của `vision-contract.generated.ts` chỉ gồm
   `agent_mode` và `blocked_action_terms`.

## Phase

| # | Phase | Trạng thái | Phụ thuộc | Owner | QA |
|---|---|---|---|---|---|
| 0 | [Ổn định nền](phase-00-baseline.md) | pending | — | be-developer-junior | skip |
| 1 | [Contract + DB + chọn engine](phase-01-contract-db-engine.md) | pending | 0 | be-developer | required |
| 2 | [Worker agent mode](phase-02-worker-agent-mode.md) | pending | 1 | be-developer | required |
| 3 | [Prompt + bridge](phase-03-prompt-bridge.md) | pending | 1 | be-developer | required |
| 4 | [Agent loop processor + safety](phase-04-agent-loop-processor.md) | pending | 1, 2, 3 | be-developer | required |
| 5 | [Dashboard](phase-05-dashboard.md) | pending | 1, 4 | fe-developer-junior | required |
| 6 | [End-to-end + benchmark + docs](phase-06-e2e-benchmark-docs.md) | pending | 2, 3, 4, 5 | be-developer | required |

Phase 2 và 3 chạy song song được sau phase 1; phase 5 sau phase 4. Mỗi file chỉ thuộc một phase.

Soi plan: `reports/plan-review/leader.md`, `reports/plan-review/qa.md` (cả hai FAIL ở bản đầu; đã sửa theo mọi phát hiện
không cần user quyết — xem mục "Sửa sau review" cuối file).

## Sửa sau review
- `total_candidates` bỏ; dùng `skipped_count` có sẵn (`codex_bridge.py:133`). Test 300 element đổi thành test renderer
  với 100 element tên dài + `skipped_count` lớn.
- Ngân sách operation của worker (`1 + max_states*(2*max_hops+3)`, `vision-operations.ts:189`, kiểm lại ở
  `infrastructure/vision_worker.py:118-135`): phase 4 mở worker với `max_states`/`max_hops` sao cho budget ≥ 401
  (= 1 + 20 lần gọi × 10 action × 2) và có test; không đổi công thức.
- Nguồn trần 20 lần gọi, retry và `need_screenshot` tính vào trần: ghi ở mục "Ngân sách gọi model".
- Cờ cho dashboard: phase 1 thêm `agent_loop_enabled` vào response đọc vision policy.
- `VisualWorkerOpen` của agent loop dựng trong `vision_agent_loop.py`; đọc step log nằm ở `vision_unit_of_work.py` (phase 1).
- Phase 3: prompt dùng snapshot đã render trong `agent_context`; `dom` qua spool chỉ để kiểm toàn vẹn.
- Bỏ `origin_policy` (agent mode chỉ có một chính sách K3); thêm `blocked_action_terms` (một nguồn từ khoá).
- Bỏ nới enum purpose (contract đã cho back/navigate explore); `AgentLoopContext.history` = tuple chuỗi đã render, max 5.
- Trần snapshot vào `config.py` (`vision_agent_snapshot_chars`).
- Phase 0 ghi hash đối chứng v4; phase 3 đổi `qa: required`; phase 5 thêm e2e UI, bỏ ảnh chụp khỏi tiêu chí dev;
  phase 6 không sửa `run.py` (engine truyền qua helper chạy vòng).
- Giữ nguyên (đụng schema đã duyệt, chờ user nếu muốn đổi): cột `job_id`, `stop_reason` của `visual_agent_steps`;
  re-baseline form cho batch `type A → type B`.
