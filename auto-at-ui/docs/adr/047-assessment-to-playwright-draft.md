# ADR 047: Từ task assessment của agent loop sang bản nháp test Playwright

Trạng thái: accepted (user duyệt toàn bộ thiết kế ngày 2026-11-26; chưa có dòng code nào, code nằm ở phase 07-16 của
plan). Ngày: 2026-11-26. Phase 06 của `plan/20261125-2140-agent-loop-task-testing`. Mười câu hỏi (Q1-Q10) đã được user
chốt cùng ngày (mục "Quyết định của user"), sau đó user duyệt toàn bộ tài liệu, gồm cả lựa chọn "người yêu cầu nhập giá
trị test trong request tạo bản nháp, cần hai actor". Sau spike phase 07 (cùng ngày) user chốt thêm Q11 (artifact của
run). Không còn câu hỏi mở (xem "Câu hỏi mở"). Kết quả spike: `plan/20261125-2140-agent-loop-task-testing/reports/phase-07/runner-r1.md`
(viết tắt "spike phase 07"); phạm vi đo của spike: fixture `task-ui` và benchmark cục bộ, trang `data:` cho phần trace,
Playwright 1.50.1.

Quy ước ghi nguồn: `đường/dẫn:dòng` là dòng trong working tree ngày 2026-11-26 (một số file của phase 02-03 chưa
commit). Những chỗ chỉ suy ra từ đọc code mà chưa chạy được ghi rõ là "suy từ đọc code, cần kiểm chứng ở phase
B0".

## Bối cảnh

