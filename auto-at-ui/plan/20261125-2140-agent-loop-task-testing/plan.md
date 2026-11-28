---
title: "Agent loop làm engine test theo task cho FE của người dùng"
status: completed
closed: 2026-11-28
created: 2026-11-25
slug: agent-loop-task-testing
branch: feat/agent-loop-task-testing
auto_continue: false
progress_url: https://claude.ai/artifact/CMp25LMe3Mx8M2rW78Dgmu
---

# Agent loop làm engine test theo task

File này là điểm vào cho phiên mới. Đọc file này trước, rồi `docs/adr/046-agent-loop-task-testing.md` khi cần
lý do của một quyết định. Không cần đọc lại lịch sử plan cũ.

## Mục tiêu (người dùng chốt 2026-11-25)

Test được các task UI trên FE do người dùng sở hữu (dev/staging), kết quả ổn định giữa các lần chạy.
Mục tiêu cũ (">95% mọi control trên mongchiton") không còn là thước đo.

**Bổ sung 2026-11-26 (user, trong phase 05):** `mongchiton.vn` là trang chuẩn để đánh giá engine, nguyên văn "mongchiton mới là
web chuẩn, vì tôi sẽ làm việc trên web đấy". Fixture cục bộ vẫn là bộ đo hồi quy, nhưng ổn định trên fixture chưa phải đích. Trang
này là production: cờ FE test tắt, task chỉ đọc, cho tới khi user đưa origin staging/test. Kết quả hiện tại ở mục "Kết quả trên
mongchiton.vn".

Hai quyết định của người dùng: (1) mở lại engine `agent_loop` làm engine test theo task, planner v4 giữ nguyên
và vẫn là mặc định; (2) project được đánh dấu "FE test của tôi" thì cho submit form và nhập dữ liệu test.

## Đóng plan (2026-11-28, user quyết)

Plan đóng sau phase 17. Mọi phase 01–17 (kèm 15b, 15c) `completed`; code phase 02–17 và h-fix ADR-048 đã commit trên nhánh
`feat/agent-loop-task-testing` (chưa push). `reports/` cố ý không commit; `benchmark/vision/accuracy/run.py` (diff ADR-043,
plan vision-accuracy) và `benchmark/vision/visual-buttons/offline-result.json` (test ghi đè) để ngoài commit.

Đạt được: trên fixture `task-ui`, 3 test sinh từ phiên agent-loop và đã duyệt chạy lại 15/15 `passed` qua `POST /runs`; trên
mongchiton.vn sau h-fix ADR-048, 15/15 phiên `completed`, nhất quán 93%, nhưng đúng kỳ vọng 9/15 (kỳ vọng `home-license` nhiều khả năng
sai, chưa đối chiếu bằng mắt). Luồng bản nháp Playwright chưa chạy trên mongchiton.

Nợ chuyển ra ngoài plan (chưa lập phase/plan nào):
- **F4**: `search-results` không assert kết quả tìm. Nguyên nhân ở worker `workers/playwright/src/vision-dom.ts:46-48` (không đọc
  `<li>`); kết quả còn chứa từ khoá đã gõ nên cờ F5 cũng loại → cần mở rộng bộ chọn chữ trang + quy tắc riêng
  (`reports/phase-17/be-developer-r1.md`, `user-answers-r1.md`). Chỉ lập nếu mongchiton có task tìm kiếm cần kiểm.
- Quy tắc overlap của `derived_from_typed` chưa chuẩn hoá Unicode NFC (`reports/phase-17/qa-r1.md`).
- Phiên lưu trước phase 17 không có cờ `derived_from_typed`; draft từ phiên cũ giữ hành vi F5 cũ.
- Đối chiếu bằng mắt kỳ vọng `home-license` trên mongchiton; thử luồng draft trên một task chỉ đọc của mongchiton.
- `ruff check .` đỏ E501 `benchmark/vision/accuracy/run.py:292` (ADR-043, ngoài plan); dashboard image cũ.

## Trạng thái khi dừng (2026-11-25)

- **Code đã commit ngày 2026-11-26** trên nhánh `feat/agent-loop-task-testing`: 5 commit `5a9d713`..`d7d2b06`
  (phase 01), chưa push. Thư mục `reports/` của plan này cố ý chưa commit.
- **DB cục bộ đã ở migration `c8d0e2f4a6b8`**. Stack build từ `develop` không khởi động được cho tới khi
  nhánh này được merge, hoặc DB được downgrade về `b7c9d1e3f5a7` từ chính nhánh này.
- **Stack đang chạy** bằng code của nhánh (4 file compose, xem "Cách chạy"). Project "Task UI fixture" đã có
  trong tenant `demo-tenant`, policy đã bật `vision_owned_test_target`.
- Docker trên máy là engine **Kiri (WSL2)**, không phải Docker Desktop.
- **Từ 2026-11-26: container `auto-at-ui-playwright-worker-1` đang chạy với 2 GiB** (`docker update --memory 2g`, user chọn giữ tạm
  thời). `docker-compose.yml` vẫn ghi 1 GiB, nên tạo lại container sẽ quay về 1 GiB. Token bridge Claude xuất lại cùng ngày.