ADR-046 làm `agent_loop` thành engine test theo task. Một phiên kết thúc `completed` kèm `task_assessment`
(`achieved | not_achieved | blocked | inconclusive`, tối đa 12 check, số liệu controller tự đo, `advisory: true`,
`domain/vision_task_assessment.py:12-14,38-50`). Đó là lời của agent, không phải verdict:
`exploration_conclusion.business_outcome` luôn là `unverified` (`domain/vision_conclusion.py:52`). Verdict chỉ đến từ
một lần chạy deterministic của test đã duyệt (ADR-001, ADR-002; `AGENTS.md`, mục `agents/`: "never change test suites
or execution verdicts without an explicit approval flow").

ADR-046 ghi rõ "turning an assessment into a test draft is not part of this ADR" (`docs/adr/046-...md`, mục
Consequences). Thiết kế này lấp chỗ đó: biến một (hoặc vài) phiên đã `completed` thành **bản nháp** chờ duyệt, để
có verdict thật.

Số đo nền (plan.md, bảng r1-r4; `reports/phase-04/runner-r1.md`): r4 có 50 phiên, 100% `completed`, nhất quán trạng
thái 98%, đúng kỳ vọng 98% (49/50). Phiên sai duy nhất là `search-results` #3, `not_achieved` trong khi 4 phiên còn
lại `achieved`. Số này chỉ cho `claude_cli / claude-opus-5-5`, trang đơn giản, prompt `agent-loop-v4`; r1-r3 dùng
prompt v3 nên không so trực tiếp.

## Cái gì đã có, cái gì thiếu (đối chiếu source)

Đã có và dùng lại được:

| Cơ chế | Chỗ trong source |
| --- | --- |
| Draft Playwright chờ duyệt: `generated_test_drafts` (`state=pending_review`), một quyết định bất biến mỗi draft | `infrastructure/persistence/models.py:524-549`, `application/generation.py:173,248-256,343-352` |
| Duyệt tạo đúng một test case và đúng một run deterministic; runner là nguồn verdict duy nhất | `application/generation.py:313-342`, `contracts/execution.py:65-75,116-125`, `runners/ports.py:6-9` |
| Source sinh ra chỉ import `@playwright/test`, cấm `process`, `fetch`, `fs`...; hash khớp nguồn; origin phải nằm trong allowlist | `contracts/execution.py:13-37,78-107`, `workers/playwright/src/execute.ts:239-282` |
| Kiểm preflight trong worker ghim phiên bản trước khi tạo run | `application/generation.py:276-312`, `execute.ts:195-229` |
| Sinh draft từ bằng chứng Vision: handoff bất biến, model chỉ chọn nhánh và assertion, renderer xác định tự dựng selector | `application/vision_handoff.py:11-99`, `agents/generation/vision_plan.py:33-52`, `application/vision_source_renderer.py:34-138`, `contracts/generation.py:128-146` |
| Draft từ handoff có provenance (`vision_source`, `selected_branch_ids`, `operation_ids`) | `contracts/generation.py:116-125`, `application/generation_events.py:89-148` |
| Audit khi gửi, khi duyệt: `generation.requested`, `generated_draft.approved/rejected`; idempotency; outbox | `application/generation.py:111-133,353-363` |
| Quyền: `SUBMIT_GENERATION`, `DECIDE_GENERATION`, `MANAGE_PROJECT` | `domain/authorization.py:21-31,35-55` |
| Tiền lệ "sinh draft thay thế từ bằng chứng có sẵn, người có `SUBMIT_GENERATION` bấm": `POST /runs/{id}/revised-draft` | `api/v1/routes/runs.py:294-330` |
| Bảng step log theo thứ tự `step_index` và `operation_ids` (nguồn thứ tự thật của phiên agent) | `models.py:474-504`, `infrastructure/persistence/vision_unit_of_work.py:485-515` |

Thiếu hoặc không khớp (đây là lý do cần thiết kế riêng, không chỉ "gọi lại handoff"):

1. **Phiên agent-loop không sinh handoff.** `finish(...)` của agent chỉ truyền `task_assessment`
   (`application/vision_agent_loop.py:475`); handoff chỉ do planner v4 truyền vào `finish`
   (`vision_unit_of_work.py:162-170`).
2. **Bộ dựng handoff giả định cây, phiên agent là một chuỗi tuyến tính.** `build_vision_handoff` lấy "lá" là
   operation `explore` không phải cha của operation `explore` nào và leo theo `parent_operation_id`
   (`vision_handoff.py:16-37`). Ở agent mode, worker không đưa operation `explore` vào `ancestry`
   (`workers/playwright/src/vision-operations.ts:586-588,759,909-914`; chú thích `vision_agent_loop.py:311-315`), nên
   cha của mọi action là operation `setup` gần nhất (navigate hoặc refresh). Suy từ đọc code: mỗi action thành một
   nhánh riêng `navigate -> action`, mất các bước trước nó (đăng nhập = ba nhánh rời nhau). **Đã kiểm chứng ở phase 07:
   ĐÚNG.** Trên 15 phiên của 3 task (fixture `task-ui`): số nhánh luôn bằng số action, mọi nhánh dài đúng 2 bước, 0/15 phiên
   có nhánh chứa đủ chuỗi (`login-success` ra 3 nhánh rời; nhánh `ready` chỉ là một cú bấm lẻ); báo cáo spike mục 1. Thứ tự
   đúng nằm ở `visual_agent_steps.operation_ids` và `visual_operations.sequence` (đã kiểm chứng: xếp theo hai nguồn khớp
   106/106 phiên agent-loop có operation, mục 6; chỉ đo trên DB cục bộ). Kèm ba quy tắc cho bộ dựng mới: bỏ operation
   `setup`; action bị bỏ qua sau khi dừng sớm không có operation id (chỉ nằm trong `actions` JSONB của step) và `wait
   completed` có id thì phải xử lý; step `worker_result_mismatch` và operation `failed|rejected|unknown` thì từ chối.
3. **Mọi nhánh có ô nhập đều bị chặn.** Contract không cho nhánh `ready` chứa bước `type`
   (`contracts/vision.py:494-496`), bộ dựng đặt `input_binding_required` (`vision_handoff.py:67-68`) và renderer ném
   lỗi (`vision_source_renderer.py:66-67`). Đăng nhập, thêm việc, tìm kiếm đều có `type`. Đã kiểm chứng ở phase 07: ĐÚNG,
   21/38 nhánh của 15 phiên là `blocked/input_binding_required` (cả 50 phiên r4: 41/123 nhánh); báo cáo spike mục 1.
4. **Assertion hiện chỉ có `visible` và `enabled` của chính control sắp bấm** (`contracts/generation.py:128-134`,
   `vision_source_renderer.py:88-93`), đúng ghi chú "business outcomes remain unverified"
   (`vision_source_renderer.py:129-132`). Điều task cần kiểm (thông báo lỗi, tiêu đề, bộ đếm) không có chỗ biểu diễn.
   `VisualOperation` chỉ có `url_change`/`visual_change` dạng enum, không có URL hay chữ
   (`contracts/vision.py:370-394`), và chữ trang (phase 02-03) không được lưu; worker chỉ log số đếm (ADR-046 mục 9).
   Phần duy nhất còn lại của kỳ vọng là câu chữ do model viết trong `checks[].expectation/evidence`
   (`contracts/codex_bridge.py:469-483`), chưa kiểm chứng được bằng máy.
5. **Giá trị gõ không được lưu.** Step log chỉ giữ `text_chars` (`vision_agent_loop.py:216-223`); action lưu cho
   trajectory là `{kind, x, y}`, không có text (`vision_agent_loop.py:813`). Tài khoản test nằm trong chữ của task
   (`benchmarks/task-ui/tasks.v1.json`: "mật khẩu Demo1234"), được mã hoá trong `encrypted_task_intent` và chỉ đọc lại
   được trong thời hạn lưu tối đa 60 ngày (`models.py:128-129`, `config.py:98`, `vision_agent_loop.py:432-434`).
6. **Selector.** Locator đã bind của worker nằm ở `visual_locator_evidence` và bị lọc bởi `validate_locator_value`
   (từ nhạy cảm như `password`, e-mail, chuỗi từ 7 chữ số, `contracts/vision.py:214-233`). Một ô có nhãn tiếng Anh
   "Password" không có locator được xác minh (ADR-046 mục 5). `dom_path` chỉ dùng được cho phiên sống và bị coi là
   `ephemeral_locator` (`vision_handoff.py:52-55`, `contracts/vision.py:264-272`). Đã kiểm chứng ở phase 07 (chỉ trên
   fixture `task-ui`, nhãn tiếng Việt): mọi op `type`/`click` của 15 phiên có locator `verified`, strategy `role`, không có
   `ephemeral_locator`; toàn DB agent-loop: 260 `role`, 0 `dom_path`. Nhãn "Password" tiếng Anh: không kiểm được (fixture
   không có), vẫn chờ phase 05; báo cáo spike mục 2.
7. **Request sinh draft từ task không dùng được cho task chứa tài khoản:** `SubmitGeneration` từ chối chữ bị
   redact thay đổi (`generation.py:68-70`) và `generation_requests.redacted_request` lưu nguyên văn chữ đó
   (`models.py:507-522`); `generation_events.py` đưa nó tới model sinh (`vision_plan.py:11-29`). ADR-002 nói
   "Login and supplied credentials are outside v1 scope" và "Raw requests and credentials are not persisted or sent
   to a model" (`docs/adr/002-generated-test-authority.md:17-20`). Cho phép draft có tài khoản test là sửa ADR-002
   cho phạm vi dự án FE-của-tôi, quyết định của người dùng.
8. **Runner không có kênh nào nhận dữ liệu test ngoài source.** `PlaywrightTestSourceMode` là `extra="forbid"`
   (`contracts/execution.py:78-86`), env của tiến trình test chỉ có `PATH/HOME/TMPDIR/PLAYWRIGHT_*`
   (`workers/playwright/src/execute.ts:269-282`) và source không được dùng `process` (`contracts/execution.py:15`). Mọi giá trị test hoặc nằm literal
   trong source, hoặc cần thêm một kênh (đổi contract + worker).
9. **Bảng proposal/approval cũ không khớp.** `agent_proposals.run_id` là FK bắt buộc tới `test_runs`
   (`models.py:580-584`) và `DecideProposal` dùng `DECIDE_PROPOSAL` kèm outbox "review-branch"
   (`application/proposals.py:19-82`; `domain/proposals.py:4-6`); phiên Vision chưa có run. Nhánh draft
   (`generated_test_drafts`/`generated_test_decisions`) là cơ chế duyệt đúng cho "test mới".

## Quyết định (đề xuất)

**Một bản nháp Playwright dựng từ bằng chứng của phiên agent-loop, đi qua đúng đường duyệt hiện có.** Không thêm engine
mới, không đổi runner, không đổi hình dạng `TestExecutionRequest`/`TestExecutionResult`.

1. **Chuỗi tuyến tính bất biến, không dùng lại handoff cây.** Thêm một "gói vết task" (tên tạm `AgentTaskTrace`
   v1): các bước theo thứ tự `visual_agent_steps` (operation id, loại action, locator đã xác minh, độ dài chữ gõ,
   kết quả controller đo), kèm `task_assessment`, `intent_hash`, hash nội dung, `tenant/project/session`. Dựng bằng
   hàm mới (không sửa `build_vision_handoff`, vì contract handoff có hash ghim bởi test và chặn `type`), không dùng lại
   `visual_locator_handoffs` (payload bị validator `VisualLocatorHandoff` ép, `contracts/vision.py:500-518`). Bản đầu
   KHÔNG có bảng mới và không có migration: gói vết dựng theo yêu cầu từ `visual_agent_steps` của phiên đã `completed`
   (bất biến), hash của nó và `session_id` được ghi vào `provenance` của draft; chỉ thêm bảng nếu B0 chứng minh cần dùng
   lại gói giữa nhiều lần yêu cầu hoặc sau retention của bằng chứng (r3: thu gọn theo gợi ý của leader).
2. **Đi qua bảng request -> draft hiện có, dựng đồng bộ.** Bộ dựng là xác định và không gọi model, nên không cần
   vòng outbox/processor của `generation_events.py`. Use case của route tạo trong một transaction: một
   `generation_requests` ở trạng thái `completed` (không thêm cột; `redacted_request` là câu cố định trung tính, không
   phải chữ task), một `generated_test_drafts` `pending_review` (cùng ràng buộc `planning_request_id` unique,
   `models.py:526-528`) và audit. Nhờ vậy preflight, `DecideGeneratedDraft` và đường tạo test case + run giữ nguyên.
   Draft loại này nhận biết qua `provenance.agent_trace_source`. Idempotency key theo (`session_id`, hash gói vết);
   gọi lại trả draft cũ, không bao giờ băm hay so giá trị test. Lựa chọn kỹ thuật này đã được user chấp nhận khi duyệt ADR; B0/B7 vẫn xác nhận lại bằng thực nghiệm.
3. **Selector không do model viết** (Q2, user chốt). Renderer xác định dựng từ locator đã xác minh của worker (cùng
   nguyên tắc `vision_source_renderer.py:1` và `contracts/generation.py:138`), không dựng từ ref `version:n` của agent.
4. **Assertion kết quả chỉ lấy từ chữ trang mà controller đã quan sát và kiểm chứng** (Q8, user chốt). Khi phiên kết
   thúc, controller đối chiếu trích dẫn trong `checks[].evidence` của các check `met` với mục `page_text`/tên control đã
   thấy trong chính phiên (đã qua cùng bộ lọc `validate_locator_value`, tối đa 160 ký tự/mục), chỉ giữ cái khớp làm
   "ứng viên assertion". Model không được tự đặt chữ kỳ vọng. Phần này đụng `vision_agent_loop.py` nên là phase riêng.
5. **Người duyệt thấy mọi thứ trước khi chạy** (assessment, check, báo cáo nhất quán, source, danh sách giá trị test) và
   chỉ khi duyệt mới có test case và run.
6. **Giá trị test, redaction, audit, người duyệt theo mục "Quyết định của user"** ngay dưới.

## Quyết định của user (chốt 2026-11-26)

Mỗi câu một dòng quyết định, một dòng phương án đã loại và hệ quả cho thiết kế. Đây không phải lời duyệt toàn bộ ADR.

| Câu | Quyết định (user chốt 2026-11-26) | Phương án đã loại, vì sao | Hệ quả cho thiết kế |
| --- | --- | --- | --- |
| Q1 Giá trị test | A: literal trong `playwright_test_source`, chỉ cho project bật `vision_owned_test_target`; người duyệt xác nhận tài khoản dùng một lần; **ADR-002 phải sửa** | B (bộ dữ liệu test mã hoá, runner tiêm) để sau: đổi `PlaywrightTestSourceMode` (`extra="forbid"`), worker, TS generated, nặng hơn bản đầu. C (người duyệt điền) loại: người duyệt không nên là người nhập giá trị | Xem "Giá trị test (Q1)" và "Phần ADR-002 phải sửa" dưới |
| Q2 Selector | A: locator đã bind/xác minh của worker; ô có nhãn nhạy cảm bị chặn | Ref của agent: chỉ hợp lệ trong một snapshot (`agents/prompts/agent_loop.py:69-70`), không bền, trái nguyên tắc selector không do model viết | Renderer chỉ dùng `visual_locator_evidence` đã `verified`; bước thiếu locator thì từ chối `locator_unavailable` |
| Q3 Số phiên | A: một phiên nguồn + báo cáo nhất quán của các phiên cùng (`project`, `target_url`, `intent_hash`); từ chối dưới ngưỡng cấu hình, khởi điểm 90% | B (bắt buộc N phiên) tốn chi phí tuyến tính; C (hợp nhất vết nhiều phiên) dễ trộn bước khác nhau | Mục "Dùng nhiều phiên nhất quán" |
| Q4 Nhãn "Password" | A: giữ nguyên chính sách redaction; xem lại khi phase 05 trên FE thật cho thấy cần | Bỏ từ `password` khỏi tên (đổi redaction toàn hệ thống, Python + TS + generated) hoặc nới theo dự án (phải đưa ngữ cảnh dự án vào hàm lọc thuần hai phía) | Ô mật khẩu có nhãn "Password" thì bước bị chặn, draft từ chối `locator_unavailable`; không có đường sửa tay trong ADR này |
| Q5 Task `password=...` | A: giữ từ chối | Nới cho owned test target: thêm đường đọc task riêng và hạn 60 ngày của `encrypted_task_intent` | Giá trị không bao giờ trích từ chữ task; xem Q1 |
| Q6 Audit route policy | A: thêm audit event cho `PUT .../policy` (cả trường mới lẫn cũ), là một phase code riêng | Không thêm: không chứng minh được ai bật cờ và khi nào | Phase B5; draft chụp giá trị cờ vào `provenance` và audit policy làm bằng chứng gốc |
| Q7 Người duyệt | B: người duyệt khác người yêu cầu và có vai `reviewer`/`project_admin`/`tenant_admin` cho loại draft này (theo ADR-004) | Giữ `DECIDE_GENERATION` (contributor tự duyệt) trái ADR-004; yêu cầu `MANAGE_PROJECT` chặt quá | Xem "Ranh giới duyệt" |
| Q8 Chữ kỳ vọng | A: controller đối chiếu trích dẫn trong check `met` với chữ trang/tên control đã thấy, chỉ giữ cái khớp | Chỉ `visible/enabled` (test yếu); model đề xuất chữ (trái nguyên tắc) | Phase B3 |
| Q9 Phiên `not_achieved` | A: không sinh draft "kỳ vọng fail" ở bản đầu | Draft kỳ vọng fail cần quy ước expected-fail và verdict đảo chiều | Business flow: `not_achieved` chỉ hiển thị để điều tra |
| Q10 Source có tài khoản ở `test_runs.request`, `outbox_events.payload`, workflow Temporal (hỏi sau leader-r1) | A: chấp nhận lưu nguyên văn ở các nơi đó; chặn đường gửi source có tài khoản tới model; ghi đủ danh sách nơi lưu vào đoạn ngoại lệ ADR-002 | B (che source bằng tham chiếu, nạp lúc gửi worker) và C (placeholder, giải mã lúc gửi) loại: đổi `runs.py`, `temporal.py`, `runners.py`, thêm phase, nặng; Q1 đã chấp nhận tài khoản dùng một lần. Không thêm phase che source ở dispatch | Bảng 12 nơi ở "Giá trị test (Q1)"; guard nơi 11, 12; ngoại lệ ADR-002 liệt kê đủ; AC3 khẳng định tập nơi cho phép gồm outbox, `test_runs.request`, workflow |
| Q11 Artifact của run (nơi 9: trace zip, snapshot DOM, screenshot, video; hỏi sau spike phase 07, `reports/phase-07/user-answers-r1.md`) | A: chấp nhận, mở rộng Q10 sang nơi 9: spike xác nhận artifact chứa nguyên văn giá trị gõ (kể cả ô mật khẩu trong snapshot DOM), kể cả khi test pass, mặc định giữ 30 ngày. Ghi nơi 9 vào đoạn ngoại lệ ADR-002 (phase 13, chữ do user duyệt lúc đó); phase 16 thêm ca quét trace/screenshot bằng giá trị mẫu. Không đổi cấu hình trace/video/screenshot của runner; không thêm kiểm quyền xem artifact riêng | B (test case có giá trị test buộc trace/video/screenshot `retain-on-failure` hoặc tắt) và C (chấp nhận nhưng giới hạn quyền xem artifact loại này) loại: B đổi `execute.ts`/contract artifact và làm yếu chẩn đoán lỗi, C thêm kiểm quyền riêng; Q1 đã chấp nhận tài khoản dùng một lần | Nơi 9 thuộc tập nơi cho phép (có trong danh sách khai báo ở AC3 và đoạn ngoại lệ ADR-002); loại excerpt `playwright-output` (và xét `worker-result`) của run `contains_test_values` khỏi evidence gửi model là bắt buộc (nơi 10); rủi ro về job xoá artifact lỗi ghi ở "Rủi ro" |

**Giá trị test (Q1).** Hệ thống không có giá trị đã gõ (chỉ `text_chars`, `vision_agent_loop.py:216-223`), và theo Q5 không
được trích từ chữ task. Vì vậy thiết kế (lựa chọn kỹ thuật do PM đề xuất và đã được user chấp nhận khi duyệt ADR, 2026-11-26): người yêu cầu nhập giá trị cho từng bước `type` trong chính request tạo draft (form liệt kê bước theo thứ tự,
tên locator và độ dài mong đợi). Hệ thống chỉ kiểm độ dài khớp `text_chars` của bước (khớp độ dài không chứng minh đúng
giá trị; bằng chứng đúng/sai là lần chạy deterministic sau duyệt). Giá trị đi thẳng vào source của draft trong cùng
transaction và không vào: `generation_requests`, audit, log, `provenance`, idempotency key, hay response của route yêu
cầu. Nhưng source không đứng yên ở draft: sau duyệt nó đi cùng `runner_config` qua cả đường chạy. Danh sách đầy đủ các
nơi giá trị literal nằm (đã đọc source, trừ chỗ ghi "chưa kiểm chứng"):

| # | Nơi | Dẫn chứng | Trạng thái |
| --- | --- | --- | --- |
| 1 | `generated_test_drafts.playwright_test_source` | `models.py:524-539`, ghi ở `application/generation.py:168-182` | đã đọc |
| 2 | `test_cases.specification.playwright_test_source` (sau duyệt) | `application/generation.py:313-327` | đã đọc |
| 3 | `test_runs.request` (JSONB, chứa `runner_config` với source) | `application/runs.py:86-97` (dựng `TestExecutionRequest`, `run.request = request`), `models.py:560`, `infrastructure/persistence/repositories.py:401` | đã đọc |
| 4 | `outbox_events.payload.request.runner_config` của sự kiện `test.run.requested` | `application/generation.py:328-340` (đưa source vào `CreateRun`), `application/runs.py:140-152` (`request.model_dump(mode="json")` vào payload), `models.py:671-681`. Repo chỉ đặt `published_at` (`repositories.py:541-546`) và tôi không tìm thấy mã xoá hàng outbox, nên coi như giữ lại | đã đọc. Đã kiểm chứng ở phase 07: ĐÚNG, giữ lại (DB cục bộ `outbox_events` 275 hàng đều đã publish, cũ nhất 126 ngày; không có DELETE nào cho outbox trong `apps/`, `packages/`, migration, compose; `reports/phase-07/runner-r1.md` mục 4a). Chỉ đo DB cục bộ; DB production chưa có |
| 5 | Workflow Temporal: input của workflow và activity (history của Temporal) | `infrastructure/workflows/temporal.py:129-141` (`start_run`, `RunWorkflowInput(request=request)` ở `:137`), `infrastructure/workflows/definitions.py:12-20`, `temporal.py:42-45` | đã đọc code. Đã kiểm chứng ở phase 07: retention history namespace cục bộ `auto-at-local` = 24h (`docker-compose.yml:198-199` `DEFAULT_NAMESPACE_RETENTION: 1d`; server báo `WorkflowExecutionRetentionTtl 24h0m0s`, archival tắt; runner-r1 mục 4b). Chỉ cục bộ; production chưa chọn retention (ADR-002) |
| 6 | Thân HTTP tới worker (`/execute`, `/preflight`), tạm thời | `infrastructure/runners.py:38,65`; worker không log thân request (`workers/playwright/src/server.ts:40-84` chỉ log id/trạng thái) | đã đọc |
| 7 | Workspace tạm của worker (`generated.spec.ts`, mode 0o400), xoá ở `finally` | `workers/playwright/src/execute.ts:195-236` (preflight, ghi file `:212`, `rm` `:235`), `:239-314` (chạy, ghi file `:259`, `rm` `:313`) | đã đọc |
| 8 | Phản hồi API trả source: `RunResponse.playwright_test_source` và `DraftResponse.playwright_test_source` (mọi người có `READ` trên project, và dashboard hiển thị) | `api/v1/routes/runs.py:77,215-219`, `api/v1/routes/generation.py:63,137` | đã đọc |
| 9 | Artifact của run: `playwright-output`, trace, video, screenshot (mặc định bật cả khi thành công, giữ `retain_days`=30) | `workers/playwright/src/execute.ts:300-304`, `contracts/execution.py:53-62` | Đã kiểm chứng ở phase 07: ĐÚNG, giá trị `fill` nằm nguyên văn trong trace zip (`0-trace.trace`, `test.trace`, bản sao source `resources/src@*.txt`) của cả test pass lẫn fail, kể cả giá trị ô mật khẩu trong snapshot DOM; screenshot hiện nguyên chữ ở ô không phải mật khẩu (ô mật khẩu hiện chấm, lộ độ dài); video là pixel, không grep được nên suy theo screenshot. Phạm vi đo: fixture dạng trang `data:`, Playwright 1.50.1, `fill`, config như `execute.ts:259-263` (runner-r1 mục 3). **Bổ sung phase 15c (phase 16 r1 đo trên trang thật):** khi trang gửi request (đăng nhập, thêm việc), giá trị gõ còn nằm trong `0-trace.network` (`postData.params[].value`) và trong `resources/<sha1>.dat` (thân request) của trace zip; spike phase 07 đo 0 lần vì trang `data:` không gửi request. Vẫn là nơi 9 (trace zip), không thêm loại artifact mới; `0-trace.stacks` vẫn 0 lần. Giữ `retain_days`=30 theo contract, nhưng job xoá artifact hết hạn đang lỗi cục bộ nên thời gian lưu thực tế không bảo đảm (xem "Rủi ro"). User đã chấp nhận (Q11) |
| 10 | Đường tới model: (a) excerpt của `playwright-output` trong evidence báo cáo/triage, chỉ qua `redact_value` theo mẫu, không biết giá trị tài khoản | `agents/shared/evidence.py:24,70-90` | Đã kiểm chứng ở phase 07: ĐÚNG có điều kiện. Khi test fail, khung mã ±2 dòng của `line` reporter in dòng `fill('<giá trị>')` nếu dòng đó nằm gần dòng lỗi (1 lần trong output của test fail; test pass không có); `redact_value` theo mẫu không biết giá trị literal nên không bắt được. Phạm vi đo: một cấu hình, Playwright 1.50.1, `--reporter=line`. `worker-result` chưa đo. Hệ quả (BẮT BUỘC, không còn điều kiện): loại excerpt `playwright-output` của run có `contains_test_values` khỏi evidence gửi model, và xét loại cả `worker-result` (phase 13 đo hoặc loại luôn), cùng tinh thần guard nơi 11, 12, để cam kết "không gửi tới model" không tuỳ may rủi |
| 11 | Đường tới model: (b) sửa preflight tự do nhúng nguyên source vào `SubmitGeneration` (lưu `generation_requests.redacted_request`, rồi tới model sinh), chỉ bị chặn với draft có `vision_handoff_id` | `application/generation.py:289-312` (chặn ở `:290-294`), `models.py:507-522` | đã đọc: draft agent PHẢI được chặn tương tự |
| 12 | Đường tới model: (c) `POST /runs/{id}/revised-draft` nhúng "Approved source" vào request sinh | `api/v1/routes/runs.py:306-345` (nhúng ở `:340`) | đã đọc: PHẢI chặn với test case có `contains_test_values` |

Hệ quả thiết kế cố định (không cần user quyết): bước 11 và 12 bị chặn bằng lỗi `credentials_in_source` cho draft/test
case có `contains_test_values` (cùng cách `generation.py:290-294` chặn handoff), nên draft loại này không có đường "sửa
tự do bằng model"; muốn sửa thì sinh draft mới từ phiên. Chỉ project bật cờ (kiểm lại lúc yêu cầu và lúc duyệt) mới nhận
giá trị; ngược lại từ chối `input_value_not_allowed` (mọi bước `type` mang giá trị literal nên đều cần cờ, kể cả ô tìm
kiếm; đây là hệ quả của "chỉ cho project bật cờ" ở Q1). Người duyệt phải gửi xác nhận tường minh
`acknowledge_disposable_credentials=true` (trường mới, additive, trong `DecisionRequest`, `routes/generation.py:88-90`) khi
draft có giá trị test; thiếu thì từ chối. Cờ `contains_test_values` được ghi vào `provenance` để dashboard và test dựa vào.

Q10 (user chốt 2026-11-26, phương án A): chấp nhận lưu nguyên văn ở các nơi 1-5 và 8, kèm chặn 11-12; không che source
ở dispatch. Retention của outbox và history Temporal vẫn chưa rõ (B0 đo), nhưng không đổi quyết định. Phase 07 đã đo hai điểm này: outbox giữ lại (nơi 4), history Temporal cục bộ 24h (nơi 5); xem bảng.

Q11 (user chốt 2026-11-26, phương án A): chấp nhận lưu nguyên văn ở nơi 9 (artifact của run) như Q10 đã làm cho nơi 1-5 và 8;
mở rộng Q10, không đổi cấu hình artifact của runner, không thêm kiểm quyền xem artifact.
Cập nhật phase 15c (user chấp nhận 2026-11-28, sau phase 16 r1): phạm vi nơi 9 gồm cả `0-trace.network` (`postData`) và
`resources/<sha1>.dat` của trace zip khi trang gửi request; spike phase 07 không thấy vì dùng trang `data:`. Không đổi cấu hình
artifact, không thêm loại artifact. Điều kiện sử dụng: giá trị test chỉ được nhập ở request tạo bản nháp. Nếu chính câu task
chứa giá trị thì model chép lại vào chữ tự do của phiên (`task_assessment`, `visual_agent_steps.memory/evaluation_previous_goal/next_goal`);
các cột đó nằm ngoài danh sách nơi lưu đã khai báo và hệ thống không che chúng (redaction theo mẫu không biết giá trị đã gõ).
Đó là điều kiện sử dụng, không có code che: đừng đưa giá trị vào câu task.

**Phần ADR-002 phải sửa (không sửa ở phase này).** Hai câu của `docs/adr/002-generated-test-authority.md:16-20`: "Raw requests
and credentials are not persisted or sent to a model. Login and supplied credentials are outside v1 scope." Cần bổ sung
một đoạn ghi ngoại lệ có phạm vi: chỉ project có `vision_owned_test_target`, chỉ draft dựng từ vết task của phiên agent
(`provenance.agent_trace_source`). Giá trị tài khoản dùng một lần có thể nằm literal ở MỌI nơi source đi qua, tức các
nơi 1-5 và 8 của bảng trên (draft, test case, `test_runs.request`, `outbox_events.payload`, history workflow Temporal,
phản hồi API/dashboard), thêm workspace tạm của worker (nơi 7, tạm thời) và artifact của run (nơi 9: trace, snapshot DOM kể cả ô mật khẩu,
screenshot, video; spike phase 07 đã xác nhận có giá trị, kể cả khi test pass, giữ `retain_days`=30 theo contract).
Thời gian lưu thực tế của artifact không được bảo đảm 30 ngày vì job xoá artifact hết hạn đang lỗi trên stack cục bộ (xem "Rủi ro").
Vẫn không nằm trong raw request (`generation_requests`), audit, log, `provenance`; đường dựng không gọi model, còn các
đường sửa bằng model (nơi 11, 12) bị chặn, và excerpt `playwright-output` (xét thêm `worker-result`) của run có giá trị test BẮT BUỘC bị loại khỏi evidence gửi model (nơi 10)
(phiên agent gốc đã gửi task cho nhà cung cấp mà tenant đồng ý, ADR-046 mục Consequences). Danh sách nơi lưu này đã được
user chấp nhận ở Q10 (nơi 1-5, 8) và Q11 (nơi 9). Các câu còn lại của ADR-002
(planner không có quyền, allowlist origin, import chỉ `@playwright/test`, duyệt bất biến, thực thi trong workspace tạm)
giữ nguyên. Việc sửa là một phần của phase B6 và cần user duyệt chữ cụ thể lúc đó; ADR-047 chỉ nêu phạm vi sửa.

## Contract 4 trường

**Outcome.** Từ một phiên agent-loop `completed` có `task_assessment.status = achieved`, người có quyền yêu cầu một
bản nháp Playwright. Hệ thống tạo draft `pending_review` kèm bằng chứng (assessment, check, báo cáo nhất quán giữa
các phiên, vết các bước). Sau khi người có quyền duyệt, hệ thống tạo test case và đúng một run deterministic; kết
quả `TestExecutionResult.status` là verdict. `business_outcome` của phiên vẫn `unverified`.

**Constraints.**
- Không verdict từ model; không tự duyệt, không tự chạy, không tự thay hay sửa suite (ADR-001, ADR-002, `AGENTS.md`).
- Contract thực thi `TestExecutionRequest`/`TestExecutionResult` v1 không đổi hình dạng (`AGENTS.md`, mục Required
  checks 4); thêm trường phải qua version rõ ràng.
- Selector do code dựng từ locator đã xác minh; source chỉ import `@playwright/test` (`execution.py:29-37`).
- Giá trị đã gõ không được lưu trong phiên (chỉ độ dài). Giá trị test của bản nháp chỉ do người yêu cầu nhập lúc tạo
  draft; nó nằm literal trong source nên đi theo source tới mọi nơi liệt kê ở "Giá trị test (Q1)" (draft, test case,
  `test_runs.request`, `outbox_events.payload`, workflow Temporal, phản hồi API, và artifact của run, Q11); nó không
  vào audit, log, `provenance`, `generation_requests`, và không tới model qua đường sửa tự do.
- Chỉ dự án khai báo "FE test của tôi" (`vision_owned_test_target`) mới được sinh draft có bước `type` (mọi bước `type`
  mang giá trị literal, kể cả ô tìm kiếm; hệ quả của Q1); cờ này là khai báo của người có `MANAGE_PROJECT`, mặc định
  tắt (ADR-046 mục 5).
- Allowlist origin của dự án áp dụng như mọi draft (`generation.py:71-75`, `execution.py:93-106`).
- Prompt mới (nếu có) ở `agents/prompts/`, kèm README và version (`AGENTS.md`). Thay đổi hành vi kèm test tập trung.
- Không phụ thuộc phase 05 (FE thật); thiết kế phải chạy được trên fixture `task-ui`.

**Non-goals.**
- Không viết code, migration, test Playwright thật trong ADR này.
- Không đổi planner v4, handoff của planner, prompt `agent-loop-v4`, `domain/vision_task_assessment.py`.
- Không để assessment thành verdict; không đổi `business_outcome`.
- Không chọn framework/runner mới; không thêm API/Game runner.
- Không tự sửa/chữa draft bằng model sau khi sinh (khác `preflight-repair`, `generation.py:295-312`).
- Không tự chọn tài khoản test, không quản lý vòng đời tài khoản trên FE của người dùng.
- Không bộ dữ liệu test mã hoá, không kênh tiêm giá trị vào runner (phương án B của Q1, để sau).
- Không sinh draft từ phiên `not_achieved` (Q9), không sửa tay locator của bước bị chặn (Q4).
- Không đổi chính sách redaction hiện có (Q4, Q5) và không tự sửa ADR-002 trong phase thiết kế.
- Không sinh test cho mọi control của một trang (đó là mục tiêu cũ đã bỏ).

**Acceptance criteria (cho giai đoạn code, đo được).**
1. Trên fixture `task-ui`, với task `login-success`, `todo-add`, `search-results`: từ phiên `achieved` sinh được draft;
   draft duyệt xong chạy `passed`; chạy lại trên fixture bị phá cố ý (`/broken`) thì `failed` (test không "pass nhầm").
2. Mọi bước `type` có mặt trong source đúng thứ tự phiên; thứ tự bước của draft bằng thứ tự `step_index` (test đơn vị
   trên dữ liệu có nhiều action mỗi step, nhiều step).
3. Chuỗi giá trị test (dùng một giá trị mẫu duy nhất trong test) chỉ xuất hiện ở đúng tập nơi cho phép: source của draft,
   `test_cases.specification`, `test_runs.request`, `outbox_events.payload`, input workflow, phản hồi `GET` draft/run,
   và artifact của run (trace, snapshot DOM, screenshot; nơi 9, Q11; test quét trace/screenshot thật ở phase 16 để khẳng định
   tập này); KHÔNG xuất hiện ở DB phiên, step log, `audit_events`, log của control plane và worker,
   `provenance`, `generation_requests`, idempotency key, response của route yêu cầu, response lỗi. Test quét từng bảng và
   từng nguồn log (không chỉ hai bảng draft/test case) và khẳng định tập nơi xuất hiện bằng danh sách khai báo; thêm một
   nơi lưu mới làm test fail (Q10 = A: outbox, `test_runs.request` và workflow nằm trong tập cho phép). Giá trị có độ dài khác `text_chars` bị từ
   chối; project không bật cờ bị từ chối. Với draft/test case `contains_test_values`, đường sửa bằng model
   (`generation.py:289-312`, `routes/runs.py:306-345`) bị từ chối `credentials_in_source`.
4. Không đường nào tạo test case hay run mà không có quyết định `approved` của người có quyền (test: gọi trực tiếp
   use case và route với actor thiếu quyền; kiểm bảng `test_cases`/`test_runs` không đổi). Với draft loại này, người
   duyệt trùng người yêu cầu, hoặc không có `DECIDE_PROPOSAL`, hoặc thiếu `acknowledge_disposable_credentials` khi có giá
   trị test, đều bị từ chối và không đổi gì.
5. Draft từ nhóm phiên không nhất quán bị từ chối với lý do `assessment_inconsistent` và báo cáo (không có "đa số thắng"
   ngầm).
6. Audit có sự kiện cho: yêu cầu draft, draft sẵn sàng/thất bại, duyệt/từ chối, và bật/tắt cờ owned test target trên
   route policy; tất cả kèm `actor` là người thật (không dùng `system`), `correlation_id` xuyên suốt.
7. `uv run ruff check .`, các test mới và test hiện có của generation/vision qua; graph mới và graph bị chạm được cập nhật.

## Business flow

**Actor:** người yêu cầu có `SUBMIT_GENERATION` trên dự án; người duyệt là người khác có `DECIDE_PROPOSAL`
(`reviewer`, `project_admin` hoặc `tenant_admin`, Q7); control plane; worker Playwright. Agent/model không phải actor
có quyền.

**Tiền điều kiện:** phiên `exploration_engine=agent_loop`, `state=completed`, có `task_assessment` với
`schema_version=v1`; dự án có `vision_owned_test_target=true` nếu chuỗi có submit/gõ tài khoản; origin nằm trong
allowlist; phiên còn bằng chứng (không bị xoá theo retention).

**Các bước chính**
1. Người dùng mở kết quả phiên (`GET /explorations/{id}/result`, `routes/vision.py:805-828`) và chọn "tạo bản nháp
   test".
2. Control plane kiểm điều kiện và quyền; gom các phiên cùng nhóm (cùng `tenant`, `project`, `target_url`,
   `intent_hash`; `intent_hash` là sha256 của chữ task, `application/vision.py:93`, cột ở `models.py:127`), lập báo cáo
   nhất quán và so với ngưỡng cấu hình (khởi điểm 90%).
3. Phiên nguồn là phiên được chọn để yêu cầu (Q3); dựng hoặc đọc `AgentTaskTrace`, kiểm tra từng bước còn dựng được
   (locator xác minh, khung hình còn, không có hành động bị chặn).
4. Nếu chuỗi có bước `type`, form liệt kê các bước theo thứ tự; người yêu cầu nhập giá trị cho từng bước (Q1). Chỉ project
   bật cờ owned test target được nhận; độ dài phải khớp `text_chars`.
5. Một transaction: dựng source xác định, kiểm `validate_playwright_test_source`, tạo request `completed` + draft
   `pending_review` + audit `generation.requested` và `generation.completed` với actor là người yêu cầu.
6. Người duyệt (khác người yêu cầu, có `DECIDE_PROPOSAL`) xem draft cùng assessment, check, báo cáo nhất quán, danh sách
   giá trị test, rồi duyệt hoặc từ chối (`POST /test-generations/drafts/{id}/decision`, `routes/generation.py:332-371`);
   nếu có giá trị test phải gửi `acknowledge_disposable_credentials=true`.
7. Duyệt: preflight ở worker, tạo test case + một run, runner deterministic chạy, `TestExecutionResult` là verdict.

**Điểm rẽ nhánh và đường lỗi**

| Tình huống | Hành vi |
| --- | --- |
| `task_assessment.status = not_achieved` | Không sinh draft (Q9, user chốt); hiển thị "có thể là lỗi sản phẩm hoặc task sai" và đường điều tra |
| `blocked` hoặc `inconclusive` (`from_stop`, `from_step_limit`, `vision_task_assessment.py:59-73`) | Không sinh draft; trả lý do kèm số liệu controller |
| Phiên `unavailable` hoặc không có assessment (phiên cũ, ADR-046 mục Consequences) | Từ chối, `assessment_unavailable` |
| Nhiều phiên cùng nhóm, đồng thuận dưới ngưỡng, hoặc phiên nguồn không thuộc trạng thái modal | Từ chối, `assessment_inconsistent` kèm báo cáo; người dùng chạy thêm phiên (Q3) |
| Có bước `type` mà thiếu giá trị, độ dài không khớp `text_chars`, hoặc project không bật cờ | Từ chối `input_value_missing` / `input_value_mismatch` / `input_value_not_allowed`; draft không bao giờ chứa giá trị suy đoán |
| Ô nhập có nhãn bị lọc (ví dụ "Password"), Q4 giữ nguyên | Bước thiếu locator xác minh: từ chối `locator_unavailable` và nêu chính xác bước nào; không sửa tay |
| Người duyệt trùng người yêu cầu, hoặc thiếu `DECIDE_PROPOSAL`, hoặc thiếu xác nhận tài khoản dùng một lần | Từ chối ở use case duyệt (Q7, Q1); trả 409/404 theo mẫu hiện có, không tạo test case |
| Bước có `ephemeral_locator` (`dom_path`) | Từ chối bước đó; không sinh selector không bền |
| Khung hình/bằng chứng đã hết hạn (retention) | Từ chối `evidence_expired`; không dựng từ bằng chứng thiếu |
| Hành động `action_outcome_unknown`, hoặc operation `failed` trong chuỗi | Từ chối; chỉ chuỗi hoàn chỉnh mới dựng được |
| Preflight ở worker lỗi khi duyệt | Giữ nguyên hành vi hiện có cho draft từ Vision: báo lỗi, không sửa tự do (`generation.py:290-294`) |
| Duyệt rồi run `failed` | Đó là verdict `failed` thật; đi tiếp luồng triage/report hiện có, không tự sửa draft |

**Hậu điều kiện:** draft ở `pending_review` (chưa có test case, chưa có run) cho tới khi có quyết định; sau quyết
định bất biến (`generated_test_decisions.draft_id` unique, `models.py:542-549`). Phiên gốc không đổi; assessment vẫn
advisory.

## Data flow

```
visual_exploration_sessions (task_assessment, intent_hash, target_url, state)        [đọc]
visual_agent_steps (step_index, operation_ids, actions{kind,ref,text_chars})         [đọc]
visual_operations + visual_locator_evidence + visual_operation_frames                [đọc]
        |  (1) dựng gói vết: xếp theo step_index, ghép locator xác minh, bỏ ref, chỉ giữ độ dài chữ gõ
        v
gói vết trong bộ nhớ (không bảng mới; hash + session_id sẽ vào provenance)          [không ghi]
        |  (2) báo cáo nhất quán: nhóm theo (tenant, project, target_url, intent_hash)
        v
POST .../test-draft (body: giá trị test cho từng bước type, nếu có)
        |  (3) renderer xác định (không gọi model): source + assumptions + stop_conditions
        v
generation_requests(completed) + generated_test_drafts (pending_review, source_hash,
  provenance{agent_trace_source{session_id, trace_hash}, contains_test_values, owned_test_target,
  requested_by})  + audit generation.requested/completed                             [GHI #1, MỘT transaction]
        |  (4) người duyệt (khác người yêu cầu, DECIDE_PROPOSAL): POST .../drafts/{id}/decision
        v
preflight(worker) -> test_cases + test_runs(request) + outbox_events(payload.request)
  + decision + audit                                                                 [GHI #2, một transaction như hiện nay]
        |  (5) outbox -> workflow Temporal (input + history) -> TestExecutionRequest v1 -> worker (HTTP)
        v
workspace tạm của worker -> TestExecutionResult v1 (status = verdict) + artifacts      [đường hiện có]
```

Source (và giá trị literal trong đó) lặp lại ở: `generated_test_drafts`, `test_cases.specification`, `test_runs.request`,
`outbox_events.payload`, input/history của workflow Temporal, thân HTTP tới worker, workspace tạm, phản hồi API, và có
thể artifact; bảng đầy đủ kèm `file:line` ở mục "Giá trị test (Q1)".

Biến đổi hình dạng: (1) chuỗi step/operation -> danh sách bước tuyến tính, mất ref `version:n` và toạ độ; (3) bước ->
dòng Playwright (`getByRole/getByLabel/getByTestId/locator`, `locator_expression` ở `vision_source_renderer.py:16-31`),
check đã kiểm chứng -> `expect(...)`.

Side effect: chỉ ghi DB nội bộ ở (1)-(4) và đọc worker để preflight khi duyệt; (5) mở trình duyệt tới origin trong allowlist. Không có side effect lên FE
của người dùng trước bước duyệt. Lưu ý: run chạy thật sẽ gửi form và đổi dữ liệu trên FE test (cùng bản chất với phiên
agent, ADR-046 mục 5), nên cờ owned test target là điều kiện.

Transaction boundary (theo mẫu hiện có): bước (1) chỉ đọc; GHI #1 là một transaction ở route (như `submit`,
`routes/generation.py:213-227`, nhưng hoàn tất request và draft ngay, không qua outbox, audit ghi actor là người yêu cầu
thay vì `system` ở `generation.py:115`); GHI #2 một transaction qua `transactional_session`
(`routes/generation.py:340-363`), tạo test case, run, outbox, quyết định, audit cùng lúc. Gọi worker (preflight, chạy
run) không nằm trong transaction ghi của phiên Vision.

Redaction:
- Giá trị đã gõ không vào gói vết (chỉ `text_chars`), không vào audit, log, provenance. Quy tắc này giữ nguyên
  ADR-046 mục 5.
- Chữ model viết (`summary`, `checks`) đã qua `redact_value` khi lưu (`vision_unit_of_work.py:159-161`); gói vết chép
  lại bản đã redact, không đọc lại từ model.
- Giá trị test nằm literal trong source (Q1, user chốt) và theo source tới các nơi trong bảng ở "Giá trị test (Q1)",
  kèm ngoại lệ ADR-002 mô tả ở "Phần ADR-002 phải sửa". Source không được che ở outbox/workflow (Q10 = A). Body của
  request tạo draft chứa giá trị nên không được log nguyên văn (cần kiểm log của framework ở B7), và response của
  route yêu cầu không trả lại giá trị ngoài source của draft.
- Locator: dùng nguyên bộ lọc hiện có `validate_locator_value`, không đổi (Q4, Q5 giữ nguyên).
- Bằng chứng nhạy cảm của chạy lại: `ArtifactPolicy` mặc định giữ trace, video, screenshot cả khi thành công
  (`contracts/execution.py:53-62`); trace/video/output của một run có bước gõ tài khoản chứa giá trị. Đã kiểm chứng ở phase 07 (xem nơi 9, 10):
  trace và snapshot DOM chứa nguyên văn (kể cả mật khẩu), screenshot hiện chữ ở ô thường; B6 đưa kết quả vào mô tả xác nhận
  cho người duyệt. Rủi ro này đã được chấp nhận ở Q11 (mở rộng Q10) cho artifact; đường artifact tới model báo cáo (nơi 10):
  loại excerpt `playwright-output` (xét thêm `worker-result`) của run `contains_test_values` khỏi evidence gửi model là bắt buộc.