## Đã làm

| Việc | Ở đâu |
| --- | --- |
| Phiên agent kết thúc `completed` + `task_assessment` (achieved / not_achieved / blocked / inconclusive, checks, số liệu controller đo). Advisory, không phải verdict | `domain/vision_task_assessment.py`, `application/vision_agent_loop.py`, `vision_unit_of_work.py::finish`, `vision_results.py` |
| Đầu ra mới của agent `task_result`; planner (`codex-dom-v11`) không đổi | `packages/contracts/.../codex_bridge.py` |
| Prompt `agent-loop-v3`: đọc task thành kỳ vọng, kiểm từng hiệu ứng, xin ảnh chụp trước khi kết luận về chữ, kết thúc bằng `task_result` | `agents/prompts/agent_loop.py` + README |
| Mất một lượt gọi model / trang chưa đứng yên không giết phiên (thử lại có giới hạn) | `vision_agent_loop.py` |
| Cờ project `vision_owned_test_target`: submit form, gõ tài khoản test, thấy và gõ ô mật khẩu | migration `c8d0e2f4a6b8`, `routes/generation.py`, `vision_agent_safety.py`, worker `vision-operations.ts` / `vision-dom.ts` / `vision-locators.ts` (capability `owned-test-target-v1`) |
| Đọc lại spool khi file bị thay giữa lúc đọc (`ENODATA`, `ESTALE`, link count lạ lúc rename) | `infrastructure/codex_bridge/spool.py`, `doctor.py` (heartbeat) |
| Mở phiên worker chờ worker đang khởi động (1 + 2 + 4 giây, chỉ khi chưa kết nối được) | `infrastructure/vision_worker.py` |
| Doctor nhận diện container không có `/.dockerenv` (người dùng duyệt) | `doctor.py::inside_container` |
| Spool trên volume Linux cho engine Kiri | `docker-compose.spool-volume.yml` |
| Dashboard: panel đánh giá task, ô bật cờ FE test, nhãn engine | `apps/dashboard/app/components/vision-task-assessment*.ts(x)` và các file liên quan |
| FE mẫu cục bộ + bộ task + bộ đo | `benchmarks/targets/task-ui`, `benchmarks/task-ui/tasks.v1.json`, `benchmark/task_ui/stability.py`, `scripts/run_task_stability.py`, `docker-compose.agent-loop.yml` |

## Kết quả đo trên fixture (10 task, `claude_cli / claude-opus-5-5`)

| Lượt | Phiên | `completed` | Nhất quán | Đúng kỳ vọng | Ghi chú |
| --- | ---: | ---: | ---: | ---: | --- |
| r1 | 10 | 9 | n/a | 8 | 1 phiên hỏng do worker vừa khởi động lại; `login-failure` bị `not_achieved` sai vì snapshot không có chữ |
| r2 (2 lần/task) | 20 | 19 | 100% | 19 | 1 phiên `bridge_offline` do tranh chấp đọc heartbeat, sửa sau lượt này |
| r3 (3 task từng lỗi, code cuối) | 3 | 3 | n/a | 3 | lượt xác nhận, không phải lượt đo đầy đủ |
| r4 (5 lần/task, prompt `agent-loop-v4`) | 50 | 50 | 98% | 49 (98%) | HEAD `d7d2b06` + thay đổi chưa commit của phase 02-03; prompt v4 nên không so trực tiếp với r1–r3 (v3); 1 phiên `search-results` `not_achieved` sai; trung bình 2,32 lượt gọi model/phiên (5 lượt ảnh trong 50 phiên) |

Mỗi phiên 25–61 giây, khoảng 3 lần gọi model. Dữ liệu ở `.pytest-artifacts/task-stability/r1|r2|r3` (gitignore).
**Ổn định** trên fixture cục bộ theo ngưỡng của bộ đo (r4: `completed` 100% và nhất quán 98%, cùng ≥ 90%), chỉ cho `claude_cli / claude-opus-5-5` và trang đơn giản.

Kiểm thử đã chạy: `ruff` sạch; các nhóm test Python liên quan qua (715 + 359 + các nhóm nhỏ); 213 spec worker
qua; dashboard unit/typecheck/lint qua và spec dashboard qua với dữ liệu giả. Bộ test Python **chưa chạy trọn
một lượt** (bị dừng ở 87% vì giới hạn 40 phút).

## Kết quả trên mongchiton.vn (phase 05, 2026-11-26)

3 task chỉ đọc trên trang chủ (`home-requirements` và `home-license` kỳ vọng `achieved`, `home-missing-shop` kỳ vọng
`not_achieved`), project `Project-MCT` (`8f2d5531-f00d-4ce9-981e-f4b626657818`), cờ `vision_owned_test_target` tắt,
`claude_cli / claude-opus-5-5`, prompt `agent-loop-v4`, HEAD `d7d2b06` + thay đổi chưa commit của phase 02-03.

| Lượt | RAM worker | Phiên | `completed` | Đúng kỳ vọng | Lý do các phiên còn lại |
| --- | --- | ---: | ---: | ---: | --- |
| r1 | 1 GiB | 6 | 0 | n/a | 6 `bridge_model_unavailable` (token bridge hết hạn; không tính vào tỉ lệ) |
| r2 | 1 GiB | 6 | 1 | 1/1 | 4 `state_changed_during_observation`, 1 `state_mismatch`; `memory.events max` 2505 luỹ kế r1 + r2 (trước r1 là 0, không tách được riêng r2) |
| r3 | 2 GiB | 6 | 3 | 3/3 | 3 `state_changed_during_observation`; đỉnh 0,87 GiB, 0 lần chạm trần |
| r4 | 2 GiB | 15 | 1 | 0/1 | 10 `state_changed_during_observation`, 4 `state_mismatch`; đỉnh luỹ kế 0,90 GiB, 0 lần chạm trần |

| r5 (sau h-fix, code vòng 1) | 2 GiB | 15 | 14 | 10/14 | 1 `initial_capture_failed` (lệnh dừng đồng hồ ném lỗi; sửa ở vòng 2) |
| r6 (sau h-fix, code vòng 2) | 2 GiB | 15 | 14 | 9/14 | 1 `initial_capture_failed` (trần 1 s của lần settle thứ hai; sửa ở vòng 3) |
| r7 (sau h-fix, code cuối) | 2 GiB | 15 | 15 | 9/15 | không có; 0 dòng `vision.state.mismatch`; đỉnh 0,80 GiB |

**Sau h-fix 2026-11-27 (ADR-048, chưa commit): ổn định theo ngưỡng của bộ đo ở r7** (`completed` 15/15, nhất quán 93%). "Đúng kỳ vọng"
thấp vì `home-license` 14/14 phiên chạy xong đều `not_achieved`: chữ "Mộng Chí Tôn" chỉ có trong `<title>`/meta của trang chủ, agent
báo đầu trang chỉ có logo "Võ Lâm Chân Mệnh", nên kỳ vọng `achieved` của suite nhiều khả năng sai (chưa ai đối chiếu bằng mắt). Chi
tiết, số đo và nợ: `plan/20261126-2020-fix-agent-loop-autoplay-state/` (`impact.html`, `qa/test-report.md`). Đoạn dưới đây là kết
luận TRƯỚC h-fix, giữ lại làm mốc.

**Không ổn định** theo ngưỡng của bộ đo: ở 2 GiB gộp r3 + r4 là 4/21 phiên `completed` (19%), ngưỡng là 90%. Ở 1 GiB là 1/6;
mẫu 1 GiB nhỏ, nhưng hết chạm trần bộ nhớ mà tỉ lệ vẫn thấp nên nâng RAM không đủ để đạt ngưỡng (r3 có 3/6, r4 chỉ 1/15). Ba việc mở, chưa có phase:

- **Trang không đứng yên**: 17/21 phiên ở 2 GiB dừng vì worker thấy trang đổi giữa lúc quan sát và lúc gửi thao tác (log worker
  `vision.state.mismatch` ở `dom_observation`, `operation_prepare`, `operation_ack`). Nghi carousel/animation của landing (tiền lệ
  mct-47 ở planner v4); nguyên nhân trong đường agent-loop **chưa được điều tra**.
- **Agent chốt `not_achieved` khi check còn `not_checked`**: phiên r4 `bef6fc15-38a3-4e79-b8ee-52901dcbc29d` kết luận sai
  (kỳ vọng `achieved`); agent nêu thiếu chữ trang và chưa có ảnh chụp, vẫn chốt thay vì `inconclusive`. Luật mong muốn (chưa
  quyết): còn check `not_checked` mà chưa xem ảnh thì phải `inconclusive`; áp ở prompt (đổi version, phải đo lại fixture) hay ở
  bộ kiểm assessment là việc của phase sửa.
- **Chưa ai đối chiếu bằng mắt người**: 5 phiên `completed` mới được runner đối chiếu qua HTML (curl), không xem frame.

Dữ liệu ở `.pytest-artifacts/task-trial-mongchiton/r1|r2|r3|r4` (gitignore), suite `tasks.json` cùng thư mục; báo cáo ở
`reports/phase-05/runner-r1..r4.md`.

## Việc tiếp theo (theo thứ tự đề xuất)

**Đã làm 2026-11-27 (h-fix, QA PASS sau 3 vòng, chưa commit):** lỗi "trang không đứng yên". Root cause: 3 Swiper autoplay (delay
3000 ms) làm state scope `all` đổi mỗi ~3,3 s, vòng agent giữ state qua lượt gọi model ~9 s. Sửa: capability `agent-frozen-clock-v1`,
worker đóng băng đồng hồ của trang giữa các thao tác (`docs/adr/048-agent-frozen-page-clock.md`). Kết quả r7: 15/15 `completed`;
fixture 30/30 (đo trên code vòng 2). Còn mở: kỳ vọng `home-license` cần người đối chiếu; agent chốt `not_achieved` khi chưa xem ảnh
(r7 `6020ccba`); refresh `settle_timeout` để state cũ (ghi ở Limits của ADR-048); `vision-settle-suppression.spec.ts:84` dao động khi
chạy song song; test pytest đỏ có sẵn `test_qa_r8_agent_evidence.py::test_worker_dom_skips_private_inputs_and_redacts_sensitive_names`.
Trước khi commit: `benchmark/vision/codex/manifest.json` đã refresh sau vòng 3; chạy lại `hgraph check --changed` sau commit. Worker
đang ở 2 GiB bằng `docker update` (tạo lại container sẽ về 1 GiB).