## Dùng lại và làm mới

| Phần | Dùng lại | Mới |
| --- | --- | --- |
| Trạng thái draft, quyết định bất biến, tạo test case + run, audit duyệt | `application/generation.py:230-364`, `models.py:524-549` | Kiểm điều kiện trước khi duyệt cho draft loại này: người duyệt khác người yêu cầu, có `DECIDE_PROPOSAL`, xác nhận tài khoản dùng một lần (Q7, Q1) |
| Hình dạng thực thi | `TestExecutionRequest/Result` v1, `PlaywrightTestSourceMode`, `ExecutionRunner` | Không đổi (Q1 chọn literal trong source, không thêm kênh tiêm giá trị) |
| Bảng request -> draft | `GenerationRequestModel`, `GeneratedTestDraftModel`, `complete_generation`-kiểu ghi draft `pending_review` | Không thêm cột; request tạo `completed` cùng draft trong một transaction, không qua outbox/`generation_events.py`; thêm guard `credentials_in_source` ở `generation.py:289-312` và `routes/runs.py:306-345` |
| Renderer | `locator_expression`, `literal`, `validate_playwright_test_source` (`vision_source_renderer.py:12-31`) | Renderer tuyến tính: `type`, thứ tự tuyến tính, assertion kết quả |
| Provenance | `PlanningProvenance` (`contracts/generation.py:116-125`) | Trường tuỳ chọn `agent_trace_source`, danh sách phiên bổ trợ, `owned_test_target` tại thời điểm tạo; phải thêm theo kiểu additive vì model `extra="forbid"` |
| Quyền | `SUBMIT_GENERATION` (yêu cầu), `DECIDE_PROPOSAL` (duyệt loại draft này; chỉ người, không service, `authorization.py:107-115`) | Không đổi ma trận vai; thêm quy tắc "khác người yêu cầu" và nhánh kiểm quyền theo `provenance.agent_trace_source` trong use case/route duyệt |
| Dựng bằng chứng | `visual_agent_steps`, `visual_operations`, `visual_locator_evidence` | Hàm dựng gói vết tuyến tính (không bảng mới), báo cáo nhất quán |
| API | Mẫu `POST /runs/{id}/revised-draft` (CSRF, `SUBMIT_GENERATION`, idempotency) | `POST /vision/explorations/{id}/test-draft` (tên tạm), `GET` báo cáo nhất quán; thêm trường `acknowledge_disposable_credentials` vào `DecisionRequest` |
| Audit route policy | `AuditEvent`, `SqlAlchemyAuditEventRepository` (đã dùng ở `routes/generation.py:213-219`) | Audit cho `PUT .../policy` (Q6) |
| Bảng `agent_proposals`/`approvals` | Không dùng: `run_id` bắt buộc (`models.py:584`) | Giữ nguyên cho triage/healing |