**Ưu tiên user chọn 2026-11-26 (sau phase 05), đã xong ở đoạn trên:** `/h-fix` lỗi "trang không đứng yên" của đường agent-loop trên mongchiton.vn
(`state_changed_during_observation` / `state_mismatch`, 17/21 phiên ở worker 2 GiB), trước khi làm phase 08–16. Điểm bắt đầu:
`reports/phase-05/runner-r4.md` (phân bố lỗi, dòng log worker `vision.state.mismatch`), `leader-r1.md` mục 7 (thí nghiệm rẻ nhất để
tách giả thuyết carousel), dữ liệu `.pytest-artifacts/task-trial-mongchiton/`. Lệnh đo lại: như "Cách chạy" nhưng
`--suite .pytest-artifacts/task-trial-mongchiton/tasks.json --project Project-MCT --base-url https://mongchiton.vn --no-reset`,
không chạy `prepare`.

1. **Commit nhánh** khi người dùng đồng ý. Trước khi commit: chạy lại
   `python .pytest-artifacts/refresh_manifest.py` nếu còn sửa file nguồn (test
   `test_codex_bridge_benchmark.py` ghim hash trong `benchmark/vision/codex/manifest.json`), và không commit
   `benchmark/vision/visual-buttons/*.json` (hai file này bị test ghi đè khi chạy).
2. **Đo lại đầy đủ trên code cuối**: 10 task × 3–5 lần (lệnh ở "Cách chạy"). Tiêu chí "ổn định" trong bộ đo:
   `completed` ≥ 90% và nhất quán ≥ 90%.
3. **Đưa chữ trên trang vào snapshot** (cách sửa gốc cho việc agent không thấy thông báo, tiêu đề, bộ đếm).
   Hiện v3 buộc agent xin ảnh chụp, tốn thêm lượt gọi. Hướng làm: worker thu chữ nhìn thấy (role alert/status,
   heading, đoạn văn ngắn; có giới hạn; qua bộ lọc nhạy cảm) sau capability mới, chỉ ở agent mode; thêm trường
   tuỳ chọn vào `CodexDomObservation` và bỏ khỏi serialization khi rỗng để không đổi hash của v4;
   `render_snapshot` thêm phần chữ. Cần regenerate `vision-contract.generated.ts`.
4. **Chạy trên FE thật của người dùng**: tạo project, đặt allowed origin, bật cờ FE test, thử 2–3 task. Đo tài
   nguyên worker trong lúc chạy (lệnh bên dưới) để quyết định có nâng giới hạn container hay không.
5. **Nối đánh giá task sang bản nháp test Playwright** (để có verdict thật từ lần chạy deterministic). Đã thiết kế và
   user duyệt 2026-11-26: `docs/adr/047-assessment-to-playwright-draft.md` (accepted). Việc code là phase 07–16 (bảng bên dưới).

## Phase

Mỗi "Việc tiếp theo" thành một file phase cùng thư mục, để skill h-cook chạy từng phase. Việc 3 tách thành hai phase
(đổi contract chung + worker TS trước, phía Python sau) nên có 6 phase; đánh số theo thứ tự chạy. Việc 5, sau khi
thiết kế được duyệt (ADR-047), tách thành 10 phase code 07–16 (cùng một tính năng, chạy theo thứ tự phụ thuộc).

| Phase | Tên | Owner | QA | Trạng thái | Phụ thuộc |
| --- | --- | --- | --- | --- | --- |
| [01](phase-01-commit-branch.md) | Commit nhánh (5 commit `5a9d713`..`d7d2b06`, chưa push) | none | skip | completed | — |
| [02](phase-02-page-text-contract-worker.md) | Chữ trên trang: contract + worker (leader + QA PASS sau 3 lượt; chưa commit) | both | required | completed | 01 |
| [03](phase-03-page-text-snapshot-prompt.md) | Chữ trên trang: `render_snapshot` + prompt (leader + QA PASS sau 1 lượt, prompt `agent-loop-v4`; chưa commit) | be-developer | required | completed | 02 |
| [04](phase-04-stability-remeasure.md) | Đo lại 10 task × 3–5 lần trên code cuối (r4: 50 phiên, STABLE, leader PASS) | none | skip | completed | 03 |
| [05](phase-05-run-on-real-fe.md) | Chạy trên trang thật: đo trên mongchiton.vn (user đổi phạm vi; **không ổn định**, 4/21 phiên `completed` ở worker 2 GiB; leader PASS sau 2 lượt; nợ: chưa đối chiếu bằng mắt người; chỉ tài liệu, chưa commit) | none | skip | completed | 01, 04 |
| [06](phase-06-design-assessment-to-playwright-draft.md) | Thiết kế assessment → bản nháp Playwright (ADR-047 `accepted`, user duyệt 2026-11-26; leader PASS sau 2 lượt; chỉ tài liệu, chưa commit) | none | skip | completed | 01 |
| [07](phase-07-verify-trace-assumptions-spike.md) | Spike kiểm chứng giả định ADR-047 (handoff cây, locator `type`, giá trị trong trace/output, retention outbox/Temporal; không đổi code; leader PASS, không kết quả nào làm sai thiết kế) | none | skip | completed | 06 |
| [08](phase-08-agent-task-trace.md) | Gói vết task `AgentTaskTrace` v1 (hàm dựng tuyến tính, không bảng/migration; graph `agent-task-draft` đã lập; leader PASS vòng 1, QA FAIL vòng 1 vì ref `1:7` trong free text của assessment lọt vào gói vết, PASS vòng 2: 199 passed; chưa commit. User quyết 2026-11-27: giữ `summary`/`evidence` trong gói vết (đã che ref). Ràng buộc cho phase 11/14: chỉ `trace_hash` + `session_id` vào provenance/audit/log; mã từ chối mới `action_unsupported`; `read_agent_task_trace` không kiểm RBAC) | be-developer | required | completed | 07 |
| [09](phase-09-session-consistency-report.md) | Báo cáo nhất quán giữa các phiên cùng task (`GET /api/v1/vision/explorations/{session_id}/consistency`, ngưỡng `AGENT_TASK_CONSISTENCY_THRESHOLD` mặc định 0,9; leader + QA PASS vòng 1: 275 passed, 1 xfailed; chưa commit. Nợ: `agent_task_consistency.py:80` trả 500 nếu `task_assessment.status` là list (không tạo được qua đường ghi hiện tại, QA để test xfail strict); chưa kiểm trên stack đang chạy vì container control plane build từ code cũ. Ràng buộc cho phase 14: một phiên duy nhất đồng thuận 100% vẫn `eligible=true`, phải đọc cờ `small_sample` (< 3 phiên)) | be-developer | required | completed | 08 |
| [10](phase-10-verified-assertion-candidates.md) | Ứng viên assertion do controller kiểm chứng từ chữ trang đã thấy (khoá `verified_text` trong `task_assessment`; ESCALATE vì contract phase 08 từ chối khoá mới, user chọn phương án A: thêm trường đóng vào `AgentTaskAssessmentCopy`; leader + QA PASS vòng 1; chạy thật 2 phiên trên fixture sau khi rebuild `control-plane` + `temporal-worker`: `todo-add` 4 ứng viên, `search-empty` 1 ứng viên, 5/6 trích dẫn khớp; chưa commit. Nợ: quote 2-3 ký tự khớp mảnh trong đoạn văn (`FRAGMENT_MIN_CHARS`, `domain/verified_text.py:20`); nháy `‘…’`/`«…»` không được nhận; chưa có chỗ hiển thị khoá ở dashboard (phase 15). Ràng buộc cho phase 11: chuỗi hoá ứng viên bằng literal an toàn) | be-developer | required | completed | 08 |
| [11](phase-11-linear-renderer-provenance.md) | Renderer tuyến tính + provenance additive (`render_agent_task_source` trong `application/agent_task_renderer.py`, 4 trường tuỳ chọn trong `PlanningProvenance`; không gọi model, không DB/migration; leader + QA PASS vòng 1: dev 102 passed, QA 122 passed + 1 xfail; chưa commit. Ràng buộc cho phase 14: mọi draft mới giờ ghi 4 khoá `null` vào provenance (`application/generation.py:179`), nên dump bằng `exclude_none` để rollback không vấp `extra="forbid"`; ánh xạ mã từ chối của renderer sang API. Cho phase 16: assertion `getByText(...).first()` khớp chuỗi con, ca âm `/broken` là chốt) | be-developer | required | completed | 08, 10 |
| [12](phase-12-audit-project-policy-route.md) | Audit event cho route policy của project (`set_policy` trong `routes/generation.py` ghi `project_policy.owned_test_target.enabled`/`.disabled`/`project_policy.updated` cùng transaction; không đổi schema, không backfill; r1 ESCALATE vì `test_vision_tree_capacity.py` vỡ, user duyệt 2026-11-27 mở rộng phạm vi sang file test đó, r2 thêm một monkeypatch; leader + QA PASS vòng 1: 155 passed, 7 ca trên PostgreSQL fixture thật; chưa commit. Nợ có từ trước: khoá chính `project_execution_policies` chỉ là `project_id`, tenant khác PUT lên project id đã có trả 500, đã rollback, không rò) | be-developer-junior | required | completed | 06 |
| [13](phase-13-review-boundary-adr002-guards.md) | Ranh giới duyệt (`DECIDE_PROPOSAL`, khác người yêu cầu, `acknowledge_disposable_credentials`, kiểm lại cờ lúc duyệt), guard `credentials_in_source` (preflight, `revised-draft`), evidence của run `contains_test_values` bỏ mọi excerpt và `review_context`; ADR-002 thêm mục "Scoped exception" (user duyệt chữ 2026-11-27, bản PM + 3 chỉnh sửa). r1 ESCALATE: đường rò thứ ba `review_context` ở `reporting_events.py`, user duyệt mở rộng phạm vi sang `reporting_events.py`/`temporal_worker.py`/`test_reporting_event_processor.py`; leader + QA PASS vòng 1: 157 passed; chưa commit. Nợ: `manifest.json` của benchmark codex ghim hash HEAD của `routes/generation.py` và `test_vision_tree_capacity.py` → chạy `refresh_manifest.py` khi commit; chưa đo `result.summary`/`runner_metadata` khác do worker sinh | be-developer | required | completed | 11, 12 |
| [14](phase-14-create-draft-api.md) | API tạo bản nháp từ phiên agent-loop (`POST /api/v1/vision/explorations/{session_id}/test-draft`, use case `application/agent_task_draft.py`; không DB/migration; leader + QA PASS vòng 1: 119 test của phase, 0 fail, 0 skip; lệch: cùng `Idempotency-Key` khác body trả 200 + draft cũ thay vì 409, `provenance.consistency` ngoài contract, hai request đồng thời `[201, 500]`; chưa commit) | be-developer | required | completed | 09, 11, 13 |
| [15](phase-15-dashboard-draft-review.md) | Dashboard: yêu cầu và duyệt bản nháp (leader PASS r1, QA PASS r1; nợ: form chưa hiện độ dài mong đợi, user duyệt thêm phase 15b 2026-11-27) | fe-developer | required | completed | 14 |
| [15b](phase-15b-type-steps-expected-length.md) | API trả độ dài mong đợi của bước `type` (`GET .../test-draft/inputs`, additive) và form hiện độ dài; trả nợ phase 15; user duyệt 2026-11-27; thêm `has_type_steps` sau ASK_PM; leader PASS r1, QA PASS r1 (route thật trên stack chưa test: image cũ) | both | required | completed | 15 |
| [15c](phase-15c-fix-e2e-findings.md) | Sửa lỗi e2e của phase 16 r1: F1 `traceparent` chặn `POST /runs`, F2 renderer assert chữ trạng thái trước, F3 cập nhật danh sách nơi lưu (user quyết 2026-11-28, `reports/phase-16/user-answers-r1.md`); r1 ESCALATE F2, user mở rộng phạm vi sang `vision_agent_loop.py` (`ObservedText` chỉ theo quan sát cuối); F1 sửa ở worker `contract.ts` (`traceparent` tuỳ chọn, kiểm W3C); leader PASS r1, QA PASS r1 (41 ca QA); chưa commit. Nợ: F4 `search-results` 0 ứng viên; worker + control-plane image phải build lại trước phase 16 r2 | be-developer | required | completed | 15b |
| [16](phase-16-end-to-end-fixture.md) | End-to-end trên fixture `task-ui` với hai actor, ca âm, độ ổn định của test (r1 ESCALATE 2026-11-28: todo-add 0/6 do F2, F1, F3 → phase 15c; r2 PASS: 3 test đã duyệt chạy lại 15/15 `passed` qua `POST /runs`, ca âm a–j đúng (i: `assessment_not_achieved`), không giá trị ngoài danh sách khai báo; 17 phiên, draft 7/7; leader PASS r1, QA PASS r1; chỉ be-developer (mọi file Python). Nợ: **F5** `agent_task_renderer.py:61-75` assertion chứa chữ agent gõ ở phiên, người yêu cầu nhập giá trị khác → test `failed` (chỉ báo lỗi thừa); **F4** `search-results` không assert kết quả; `ruff check .` đỏ E501 `benchmark/vision/accuracy/run.py:292` ngoài phase; dashboard image cũ; chưa commit) | both | required | completed | 15, 15b, 15c |
| [17](phase-17-typed-text-candidates-and-outcome.md) | Sửa nợ phase 16: **F5** xong — cờ `derived_from_typed` (chỉ boolean, không lưu giá trị gõ) trên `verified_text` trong contract phase 08/10, bỏ khi false nên `trace_hash` phiên cũ giữ nguyên; renderer loại ứng viên có cờ, ghi `stop_conditions`. Stack thật (control-plane + temporal-worker build lại): marker khác giá trị task `passed`, 3 test chính `passed` + 6/6 rerun. **F4** ESCALATE: nguyên nhân ở worker `vision-dom.ts:46-48` không đọc `<li>` (kết quả tìm), và kết quả chứa từ khoá đã gõ nên cờ F5 cũng loại; user chọn 2026-11-28 mở phase riêng về worker (`reports/phase-17/user-answers-r1.md`), **chưa lập**. Leader PASS r1, QA PASS r1 (nhóm DB 197 passed, 0 DB skip). Giới hạn: phiên trước phase 17 không có cờ; overlap không chuẩn hoá Unicode NFD/NFC; draft login mất assertion "Xin chào, demo". Chưa commit | be-developer | required | completed | 16 |