## Dùng nhiều phiên nhất quán làm bằng chứng

Định nghĩa nhóm: cùng `tenant`, `project`, `target_url`, `intent_hash` (`models.py:127`). Chỉ tính phiên `completed` có
assessment; phiên `unavailable` không phải bằng chứng về task (ADR-046 mục 1).

Báo cáo nhất quán (read-only, hiển thị cho người dùng và người duyệt, và lưu hash vào provenance): số phiên, phân bố
trạng thái assessment, tỉ lệ đồng thuận (cùng cách tính với bộ đo `benchmark/task_ui/stability.py:138-146`: phiên
trùng trạng thái modal / phiên có assessment). Bản đầu chỉ có tỉ lệ đồng thuận (r3: bỏ chỉ số "mức giống nhau của vết";
thêm sau nếu thực tế cần). Lưu ý đồng thuận trạng thái chưa chứng minh vết giống nhau; người duyệt vẫn thấy vết của
phiên nguồn.

Quy tắc (Q3, user chốt 2026-11-26):
- Draft luôn dựng từ **một** phiên nguồn; các phiên khác chỉ là bằng chứng bổ trợ. Đã loại: bắt buộc N phiên, hợp nhất
  vết nhiều phiên.
- Từ chối khi trạng thái modal khác `achieved`, hoặc phiên nguồn không thuộc trạng thái modal, hoặc đồng thuận dưới
  ngưỡng. Ngưỡng 90% lấy làm điểm xuất phát vì là ngưỡng đã dùng ở `stability.py:23` (đo trên fixture), là tham số
  cấu hình (user chốt "khởi điểm 90%"), không phải hằng bất biến.