Ánh xạ với "Việc tiếp theo": 1 → phase 01; 2 → phase 04; 3 → phase 02 + 03; 4 → phase 05; 5 → phase 06 (thiết kế) rồi phase
07–16 (code; ADR-047 phase B0–B9 tương ứng 07–16). Thứ tự đề
xuất cũ đặt đo (việc 2) trước chữ trang (việc 3); đã đảo vì "đo trên code cuối" phải sau khi code chữ trang xong.

Các "Quyết định còn chờ người dùng" bên dưới được gắn vào mục "Rủi ro/việc cần user duyệt" của phase bị ảnh hưởng
(nhãn Password: 02, 03, 05, 06; `password=...`: 03, 05, 06; giới hạn container: 04, 05; `step_deadline`: 02, 05;
audit policy route: 05, 06, nay phase 12). Không quyết định nào được tự quyết trong phase.

## Quyết định còn chờ người dùng

- **Giới hạn container worker** (256 pids, 1 GiB): fixture đơn giản đã dùng 120 pids và 394 MiB. Có thể là
  nguyên nhân lỗi chụp ảnh ở Q4/Q5 trên trang nặng. Số đo trên mongchiton.vn (phase 05): ở 1 GiB bộ nhớ chạm trần 2505 lần
  luỹ kế qua 12 phiên r1 + r2 (trước r1 là 0; không đo riêng từng lượt; không OOM kill); ở 2 GiB đỉnh 0,90 GiB qua 21 phiên, 0 lần chạm trần; pids đỉnh 123/256. Không có lỗi chụp ảnh ở
  cả hai mức. User giữ 2 GiB tạm thời trên container đang chạy; đổi lâu dài trong compose vẫn chờ quyết định.
- **Dung sai cho `step_deadline`** ở worker (xem "Lưu ý" bên dưới): đụng guard runtime.

## Quyết định đã chốt (user, 2026-11-26)

Từ thiết kế ADR-047 (`reports/phase-06/user-answers-r1.md`); mỗi dòng là một quyết định, không phải việc chờ:

- **Nhãn tiếng Anh "Password"**: giữ nguyên chính sách redaction (ô tên "Password" vẫn bị chặn; nhãn "Mật khẩu" chạy được);
  xem lại khi phase 05 trên FE thật cho thấy cần.
- **Task viết `password=...`**: giữ từ chối lúc gửi (`redact_generation_request`); tài khoản viết thành câu.
- **Audit route policy** (`PUT .../policy`, cả trường mới lẫn cũ): thêm audit event, là phase 12.
- Bản nháp test từ phiên agent-loop (phase 07–16, ADR-047): giá trị test literal trong source, chỉ project bật cờ FE test, người
  duyệt khác người yêu cầu (`DECIDE_PROPOSAL`), người yêu cầu nhập giá trị test trong request (cần hai actor), lưu source nguyên văn
  ở `test_runs.request`/outbox/workflow, chặn đường gửi source có tài khoản tới model, ADR-002 phải sửa (phase 13, user duyệt chữ).
- **Free text của assessment trong `AgentTaskTrace` (2026-11-27, sau phase 08)**: giữ `summary` và `checks[].evidence` trong gói vết, ref dạng `số:số` bị che lúc dựng; phase 11/14 chỉ đưa `trace_hash` + `session_id` vào provenance/audit/log và không coi free text là bản ghi tin cậy (giá trị đã gõ mà model trích vẫn có thể nằm trong đó).
- **`verified_text` trong `AgentTaskTrace` (2026-11-27, ESCALATE của phase 10)**: thêm trường đóng tuỳ chọn `verified_text` vào `AgentTaskAssessmentCopy` (phương án A), `trace_hash` phủ ứng viên assertion; phạm vi phase 10 mở rộng sang `contracts/agent_task_trace.py` + `domain/agent_task_trace.py` + test của chúng. Hệ quả đã chấp nhận: gói vết mang chữ trang đã khớp, có thể trùng giá trị đã gõ không nhạy cảm (vd tên todo vừa thêm), nới tiêu chí 4 của phase 08 cho riêng trường này.
- **Điểm lệch của phase 14 (2026-11-27, user chấp nhận, ghi nợ)**: (a) `Idempotency-Key` bắt buộc nhưng không lưu; replay theo (`session_id`, `trace_hash`), cùng key khác body trả 200 + draft cũ (không so giá trị test, đúng ADR-047), 409 chỉ khi lệch project/target/hash; (b) nợ: `provenance.consistency` nằm ngoài `PlanningProvenance` (`extra="forbid"`), chưa ai validate lại; (c) nợ: hai request đồng thời lần đầu cho `[201, 500]` (một draft, rollback sạch), gợi ý bắt `IntegrityError` rồi trả replay; (d) cổng 55437 của recipe pytest nằm trong dải Windows reserve (55434-55533), phase 14 chạy Postgres ở 57555-57557 bằng plugin ngoài repo.
- **Artifact của run (Q11, sau spike phase 07, `reports/phase-07/user-answers-r1.md`)**: chấp nhận artifact (trace, snapshot DOM, screenshot,
  video) chứa nguyên văn giá trị gõ kể cả mật khẩu, kể cả khi test pass, giữ 30 ngày; mở rộng Q10. Ghi vào đoạn ngoại lệ ADR-002 (phase 13),
  phase 16 quét trace/screenshot bằng giá trị mẫu; không đổi cấu hình trace/video/screenshot, không thêm kiểm quyền xem artifact.

## Cách chạy