- Mâu thuẫn không được giải bằng "đa số thắng" tự động. Số đo cho thấy: ở r4 phiên bất đồng là phiên sai (agent
  nhập hai lần rồi kết luận thiếu "Balo laptop"); ở r1 `login-failure` bị `not_achieved` sai vì snapshot không có chữ
  (plan.md, bảng r1). Ngược lại, đồng thuận 100% vẫn có thể cùng sai (lỗi hệ thống, ví dụ prompt hay trang thiếu chữ).
  Nhiều phiên nhất quán chỉ làm giảm nhiễu ngẫu nhiên, không thay người duyệt. Bộ đo có nhãn kỳ vọng
  (`tasks.v1.json`), người dùng thật thì không, nên người duyệt phải đọc check và bằng chứng.
- Chi phí: mỗi phiên 25-61 giây và khoảng 2-3 lượt gọi model (r4: 2,32). Báo cáo nhất quán chỉ đọc các phiên đã có, không
  tự chạy thêm phiên; người dùng chạy thêm phiên khi muốn tăng độ tin cậy.

## Ranh giới duyệt

- **Ai yêu cầu:** `SUBMIT_GENERATION` trên dự án (`authorization.py:35-43,56-68`), cùng CSRF như route tiền lệ
  (`routes/runs.py:294-299`). Service principal không có quyền này (`authorization.py:69`).
- **Ai duyệt (Q7, user chốt 2026-11-26):** người khác người yêu cầu và có vai `reviewer`, `project_admin` hoặc
  `tenant_admin`, đúng ADR-004 ("proposal author ... can never approve it",
  `docs/adr/004-proposed-identity-rbac.md:41-43`). Hiện route duyệt đòi `DECIDE_GENERATION`
  (`routes/generation.py:350`), thuộc `contributor`/`project_admin`/`tenant_admin` (`authorization.py:35-55`) mà không
  có vai `reviewer`, và `DecideGeneratedDraft` không so người gửi với người duyệt (`generation.py:242-364`). Với draft
  có `provenance.agent_trace_source` thì use case/route duyệt đòi `DECIDE_PROPOSAL` (đúng ba vai trên, người thật,
  `authorization.py:44,50,61,110-114`) thay cho `DECIDE_GENERATION`, và đòi `decided_by != provenance.requested_by`
  (chuỗi `subject` chụp lúc yêu cầu). Các loại draft khác giữ hành vi cũ, không đổi ma trận vai. Hệ quả: một actor đơn
  lẻ (tenant local chỉ có một `tenant_admin`) không hoàn tất được vòng này; test E2E (B9) cần hai actor, cách header local
  `X-Actor-Id` phục vụ được. Người yêu cầu cần `SUBMIT_GENERATION` (không có ở `reviewer`) nên hai việc tách vai tự nhiên.
- **Audit:** dùng lại `generation.requested`, `generation.completed/failed`, `generated_draft.approved/rejected`
  (`generation.py:111-121,186-197,353-363`). Hai điểm yếu phải sửa cho đường mới: (a) `generation.requested` hiện ghi
  `actor="system"` (`generation.py:115`), đường mới phải ghi người yêu cầu; (b) `audit_events` chỉ có
  `actor, action, entity_type, entity_id, correlation_id` (`models.py:622-629`), không có hash trước/sau như
  `docs/architecture-implementation.md:203` mô tả, nên hash gói vết, danh sách phiên bổ trợ và giá trị cờ owned test
  target tại thời điểm tạo được ghi vào `provenance` của draft chứ không phải vào audit.
- **Audit của route policy (Q6, user chốt 2026-11-26: thêm).** Hiện `PUT .../policy` không ghi audit
  (`routes/generation.py:154-177`, `repositories.py:341`) cho cả trường cũ lẫn `vision_owned_test_target`. Phase B5 thêm
  một `AuditEvent` mỗi lần gọi (actor là `subject` của người gọi, `entity_type=project_execution_policy`,
  `entity_id=project_id`, `correlation_id` mới vì request không mang), với `action` phân biệt khi cờ đổi trạng thái
  (`project_policy.owned_test_target.enabled/disabled`) và `project_policy.updated` cho phần còn lại. `audit_events`
  không có cột payload (`models.py:622-629`) nên sự kiện không mang giá trị cũ/mới ngoài tên action; không schema mới.
  Cần biết giá trị cũ để phân loại, nên `set_policy` (`repositories.py:341`) phải trả cả giá trị trước. Draft vẫn chụp
  giá trị cờ lúc tạo vào provenance; audit policy là bằng chứng ai bật và khi nào. Đã loại: không thêm audit (không
  chứng minh được ai bật cờ). Bản ghi cũ trước B5 không có audit này; điều đó được ghi trong B5.
- **Không bao giờ tự chạy hay thay suite:** đường duy nhất tới test case/run là `DecideGeneratedDraft` với
  `approved=true` (`generation.py:262-342`); thiết kế không thêm đường nào khác. Draft mới là bản ghi mới, không sửa
  test case đã duyệt (cùng nguyên tắc "the failed revision remains immutable", `routes/runs.py:307`). Thay suite hiện có là
  ngoài phạm vi.
- **Duyệt thấy gì:** source đầy đủ và hash, assessment (đánh dấu advisory), từng check với evidence, báo cáo nhất
  quán, số liệu controller (`actions_completed/failed/blocked_or_skipped`), danh sách bước bị loại và lý do, nơi giá
  trị test đến từ đâu.
- **Duyệt xong, run fail:** là verdict `failed` thật, không tự sửa.

## Hệ quả của việc giữ chính sách redaction (Q4, Q5)

- Q4: ô mật khẩu có nhãn tiếng Anh "Password" không có locator xác minh (`contracts/vision.py:214-217,226-233`), nên bước
  đó bị chặn `locator_unavailable` và draft bị từ chối. Draft đăng nhập chỉ dựng được khi nhãn không chứa từ nhạy cảm
  (ví dụ "Mật khẩu"). Page text có chữ "password" cũng đã bị lọc từ phía worker (ADR-046 mục 9), nên ứng viên assertion
  loại các chữ đó. Xem lại khi phase 05 trên FE thật cho thấy cần.
- Q5: `password=...` trong task tiếp tục bị từ chối khi gửi (`application/vision.py:87`, `generation.py:68-70`;
  `contracts/generation.py:20-32`). Giá trị không bao giờ được trích từ chữ task, nên thiết kế Q1 lấy giá trị từ người
  yêu cầu nhập trực tiếp.

## Chia phase đề xuất cho giai đoạn code

Theo các quyết định đã chốt. Mỗi phase kèm test tập trung (`AGENTS.md`). `qa required` nghĩa là cần QA độc lập sau
leader review. Số phase là số thứ tự trong ADR; số phase trong plan.md do PM gán khi user duyệt.

| Phase | Outcome | Owner | QA | Phụ thuộc | Graph đọc trước / cập nhật |
| --- | --- | --- | --- | --- | --- |
| B0 Kiểm chứng (spike, không đổi code) | Chạy handoff builder trên 3 phiên agent thật (login, todo, search) để xác nhận giả định 2 và 3; chỉ ra trường nào dùng được; xác nhận locator xác minh có cho `type`; xác nhận trace/video/`playwright-output` của run có chứa giá trị gõ hay không và excerpt báo cáo có mang nó tới model không (nơi 9, 10); xác nhận retention của outbox và history workflow Temporal (nơi 4, 5); kết luận bằng số | none | skip | duyệt ADR | đọc `vision-agent-loop`, `vision-exploration` |
| B1 Gói vết | Contract `AgentTaskTrace` v1 và hàm dựng tuyến tính từ `visual_agent_steps` (thuần, không bảng, không migration), hash ổn định, không chứa giá trị gõ, từ chối khi bằng chứng thiếu | be-developer | required | B0 | đọc `vision-agent-loop`, `vision-exploration`; lập mới `agent-task-draft` |
| B2 Báo cáo nhất quán | Truy vấn nhóm phiên, chỉ số đồng thuận, endpoint đọc (`READ`), không sinh draft. Giữ phase riêng (không gộp vào B7): endpoint chỉ đọc, nhỏ, kiểm độc lập và chạy song song với B3 sau B1 | be-developer | required | B1 | `agent-task-draft`; tái dùng cách tính `task-ui-stability` |
| B3 Ứng viên assertion kiểm chứng (Q8) | Controller đối chiếu check `met` với chữ trang/tên control đã thấy trong phiên, lưu ứng viên đã kiểm chứng; không có model tự đặt chữ | be-developer | required | B1 | đọc `vision-agent-loop`, `playwright-vision-worker` (chỉ đọc); cập nhật `vision-agent-loop`; nếu đổi prompt: `agents/prompts/README.md` |
| B4 Renderer tuyến tính + provenance | Renderer xác định cho `navigate/click/type/scroll/wait` + assertion từ ứng viên B3; chỉ locator `verified` (Q2); `type` nhận giá trị từ tham số; provenance additive (`agent_trace_source`, `contains_test_values`, `owned_test_target`, `requested_by`); test snapshot source | be-developer | required | B1, B3 | `agent-task-draft`; `contracts/generation.py` (chạy lại test hợp đồng) |
| B5 Audit route policy (Q6) | `PUT .../policy` ghi `AuditEvent` (actor thật, `project_policy.owned_test_target.enabled/disabled`, `project_policy.updated`); `set_policy` trả giá trị trước; test route + audit; độc lập với B1-B4, có thể chạy song song | be-developer | required | duyệt ADR | đọc `vision-exploration`; cập nhật `vision-exploration` (routes) |
| B6 Ranh giới duyệt và ngoại lệ ADR-002 (Q1, Q7) | Use case/route duyệt cho draft có `agent_trace_source`: `DECIDE_PROPOSAL`, khác `requested_by`, `acknowledge_disposable_credentials` khi có giá trị test; guard `credentials_in_source` cho sửa preflight tự do và `revised-draft`; loại excerpt `playwright-output` (xét thêm `worker-result`) của run `contains_test_values` khỏi evidence gửi model (bắt buộc, kết quả spike phase 07); không che source ở outbox/workflow (Q10 = A); kết quả B0 về trace/video/workflow history ghi vào mô tả xác nhận; **sửa ADR-002** bằng đoạn ngoại lệ liệt kê đủ các nơi lưu, gồm artifact của run (Q11) và ghi chú job retention artifact (chữ cụ thể do user duyệt lúc đó) | be-developer | required | B4, B5 | `agent-task-draft`; `docs/adr/002-generated-test-authority.md` (được sửa ở phase này, cần user duyệt) |
| B7 API tạo draft | `POST` tạo draft (CSRF, `SUBMIT_GENERATION`, idempotency theo `session_id` + hash gói), kiểm cờ project, độ dài giá trị khớp `text_chars`, một transaction request + draft + audit với actor thật; body có giá trị không được log; không đưa giá trị vào response ngoài source của draft; không migration; test quét nơi lưu theo AC3 | be-developer | required | B2, B4, B6 | `vision-exploration` (routes), `agent-task-draft` |
| B8 Dashboard duyệt | Panel xem assessment, check, nhất quán, source, danh sách bước `type` để nhập giá trị; nút yêu cầu draft; hộp xác nhận tài khoản dùng một lần; duyệt qua route hiện có | fe-developer | required | B7 | `vision-dashboard` |
| B9 End-to-end trên fixture | Chuỗi hoàn chỉnh trên `task-ui` với hai actor: achieved -> yêu cầu -> người khác duyệt -> run passed; ca âm: `/broken`, `not_achieved`, không nhất quán, thiếu quyền, tự duyệt, thiếu xác nhận, project không bật cờ, bằng chứng hết hạn, nhãn "Password"; đo độ ổn định của test qua N lần chạy lại | both | required | B8 | `task-ui-stability`, `vision-agent-loop` |

Gợi ý thứ tự: B0 -> B1 -> (B2, B3 song song, B5 song song từ lúc duyệt ADR) -> B4 -> B6 -> B7 -> B8 -> B9. Phase 05 (FE
thật) không phải điều kiện; chạy trên FE thật là bước đo sau B9.

**Graph.** Đọc: `docs/graphs/vision-agent-loop.md`, `docs/graphs/vision-exploration.md`, thêm
`docs/graphs/playwright-vision-worker.md` khi đụng worker/contract, `docs/graphs/vision-dashboard.md` cho B8,
`docs/graphs/task-ui-stability.md` cho B9. **Lập mới** `docs/graphs/agent-task-draft.md` (`hgraph add agent-task-draft ...`)
gồm file mới của B1-B7 và các file hiện chưa thuộc graph nào mà thiết kế này chạm:
`application/generation.py`, `application/vision_handoff.py`, `application/vision_source_renderer.py`,
`domain/proposals.py`, `application/proposals.py`, `runners/ports.py` (kết quả `hgraph brief` ngày 2026-11-26: các
file này "chưa thuộc graph nào"). Cập nhật `vision-exploration` khi thêm route (B4, B7), `vision-agent-loop` khi B3
đụng `vision_agent_loop.py`.

## Rủi ro

- **Giả định 2 (handoff cây so với chuỗi agent): đã kiểm chứng ở phase 07, ĐÚNG** (0/15 phiên có nhánh đủ chuỗi), nên
  đường dựng mới như thiết kế là bắt buộc. Phạm vi: fixture `task-ui`; FE thật có thể có `dom_path`/`ephemeral_locator`,
  đã có ca từ chối ở phase 08, 11, 16.
- **Job xoá artifact hết hạn đang lỗi cả lô trên stack cục bộ (lỗi có sẵn, ngoài phạm vi, ghi nợ).** Spike phase 07: log worker
  có `artifact.retention.failed` mỗi giờ; 12 artifact `file://` hết hạn từ 2026-08 vẫn còn; chưa quan sát được lần xoá
  thành công nào. `ExpireArtifacts.execute` bắt lỗi từng artifact trong vòng lặp (`application/artifact_retention.py:25-30`,
  rồi log `artifact.retention.completed` kèm `failed_count`), còn `artifact.retention.failed` được ghi ở `except` ngoài cùng
  của `expire_artifacts_forever` (`infrastructure/workflows/temporal_worker.py:111-132`), tức ngoại lệ ở phiên,
  `list_expired` hoặc dựng store làm hỏng cả lô, kể cả artifact `s3://`; nguyên nhân chưa chẩn đoán. Hệ quả: giá trị
  tài khoản trong trace/screenshot (nơi 9, Q11) có thể sống lâu hơn 30 ngày `retain_days`, nên thời gian lưu thực tế không được
  bảo đảm. User xử lý riêng bằng `/h-fix`; không thêm phase, không chặn phase 08-16.
- **Test pass nhầm do assertion yếu.** Nếu chỉ có `visible/enabled` thì test pass dù tính năng hỏng. Đó là lý do B3,
  và là lý do ca âm `/broken` nằm trong tiêu chí xong.