```bash
# từ auto-at-ui/
export CLAUDE_BRIDGE_TOKEN_DIR=C:/Users/hen/.auto-at/claude-bridge-secrets   # đường dẫn, không phải secret
docker compose -f docker-compose.yml -f docker-compose.codex.yml \
  -f docker-compose.agent-loop.yml -f docker-compose.spool-volume.yml \
  --profile claude up -d --wait --wait-timeout 240

# token bridge hết hạn hoặc bị thu hồi (bridge_model_unavailable):
uv run python scripts/export_claude_bridge_token.py C:/Users/hen/.auto-at/claude-bridge-secrets

# header đăng nhập cục bộ cho script (auth_mode=local); tạo lại nếu .pytest-artifacts bị dọn:
# .pytest-artifacts/accuracy-local-headers.json =
#   {"X-Tenant-Id": "demo-tenant", "X-Actor-Id": "task-stability", "X-Actor-Roles": "tenant_admin"}

# đo độ ổn định (mỗi phiên gọi model thật qua bridge)
uv run python scripts/run_task_stability.py run --project "Task UI fixture" \
  --base-url http://task-target:7300 --repeat 5 --out .pytest-artifacts/task-stability/r4
uv run python scripts/run_task_stability.py report --out .pytest-artifacts/task-stability/r4

# đỉnh tài nguyên của worker
docker exec auto-at-ui-playwright-worker-1 sh -c \
  'cat /sys/fs/cgroup/pids.peak /sys/fs/cgroup/memory.peak; cat /sys/fs/cgroup/memory.events'
```

Test trên host:

```bash
docker run --rm -d --name agent-task-fixture-postgres -e POSTGRES_PASSWORD=vision-fixture-only \
  -p 127.0.0.1:55437:5432 postgres:17-alpine          # thiếu container này thì test DB tự skip
CODEX_BRIDGE_ENABLED=false uv run pytest tests/test_vision_agent_task_assessment.py \
  tests/test_vision_agent_loop.py -q --basetemp=.pytest-artifacts/tmp-x -p no:cacheprovider
cd workers/playwright && npm.cmd run typecheck && npx.cmd playwright test src/vision-agent-mode.spec.ts
```

Dùng trên dashboard: tab Vision, chọn engine "Agent loop (task testing)", nhập URL + task. Bật cờ FE test ở form
policy của project ("This is a test environment I own").

## Lưu ý dễ vấp

- `tests/test_vision_page_batch.py` **dao động có sẵn** trên host Windows (`invalid_step_deadline`): HEAD trượt
  4/21, nhánh này 9/21. Worker so `step_deadline` với `Date.now()` không dung sai, mà đồng hồ Node trên máy này
  chậm hơn Python 0,2–10 ms tuỳ tiến trình. Trong container Linux không gặp. Đừng coi là hồi quy nếu chưa A/B
  với HEAD.
- Bộ test Python đầy đủ mất hơn 40 phút trên máy này, lâu hơn khi stack đang chạy.
- `npx.cmd playwright test -g` với mẫu có dấu cách hoặc `|` làm hỏng shim trên Windows; dùng một từ.
- Sau `up`, đợi vài giây rồi mới gửi phiên: `playwright-worker` không có healthcheck.
- Đừng tạo git worktree trong thư mục tạm của phiên: nó bị dọn giữa chừng.
- `run_task_stability.py prepare` **bật cờ FE test**: không dùng cho mongchiton.vn (production). `run` gửi hết các cặp còn thiếu
  trong một lần gọi, không dừng sau phiên lỗi đầu; muốn thử một phiên thì dùng `--task <id> --repeat 1`.
- Phiên agent cũ trong DB vẫn có dạng `unavailable / agent_done`, không có `task_assessment`.
- **Job xoá artifact hết hạn lỗi cả lô trên stack cục bộ (ghi nợ, ngoài phạm vi plan)**: worker log `artifact.retention.failed` mỗi giờ,
  12 artifact `file://` hết hạn từ 2026-08 vẫn còn (spike phase 07, `reports/phase-07/runner-r1.md` mục 4c). Lỗi ở ngoài vòng lặp từng
  artifact (`temporal_worker.py:111-132`, khác `application/artifact_retention.py:25-30`), nên thời gian lưu thực tế của artifact (chứa giá trị
  test, Q11) không bảo đảm 30 ngày. User xử lý riêng bằng `/h-fix`; không thêm phase, không chặn phase 08-16. Ghi cả ở ADR-047 mục "Rủi ro".

## Tài liệu liên quan

- Quyết định và phạm vi: `docs/adr/046-agent-loop-task-testing.md`
- Thiết kế assessment → bản nháp Playwright (accepted 2026-11-26, phase 07–16): `docs/adr/047-assessment-to-playwright-draft.md`
- Plan gốc của engine (đã ghi chú mở lại): `plan/20261119-2212-browser-agent-loop/plan.md`
- Plan độ chính xác cũ (vẫn dừng): `plan/09112026103202-vision-accuracy-loop/README.md`
- FE mẫu: `benchmarks/targets/task-ui/README.md` (tài khoản test `demo` / `Demo1234`, trang `/broken` cố ý lỗi)