- **Lệch giữa chữ agent thấy và chữ chạy lại** (trang đổi theo dữ liệu, thứ tự): draft có thể flaky dù phiên ổn
  định. B9 đo độ ổn định của test chứ không chỉ của phiên.
- **Dữ liệu trên FE test bị đổi mỗi lần chạy** (thêm, xoá): test lặp lại cần trạng thái đầu xác định. Fixture có
  `POST /__reset` (ghi chú trong `tasks.v1.json`); FE thật của người dùng không có, nên đây là điều kiện tiên quyết
  người dùng phải trả lời trước khi chạy trên FE thật, ngoài phạm vi ADR này.
- **Credential lặp ở nhiều nơi lưu** (Q1 chấp nhận tài khoản dùng một lần, nhưng nơi lưu rộng hơn draft/test case:
  `test_runs.request`, `outbox_events` không có mã xoá (đã kiểm chứng), history Temporal cục bộ 24h (đã kiểm chứng), phản hồi API, và artifact
  của run (đã kiểm chứng có giá trị; xem bảng ở "Giá trị test (Q1)", B6). User đã chấp nhận lưu nguyên văn ở outbox/workflow (Q10) và artifact (Q11). Hệ quả: đừng bật cờ owned test target cho site thật; ADR-046 đã nói cờ không dành cho production.
- **Giá trị nằm trong câu task** (phase 16 r1 đo, user chấp nhận 2026-11-28): nếu câu task do tác giả viết chứa giá trị (tài khoản
  demo, từ khoá), model chép lại vào `visual_exploration_sessions.task_assessment` và `visual_agent_steps` (chữ tự do), ngoài danh sách
  nơi khai báo. Giá trị chỉ nhập lúc xin draft thì vắng ở các bảng phiên (đo bằng giá trị mẫu). Điều kiện sử dụng: giữ giá trị
  ngoài câu task; không thêm code che chữ tự do.
- **Giá trị do người yêu cầu nhập** (user đã chấp nhận khi duyệt ADR, 2026-11-26): nếu sau này muốn nguồn khác (ví dụ
  trích từ task), phải mở lại vì xung đột Q5.
- **F5, kết quả chứa chữ đã gõ ở phiên (phase 16 phát hiện, phase 17 sửa cho phiên mới).** Ứng viên `verified_text` lấy nguyên
  văn chữ trang, nên ứng viên như `hoàn thành: <tên việc>` mang giá trị agent đã gõ; khi người yêu cầu nhập giá trị khác lúc xin
  draft, test sinh ra `failed` sai (draft `81267bb8`, run `ea7cbb7a`; hướng an toàn, không pass nhầm, không lộ giá trị). Cách sửa
  (phương án (i) của leader, user chọn 2026-11-28): lúc controller dựng ứng viên (`domain/verified_text.py`, gọi ở
  `application/vision_agent_loop.py`), ứng viên nào bằng hoặc chứa hoặc nằm trong một giá trị agent đã gõ ở phiên (so không phân biệt
  hoa thường, gộp khoảng trắng; đoạn ngắn hơn 2 ký tự chỉ tính khi trùng cả mục) được đánh cờ `derived_from_typed` trong
  `AgentTaskAssessmentCopy.verified_text.items[]` (contract đóng, trường tuỳ chọn mặc định false). Chỉ lưu cờ, không lưu giá trị gõ
  (giá trị chỉ nằm trong bộ nhớ của vòng lặp, cùng đời với `ObservedText`). Renderer (`application/agent_task_renderer.py`) không
  sinh assertion cho ứng viên có cờ và ghi vào `stop_conditions` "N candidate(s) were left out: their text holds a value typed in the
  session..." (không kèm chữ nào). Hệ quả cố ý: test của task có kết quả phụ thuộc giá trị gõ (tìm kiếm, đăng nhập "Xin chào, <tên>", thêm
  việc) bớt assertion, có khi chỉ còn `visible/enabled` (đã có ghi chú "chưa được assert"); đổi lấy việc test không `failed` sai khi
  người yêu cầu nhập giá trị khác. `trace_hash`: cờ false bị bỏ khỏi mọi bản dump (`exclude_if`), nên phiên cũ (không có cờ) và phiên
  mới không có ứng viên nào bị đánh cờ giữ đúng hash của phase 16 (test ghim bằng sha256 độc lập); chỉ phiên mới có ít nhất một ứng
  viên bị đánh cờ đổi hash, đúng vì nội dung khác. Draft đã tạo giữ provenance cũ (replay theo `session_id` + `trace_hash` không bị
  ảnh hưởng). **Giới hạn đã biết:** phiên lưu trước phase 17 không có cờ và không thể bổ sung (giá trị gõ không bao giờ được lưu),
  nên draft dựng từ phiên cũ vẫn giữ hành vi cũ; muốn có cờ phải chạy lại phiên bằng control plane mới. So khớp theo chữ nên có hai
  sai số: ứng viên trùng ngẫu nhiên với giá trị gõ (bị loại thừa, test yếu hơn, hướng an toàn) và chữ trang biến đổi giá trị gõ (ví dụ
  viết hoa theo ngôn ngữ khác, bỏ dấu) thì không bị bắt (test `failed` sai như cũ).
- **F4, `search-results` không assert kết quả tìm (phase 16 phát hiện, KHÔNG sửa ở phase 17, ESCALATE).** Nguyên nhân có bằng chứng:
  chữ kết quả không bao giờ vào `ObservedText`. Worker chỉ đọc chữ trang từ `[role="alert"]`, `[role="status"]`, `h1-h6/[role="heading"]` và
  `p` (`workers/playwright/src/vision-dom.ts:44-48`) còn danh sách kết quả của fixture là `<li>` (`benchmarks/targets/task-ui/server.mjs:176`;
  trace r2 ghi `<li data-name="balo laptop">Balo laptop - 310.000 đ</li>` và `<p id="empty" role="status" hidden>`). Nên "Balo laptop" không
  thể thành ứng viên dù agent trích dẫn, và chỉ còn tên điều khiển ("Từ khoá", "Tìm"). F2 (reset `ObservedText` ở mỗi lần quan sát) và bộ
  lọc `verified_text` không phải nguyên nhân (quan sát cuối chính là trang kết quả). Chưa phân biệt được offline việc agent có trích
  "Balo laptop" hay không (cần DB phiên); không đổi kết luận. Sửa phải đổi worker (mở rộng bộ chọn chữ trang sang `li`/ô bảng, TS, build
  lại worker, đo lại ngân sách chữ trang) và bàn lại F5 cho riêng loại task này: kết quả tìm chứa chính từ khoá gõ nên cờ
  `derived_from_typed` sẽ loại nó (test `test_f4_02`), do đó cần một quy tắc khác (ví dụ assert số lượng hoặc phần không chứa từ khoá).
  Ngoài phạm vi controller/renderer của phase 17 nên chuyển thành phase riêng do user quyết; `passed` của `search-results` hiện chưa
  chứng minh kết quả tìm kiếm.
- **Người duyệt khác người yêu cầu** làm vòng không chạy được với một actor duy nhất (tenant local); chấp nhận cho loại
  draft này.
- **Cờ owned test target bị tắt giữa chừng:** draft đã tạo vẫn tồn tại; kiểm lại cờ ở bước duyệt cho draft có
  `contains_test_values` (B6).
- **Chi phí và độ trễ** của nhiều phiên làm bằng chứng: chỉ phát sinh khi user tự chạy thêm phiên (Q3).
- **Một đường kiểm duyệt duy nhất:** nếu về sau có người thêm đường tạo test case không qua `DecideGeneratedDraft`,
  mất bảo đảm của ADR-002. Test AC4 ghim điều này.

## Câu hỏi mở

Không còn câu hỏi mở chặn thiết kế. Mười một câu (Q1-Q11) đã được user chốt ngày 2026-11-26, ghi ở mục "Quyết định của
user"; Q10 (chỗ lưu source ở outbox/`test_runs.request`/workflow) được hỏi sau khi lần theo đường đi của source, Q11
(artifact của run) sau spike phase 07.

Hai lựa chọn kỹ thuật do PM đề xuất đã được user chấp nhận khi duyệt toàn bộ ADR (2026-11-26): (a) giá trị test do người
yêu cầu nhập trong request tạo draft (qua HTTP body), cần hai actor cho một vòng; (b) draft dựng đồng bộ trong một
transaction, không qua outbox.

## Hệ quả

- Thiết kế không thay đổi hành vi hiện tại; mọi thay đổi nằm ở giai đoạn code sau khi user duyệt.
- Nếu user duyệt, plan.md thêm các phase B0-B9 (PM lập) và ADR chuyển trạng thái. ADR-002 phải được sửa ở phase B6
  (phạm vi nêu ở "Phần ADR-002 phải sửa") trước khi bất kỳ draft có giá trị test nào được tạo; ADR-047 không tự sửa nó.
- Phase B5 (audit route policy) có ích độc lập và không phụ thuộc phần còn lại.
- Q10 = A và Q11 = A: đoạn ngoại lệ ADR-002 (phase B6) liệt kê đủ các nơi lưu ở bảng "Giá trị test (Q1)", gồm artifact
  của run; không có phase che source ở dispatch.
- Phát hiện kèm theo: `authorization.py` và ADR-004 lệch nhau về quyền duyệt chung (`authorization.py:35-43` so với
  `adr/004...:41-43`) vẫn còn cho mọi loại draft khác (chỉ draft loại này được siết, Q7), và `generation.requested`
  ghi `actor="system"` (`generation.py:115`) cho đường cũ. Nên xử lý riêng.

## Không thay đổi

Planner v4 và handoff của nó, prompt `agent-loop-v4`, `domain/vision_task_assessment.py`, hình dạng
`TestExecutionRequest/Result` v1, allowlist origin, quy tắc "model không bao giờ đưa verdict", `business_outcome =
unverified`.
