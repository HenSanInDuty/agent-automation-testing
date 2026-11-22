# Vòng lặp cải thiện Vision đến >95%

Ngày lập: 2026-11-09, Asia/Saigon. Trạng thái: in progress — phase 04 reopened after round 17 qualification failure; 3/5 phase completed.
Đây là hồ sơ tiến độ chuẩn; mọi vòng chạy cập nhật ở đây và trong nhật ký benchmark.
progress_url: https://claude.ai/artifact/7Wpg2znWAUaQAPGrx6PQxP (`progress.html`, h-cook) · auto_continue: false

## Mục tiêu và quyết định

Yêu cầu: chạy → xem vì sao lỗi → sửa → chạy tiếp, đến khi >95% chính xác.
Phạm vi ban đầu: tác vụ Mongchiton đã lưu, trang chủ desktop và các nút trong
phạm vi đã gán nhãn; không suy rộng thành độ đúng nghiệp vụ của cả website.

Đã xác nhận từ phiên trước: giữ `codex_cli / gpt-6-luna`, prompt v11, consent,
20 model calls/phiên, 5 calls/phút, 50 states, 10 hops, 120 giây/bước.
Revision được duyệt 2026-11-09: project local đang dùng **100 states + 20 hops**;
người dùng xác nhận "duyệt, làm đi bạn". Các caps khác giữ nguyên. Chi tiết
phạm vi tại `policy-expansion-proposal.md`; đã deploy và PUT/GET policy xác minh.
Chỉ triển khai local, không thay đổi website đích hay phê duyệt test được sinh.

Giả định chờ người dùng điều chỉnh: “>95%” yêu cầu **cả bao phủ đã xác minh lẫn
độ chính xác tương tác**, trên **3 lượt liên tiếp** của cùng một bản mã/config/dataset.
Đã hỏi riêng người dùng về cách hiểu này; chưa có phản hồi tại lúc lập kế hoạch.
Không chờ xác nhận các lựa chọn kỹ thuật thông thường khi thực thi đã được yêu cầu.

## Bộ đo và điều kiện hoàn thành

| Chỉ số | Định nghĩa | Ngưỡng |
| --- | --- | --- |
| Bao phủ đã xác minh C | Số mục tiêu duy nhất đúng trong oracle có thao tác và kết quả UI được xác minh / toàn bộ mục tiêu dương trong oracle của lượt | >95% mỗi lượt |
| Độ chính xác A | Số lần tương tác đúng mục tiêu, đúng loại hành động và đúng kết quả UI dự kiến / tất cả lần thử click/type explore, gồm rejected/failed/unknown/thiếu bằng chứng | >95% mỗi lượt |
| Phát hiện nút | Precision và recall đối với positives/negatives được gán nhãn độc lập | Cả hai >95% |
| Bất biến an toàn | Nhấn sai mục tiêu, hành động ngoài phạm vi, lặp side effect không được phép, tự sửa verdict, bỏ qua guard | 0 |
| Bằng chứng | Mọi mục tiêu được tính đúng có operation, locator/live binding, before/after và oracle khớp | 100% của tử số |
| Lặp lại | 3 lượt liên tiếp, browser context mới, một bản mã/config/oracle, ít nhất 100 lần thử tương tác cộng lại | Tất cả qua |

Với oracle vẫn là 47 nút, ít nhất **45/47 = 95,74%** phải được xác minh mỗi lượt.
47 chỉ là dữ liệu ví dụ, không hard-code vào runtime; dùng so sánh nguyên
`100 * numerator > 95 * denominator`, không làm tròn 95% thành đạt.
Mẫu số rỗng → không thể đánh giá. Các wait/scroll/restore không làm tăng A;
báo cáo tỷ lệ và lỗi của chúng riêng. Click lặp cùng một nút không tăng C.
Sai mục tiêu là hard failure dù A tổng vẫn >95%.

“Đúng kết quả” ở đây là kết quả UI khai báo trước: đúng URL/popup, trạng thái
nút/tab/carousel, hoặc no-op được gán nhãn trước và có bằng chứng. HTTP 200,
`completed`, ảnh khác đi hay lời tự đánh giá của LLM không đủ.
Mục chưa có oracle hoặc thiếu evidence không được tính vào tử số.
Business outcome vẫn `unverified` nếu không có test nghiệp vụ riêng.

Đạt benchmark >95% không được đổi kết luận runtime `partial` thành `completed`.
Có thể còn tối đa một phần nhỏ chưa xác minh: phải liệt kê ID/lý do từng mục.
Không tuyên bố “độ tin cậy thống kê >95%” hoặc đúng cho mọi website từ 3 lượt.

## Bằng chứng từ source scout

| Nguồn | Hiện trạng và hệ quả |
| --- | --- |
| `benchmark/vision/sequential/COMPLETION-20261109.md` | Lượt cuối c8fbd0ea-c2cd-467d-a90e-3fabab39e462: 27/47, 80 completed operations, 1 rejected restore wait, 36 states; chưa có accuracy oracle cho 27 click |
| `apps/control-plane/application/vision_trace_events.py` | restore giữ checkpoint gốc, popup cursor, preflight toàn replay path, bounded refresh sau Back; chưa xử lý tổng quát race prepare→dispatch của restore |
| `workers/playwright/src/vision-operations.ts` | execute so sánh state sau prepare trước dispatch; viewport cố định 1280×720; guard đã chặn thay đổi tương tác thật ở lượt cuối |
| `workers/playwright/src/vision-checkpoints.ts` | Tách interaction/visual semantics; private form values chỉ trong RAM; không bỏ guard để tăng điểm |
| `workers/playwright/src/vision-revalidation.ts` | Có kiểm tra Page/document/context/private forms/exact node và ánh xạ binding; có thể tái sử dụng có kiểm chứng, không mặc nhiên là checkpoint restoration |
| `apps/control-plane/domain/vision_conclusion.py` | completed operation không chứng minh business success; giữ nguyên ngữ nghĩa kết luận |
| `benchmark/vision/visual-buttons/mongchiton-desktop.json` | 47 positives + 14 negatives, gán nhãn độc lập ngày 01/11, viewport 1440×900: phải rà lại tại 1280×720 |
| `workers/playwright/src/fixtures/visual-buttons-audit.ts` | Audit chỉ đọc, hiện ghi đè live-audit.json và dùng expected=47: cần output riêng mỗi lượt và denominator từ dataset |
| `benchmark/vision/codex/run_offline.py` | Harness DB/Chromium cô lập, không credential/provider; loại configured-stack test |
| `benchmark/vision/sequential/run.py` | Benchmark synthetic cũ ghi file theo ngày cố định; không dùng làm loop production hoặc ghi đè lịch sử |
| `apps/control-plane/application/vision_reload.py` | Reload kiểm tra quyền, consent fingerprint, model và idempotency; tận dụng thay vì ghi DB để tạo phiên |

Đọc thêm ADR-001, 019, 020, 022; `docs/architecture.md`; `pyproject.toml`,
`uv.lock`; `packages/contracts/src/auto_at/contracts/execution.py`.
Working tree có nhiều thay đổi từ các phiên trước: không reset/stash/ghi đè.

## Vòng lặp vận hành

1. Đóng băng source hash, image digest, model/prompt, policy, viewport và oracle.
2. Chạy regression cô lập trước; qua mới triển khai local khi không có phiên đang chạy.
3. Reload đúng tác vụ qua API, một phiên live mỗi lúc, key mới cho vòng mới.
   Khi timeout transport, dùng lại key cũ để đối soát, không tạo lượt thứ hai.
4. Đợi terminal, thu conclusion + trace + frame + safe diagnostics; tính C/A,
   ghi mọi lỗi, thiếu bằng chứng, quota và thời gian.
5. Chọn nguyên nhân có bằng chứng và tác động lớn nhất; tái hiện local → red
   regression → sửa tối thiểu → green regression + negative safety tests.
6. Quay lại bước 1. Mỗi lần thay mã/config/oracle, chuỗi qualification về 0.
   Không kết thúc chỉ vì “đã sửa được lỗi” hoặc một lượt tiến bộ.
7. Khi đạt các gate offline, chạy qualification 3 lượt liên tiếp; thất bại quay
   lại bước 5. Chỉ đánh dấu hoàn thành khi toàn bộ điều kiện ở trên được chứng minh.

Mỗi 5 vòng ghi nhận xu hướng C/A, nhóm lỗi và chi phí/call count để đổi giả thuyết
nếu đứng yên; đây là điểm rà soát, không phải tự dừng hoặc tự giảm tiêu chí.
Không reload mù khi chưa biết nguyên nhân hoặc chưa có thay đổi liên quan.
Nếu hết quota, có side effect chưa rõ, thiếu quyền/consent, target ngoài phạm vi,
hay cần tăng ngân sách: ghi trạng thái chặn thực tế, không báo đạt.
Phạm vi được phép trước đây không tự mở rộng sang thanh toán, gửi form thật,
tạo tài khoản, cài/chạy file tải về hoặc mục tiêu production mới.

## Các phase

| # | Mục tiêu | Trạng thái | Phụ thuộc | Validation |
| --- | --- | --- | --- | --- |
| 01 | [Đóng băng oracle và bộ chấm](phase-01-metrics-oracle.md) | completed | Không | 37 Python + 6 worker tests; audit 1280×720 |
| 02 | [Harness vòng chạy và chẩn đoán](phase-02-loop-evidence.md) | completed | 01 | 35 Python tests; historical API import |
| 03 | [Tái hiện và sửa lỗi restoration](phase-03-restoration.md) | completed | 01, 02 | 177 regression + 6 recovery; 102 worker tests |
| 04 | [Chạy vòng cải thiện liên tục](phase-04-iterate.md) | in progress | 01–03 | Reopened: round 17 carousel outcome evidence fails; round 16 pass retained. r8 (2026-11-21): A1–A3 flags offline, leader PASS, QA PASS; live not run |
| 05 | [Qualification và bàn giao](phase-05-qualification.md) | in progress; awaiting phase 04 | 04 | Offline 1151 passed, 2 explained skips; first fresh attempt failed, streak 0/3 |

Trong phase 04, quay lại công việc phase 02/03 khi nguyên nhân mới cần thêm
chẩn đoán/fixture; ghi vòng và bằng chứng trong README, không làm mất lịch sử.

## Ràng buộc kiến trúc và vận hành

- Python chạy bằng uv; TS dành cho worker/dashboard. Không thêm framework/runner.
- `TestExecutionRequest/TestExecutionResult v1` không đổi. Benchmark artifact có
  schema riêng; nếu private worker transport cần thêm trường/capability thì sửa
  nguồn contracts dùng chung, generator và compatibility tests trước rollout.
- Route chỉ gọi use case. Benchmark dùng API, không import DB client vào route.
- LLM giữ vai trò đề xuất; oracle/score không do cùng model tự chấm.
  Prompt thay đổi chỉ ở `apps/control-plane/agents/prompts/`, có version và README.
- Dữ liệu public UI đã được phép; chỉ safe metadata vào report. Form values,
  token/cookie, credentials và intent thô không vào prompt/log/oracle.
- Giữ tenant/project/actor/RBAC/fencing, consent và secret mount hiện hữu.
  Ảnh qua endpoint có quyền; giữ retention hiện có, không chọn thời hạn mới.
- Giữ per-session limits; theo dõi tổng model calls và quota qua nhiều vòng.
  Không coi một trường cost metadata là cơ chế ngân sách tiền có hiệu lực.
  Không bật billing/đổi model; ngân sách material mới cần user direction.
- Local Compose + Temporal hiện có; drain trước rebuild; không reset volume.
  Không chạy Chromium regression cạnh live qualification để tránh nhiễu.
- Correlation/session/operation IDs nối evidence. Operation unknown phải đối soát
  và dừng side effect; không thử click lại. Không tự phê duyệt generated suite.
- Không đặt SLO production mới; đo p50/p95 thời gian, số call/state và lỗi theo vòng.

## Rủi ro, triển khai và ngoài phạm vi

Carousel là giả thuyết từ ảnh, chưa xác định node cụ thể gây mismatch. Không sửa
bằng cách tắt animation của website, nới fingerprint toàn cục hoặc xóa nút khó.
50 states có thể không đủ cho oracle + refresh; đo nguyên nhân chi tiêu trước,
không lách cap bằng chia phiên rồi gộp coverage để giả vờ một lượt đạt.

Dataset/site thay đổi cần version mới và qualification lại; không tự chuyển miss
thành negative. Phạm vi mobile/trang con mới/API/game và đúng nghiệp vụ không nằm
trong kế hoạch này. Không dự kiến migration; nếu phát sinh phải cập nhật plan trước.

Rollback về image đã ghi nhận, drain phiên, giữ nguyên lịch sử của phiên thất bại.
Không rollback bằng reset working tree nhiều thay đổi hiện hữu.

## Nhật ký tiến độ

- 2026-11-09: khảo sát, xác định baseline và giả định acceptance; chỉ tạo plan.
- 2026-11-09: bắt đầu phase 01 theo yêu cầu thực thi toàn kế hoạch;
  chuẩn hóa oracle 1280×720 và bộ chấm, giữ nguyên runtime và dữ liệu gốc.
- 2026-11-09 11:34 +07: phase 01 completed. Thêm `benchmark/vision/accuracy/README.md`,
  `metrics.py`, `oracle-mongchiton-1280-v1.json`, `baseline-20261109.json`, ba cặp
  audit JSON/PNG tại thư mục đó; thêm `tests/test_vision_accuracy_metrics.py`;
  sửa `workers/playwright/src/fixtures/visual-buttons-audit.ts`, thêm
  `visual-buttons-audit-model.ts` và `visual-buttons-audit.spec.ts` cùng thư mục.
  `uv run pytest tests/test_vision_accuracy_metrics.py tests/test_vision_conclusion.py -q`:
  37 passed; scoped Ruff passed; worker typecheck passed; hai spec đã nêu: 6 passed.
  Audit visible: 47/47, zero unexpected; audit oracle kế tiếp: 46/47,
  precision 100%, recall 97,87%, thiếu mct-47. Exit 1 của audit là kiểm tra
  completeness nghiêm ngặt hơn benchmark >95%; không giấu hoặc relabel miss.
  Accuracy thao tác vẫn chưa established. Development audit đếm nhầm 3 video
  khuất đã được sửa và giữ evidence. Không đổi runtime/guard/policy.
- 2026-11-09 11:34 +07: phase 02 in progress; phase 01 mở khóa harness API,
  persistent idempotency, safe evidence collector và failure taxonomy.
- 2026-11-09 11:44 +07: phase 02 completed. Thêm `benchmark/vision/accuracy/run.py`,
  `evidence.py`, `tests/test_vision_accuracy_loop.py`; bổ sung OutcomeReview và
  qualification eligibility trong `metrics.py` cùng tests/README. Historical
  import `runs/51a086ac-8612-4808-8fbe-ca091955f44c/` giữ 81 operations,
  xác định đúng before_dispatch/state_mismatch, zero missing evidence, không POST.
  Validation: `uv run pytest tests/test_vision_accuracy_loop.py tests/test_vision_accuracy_metrics.py
  -q --tb=short --basetemp .pytest-artifacts/accuracy-tests-20261109-c`: 35 passed;
  scoped Ruff passed. Lượt test đầu lỗi quyền Windows Temp (11 setup errors),
  chạy lại trong thư mục workspace mới đã qua, không đổi assertions.
  Deviation: API chưa xuất actual model-job/cost usage; phase 04 lấy safe metadata
  từ bridge hiện có, giữ cost unknown nếu không có evidence, không giả số calls.
- 2026-11-09 11:44 +07: phase 03 in progress. Tiếp theo tạo barrier fixture cho
  restore wait bị reject sau prepare và trước dispatch; giữ nguyên mọi guard.
- Vòng thực thi sẽ ghi: iteration ID, source/config/oracle hashes, hypothesis,
  test red/green, session ID, C/A, safety failures, calls, evidence, next action.

- 2026-11-09 12:05 +07: phase 03 completed. Red reproduction dừng đúng ở rejected
  restore wait trước dispatch. Thêm nullable dispatch proof trong
  `packages/contracts/src/auto_at/contracts/vision_worker.py` và generated
  `workers/playwright/src/vision-contract.generated.ts`; worker
  `vision-operations.ts` xuất proof. Controller `application/vision_trace_events.py`
  chỉ cho tối đa hai read-only observations rồi so checkpoint gốc;
  `application/vision_operations.py` giữ deadline ceiling của bước bị reject.
  Không retry click/Back/scroll, không đổi verdict, giữ state/hop policy guards.
  Thêm ADR-023, barrier fixture `workers/playwright/src/fixtures/vision-target.ts`,
  tests trong `tests/test_vision_page_batch.py`, `tests/test_vision_contracts.py`,
  `workers/playwright/src/vision-operations.spec.ts`; cập nhật codex manifest.
  Red: 1 failed (artifact a18400c2ff11); green cuối: 6 passed (57e75f4a2884),
  gồm temporary/permanent/private-form/state-cap/hop-cap/legacy worker.
  Broad isolated command của phase, cộng ba modules accuracy/contracts:
  177 passed, zero skipped/errors (9af03cf979a4, 800,882s).
  Broad run được build trước bổ sung hop guard; 6 ca focused đã kiểm final hop guard.
  Worker: 20 barrier schedules + 82 remaining tests passed; typecheck,
  generated-contract check, `uv run ruff check .`, `git diff --check` passed.
  Validation portable: `benchmark/vision/accuracy/phase03-validation-20261109.json`.
  Deviation hợp lệ: cần private result proof nên rollout controller/worker đồng bộ;
  execution v1/API/DB không đổi. Live >95% chưa được chứng minh.
- 2026-11-09 12:05 +07: phase 04 in progress. Build ba services đã qua,
  active sessions=0. Giả thuyết vòng đầu: bounded reobservation khắc phục race
  restore đã thấy tại operation 81. Giữ oracle, model/prompt và caps hiện hữu.
- Vòng 01: iteration `7b45b398-fd6a-442b-b534-0ce0f79365de`, session
  `79a9170d-1882-4b6a-abbf-5325c06e5174`, đã submit một lần qua harness.
  Image IDs, source/config/oracle hashes và limits trong thư mục run; cả ba
  service mới đều xác minh source checksum khớp workspace.
- Vòng 01 terminal: unavailable/state_restore_failed, 22 explore clicks completed,
  63 completed operations + 1 rejected close_popup (operation 64), 128/128 frames,
  zero unknown/pending. Diagnostics: before_dispatch, interaction/visual drift,
  cùng Page trước/sau; ảnh trắng rồi hydrate trang hướng dẫn tải game PC.
  Detection từ inventory keys đối chiếu oracle: precision 46/47, recall 46/47.
  Outcome accuracy chưa established; score lưu conservative lower bound 0 verified,
  tối đa có thể 22/47 nên chắc chắn chưa đạt. Không gọi 22 completed là 22 đúng.
  Ba bridge jobs completed, token usage lưu `usage.json`, monetary cost unknown.
  Evidence/assessments/detection/review-status/score bất biến trong thư mục run.
- Giả thuyết kế tiếp: popup hydrate giữa prepare/dispatch khiến close bị từ chối,
  trong khi child và parent vẫn giữ nguyên. Barrier red tái hiện đúng rejected
  close ở operation 3 (artifact e41aa3a9cc18: 1 failed). Mở rộng ADR-023 cho tối đa
  hai lần quan sát + close mới, chỉ với explicit no-dispatch proof và cùng child/
  parent, giữ original step deadline và kiểm checkpoint opener sau khi đóng.
  7 close variants + 6 wait variants: 13 passed (f5dbbee9ca8e, 113,007s),
  zero failures/skips/errors; Ruff, typecheck, generated contract check passed.
  Không retry dispatched/unknown close. Source thay đổi: `vision_trace_events.py`,
  `vision-target.ts`, `test_vision_page_batch.py`, ADR-023 và codex manifest.
  Portable validation: `benchmark/vision/accuracy/popup-close-validation-20261109.json`.
- Vòng 02: iteration `d2c0d660-1309-4dab-85f3-fbb777e2b19d`, session
  `378d318d-ecca-4637-ae22-cbd8bf5619fc`, đang chạy với close recovery đã kiểm.
  Drain=0 active trước deploy, services healthy, source checksum controller/
  Temporal worker khớp workspace; giữ nguyên oracle/policy/model/prompt.
- Vòng 02 terminal: 26 clicks, 78/78 operations completed, 156/156 frames,
  zero unknown/pending. Lý do `exploration_coverage_incomplete`: sau click SỰ KIỆN
  và Back, cursor hop=10 chặn refresh tiếp theo. 36 states, không phải hết 50;
  baseline đã dùng 7 scroll hops. Bốn bridge jobs completed, detection 46/47
  precision và recall. Outcome accuracy chưa established; conservative score
  và upper bound 26/47 lưu riêng, không có claim >95%.
- Giả thuyết vòng 03: giảm baseline overlap dư thừa trong giới hạn sẵn có.
  ADR-024: private stride tối đa 80% viewport, giảm theo top của control bị cắt
  ở mép dưới; không bỏ nút cao, không giảm denominator, không tăng caps.
  Thêm metadata ngoài model observation; old worker mặc định stride cũ.
  Worker red: 3 failures đúng thiếu stride; integration red đang kiểm 45 click
  trong 50 states. Contracts: 105 passed, Ruff passed; green đang chạy.
- Kết quả stride-only: 3 worker edge tests passed, 38 worker regressions passed,
  67 transport/model tests passed. Integration red 9e6870121bd9 và lượt stride-only
  9c886f6f1032 đều cho `dom_snapshot_limit` ở fixture 45 nút; lượt sau có 6 passed,
  1 failed, không phải green. Không deploy bản chưa đạt.
  Bổ sung reuse bound observation chỉ khi cùng Page, full semantics và interaction
  fingerprint đều giữ nguyên; states/frames vẫn được tính đủ. Test replacement
  đảm bảo clone cùng hình thức không được kế thừa proposal. ADR-024 ghi chi tiết;
  validation đang chạy trên nhóm recovery/navigation/no-op/cap liên quan.
- Final stride/reuse validation: 2162535903a4, 3 passed (257,389s): 47/47 positive
  fixture, zero negative clicks; 45 unique once-only clicks trong <=50 states và
  <=10 hops; identical replacement bị reject và không click. Nhóm liên quan
  d3a08bbf165e có 16 passed + 2 lỗi test fall-through; 4379aace87db lặp lại 2 lỗi
  assertion nhầm fixture đó. Đã sửa if/elif wiring, giữ nguyên mọi behavioral
  assertions; final run ở trên xác nhận green. Private source/test changes:
  `packages/contracts/src/auto_at/contracts/codex_bridge.py`, generated worker
  contract, `vision-dom.ts`, `vision_trace_events.py`, fixture và DOM/page-batch/
  contract specs; ADR-024, codex manifest. Ruff/typecheck/generator/diff passed.
  Chưa deploy các lượt fail. Tiếp theo vòng live 03 trên bản tối ưu đã kiểm.
- Vòng 03 đã submit qua harness: iteration `dab64d78-48cd-4b3b-ae85-4f34bf482a30`,
  session `548b4945-ad5e-44e2-a215-1e8394a56517`. Source hash
  `1a4cf32dc0bfd8b21fe4e5cce1c30ec70f32919ddeb951df46dbdb46e620f96f`;
  services healthy, verify controller/worker source khớp, active=0 trước deploy.
  Giữ nguyên limits và oracle; đang theo dõi baseline và terminal evidence.

- Vòng 03 terminal: `unsafe_replay`, 20 clicks, 54/54 operations completed,
  108/108 frames, zero unknown/pending. Baseline giảm còn 4 scrolls; detection
  precision/recall 46/47. Outcome accuracy chưa established, upper bound 20/47.
  Sau click SỰ KIỆN, Back và hai refresh vẫn ở `/su-kien`. Probe độc lập
  `history-probe-20261109.json` chứng minh một click tạo hai history entries.
  Vì vậy tăng thời gian chờ không giải quyết được lỗi này.
- Đang sửa theo ADR-025: chọn đúng history entry đã lưu, chỉ với GET proof,
  cùng Page/URL hash và history không đổi giữa prepare/dispatch; vẫn kiểm đầy
  đủ checkpoint gốc sau đó. Red fixture `70441c9254bd`: 1 failed đúng lỗi restore.
  Typecheck và 42 contract tests passed; integration và worker adversarial tests
  đang chạy. Chưa deploy bản history mới, phase 04 vẫn in progress.
- History validation green: 8 integration cases passed (`91104c509edb`,
  103,322s), 89 worker tests passed (5,3 phút), 8 final history tests passed
  (thêm deadline guard), 42 contract tests passed; Ruff/typecheck/generator passed.
  Bằng chứng portable: `benchmark/vision/accuracy/history-validation-20261109.json`.
  Thay đổi: private worker contract/generated schema, `vision-history.ts`,
  `vision-operations.ts`, `vision_trace_events.py`, history/browser fixtures,
  contract/page-batch tests và ADR-025. Execution v1, model/prompt/caps giữ nguyên.
  Drain=0, đang triển khai đồng bộ để bắt đầu vòng live 04.
- Vòng live 04: iteration `aee8f4a3-d93f-4e81-b3fd-3627f36dce48`, session
  `c1c2bd97-5c11-4e06-87e2-536dd56183de`. Ba services healthy; checksum của
  controller, worker và private schema khớp workspace. Provenance lưu image IDs,
  actual runtime caps từ DB allowlist và hash từng source đã kiểm. Đang chạy;
  chưa có final score, giữ nguyên model/prompt/oracle/limits.
- Vòng 04 terminal: 10 completed clicks; 30 completed operations và một setup
  wait rejected tại prepare_end (`state_changed_during_prepare`). Popup hydrate
  form trong lúc chụp ảnh; URL/interaction/visual semantics/scroll không đổi,
  form presence/values đổi. Có 61 retained frames đã kiểm checksum, một after
  frame không tồn tại vì chưa dispatch; zero pending/unknown. 168,382425s từ
  operation đầu đến cuối, hai model jobs. Detection 46/47; outcome chưa established.
  Evidence immutable giữ nguyên; chẩn đoán bổ sung nằm trong `diagnostics-supplement.json`.
- Red refresh fixture `34e5d5c806a0`: 1 failed đúng prepare race. Đang kiểm bản sửa
  ADR-023 cho read-only refresh có explicit prepare/no-dispatch proof, cùng Page,
  tối đa hai quan sát mới, chung deadline đầu, giữ rejected records. Không retry
  click hay chấp nhận checkpoint form drift. Phase 04 tiếp tục, chưa deploy.
- Lượt kiểm `76e34397eb08`: 11 passed, 1 failed; focused `9b6a3da8d01d`:
  2 passed, 1 failed. Refresh đã phục hồi nhưng test phát hiện rejection khác:
  Home self-link thay history entry ID, khiến lần quay về sau đó thiếu entry cũ.
  Bổ sung ADR-025: chỉ khi checkpoint gốc khớp đầy đủ trên cùng Page, cập nhật
  private GET history handle qua lần so sánh state/form thứ hai; không sửa
  metadata/state/ancestry đã lưu. Đang chạy lại sibling/restore/refresh matrix.
  Worker barrier 3 passed (19,1s); lỗi test setup thiếu proposal_id=null ở lần
  đầu đã sửa đúng input contract, không nới assertion.
- Final refresh validation: worker checkpoint/history regressions 44 passed;
  Python contract/metrics/harness 77 passed; matrix `a1836978a391` có 21 passed
  và 1 assertion phân nhánh test chưa thêm biến thể refresh mới. Đã sửa phân
  nhánh; `4a32a759660d`: 3 passed, zero failures/skips/errors (24,396s), gồm
  once/persistent/legacy và hạn thời gian dùng chung. Ruff/typecheck/generator
  passed. Portable evidence: `refresh-prepare-validation-20261109.json`.
  Ảnh operation 30/31 xác nhận popup YouTube playlist tải UI muộn; không submit
  form. Drain=0, đang deploy bản đã kiểm cho vòng 05. Model/oracle/caps giữ nguyên.
- Vòng 05 đã submit: iteration `b06acee8-f9c9-4d80-bc09-10ddd6f524d0`, session
  `f5280096-0c1a-4499-b395-837984da4c8f`. Services healthy và deployment checksums
  khớp workspace; provenance và actual runtime policy đã lưu. Đang theo dõi,
  chưa có final score; phase 04 vẫn in progress.
- Quyết định policy đang chuẩn bị xin direction (vòng 05 vẫn chạy): đã tối ưu
  baseline còn 4 scrolls; ở 24 clicks có 30 states, gồm 6 states setup/observation.
  Chỉ riêng 45 successful unique targets tối thiểu để vượt 95% đã cần >=51 states
  nếu giữ toàn bộ bằng chứng. Project hiện 50 states/10 hops. Đề xuất cụ thể chỉ
  tăng `vision_max_states` 50→100 cho project local
  `8f2d5531-f00d-4ce9-981e-f4b626657818`, giữ allowed origins và 10 hops,
  provider/model/20 calls/120s/rate/cost caps. Before/after payload đã lưu riêng
  `.pytest-artifacts/state-limit-proposal.json`; chưa thay policy. Tiếp tục thu
  terminal evidence vòng đang chạy; lượt tiếp theo dùng cap mới cần user direction.
- Vòng 05 terminal: 35 completed clicks, 98 completed operations + một rejected
  Back (`history_checkpoint_unavailable`), 196 retained frames đã kiểm checksum,
  2 frame unavailable của rejected prepare; zero pending/unknown. 42 states,
  max hop 10; 476,84269s operation window, 5 model jobs. Detection 46/47;
  upper bound coverage 35/47, outcome accuracy chưa established.
  Lỗi sau selected-tab mct-19: URL/history entry không đổi nhưng UI đổi và live
  child đã chạm hop 10, không thể mở rộng tiếp; attempt restore sibling bị chặn.
  Những lỗi popup/hydration/history navigation trước đó đã được vượt qua.
- **Material decision pending:** đề xuất states 100 cần bổ sung hops 20 vì
  terminal evidence mới cho thấy cả giới hạn độ sâu. Scope và before/after cụ thể
  tại `policy-expansion-proposal.md`; chưa áp dụng policy hay mở rộng schema.
  Cần user direction trước thay đổi này. Phase 04 vẫn in progress; phase 05
  chưa bắt đầu, chưa có claim >95%. Stack không có live session đang chạy.
- User đã duyệt đề xuất 100 states + 20 hops. Quyết định pending phía trên đã
  được giải quyết; tiếp tục phase 04, cập nhật validation/schema/UI đồng bộ và
  policy local qua API trước vòng 06. Không chỉnh limits của các phiên lịch sử.
- Revision capacity đã kiểm: red 2 failed/1 passed đúng <=10 schema; final 45
  contract/API tests passed; isolated `33dbcf79c901` 5 passed (45,687s), gồm UI
  chain 12 bước với cap 20 và dừng 10 với cap 10. Worker 5 passed (34s), chứng
  minh 20 actions rồi reject action 21; dashboard 43 passed; cả hai typechecks,
  Ruff và generated contract check passed. Đã kiểm DB đang chạy không có CHECK
  <=10 trên project/session. ADR-026 và `capacity-validation-20261109.json` lưu
  phạm vi/evidence. Đang build/deploy API/Temporal/worker/dashboard đồng bộ.
- API/Temporal/worker/dashboard đã healthy. Policy local đã PUT và GET xác minh
  100 states + 20 hops, audit tại `policy-change-20261109.json`; lịch sử giữ nguyên.
  Vòng 06: iteration `f37c0b20-bf2f-4e24-a125-0ba8f820f186`, session
  `ccad7a7d-737a-4de8-b071-16ce457c9753`. Source checksums/images và runtime policy
  lưu trong provenance; đang chạy, chưa có final score.
- Vòng 06 terminal: 37 completed clicks, 109 completed operations + một rejected
  Back, 52 states, max hop 15, 7 model jobs. Detection precision/recall 46/47;
  outcome chưa established, coverage upper bound 37/47. Giới hạn mới chưa chạm.
  Sau mct-19 (tab Sự Kiện), các sibling proposals vẫn queued trên checkpoint cũ;
  inventory mới lọc chúng khỏi model vì đã queued. Live child vì vậy chỉ scroll
  tiếp rồi quay lại queue cũ, nơi original checkpoint không còn khớp. Đang tái
  hiện bằng fixture hai tab; sửa sẽ giữ audit proposal cũ và yêu cầu đề xuất mới
  trên trạng thái hiện tại, không replay click và không nới checkpoint guard.
- ADR-027: tái lập proposal cho sibling chưa dispatch sau thay đổi UI cùng Page,
  URL và vị trí cuộn. Ba fixture mới (hai tab, hidden form, hết model budget) đã
  pass trong `7832f5b981fe` (23,179s). Lượt trước có lỗi test audit đọc sai key
  `edges`; đã đổi sang repository trajectory chính thức, giữ nguyên assertions.
  Matrix rộng ban đầu phát hiện 3 regression popup-scroll: fingerprint đổi do
  cuộn cũng kích hoạt invalidation. Đã thêm điều kiện scroll bằng nhau để giữ
  restoration guard gốc; final matrix `d41a656cf309`: 15 passed, zero failures,
  skips/errors (224,246s). Ruff, worker typecheck và contract generator passed.
  Drain=0, build thành công; deploy bản đã kiểm cho vòng 07.
- Vòng 07: iteration `e1f4a3a4-56fb-40ec-b423-4c0e231eb78b`, session
  `3957038a-9c7e-490c-90e8-7a8661e5c260`. Deployment hashes khớp workspace,
  services healthy; provenance lưu policy 100/20 và model/prompt/caps không đổi.
  Portable validation: `mutation-queue-validation-20261109.json`.
- Vòng 07 terminal: 33 completed clicks, 94 completed operations + Back 95
  rejected (`history_checkpoint_unavailable`), 188 retained frames verified,
  2 unavailable frames; 518,046278s, 10 model jobs. Các tab mct-19/20 và search
  mct-21 đã đi tiếp được. Checkpoint Back đích thuộc scroll 72 tại y=1152,
  còn giữ sibling proposals trước thay đổi UI tại y=576. Invalidation mới chỉ
  áp dụng exact source branch, nên inventory ở viewport kế tiếp vẫn lọc các
  sibling đã queued trên branch khác. Đang thêm fixture mutation xuyên viewport;
  mở rộng release chỉ các proposal chưa dispatch cùng Page/URL, giữ guard
  original checkpoint và yêu cầu model duyệt lại trên observation mới.
- ADR-028 bổ sung diagnostic hash đích download gắn operation, bounded 8 hashes,
  không lưu URL/query/file. Đây là khoảng trống evidence của hai APK controls;
  không dùng `download_started` đơn thuần để chấm đúng. Lịch sử không backfill,
  cancellation/verdict/transport/prompt/caps giữ nguyên; đang kiểm popup,
  same-page, redaction, logger failure và download ngoài click hợp lệ.
- Cross-viewport red `8d52b40e1839` tái hiện `unsafe_replay`; matrix
  `69ac3d7f2cda` 15 regressions passed, ca mới đã click đủ nhưng assertion sai
  kỳ vọng completed thay vì partial của historical unscanned viewport. Giữ
  production conclusion, kiểm exact-once/fresh proposal/no replay/audit;
  final `41f4d1039001`: 1 passed (15,177s). Download browser 7 passed (16,7s),
  Python harness/metrics 36 passed (0,73s); Ruff/typecheck/generator passed.
  Đang build bản sửa xuyên viewport và download evidence cho vòng 08.
- Vòng 08 đã submit: iteration `db377eba-12b1-4db4-84d1-3734e2bf1f25`, session
  `63b8b5fa-e230-4fa4-b8d0-ef39c0d3889f`. Source checksums verified, services
  healthy, policy/model/prompt/oracle không đổi. Chưa có terminal score.
- Vòng 08 terminal: 15 completed clicks rồi refresh 42 bị reject `state_mismatch`
  trước dispatch, sau popup YouTube 41. Diagnostic: URL/interaction/visual/scroll
  không đổi, form presence/values đổi. Retry hiện tại mới bao phủ prepare;
  fixture `a666a5478734` tái hiện đúng rejected close rồi rejected refresh.
  Đang mở rộng refresh chỉ khi dispatch=false, before_dispatch, có after frame,
  cùng Page, giữ tối đa 3 attempts và deadline gốc; kiểm persistent/legacy/unknown/
  page change/missing frame/state/hop limits. Không retry click.
- Download vòng 08 có operation-bound destination hash; HEAD độc lập cho thấy
  query `ver` thay đổi nên chưa đủ đối chiếu trực tiếp. ADR-028 bổ sung bounded
  navigation redirect hash chain thực tế trong click, để nối declared source
  tới đúng download; không suy đoán query hay nới outcome rule.
- Refresh dispatch final `c8f146d7641b`: 24 passed, zero failures/skips/errors
  (217,683s), bao gồm các close/restore/prepare regressions và 8 biến thể mới.
  Download redirect browser: 9 passed (23,2s); harness/metrics 36 passed (0,95s).
  Ruff/typecheck/generator passed. Build hoàn tất, chuẩn bị deploy vòng 09.
- Vòng 09: iteration `65e78e75-5665-4dda-ac13-59a1f4ce60b2`, session
  `1e594cca-e0ab-4bc6-977f-620fc08a1d62`. Deployment verified và healthy;
  đang chạy với cùng 100 states/20 hops/20 calls. Portable evidence:
  `refresh-dispatch-validation-20261109.json`. Chưa đạt acceptance phase 04.
- Vòng 09 terminal: 25 completed clicks, 69 completed operations, 138 frames
  verified, zero unavailable frames/failed/rejected/unknown browser operations.
  Operation window 413,42297s; job model thứ 7 cancelled sau `bridge_offline`.
  Scoped heartbeat diagnostic: FileNotFoundError errno 2, read 2ms; bridge vẫn
  running, restart count 0. ADR-029 bổ sung tối đa 3 reads cho heartbeat missing
  khi replace, cách 10ms; không cache readiness, nới stale/auth TTL hoặc replay job.
  Red 2 cases; host bridge suite 56 passed/16 Linux-only skips. Final Linux
  `bb078006005f`: 72 passed, zero skips/failures/errors (11,561s). Ruff passed;
  build/deploy control-plane và Temporal để chạy vòng 10.
- Vòng 10: iteration `90e66243-ed11-4163-85bd-ae0ea401b9eb`, session
  `e7b676d6-da37-49c5-b1f9-44c6ac28ea7c`. Hash doctor.py kiểm trên cả API/Temporal;
  services healthy, policy/model/oracle không đổi. Portable validation:
  `heartbeat-validation-20261109.json`. Đang chạy, chưa có final score.
- Vòng 10 terminal: 34 completed clicks, 5 rejected clicks (73 và 92–95),
  một rejected Back 103; 194 retained frames verified, 12 unavailable frames,
  594,310962s, 14 model jobs. Heartbeat không lỗi. Ảnh trước/sau Mounts 91 xác
  nhận bốn character controls bị thay trước khi được click. ADR-030 ưu tiên
  accepted independent links rồi controls sâu trong panel, giữ stable ties,
  v3 current observation, tất cả guards. Fixture red `a9ff2665ed0b` tái hiện
  mất coverage; đang kiểm bản sửa với mutation/navigation/dataset regressions.
- ADR-030 final matrix `738e59068388`: 19 passed, zero failures/skips/errors
  (490,04s pytest runtime), gồm fixture mới + 45/47 buttons, popup/history,
  identical replacement và queue mutation. Ruff/typecheck passed. Build xong,
  drain=0; deploy candidate để chạy vòng 11, chưa tuyên bố đạt accuracy.
- Vòng 11: iteration `827a7e61-5752-4ab5-b8ab-43e69bd70ffc`, session
  `579fdb87-8745-433c-aed0-c079960ae124`. Source/deployment checksums verified,
  services healthy, cùng policy/model/prompt/oracle. Portable validation:
  `panel-order-validation-20261109.json`; đang chạy, chưa có terminal score.

- 2026-11-17: tiếp tục phase 04 theo yêu cầu mở Docker và nối phiên dang dở.
  Hai phiên 15–16/11 chỉ chứa yêu cầu tiếp tục; checkpoint thực tế vẫn là vòng 11.
  Docker Desktop và Compose base + Codex overlay đã khởi động, giữ container/images
  và volumes hiện hữu; API healthz OK, dashboard login HTTP 200, doctor qualified
  và authenticated (model access vẫn unverified khi chỉ chạy doctor).
- Vòng 11 đã đối soát terminal qua API: unavailable/bridge_provider_unavailable,
  17 completed clicks, 47 completed operations, 94 retained frames verified,
  zero missing/pending/unknown browser operations; operation window 221,044205s.
  Ba model jobs: hai completed, job 3 failed. Detection precision 46/46, recall
  46/47; coverage upper bound 17/47, outcome accuracy chưa established. Thu đầy đủ
  evidence/timing/usage/assessments/score trong thư mục iteration gốc; không biến
  completed thành kết quả đúng. Không đủ dữ liệu live để đánh giá ADR-030.
- Resume validation: `uv run ruff check .` passed; `uv run pytest
  tests/test_vision_accuracy_loop.py tests/test_vision_accuracy_metrics.py -q
  --tb=short --basetemp .pytest-artifacts/resume-20261117-tests`: 36 passed (0,75s).
  Bước tiếp: một lượt mới sau restart để kiểm provider với cùng candidate, policy,
  model/prompt/oracle; không thay code hay tự chuyển model vì lỗi provider.
- Vòng 12 đã submit: iteration `15967ed1-c9b7-43ad-8878-41e68b414d23`, session
  `3ec3b50d-3f9c-4375-b894-696ed9d1f370`. Deployment checksums khớp workspace;
  image IDs/source/config/oracle hashes và runtime policy được lưu trong provenance.
  Theo dõi cùng session/idempotency key; chưa có terminal score.
- Vòng 12 terminal: unavailable/unsafe_replay, 35 completed clicks, 107 completed
  operations, 214 retained frames verified, zero missing/rejected/unknown/pending;
  481,965539s, 5 completed model jobs. Detection 46/46 precision, 46/47 recall;
  coverage upper bound 35/47, outcome accuracy chưa established. Operation 104 là
  liên kết Xem Toàn Bộ (mct-29), không phải nút chọn nhân vật. Back 105 và refresh
  106–107 trả ảnh cùng viewport nhưng original checkpoint vẫn không khớp.
  Saved-entry diagnostic probe riêng không tái hiện mismatch; không suy từ ảnh
  giống nhau rằng private forms/interaction state tương đương.
- ADR-031 bổ sung checkpoint mismatch diagnostics dạng boolean và IDs, không
  đổi guard/retry/contract/prompt/caps. Red worker tests: 4 failures đúng thiếu log,
  1 passive-visual case passed. Đang kiểm green và correlation/redaction regressions;
  chưa deploy. Hai probe riêng giữ kết quả trong `return-probe-20261117.json` và
  `return-entry-probe-20261117.json`; probe đầu dùng Back thường, khác saved-entry
  restoration nên không dùng để kết luận về runtime.
- ADR-031 final matrix: 51 worker tests passed (2,2m), bao gồm 20 dispatch barriers,
  history restoration, private form/URL/control/scroll/presence diagnostics,
  passive visuals, redaction và logging failures. Worker typecheck, Ruff,
  changed-file diff check passed. Portable evidence:
  `checkpoint-diagnostic-validation-20261117.json`. Active sessions=0; build worker
  diagnostic để chạy vòng tiếp, chưa có claim sửa được lỗi restoration.
- Worker diagnostic đã deploy, source checksums verified. Vòng 13: iteration
  `5556d5db-bae4-4571-b2bb-d99d171ab8da`, session
  `472aa413-dde2-4bcd-a28e-66bd6e975d82`; giữ nguyên model/prompt/oracle/policy.
  Đang theo dõi; helper chỉ đọc `checkpoint_diagnostics.py` xuất allowlisted
  mismatch flags theo session, không lấy raw log hay giá trị private forms.
- Vòng 13 terminal trước khi mở browser: visual_exploration_unavailable,
  transport connection_error, zero operations/model calls. Compose `--wait` với
  worker chưa có healthcheck chỉ chứng minh container started, không chứng minh
  HTTP listener đã sẵn sàng; submission đã quá sớm. Evidence/score được giữ.
  Đã kiểm HTTP từ Temporal container: route Vision trả 401 đúng authentication
  boundary. Lượt tiếp theo chỉ submit sau kiểm listener này; không đổi code guard.
- Vòng 14: iteration `1de7b316-99d0-4a3a-9e02-dd684a23df60`, session
  `8037d765-3ac4-420d-8793-47d932f861c0`, deployed checksums verified. Operator helper
  thêm HTTP readiness gate trước start để không lặp startup race của vòng 13.
- Vòng 14 terminal: 30 completed clicks, 85 operations (84 completed + một setup
  wait rejected), 169 retained frames verified, một missing frame của rejected
  prepare; 368,105032s và 5 model jobs. Unsafe replay sau Xem Toàn Bộ. Diagnostics
  xác định checkpoint đích y=0, Back trả trang chủ y=576; URL/form không đổi,
  scroll/interaction khác. Không có thao tác click bị retry hay unknown.
- ADR-032: tái dùng bounded scroll reconciliation sau fresh post-Back observation,
  rồi kiểm toàn bộ original checkpoint. Red fixture `42c3aa9abfdf`: 1 failed đúng
  unsafe_replay/missing sibling và 1 form-drift negative passed. Đang kiểm bản sửa
  với popup/history/mutation matrix; chưa deploy. Không nới guard hoặc đổi limits.
- ADR-032 green `87faf65ba9cb`: 11 passed (145,33s pytest), zero failures/skips/errors.
  Final `129f7aab9295`: 6 passed (114,60s), thêm hướng cuộn lên như live và giữ
  hidden-form negative, panel order, popup hydration, identical replacement guards.
  Ruff, worker typecheck, generated contract và changed-file diff check passed.
  Portable validation: `post-back-scroll-validation-20261117.json`. Active sessions=0;
  build API/Temporal/worker trước khi deploy bản đã kiểm cho vòng kế tiếp.
- Vòng 15 đã submit sau API health + worker HTTP readiness + deployment checksum
  verification: iteration `aded2b83-bfc6-4c99-8461-d829e002a9b6`, session
  `7b15d7fc-8a90-4076-b972-90f50ae2c2c6`. Model/prompt/oracle/policy không đổi;
  provenance lưu source/images của ADR-032. Đang theo dõi, chưa có final score.


- V?ng 15 terminal: unavailable/unsafe_replay, 49 click attempts (47 completed,
  2 rejected), 46 distinct positive oracle bindings, 146 operations, 287 verified
  retained frames and 5 missing; 690.691904s, 15 model jobs. Detection 47/49
  precision, 47/47 recall. Frozen-binding accuracy upper bound 46/49=93.8776%;
  outcomes remain unverified, so retained score is a conservative lower bound.
  Extra completed click 101 opens video from another carousel DOM copy; do not
  remap it to mct-47 or change frozen labels. Rejected clicks 111/123 target other
  video copies (unsupported_target/stale_dom_target). Final restoration still
  encounters a superseded carousel checkpoint with interaction drift at equal
  URL/scroll/forms. No original guard was bypassed.
- ADR-033 isolates moving-target hit-test race after before-frame capture. Red:
  three failing synthetic cases. Green: three passed (11.3s), exact-once click
  after motion; form mutation and node replacement reject before dispatch.
  Bounded read-only stable wait applies only to retained v3 nodes, then original
  state/node/descriptor checks. Broader worker matrix in progress, no deployment
  yet. Prompt/model/policy/oracle unchanged.

- ADR-033 final matrix: 102 passed (6.2m), typecheck/Ruff/generated contract/scoped diff passed. Portable evidence: retained-target-stability-validation-20261117.json. Active live sessions=0; worker image built successfully, deploying before next iteration.

- V?ng 16 submitted: iteration fd3ddda4-ca69-4abb-818b-a8ac1ad594d8, session 58e2ad72-d3ee-4c52-9e13-820960468a46. Worker listener and deployment checksums verified; ADR-033 only, source/images retained, same model/prompt/policy/oracle.

- Phase 04 completed, phase 05 started 2026-11-17: round 16 independently passed.
  C=46/47 (97.8723%), A=46/48 (95.8333%), detection P=46/48 and R=46/47,
  inventory_complete=true, zero unsafe/wrong-target/unsettled operations.
  148 operations, 292 verified frames, four unavailable frames from rejected
  operations, 676.624587s, 12 model jobs. Forty-six content-addressed reviews
  bind each positive outcome to oracle, locator and frame checksums. Public
  redirect chains retained in redirect-review-20261117.json; click-bound APK
  evidence retained. YouTube credit is exact declared destination URL only:
  images show loading shells, no playback/content-readiness/business claim.
  Unmatched video-copy click and rejected video click remain denominator-only.
  Runtime unavailable/unsafe_replay remains unchanged for old carousel checkpoint.
  No scoring, oracle, completeness or guard rule was changed for this result.
- Freeze source 84354e173484092123a2728e3df4933b4cbbc77c9d8ea99dffbb4a69b1dd3eb3;
  candidate/provenance recorded in qualification-candidate-20261117.json.
  Phase 05 starts full isolated final-source suite before three fresh live
  qualification runs. Worker 102-case final-source matrix already passed;
  no further code changes while qualifying. Overall plan remains incomplete.

- Phase 05 first full suite (13705e22b169) reports a stale Gehihi manifest hash at test_gehihi_manifest_provenance_and_mocked_response_gates. Two fixture/test checksums refreshed; response cases/metrics/runtime/prompt/oracle unchanged, candidate source_hash asserted unchanged. Full run still in progress and retained; focused metadata validation follows. Two RustFS tests skip because the network-isolated test image cannot use a Docker host.

- Metadata repair focused validation: 5 passed (0.32s). Stop superseded full run 13705e22b169 after confirmed stale-manifest failure (last reported 68%); retain full log and full-validation-incomplete-13705e22b169.json, no full-suite-pass claim. Repeat complete suite with corrected metadata and explicit skip reasons; runtime candidate hash unchanged.

- 2026-11-17 evening resume: recovered final isolated suite 1151 passed, 2 Docker-host skips, no failures/errors (1609.153s harness). Separate RustFS initial connection failure retained; repeat 2 passed and three stability repeats each 1 passed. Source/config/oracle still match frozen candidate; full Ruff passes; no active exploration. Portable record: `benchmark/vision/accuracy/qualification-offline-complete-20261117.json`. Phase 05 proceeds with one fresh round per conversation under the new AGENTS.md handoff rule; no runtime/model/prompt/policy changes.

- Round 17 / qualification attempt 1 submitted: iteration `56e50d4d-2be0-433b-98ad-2eab68d7773f`, session `c2cb227d-6c27-4323-971d-da27bbe67fcc`. Worker HTTP readiness and deployed source checksums verified by operator helper; same frozen source/config/oracle and original limits. Quiet watcher active; no score yet.

## Round 17 handoff ? 2026-11-17 evening

- Outcome: first fresh qualification attempt failed; streak 0/3, phase 04 reopened.
- Iteration `56e50d4d-2be0-433b-98ad-2eab68d7773f`; session `c2cb227d-6c27-4323-971d-da27bbe67fcc`; terminal unavailable/unsafe_replay.
- Frozen source `84354e173484092123a2728e3df4933b4cbbc77c9d8ea99dffbb4a69b1dd3eb3`; config `99133119fce60532b32a8d26b38ab4b2f1956d5563c314cabb0eff0eb97da7c6`; oracle `9242b33d5e4cdd155b6642262c32f166b365edeec7d7b9642c5b88df35147a4e`. Images/runtime policy identical to round 16. No runtime changes.
- 47 attempts, 45 completed positive bindings; operation 26 (mct-54) after-frame shows slide 5 instead of required 4. No credit; available-evidence ceiling 44/47=93.6170%. Five positive reviews retained; saved 5/47 score is only a conservative lower bound, not true accuracy. Other outcomes left unreviewed after failed gate; all evidence retained.
- Detection P=47/48, R=47/47; 145 operations, 286 verified frames, four unavailable; 742.937198s; 12 successful bridge jobs (66,038 input / 4,551 output reported tokens). No monetary cost data; no pending/unknown exported operations or active sessions.
- Report: `benchmark/vision/accuracy/QUALIFICATION-20261117-round17.md`; machine record `benchmark/vision/accuracy/qualification-56e50d4d-2be0-433b-98ad-2eab68d7773f.json`; detailed evidence under `benchmark/vision/accuracy/runs/56e50d4d-2be0-433b-98ad-2eab68d7773f/`. Inspect `carousel-outcome-mismatch.json` first; reviewed images need not be reloaded without a new diagnostic question.
- Validation: full offline suite recovered (1151 passed, 2 explained skips); separate RustFS repeat 2 passed plus three single-case stability passes, original connection failure retained; candidate unchanged; full Ruff passed. Source and frozen identities rechecked after round.
- Changed this turn: canonical plan README, phase-04/05 status notes; new qualification report, offline-complete record, qualification JSON and round evidence/reviews. Local operator scoring helper `.pytest-artifacts/score_qualification_01.py`; no tracked runtime/test/prompt changes.
- Active processes: none from this round (watcher and collector exited); local Docker stack remains running.
- Next work: synthetic red regression for autoplay between click and after-frame; investigate before selecting a minimal fix. Do not disable autoplay, relabel mct-54, drop rejected attempts, relax guards, or repeat qualification without remediation. Separately retain final history_checkpoint_unavailable restoration diagnosis.
- First command in the fresh session:

```powershell
rg -n "capture|screenshot|settle|carousel" workers/playwright/src/vision-operations.ts workers/playwright/src/vision-screen.ts workers/playwright/src/vision-operations.spec.ts workers/playwright/src/fixtures/vision-target.ts
```

User round-boundary preference: stop here and continue in a fresh session. Overall plan remains incomplete.

- 2026-11-17 resumed phase 04: ADR-034 reproduces carousel outcome loss with a synthetic post-click autoplay timer (red: expected slide 4, retained slide 5). Optional bounded early sample runs alongside unchanged popup grace; late navigation/popup/download/form/control/target changes discard it. Initial six cases and typecheck passed; added final target-replacement guard/case. Existing worker regression is running; no live run/deployment yet. Python first attempt hit Windows pytest temp ACL (13 fixture errors); fresh workspace basetemp yields 43 passed, 3 offline-image skips. Full Ruff passed. Runtime model/prompt/policy/oracle unchanged.

- ADR-034 validation: broad worker matrix 108 passed (379.15s, zero skips/flaky); final focused seven-case matrix passed (21.05s) after connected-target guard addition; typecheck, full Ruff and manifest validation passed. Portable record `local-outcome-capture-validation-20261117.json` states exact validation scope and retained Windows temp ACL failure. Only worker rebuilt/deployed after zero active sessions; HTTP readiness checked before submission.
- Round 18 submitted: iteration `1f13a1e9-d08d-4582-8f3a-bfae43be833e`, session `3d30c88c-9d4d-499a-b4d8-11e8e6739b81`, source `4b67094dfd3603e3f55e99e90717b7d8c77a6d068884c3bd6a5be4aa05aaf6fc`. ADR-034 outcome observation timing only; model/prompt/policy/oracle unchanged. Quiet watcher active; live effectiveness and score pending. Prior full-suite result belongs to the old source and is not final qualification for this candidate.

## Round 18 handoff ? 2026-11-17

- Round 18 failed; phase 04 stays in progress, qualification streak 0/3. Iteration `1f13a1e9-d08d-4582-8f3a-bfae43be833e`, session `3d30c88c-9d4d-499a-b4d8-11e8e6739b81`; terminal unavailable/state_restore_failed.
- Current deployed source `4b67094dfd3603e3f55e99e90717b7d8c77a6d068884c3bd6a5be4aa05aaf6fc`; config `99133119fce60532b32a8d26b38ab4b2f1956d5563c314cabb0eff0eb97da7c6`; oracle `9242b33d5e4cdd155b6642262c32f166b365edeec7d7b9642c5b88df35147a4e`. Model/prompt/policy/oracle unchanged. Worker image and checksums in this round's provenance.
- ADR-034 adds bounded early observation during unchanged popup grace, with final page/document/target/form/state checks and fallback. Synthetic red reproduced loss of selected slide; broad worker matrix 108 passed, final focused seven cases passed (last connected-target guard), typecheck/Ruff passed; Python 43 passed, three harness-image skips. Initial Windows temp ACL errors retained and resolved with fresh workspace basetemp. Full final-source isolated suite is still required before qualification.
- Runtime completed 40 operations then rejected restore close_popup 41 at prepare_end when popup form presence/values changed. No physical close retry. 15 completed explore clicks; six carousel images reviewed, five match and indicator 3 shows slide 4. Saved score is a conservative lower bound (5/15 A, 5/47 C), not true accuracy. Available-evidence ceilings are 14/15 A and 14/47 C. Nine other outcomes remain unreviewed; no attempt omitted.
- Detection P=R=46/47. Two successful model jobs; reported input/output tokens 11317/1380 (bridge jobs only; cost unknown). 205.267141s, 81 verified frames, one unavailable; no active sessions or pending/unknown exported operations.
- Early sample was not reused on the six live carousel operations: after-capture delays 1111?1552ms exceed its 500ms budget. Exact rejection stage uninstrumented. Do not claim live improvement from the lightweight fixture; add safe stage timing and a realistic DOM-cost fixture before selecting another fix. Separately reproduce hydrating-popup preparation form drift without relaxing guards.
- Changed source/test: `workers/playwright/src/vision-operations.ts`, new `workers/playwright/src/vision-outcome-capture.spec.ts`; manifest source hashes updated in `benchmark/vision/codex/manifest.json`. Added ADR-034, validation record, round report/JSON and evidence/reviews; canonical progress updated. No Python runtime/prompt/contract changes, no commit/push.
- Report: `benchmark/vision/accuracy/ROUND18-20261117.md`; evidence `benchmark/vision/accuracy/runs/1f13a1e9-d08d-4582-8f3a-bfae43be833e/`; portable validation `local-outcome-capture-validation-20261117.json`. Read `capture-latency.json`, `carousel-outcome-mismatch.json` and `diagnostics-supplement.json` rather than reloading reviewed images.
- Active processes: none from this round; watchers/tests/build/collector exited. Docker stack remains running with ADR-034 worker.
- Next command in a fresh session:

```powershell
rg -n "sampleClickOutcome|prepare_end|state_changed_during_prepare|close_popup|settleState" workers/playwright/src/vision-operations.ts workers/playwright/src/vision-checkpoints.ts workers/playwright/src/vision-outcome-capture.spec.ts
```

Stop at this round boundary under the user's token-budget preference. No round 19 submitted; overall plan incomplete.


- 2026-11-18 resumed round-18 remediation: ADR-035 extends bounded known-child popup recovery to positively proven undispatched prepare-end rejection. Synthetic red failed as expected; green 22 integration cases passed (188.302s harness), 107 domain/contracts/metrics tests passed, worker timing/fallback eight cases passed (26.3s), typecheck/full Ruff/two manifest checks passed. Added allowlisted sampling-stage timing; 500ms budget and all guard/model/prompt/oracle/policy rules unchanged. Read-only worker probe confirms substantial DOM/capture cost; no claim of live carousel repair. Built API/Temporal/worker with zero active sessions; deployment and one round-19 verification follow. Full final-source qualification suite remains required.

- Round 19 submitted: iteration `9f84261c-0d0f-47c6-894c-d476f72d9bf1`, session `0d652d30-c4c7-4bde-82e4-69a6fbbf1e4e`, source `2337ebf96b2ff59e1c34d5c3cae4404590850597362b384534e99e93be4ebce4`. API/Temporal/worker healthy; deployed checksums include the new domain guard. Same model/prompt/oracle/config. One quiet watcher active; terminal evidence and score pending.


## Round 19 handoff ? 2026-11-18

- Failed accuracy ceiling; phase 04 remains open, qualification streak 0/3.
- Iteration `9f84261c-0d0f-47c6-894c-d476f72d9bf1`; session `0d652d30-c4c7-4bde-82e4-69a6fbbf1e4e`; unavailable/unsafe_replay. Final restore operation 146 rejected with history_checkpoint_unavailable; checkpoint interaction/visual drift, unchanged URL/forms/scroll.
- Frozen/deployed source `2337ebf96b2ff59e1c34d5c3cae4404590850597362b384534e99e93be4ebce4`; config `99133119fce60532b32a8d26b38ab4b2f1956d5563c314cabb0eff0eb97da7c6`; oracle `9242b33d5e4cdd155b6642262c32f166b365edeec7d7b9642c5b88df35147a4e`. API/Temporal/worker rebuilt and checksummed, source unchanged after run; model/prompt/policy/oracle unchanged.
- 49 click attempts: 47 completed, two rejected. Only 46 positive completed bindings; unmatched completed operation 101 and rejected 117/133 remain denominator-only. Accuracy ceiling 46/49=93.8776%; no full outcome review needed to establish failed gate. Saved zero-credit score is a conservative lower bound, not true accuracy/coverage. No outcome images reviewed this round. Detection P=47/49, R=47/47, inventory complete. No pending/unknown exported operations.
- All 21 popup closes succeeded; no prepare rejection occurred, so ADR-035 recovery was not exercised live. Its synthetic red/green validates the new branch; do not claim live causal improvement from progressing beyond round 18.
- 23 early samples, zero reuse: five settle deadlines, 16 screenshot timeouts, two verify deadlines. Carousel settle alone 221?325ms; two captured samples finished verification at 543/616ms; remaining four carousel samples timed out capturing. Read sample-timing.json and sample-capture-failures.json first. No budget increase or claim of live carousel repair.
- 146 operations, 287 verified frames, five unavailable; 725.713947s. Fifteen successful application model jobs report 81,219 input / 4,743 output tokens (not assistant-session usage); monetary cost unknown.
- Validation: old-code red reproduced failure; green 22 isolated integration cases passed (188.302s harness), 107 domain/contracts/metrics tests passed, eight worker cases passed (26.3s), typecheck/full Ruff/two manifest tests passed. Full final-source qualification suite still required. Operator invocation errors and successful corrected commands retained in validation record; no tests silently skipped.
- Changed runtime: new apps/control-plane/domain/vision_restoration.py, application/vision_trace_events.py, worker vision-operations.ts timing logs. Tests: new tests/test_vision_restoration.py, tests/test_vision_page_batch.py, worker vision-outcome-capture.spec.ts, fixture vision-integration-server.ts. Updated Codex/Gehihi manifest checksums; added ADR-035, validation/round records/report and evidence. Existing dirty tree preserved; no commit/push.
- Report `benchmark/vision/accuracy/ROUND19-20261118.md`; machine record `round-9f84261c-0d0f-47c6-894c-d476f72d9bf1.json`; evidence `runs/9f84261c-0d0f-47c6-894c-d476f72d9bf1/`; validation `popup-prepare-validation-20261118.json`. Local helper `.pytest-artifacts/collect_sample_timing.py` exports only allowlisted terminal timing data.
- Active sessions=0. Watcher, tests, builds, collector exited; Docker stack remains running. No round 20 submitted.
- Next work: reproduce measured DOM/PNG cost locally before choosing a bounded observation fix; investigate denominator-only operation paths 101/117/133 against frozen bindings. Preserve all rejection/oracle/private-form/exact-target/parent-checkpoint rules. Keep history restoration failure visible. Do not start another live run without relevant remediation and checks.
- First command in the fresh session:

```powershell
rg -n "sampleClickOutcome|visualButtonSemantics|inspectState" workers/playwright/src/vision-operations.ts workers/playwright/src/vision-dom.ts workers/playwright/src/vision-outcome-capture.spec.ts
```

Stop at this round boundary under the user's token-budget preference. Overall plan remains incomplete.


## Retrospective hold ? 2026-11-18

User explicitly requested holding round 20 and auditing rounds 01?19. No new live
run, deployment or runtime/policy/oracle change is authorized by this audit.
The previous next-round command is superseded by this review boundary.

- Audit: `benchmark/vision/accuracy/RETROSPECTIVE-ROUNDS01-19-20261118.md`; structured
  data with input hashes: `retrospective-rounds01-19-20261118.json`.
- Reviewed all 19 numbered runs, excluding the imported historical baseline.
  Terminal families: restoration/stale checkpoints 11, popup hydration 4,
  bridge/provider/readiness 3, capacity 1. These families are not identical root
  causes and are distinct from accuracy-scoring failures.
- Detection exceeds 95% in all 18 browser runs. Only round 16 has a passing fully
  adjudicated score; partial/unreviewed lower-bound scores cannot form an accuracy
  trend. Same-source round 17 failed after round 16 passed.
- Same unmatched video path recurs in rounds 15/16/17/19; all miss mct-47 binding.
  Rounds 15 and 19 share the exact 46/49 accuracy ceiling. Carousel outcome
  evidence fails in 17/18; round 19 telemetry confirms zero early-sample reuse.
- Recommend focused target/proposal identity and realistic capture-cost fixtures,
  then a complete state/recovery matrix. Do not start another full live loop
  merely to see whether the score fluctuates upward. Model/oracle/guard/cap changes
  are not justified by this audit alone.
- Correction: round 09 has 26 completed clicks according to retained evidence,
  assessments and review-status, not 25 as written in the older narrative.
- Only retrospective documents/data and this progress note changed. No browser,
  model, service mutation, tests or live session launched; data assertions check
  run count, family partition, repeated path and same-source comparison. Phase 04
  remains incomplete; wait for direction on the next implementation scope.


## Approved pre-round-20 remediation ? 2026-11-18

User authorized implementing the three retrospective priorities before round 20.
Completed the approved offline implementation unit. Phase 04 and the overall
plan remain open; round 20 has not started.

- [x] Read-only target preflight checks per-node action identity before dispatch.
  Stale queued proposals are audited/retired and require fresh observation/model
  proposals within existing limits. Verified restored DOM nodes are rebound
  individually; same-URL unsolicited reloads and private-form changes still stop.
- [x] Optional outcome capture uses fast lossless PNG and interaction-only
  readiness reads, followed by complete verification. The 500 ms budget and all
  final guards remain. Same 575-node/large-PNG fixture at one CPU/1 GiB: baseline
  0/5 passed; changed implementation 5/5 passed, 389-487 ms, correct slide retained.
- [x] Refresh, restore verification and popup close share one explicit
  no-dispatch evidence matrix. Prepare and dispatch races are covered; missing
  proof, persistent/private-state changes and exhausted limits still fail safely.
- Validation: 85 browser integration cases passed across two isolated
  shards; 210 Python domain/transport/contracts/metrics/provenance checks passed;
  60 affected worker cases covered (49 DOM/visual/sample guards plus 11 preflight).
  Earlier broad worker matrix: 198 passed before the restored-binding follow-up.
  TypeScript typecheck and whole-repository Ruff passed. Red controller ablations
  preserve four target failures and one restore-prepare failure. Intermediate
  regressions and their corrected fixtures are retained in the validation record.
- Candidate source: `2cd003097edc26d20dea1320ed9c58b0896c4d0a43b519fe2005ea9363849578`. Portable record:
  `benchmark/vision/accuracy/pre-round20-validation-20261118.json`; design:
  `docs/adr/036-validate-queued-targets-and-bounded-evidence.md`.
- No live model calls, deployment, round-20 submission, oracle/model/prompt/limit
  changes, commit or push. Existing Docker stack remains the round-19 source.
  Owned fixture containers were removed. This does not establish improved live
  accuracy or repair of mct-47; distinct video copies are not merged or relabeled.
- Next work unit: deploy the matching controller/worker candidate together (new
  `target-preflight-v1` capability), then one separately reviewed round 20 under
  the frozen policy/oracle. Full final-source qualification remains pending.

Stop at this implementation boundary under the user's session/token preference.
Read this handoff and portable validation record first; do not reload old images
or complete logs. No benchmark/model watcher remains active from this work unit.

## Round 20 in progress - 2026-11-18

User authorized one live round after ADR-036 remediation. Preflight confirms zero
active sessions, unchanged round-19 reload policy, and validated candidate source
`2cd003097edc26d20dea1320ed9c58b0896c4d0a43b519fe2005ea9363849578`.
Build/deploy matching API, Temporal worker and Playwright worker; verify deployed
checksums, submit once with a persisted idempotency key, monitor quietly, then
collect and independently assess evidence. No round 21 is authorized in this unit.
Phase 04 remains in progress; final score and live regression outcome pending.

- Submitted iteration `a4030533-71e3-43cd-8e4d-6816c7e7dd55`, session
  `45473832-0221-4266-a54a-4669b3d39aca`. Matching services healthy; all 18 changed
  deployed runtime file copies verified plus standard provenance checks.
- Runtime policy, observed state/hop/time limits and prompt match round 19.
  One quiet watcher is active; collect/evaluate this same iteration after terminal.


## Round 20 handoff - 2026-11-18

- Failed; phase 04 remains open, qualification streak 0/3. Iteration
  `a4030533-71e3-43cd-8e4d-6816c7e7dd55`; session `45473832-0221-4266-a54a-4669b3d39aca`.
- Deployed/frozen source `2cd003097edc26d20dea1320ed9c58b0896c4d0a43b519fe2005ea9363849578`;
  config `99133119fce60532b32a8d26b38ab4b2f1956d5563c314cabb0eff0eb97da7c6`; oracle `9242b33d5e4cdd155b6642262c32f166b365edeec7d7b9642c5b88df35147a4e`.
  Same model, prompt and limits. Validated candidate checksums match deployed
  API/Temporal/Playwright. Build/deploy passed; no runtime source changes this round.
- Runtime `unavailable / operation_unavailable`: operation 85 (mct-13 CHƠI NGAY)
  persisted unknown/worker_response_lost despite worker completed/HTTP 200.
  After PNG exists in staging/RustFS with matching checksum; DB only has before
  frame. Exception inside after-frame verification/read-back/commit remains
  unclassified; do not infer network timeout or overwrite the unknown verdict.
- 31 clicks: 30 completed, one unknown. Optimistic coverage ceiling 31/47
  (65.9574%) fails; full outcome review unnecessary to establish failed gate.
  Saved zero-credit score is a conservative unreviewed bound, not actual accuracy.
  Detection P=R=46/47. 169 verified frames, one unavailable, one unresolved operation.
- Live sample retention improved: 6/10 reused (all carousel, 350-451 ms), versus
  0/23 round 19. Slide correctness not visually reviewed. 135 target checks all
  matched; stale replan/no-dispatch restore recovery not exercised live.
- 440.536003 s operation window; five model jobs, reported tokens 28,787/3,001.
  Monetary cost unknown. No active session; watcher and collectors exited.
- Report `benchmark/vision/accuracy/ROUND20-20261118.md`; portable summary
  `benchmark/vision/accuracy/round-20-20261118.json`; evidence under
  `benchmark/vision/accuracy/runs/a4030533-71e3-43cd-8e4d-6816c7e7dd55/`.
- Changed only round evidence/reports and plan progress; private local helpers
  perform checks/deployment/collection. No commit/push, next round or runtime fix.
- Next unit: reproduce the after-frame durable commit failure and retain typed
  failure-stage diagnostics. Preserve staged evidence and unknown outcome; never
  physically retry operation 85. Exact next command:

```powershell
Get-Content benchmark/vision/accuracy/runs/a4030533-71e3-43cd-8e4d-6816c7e7dd55/terminal-storage-probe.json
```

Stop at this round boundary. Continue diagnostic/fix work in a fresh session;
do not reload old full logs/images or mark the overall plan complete.

## User-requested pause - 2026-11-18

User requested: "lưu lại thông tin rồi dừng, bữa sau chạy tiếp".
Work is paused after round 20; the plan remains incomplete. No round 21 started.
Round-20 report, portable summary, source/config/oracle identities and diagnostic
evidence are saved in the paths above. Watcher and collectors finished before
this pause; the local Docker stack remains running on the ADR-036 candidate.

On the next explicit resume, read this handoff and `ROUND20-20261118.md`, then
`terminal-storage-probe.json`. Start by reproducing/diagnosing the after-frame
durable commit failure of operation 85. Preserve its unknown verdict and staged
evidence; do not retry that physical click or begin round 21 before a scoped fix
and relevant validation. Model, prompt, oracle and limits remain unchanged.

## Round 20 remediation - 2026-11-19

Cause: **chưa chứng minh được** (unproven). Evidence chỉ cho phép loại trừ:
- Outcome là `operation_unavailable`, không phải `screenshot_byte_limit`/`frame_ack_unavailable`
  (`VisualOperationStopped` được re-raise nguyên mã), nên lỗi là một exception không-typed.
- Worker frame GET 200 xảy ra sau execute, và object RustFS đã tồn tại với checksum khớp,
  nên fetch + `write_operation_frame` đã qua. Còn lại: store read-back, hoặc giao dịch DB
  của `commit_captured` (`add_frame`, `save_operation`, `_observe`: `save_checkpoint`
  "checkpoint invariants are immutable"/"ancestors must form one branch", edge lookup
  `next()` -> StopIteration). Giao dịch rollback sẽ không để lại dòng PG ERROR, khớp
  bằng chứng; `execute()` nuốt exception và không log gì (`vision_operations.py` handler).
- Frame 1,023,509 B > `VISION_MAX_SCREENSHOT_BYTES=1000000` nhưng không phải nguyên nhân
  (check đó chạy trước khi fetch và có mã riêng); đáng ghi nhận như một rủi ro riêng.

Fix (diagnostics only, safety giữ nguyên): operation không chứng minh được vẫn
`unknown/worker_response_lost`, không bao giờ thành completed, staging và fencing/tenant
không đổi, không re-click. Thêm phân loại `failure_stage` allowlist + `error_type`/
`error_module` (không message, URL, giá trị form): log `vision.operation.failure_stage`
và `ExecuteVisualOperation.last_failure`. Stage: `frame_limit|frame_fetch|frame_signature|
store_write|store_readback|db_commit|db_frame|db_locator|db_operation|db_observe|
db_checkpoint|db_edge|db_progress|capture_before|capture_after|ack|...`.

Changed files: `apps/control-plane/application/vision_operations.py`,
`apps/control-plane/infrastructure/persistence/vision_unit_of_work.py` (chỉ
`commit_captured`/`_observe`), new `tests/test_vision_operation_failure_stage.py`.

Tests (CODEX_BRIDGE_ENABLED=false): new file 5 passed (trước fix: ImportError/không có
`last_failure`); `uv run ruff check .` pass. Các test cần PostgreSQL fixture
(127.0.0.1:55437) bị skip (149 skipped) nên chưa chạy lại được trong phiên này.

Unproven / next: lần chạy live kế tiếp sẽ đọc `failure_stage` từ log controller để chốt
nguyên nhân rồi mới sửa gốc. Không chạy lại click của operation 85.

## Round 21 in progress - 2026-11-19 (Claude via `claude -p`)

User direction: start Docker, run (a) the op-85 remediation, (b) Claude through the
same DOM-first bridge, (c) a quick Claude look, and run Claude with `claude -p`
instead of the API. (c) is folded into this round: the screenshot-only path needed
the API and would not be comparable with Codex.

- (a) Op-85 cause still unproven; typed `vision.operation.failure_stage`
  diagnostics added (see "Round 20 remediation"). This round can classify a repeat.
- (b) New provider `claude_cli / claude-opus-5-5` (ADR-037, `docs/claude-local-bridge.md`).
  Same task prompt `codex-dom-v11`, schema, validator, oracle and limits; only the
  bridge engine and model differ. Qualification streak resets (model change).
- Policy switched via local tenant admin: `benchmark/vision/accuracy/policy-change-20261119-claude.json`
  (limits unchanged; DOM + image consent bound to `claude_cli`).
- Iteration `d3e65e1e-e3bb-4818-b2b3-5d9fdfc8db32`; session `cf3385a4-8949-43ca-ab49-965280327333`;
  source `995c6b28ee68439cdf95fd80f4a63068630362def207648dccc8919a4c0a1058`; config `e3039b749716d2af4fc5f6b8cc7bb5c28879171d4041c45ad41d58c231bd2307`;
  oracle `9242b33d5e4cdd155b6642262c32f166b365edeec7d7b9642c5b88df35147a4e` (unchanged).
- Deployed control-plane, temporal-worker, dashboard and `claude-bridge`; Playwright
  worker unchanged from round 20. Offline: 444 passed / 68 DB-gated skips; doctor and
  one in-container `claude -p` smoke passed.

### Round 21 attempts 1-2 (integration defects, not model results)

- Attempt 1, iteration `d3e65e1e-e3bb-4818-b2b3-5d9fdfc8db32` / session `cf3385a4-8949-43ca-ab49-965280327333`:
  `model_output_invalid` before any bridge job. `codex_batch.py` built
  `CodexBridgeRequest` with Codex defaults, so the contract rejected the
  Claude-bound consent (ValueError → model_output_invalid). Zero model calls.
  Fixed (pass policy provider/model); red/green regression in `tests/test_claude_bridge.py`.
- Attempt 2, iteration `54f7335d-dc91-49e2-81e8-1d1cdcfb35bb` / session `2128e10e-babe-44ad-8733-cbec9553386f`:
  `exploration_call_limit`; 20/20 Claude jobs completed, 18 proposals all
  `stop`, 0 explore clicks. Root cause reproduced on host: the shared response
  schema is unsatisfiable under strict JSON Schema (candidate variants set
  additionalProperties=false without the parent-required confidence /
  expected_outcome). Codex receives the schema only as prompt text; `--json-schema`
  enforces it, so Claude's valid click batches were rejected twice and it fell
  back to stop. Fix: Claude-only `enforceable_schema` (merges common fields into
  each variant; prompt text unchanged). Host re-probe: valid click batch first try.
  Added safe per-job log (outcome, stop reason enum, candidate count, schema
  rejections). Usage attempt 2: 697,746 input (541,061 cached) / 41,017 output tokens.
- Neither attempt measures Claude accuracy; both are recorded, not scored.

## Round 21 handoff - 2026-11-19

- Scored attempt 4: iteration `39de5dc7-c68e-49e1-b1b5-9cdc3b3a6391`, session
  `3af27fd0-49f2-443a-9072-ced07a69e3f7`, `claude_cli / claude-opus-5-5`. 47 clicks, 0 rejected/unknown,
  46/47 oracle positives (missing mct-47, recurring video copy). Ceilings
  C=A=46/47=97.8723%; outcomes unreviewed, so not a pass. Runtime
  `unavailable / unsafe_replay` at restore op 154. Report `benchmark/vision/accuracy/ROUND21-20261119.md`.
- Attempt 3 fixed the round-20 op-85 class: RustFS zero-size read right after PUT
  (`store_write / ArtifactStorageError`, RustFS `FileCorrupt`); bounded verified
  read retry in `infrastructure/artifacts/rustfs.py` + `tests/test_rustfs_read_after_write.py`.
- Validation: Ruff clean; 496 passed / 69 DB-gated skips (focused sweep); dashboard
  tests/typecheck/lint passed. Deployed control-plane, temporal-worker, dashboard,
  claude-bridge (`auto-at-claude-bridge:2.1.328`). Codex bridge stopped; tenant
  policy on `claude_cli` (switch back per `docs/claude-local-bridge.md`).
- Claude access token for the bridge expires ~2026-11-20 03:50 (Asia/Saigon); rerun
  `scripts/export_claude_bridge_token.py` before another live run.
- No active session; monitors exited. No commit/push. Next command (fresh session):

```powershell
Get-Content benchmark/vision/accuracy/ROUND21-20261119.md
```

### Round 21 outcome review - 2026-11-19

- Same iteration/session/source/config/oracle as above. 46 bound clicks reviewed:
  45 correct (45 content-addressed reviews); op 128 mct-57 previous arrow shows no
  slide change -> no credit (`carousel-outcome-mismatch.json`).
- Score (`run.py evaluate` via `.pytest-artifacts/score_round21.py`): C=A=45/47
  =95.7447% pass; detection R=47/47, **P=47/50=94.0% fail** (3 recurring unmatched
  inventory keys); inventory complete; no unsafe/unsettled. **Round 21 failed.**
- Open: mct-57 previous-arrow outcome, mct-47 video copy, the 3 unmatched inventory
  keys (precision), restoration terminal. No code changes, no commit/push.
- Next command (fresh session): `Get-Content benchmark/vision/accuracy/ROUND21-20261119.md`

### Agent loop round 01 handoff - 2026-11-20

- Plan `plan/20261119-2212-browser-agent-loop` phase 6. One live session (`engine=agent_loop`, claude_cli) created:
  `552a906a-9044-4440-b4b0-fbaea0eabcc3`; no iteration was imported. It ended in 0.94 s, 0 model calls, 0 operations: the worker
  refused session open with `invalid_deadline` (control-plane sends the whole-session deadline with the per-step
  `max_session_seconds`; `application/vision_agent_loop.py:296-353` vs `workers/playwright/src/vision-operations.ts:140`).
  **Not scored.** Record: `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md`; ADR-038; runbook section "Agent loop engine".
- Source: working tree on HEAD `f85091a`, uncommitted; containers byte-identical (0 mismatches over 163 + 48 files);
  oracle `9242b33d...` and `metrics.py` unchanged. Migration `b7c9d1e3f5a7` applied locally.
- Regression: ruff clean; pytest 1771 passed, 1 failed (baseline manifest-hash test), 33 skipped; worker operations 99 passed,
  agent-mode 40 passed + 1 timing-flaky (QA-W08 passes alone); dashboard 49 passed, typecheck/lint clean.
- Active: stack still up with `VISION_AGENT_LOOP_ENABLED=true` via a scratchpad compose override (not in `.env`); claude-bridge
  token had about 7 hours left at 2026-11-20 20:30 +7 (rerun `scripts/export_claude_bridge_token.py`). No active session. No commit.
- Next: a small phase to fix the open deadline in `vision_agent_loop.py` with a test that applies the worker rule; then one fresh round
  creating a new session with `.pytest-artifacts/agent_loop_round.py submit` (delete `.pytest-artifacts/agent-loop-session.json` first),
  `run.py import`, `collect`, review, `evaluate`.

### Agent loop round 01 r2 handoff - 2026-11-20

- Phase 6 r2: fixed the worker-open deadline in `application/vision_agent_loop.py` (open with `now + step_timeout`), tests with a
  fake worker applying the worker rule (red old, green new); ruff clean; agent-loop tests 53 + 160 passed.
- Live session `84fc0fa8-8c5a-48fc-9ab6-4a4e1faa8525` (the one approved): worker open OK, setup navigate OK, then
  `bridge_offline`: container `auto-at-ui-claude-bridge-1` runs a stale image (2026-11-19, before phase 3 bridge code) and exited 1 on
  the first agent job. 1 operation, 1 cancelled bridge job, 0 steps. **Not scored.** Evidence: `plan/20261119-2212-browser-agent-loop/reports/phase-06/live-session-r2-evidence.log`.
- Active: control-plane and temporal-worker rebuilt from the tree (flag on via the scratchpad override); `claude-bridge` container is
  EXITED (not running). No active session. No commit.
- Next: rebuild and recreate `claude-bridge` (`CLAUDE_BRIDGE_TOKEN_DIR=C:/Users/hen/.auto-at/claude-bridge-secrets`,
  `docker compose -f docker-compose.yml -f docker-compose.codex.yml build claude-bridge`, then `up -d --no-deps claude-bridge`), compare its
  files with the tree, refresh the token if needed, then one new session (move `.pytest-artifacts/agent-loop-session.json` aside first),
  `run.py import`, `collect`, review, `evaluate`.

### Agent loop round 01 r3 handoff - 2026-11-20

- Bridge rebuilt by the coordinator (container files equal the tree; heartbeat online before submit). Session `685f76a7-404d-49bf-acb5-1ff6c72d66c6`
  (third and last approved): 2 bridge jobs completed (agent schema parsed live, 9636 in / 805 out tokens), 3 operations, then
  `worker_result_mismatch` at operation 3. **Not scored; nothing imported.**
- Cause: `application/vision_agent_loop.py:232` sets `browser_parent` after every completed op; the worker (agent mode, `purpose=explore`) never extends
  its ancestry (`vision-operations.ts:559,869-873`), so its `parent_operation_id` stays the root navigate. Fake worker in tests echoes the parent.
- Next: a small phase to fix the parent tracking in `vision_agent_loop.py` (advance only for operations the worker pushes: navigate, setup refresh/scroll)
  and make `FakeWorker` apply the same rule; then, with a user decision, a fourth session. Stack: bridge Up, flag on via scratchpad override. No commit.

### Agent loop round 01 r4 handoff - 2026-11-20

- Fixed `parent_operation_id` tracking and the per-step lease renewal in `application/vision_agent_loop.py`; `FakeWorker` applies the real worker rules (parent, fingerprint, stale snapshot, origin, purpose,
  refresh). Tests: agent loop + QA 188 passed, live persistence 27 passed, ruff clean. Dry run (real worker through a local TCP forwarder, scripted model, in-process, disposable database): `agent_done`
  (`reports/phase-06/r4-dry-run-3.json`, helper `.pytest-artifacts/agent_loop_dry_run.py`).
- Live session 4 `9e21e389-8145-4870-824e-8a38013ea86e`: 6 model steps (30,672 in / 2,495 out tokens), 4 clicks, ended `worker_state_unavailable` because the session lease lapsed during two all-blocked
  steps (fixed after the run; the deployed control-plane and temporal-worker contain the fix). **Not scored.** Record: `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md`.
- Active: stack up with the fix and the flag (scratchpad override); claude-bridge Up; no forwarder or other temporary container. No commit.
- Next (needs a user decision, the approved sessions are used): one more live session with `.pytest-artifacts/agent_loop_round.py submit` (move `.pytest-artifacts/agent-loop-session.json` aside),
  then `run.py import`, `collect`, review, `evaluate`. Consider a prompt hint for off-origin pages (the model kept proposing clicks that are blocked there).

### Agent loop round 01 r5 handoff - 2026-11-21

- Container sources verified byte-identical before submit (`check` 0 mismatches after the coordinator rebuilt `claude-bridge`). Live session 5 `b77691e6-90ee-4676-884c-8d6547af2d4e`: 11 model steps
  (56,686 in / 4,668 out tokens), 12 completed browser operations (8 clicks, back, 2 close_popup, setup navigate), ended `origin_blocked` (not an agent reason). **Not scored, nothing imported.**
  Record: `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md` (section r5); evidence `.pytest-artifacts/agent-loop-r5-evidence.log`.
- Cause: after a click that left the allowed origin, `_observe` got `state_mismatch` and issued a read-only refresh `wait` (`purpose=setup`); the worker rejects any action except `close_popup`/`back`
  off-origin, so the loop stopped with `origin_blocked`. A race between redirect and the first DOM observation (earlier off-origin pages did not trigger it). Small fix proposed in the record
  (retry `observe_dom` read-only for off-origin pages instead of a `wait`, plus a FakeWorker test); no code changed in this round.
- Active: stack up (control-plane, temporal-worker, claude-bridge rebuilt, playwright-worker, dashboard, rustfs, temporal, postgres, redis) with the flag via the scratchpad override; no forwarder or temporary container.
  Session file moved: `.pytest-artifacts/agent-loop-session.r4.json`; the r5 file `.pytest-artifacts/agent-loop-session.json` holds the new id. No commit.
- Next (needs a user decision; the approved sessions are used): fix `_observe` off-origin refresh (small phase, test red then green, rebuild control-plane and temporal-worker), then one more live session
  (`mv .pytest-artifacts/agent-loop-session.json .pytest-artifacts/agent-loop-session.r5.json`, `uv run python .pytest-artifacts/agent_loop_round.py submit`), then `run.py import`, `collect`, review, `evaluate`.

### Agent loop round 01 r6 handoff - 2026-11-21

- Live session 6 `fa802b9c-3a3f-4de9-be54-08824014fe08` reached the first valid agent terminal: `agent_stopped` (`unsupported_state`) after 20 model steps (20 bridge jobs, 107,235 in / 8,976 out tokens, about 4 min 37 s,
  30 operations: 24 completed, 6 `state_mismatch` rejected). Imported as iteration `1c56623e-8f37-4705-946b-5f1a6752f81c`, collected, reviewed, evaluated. **Official score C 0/47, A 0/12, detection R 0/47 (P n/a), inventory incomplete,
  unsafe 0, unsettled 0: failed.** Zero because the harness binds only `dom_path` locators and agent_loop emits `role` locators and no page inventory (`pages=[]`); manual review of the 5 header-link clicks that map to the oracle
  (mct-01, 02, 04, 05, 06) found 5/5 outcomes correct (manual ceiling C 5/47 = 10.64%, A 5/12). Record: `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md` (section r6); evidence `.pytest-artifacts/agent-loop-r6-evidence.log`;
  scoring script `.pytest-artifacts/score_r6.py`.
- Source/fix of r6: working tree on HEAD `f85091a`, uncommitted; containers byte-identical (`check` 0 mismatches, 163/163/163/48). Worker fix `workers/playwright/src/vision-operations.ts:521-529` (read-only `wait`
  `purpose=setup` + `refresh_observation` runs off-origin) plus `_observe` in `application/vision_agent_loop.py`. Leader PASS (`reports/phase-04/leader-r1.md`), QA PASS (`reports/phase-04/qa-r1.md`). **The fix ran for real:**
  10 setup refresh waits, all completed; seq 12 is the r5 scenario (HO TRO click left the origin, `state_mismatch`, refresh wait off-origin accepted, `close_popup` recovered) with 0 `origin_blocked`. Oracle `9242b33d...`,
  `metrics.py`, `run.py`, policy unchanged.
- New blocker (not a fix of this round): after a scroll on the homepage every action was rejected with `state_mismatch` (6 in a row, `interaction_changed` + `visual_semantics_changed`, `scroll_changed=false`), so the model
  stopped with `unsupported_state` having touched 5/47 oracle targets plus 3 tab buttons outside the oracle scope; 4 of its 20 calls went to external-page recovery.
- Active: stack up (control-plane, temporal-worker, claude-bridge, playwright-worker, dashboard, rustfs, temporal, postgres, redis) with the flag via the scratchpad override; no forwarder, temporary container or session.
  Session files: `.pytest-artifacts/agent-loop-session.r5.json` (r5), `.pytest-artifacts/agent-loop-session.json` (r6). Bridge token refreshed 06:35 +07, a few hours left. No commit.
- Next (needs a user decision; the approved sessions are used): (1) decide how agent_loop operations are credited by the harness without changing the oracle or rules (role-locator binding by label/box, and a source of detection/inventory
  for agent_loop, since `pages=[]`); (2) investigate the homepage `state_mismatch` drift after scroll (worker prepare fingerprint vs animated hero/news area) and, if wanted, a prompt hint on `state_mismatch`; then one more live session
  (`mv .pytest-artifacts/agent-loop-session.json .pytest-artifacts/agent-loop-session.r6.json`, `uv run python .pytest-artifacts/agent_loop_round.py check`, `submit`, `run.py import`, `collect`, review, `evaluate`).

### Agent loop round 01 r7 handoff - 2026-11-21

- Two offline directions, no deploy, no live session, no commit, no rebuild; stack unchanged from r6 (same containers, flag override, session files).
- A (harness): `benchmark/vision/accuracy/{evidence.py,run.py}` bind path-less `role` locators to the oracle (root tab, oracle viewport, role, normalized name, IoU>=0.8, unique candidate, click in box, one credit per target); path rule, oracle, `metrics.py` untouched; ADR-039; graph `vision-accuracy-harness`; new `run.py ground`. Leader PASS.
- A result: r6 re-evaluated from the stored trace, harness derived mct-01,02,04,05,06 itself = manual review. C 5/47, A 5/12, R 0/47, inventory incomplete, passed=false. Ceiling today 16/47 bindable (15 unnamed/div never bindable by role+name).
- B (worker): `vision.state.mismatch` diag only (`state_age_ms`, `interaction_*`, `failure_stage=observe_start`) in `vision-checkpoints.ts` / `vision-operations.ts`; gate, caps, prompt, control-plane unchanged. Proven: 6/6 rejections are the scope `all` interaction fingerprint drifting in the 6-10 s idle window (not stale refs, not ms races). Not isolated: which element changed. Leader PASS.
- Checks: ruff clean; accuracy tests 57 passed; agent_loop/safety 73 passed 38 skipped; worker suite 293 passed 1 timing-flaky (solo 2/2 pass); tsc exit 0; `hgraph check` exit 0 (`--changed` exit 1 = git root vs hgraph root prefix, tooling issue).
- Rebuild needed before any live session: only `playwright-worker`.
- Next (needs user decision): (1) ESCALATE for A: export scroll/url fingerprint in `/trace` (unlocks 32/47), dom_path for unnamed controls, persist inventory or accept the audit as detection source; (2) short live session after rebuilding `playwright-worker`, read `vision.state.mismatch` before touching the gate.
- Reports: `reports/phase-04/{be-developer-r6a,be-developer-r6b,leader-r2a,leader-r2b}.md`.
- User decision 2026-11-21 (after r7): (B) approved rebuild `playwright-worker` + exactly one live agent_loop session to read `vision.state.mismatch` (no gate change yet).
  (A) approved all three ESCALATE items, each behind its own config flag (default off): A1 export per-operation scroll offset + page URL fingerprint in `/trace`;
  A2 `dom_path` locators for unnamed controls in agent mode; A3 persist per-observation page inventory. Then benchmark the flag combinations and keep only what scores better; oracle/thresholds unchanged.

### Agent loop round 01 r8 handoff - 2026-11-21

- Offline implementation of the three user-approved ESCALATE items (r7 decision 2026-11-21), no deploy, no live session, no bridge/model call, no migration, no commit. ADR-040. Reports: `reports/phase-04/be-developer-r7.md`.
- **Flags (all default `false`, read only by `temporal-worker`, independent):** A1 `VISION_AGENT_CLICK_CONTEXT_ENABLED` (worker capability `click-context-v1`: `/trace` `executed_click` gains `scroll_x`, `scroll_y`, `url_fingerprint`);
  A2 `VISION_AGENT_DOM_PATH_ENABLED` (`agent-dom-path-v1`: unnamed buttons/links/custom controls get `dom_path` locators and are listed to the model as `role ""`; named controls unchanged);
  A3 `VISION_AGENT_INVENTORY_ENABLED` (control plane only: each DOM observation is merged into the state's `page_inventory`, shown in `/result` `pages`; JSON column, no migration).
  Off = worker request, worker behaviour, stored payload, `/trace`, `/result` and harness output unchanged (absent keys are never serialized, so trace revisions of old sessions are identical). Needs a rebuilt `playwright-worker` for A1/A2.
- **Harness** (`benchmark/vision/accuracy/{evidence.py,run.py}`; oracle `9242b33d...`, `metrics.py`, thresholds untouched): reads click context and inventory when present, falls back to the old rules when not. With a context both binding rules require the click on the oracle page (`url_fingerprint == sha256(source_url)`),
  the role rule may match an in-flow control at the click's scroll offset (fixed controls still at offset 0, ambiguity earns nothing). `collect`/`ground` store `inventory.json` (only when `/result` has pages) and `contexts` in `grounding.json` (only when a click has one). New `run.py detect` derives detection for the oracle page from the inventory (dom_path key, else unique role+name; other controls unexpected).
  `detect|evaluate --sources all|none|click_context,inventory --label <name>` re-score a stored session per combination into `<artifact>.<label>.json` (default artifacts untouched); A2 is a live-session property, compare sessions run with it on and off.
- **Checks (offline):** ruff clean; new python tests 20 (`tests/test_vision_agent_evidence_flags.py`) + 23 (`tests/test_vision_accuracy_agent_evidence.py`); focused python regression 509 passed 81 skipped and 75 passed 153 skipped (skips = no isolated PostgreSQL); worker `tsc --noEmit` and eslint exit 0; worker specs 6 new (`vision-agent-evidence.spec.ts`) + 111 passed 1 skipped + 123 passed regression; `hgraph check` exit 0 (`--changed` exit 1 = git-root prefix tooling issue).
- **Not verified live:** negotiation against the rebuilt worker container, dom_path stability on the real carousel (v3 paths wait for `stable`), real inventory size/truncation, the agent's behaviour once it sees unnamed controls (it cannot tell them apart except by order), and any score. DB-gated agent-loop tests skip here (no PostgreSQL on 55437); the processor behaviour was covered with stubs. No claim that C, A, P or R improved.
- **Next (needs a user decision, the approved live sessions are used):** rebuild `playwright-worker`, `control-plane`, `temporal-worker` with the flags set in the scratchpad compose override (A1+A3 first, then A1+A2+A3), run one session each with `.pytest-artifacts/agent_loop_round.py submit`, then `run.py import`, `collect`, `detect`, review, `evaluate --sources ... --label ...`, keep only what scores better. The r7 (B) session to read `vision.state.mismatch` is a separate approval already recorded above.

### Agent loop round 01 r9 handoff - 2026-11-21

- The single approved live session (A1+A3 on, A2 off) `79b90323-e05f-474e-9ca7-6f66993995f2` ended `unavailable` / `bridge_policy_revoked` after 40 s: 1 completed model step, 2 bridge jobs (job 1 completed 4,655 in / 289 out tokens; job 2 stopped by the bridge itself 2.2 s after it
  started, no usage), 2 operations (setup navigate, one SU KIEN click), 1 step-log row. **Not a valid agent terminal (AC6), not scored, not imported into `runs/`.** No source, oracle, `metrics.py`, policy or prompt change. Full record: `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md` (section r9); report `reports/phase-04/be-developer-r8.md`.
- Cause (hypothesis from timing and code, unproven): race in `FileSpool.stop_reason` (`spool.py:371-400`): the bridge takes `now` before reading `authorization.json`; the control plane rewrites it every 2 s (`recorded_at = now()`), a receipt written in between has `recorded_at > now` and is read as `bridge_policy_revoked`. Failure time = first re-authorization of job 2. Not seen in r5/r6 (31 jobs).
- **A1 and A3 worked live (first time).** A1: `click-context-v1` negotiated, the click carries `scroll_x=0, scroll_y=0, url_fingerprint=a21c4cf7...` = `sha256(oracle.source_url)`. A3: `/result` `pages` = 2 states, homepage 7 controls (`scrollable`, `skipped_count=9` `multiple_matches`, not truncated), `/su-kien` 11 controls (`skipped_count=2`); far from the 100-control cap.
- Diagnostic harness evaluation (scratch directory, **not an official score**, one reviewed click; SU KIEN = mct-02 correct): every `--sources` combination gives C 1/47, A 1/1, passed=false; detection P 7/7, R 7/47 (mct-01 to 06 and 11) with `inventory`/`all`, 0/0 and 0/47 with `none`/`click_context`; inventory incomplete (scrollable, skipped). The click credit needs no context (first viewport), so
  A1 value is only visible for below-the-fold clicks, none reached. No claim that C, A, P or R improved versus r6 (C 5/47, A 5/12, R 0/47): different run length.
- `vision.state.mismatch`: 0 in the worker log for this session; the r7 (B) question (which element drifts) stays unanswered.
- Active: stack up (control-plane, temporal-worker, claude-bridge, playwright-worker, dashboard, rustfs, temporal, postgres, redis); no temporary container or process of this round. Session files: `.pytest-artifacts/agent-loop-session.r6.json`, `.pytest-artifacts/agent-loop-session.json` (r9). Read-only dumps `.pytest-artifacts/agent-loop-r9-{trace,result,locators}.json`. Bridge token refreshed earlier today (about 6 h left at start). No commit.
- Next (needs a user decision; the approved live session is used): (1) small fix for the `stop_reason` race (take `now` after reading the receipt or allow a small skew) with a test that rewrites the receipt during polling, rebuild `control-plane`, `temporal-worker`, `claude-bridge`; (2) one new live session with the same A1+A3 flags
  (`mv .pytest-artifacts/agent-loop-session.json .pytest-artifacts/agent-loop-session.r9.json`, `agent_loop_round.py check`, `submit`), then `run.py import`, `collect`, `detect --sources inventory`, review, `evaluate --sources ... --label ...`; (3) A2 only after A1+A3 yields a valid terminal to compare against, because A2 changes what the model can click and cannot be toggled after the fact.

### Agent loop round 01 r10 offline fix handoff - 2026-11-21

- Cause: `FileSpool.stop_reason` (`spool.py`) treated a receipt with `recorded_at > now` as `bridge_policy_revoked`; the bridge samples `now` before reading `authorization.json` and the control plane re-signs it every ~2 s, so a receipt written in between killed r9 session `79b90323…`. Proven offline with a lagged poll; not proven live.
- Fix: `RECEIPT_CLOCK_SKEW = 1 s`, condition `recorded_at - RECEIPT_CLOCK_SKEW <= now`; expiry, deadline, ttl (0, 10 s], status and cancel unchanged. ADR `docs/adr/041-bridge-receipt-clock-skew-tolerance.md`.
- Tests: dev red then green (1 failed before, 134 passed / 29 skipped after); QA `tests/test_qa_r9_bridge_receipt.py` 28 passed; regression 253 passed, 46 skipped, 1 failed (pre-existing `test_codex_bridge_benchmark.py` manifest hash drift, not r9); `test_codex_bridge_end_to_end.py` does not collect (machine `.env`).
- Verdicts: leader r4 PASS, QA r3 PASS. Optional: ADR wording (lease ceiling can be ~11 s relative to bridge `now`), simplify the excessive-ttl test.
- Not rebuilt, not run live; no commit. Stack still on the r9 images.
- Next: rebuild `control-plane`, `temporal-worker`, `claude-bridge`, then one new live A1+A3 session (needs user approval), watch bridge log for `bridge_policy_revoked` from job 2 on.
- Separate round: regenerate `benchmark/vision/codex/manifest.json` (17 source hashes drifted).

### Agent loop round 01 r10 live handoff - 2026-11-21

- The one approved live session (A1+A3 on, A2 off, ADR-041 images) `22187cc7-4247-426b-83ec-446de3682f5c` ended `agent_done` after about 3 min 19 s: a **valid terminal**, imported as iteration `396af7e4-11f9-4983-adea-180d37c768db`, scored. ADR-041 worked live: 14 bridge jobs (all `completed`), 0 `bridge_policy_revoked`.
- Model steps 14, tokens 72,096 in / 5,136 out (cached 24,233). Operations 16, all completed: setup navigate 1, setup wait 1, click 10, back 1, close_popup 3. `vision.state.mismatch` 1 (lazy `IMG` added on support.tpl.vn after the HO TRO click; recovered by the setup refresh wait; gate untouched; the homepage-after-scroll drift of r6 did not recur because the model never scrolled).
- Official score (`run.py evaluate --sources <x> --label r10_<x>`, default artifacts untouched, oracle `9242b33d...`/`metrics.py`/policy/prompt unchanged): `all` and `inventory` and `click_context,inventory` C 1/47 (2.13%), A 1/10, P 7/7, R 7/47; `none` and `click_context` C 1/47, A 1/10, P n/a, R 0/47; inventory incomplete (homepage scrollable, 9 skipped), unsafe 0, passed=false in all five.
- Why C is 1/47: after click 1 (SU KIEN, the only click on the oracle page) the agent stayed on `/su-kien`, `/tin-tuc`, `/cam-nang`, tested the shared header links there (off-page), never scrolled and stopped with `complete`. With A1 the harness refuses those clicks (`off_page_url`); a label+box-only reviewer (diagnostic in scratch, not official) would credit C 5/47 / A 5/10 under `--sources none`. So A1 prevents a false 5/47; the r6 5/47 was not page-checked. Not an improvement over r6; detection R 0 to 7/47 is the only gain (from A3).
- A3 inventory real size: 14 pages, about 30 KB, 1-11 controls per page, never truncated (cap 100); homepage 7 controls + 9 skipped (below the fold).
- Active: stack up, no new process; images from the coordinator rebuild (control-plane, temporal-worker, claude-bridge with ADR-041). Session files `.pytest-artifacts/agent-loop-session.r9.json`, `.pytest-artifacts/agent-loop-session.json` (r10). Dumps `.pytest-artifacts/agent-loop-r10-{trace,result,locators}.json`. Report `reports/phase-04/be-developer-r10.md`. No source change, no commit.
- Next (needs a user decision; the approved session is used): the blockers are now agent behaviour, not the harness: (1) the agent leaves the oracle page and quits without scrolling, so 31 below-the-fold and 15 unnamed targets are not attempted; a prompt/policy change (return to the homepage, scroll on `scrollable`/`skipped_count>0`, do not stop while the oracle page has skipped controls) is a prompt-version change and needs approval; (2) A2 (`VISION_AGENT_DOM_PATH_ENABLED`) only addresses the 15 unnamed targets, and only helps if the agent reaches them, so run it after (1) or together as the single A1+A2+A3 run ADR-040 describes; (3) K1 (20 calls) is already unlikely: 10 clicks and 14 calls reached 1 target.
- User decision 2026-11-21 (after r10): approved a prompt change for agent_loop (new prompt version) so the agent returns to the oracle page and scrolls while
  below-the-fold controls remain skipped (`skipped_count > 0`), instead of ending `complete`; policy caps, gate, oracle, metrics unchanged. Then one live A1+A3 session. A2 later.

### Agent loop round 01 r12 live handoff - 2026-11-21

- The one approved live session (prompt `agent-loop-v2`, A1+A3 on, A2 off) `e0de6697-ed86-4418-8d8d-f3bc4922e36a` ended `unavailable` / `settle_timeout` after about 1 min 33 s: a worker page-readiness outcome, **not a valid agent terminal** (no `agent_done`/`agent_stopped`). Not imported into `runs/`; no official score. 5 bridge jobs (all `completed`, 0 `bridge_policy_revoked`), 27,976 in / 2,598 out tokens, 5 of 20 calls.
- Prompt v2 changed behaviour: the agent stayed on the oracle homepage, scrolled (`scroll_y=600`) and clicked 5 below-the-fold controls (Su Kien, Cam Nang, NHAN VAT, THU CUOI, Tin Tuc), all with A1 context bound to the oracle page. Then scroll op 8 failed `settle_timeout` (`state_kept_changing`, 53 state changes in 10 s) and the recovery `wait` was rejected with the same code; one `vision.state.mismatch` in between (1 control moved, geometry-only, 18 controls). Homepage drift after scroll/tab clicks, the r6-type cap, now confirmed to be in the worker settle rule, not the model.
- Diagnostic only (scratch run dir, not `runs/`): the 5 clicks bind to oracle mct-19, 20, 30, 31, 18; outcome correct for 3 (mct-19, 20, 18), 2 (mct-30, 31) lack visible matching content in the frame. `--sources all`: C 3/47 (strict) or 5/47 (lenient), A 3/5 or 5/5, P 14/35, R 14/47, inventory incomplete, passed=false. `none`/`inventory` refuse (`no_oracle_match`: a scrolled box cannot bind without scroll offset), so A1 is required for scrolled clicks.
- No improvement is claimed over r10 (1/47 official) or r6 (5/47, no page check): different terminal validity. Behaviourally: 5 calls for 5 oracle targets versus 14 calls for 1.
- Active: stack up, no process of this round. Session files `.pytest-artifacts/agent-loop-session.r10.json`, `.pytest-artifacts/agent-loop-session.json` (r12). Dumps `.pytest-artifacts/agent-loop-r12-{trace,result,locators}.json`. Report `reports/phase-04/be-developer-r12.md`. No source change, no commit.
- Next (needs a user decision; the approved session is used): (1) the blocker is the worker settle rule on the homepage after scroll/click (`state_kept_changing`), a worker/policy change (e.g. what counts as a state change when only geometry/animation moves, or a bounded retry/recovery for `settle_timeout`) that must not loosen the gate silently; (2) then one new live A1+A3 run to get a valid terminal; (3) A2 (`VISION_AGENT_DOM_PATH_ENABLED`) addresses the 15 unnamed targets and only matters once the agent can keep scrolling past the first below-the-fold panels; run it as its own session after (2).
- User decision 2026-11-21 (after r12): diagnose the homepage `settle_timeout` (state keeps changing after scroll/click) offline first; no gate change, no live session in this step.

### Agent loop round 01 r13 diagnosis handoff - 2026-11-21

- Offline only (no live session, no bridge/model, stack not rebuilt, no commit). Cause of the r12 `settle_timeout` isolated: infinite CSS pulse (`play-now-pulse`) on the viewport-visible play-now link `a.absolute.inset-0`; the scope-`all` interaction fingerprint hashes clipped bounds/hit tests of every visible control, so no 800 ms quiet window exists (probe: 79-85 changes in 15 s, longest quiet 341-431 ms, 78/79 geometry-only). Swiper autoplay only adds the discrete r6b drift.
- Probe: `.pytest-artifacts/r13-settle-probe.{mts,json}` (+ `r13-swiper-peek.mts`, `r13-link-series.mts`). New worker spec `workers/playwright/src/vision-settle-animation.spec.ts` + fixture `fixtures/settle-animated-control.ts` (graph playwright-vision-worker): `7 passed` with the "should settle" case as `test.fail()`.
- Proposals A (bounded geometry tolerance), B (layout-box for infinite-animation ancestors), C (content-only settle plus geometry check at prepare); tab-outcome options for mct-30/31 (panel below the frame). Report: `reports/phase-04/be-developer-r13.md`.
- Next (needs a user decision on the settle rule and an ADR; then rebuild playwright-worker and one new live A1+A3 session): pick A/B/C; decide the tab-outcome rule before scoring a valid run.
- User decision 2026-11-21 (after r13 diagnosis): settle fix = option **A + limited B** from `reports/phase-04/be-developer-r13.md` §4 (bounded geometry tolerance when control identity/content is unchanged, plus layout-box bounds only for controls under an identified infinite CSS animation), with a new ADR; hit test and exact-node verify at dispatch stay. Tab outcome (mct-30/31): keep the oracle rule wording, add evidence instead (an extra after-frame scrolled to the selected panel). Continue in the same conversation (user override of the fresh-session preference). Order: r14 settle fix, then r15 tab evidence, then one live session.

### Agent loop round 01 r13-r14 handoff - 2026-11-21

- Cause of the r12 `settle_timeout`: infinite CSS pulse (`play-now-pulse`) on the viewport-visible play-now link; the scope-`all` interaction fingerprint hashes clipped bounds and hit tests, so no 800 ms quiet window exists (r13 probe: 79-85 changes in 15 s, 78/79 geometry-only). Report `reports/phase-04/be-developer-r13.md`.
- ADR-042 (`docs/adr/042-settle-geometry-tolerance.md`), option A + limited B: `equivalentState` tolerates 3 px centre shift and IoU 0.8 when content is identical (centre hit must match); layout box only for controls under an eligible infinite CSS animation (scale/rotate/opacity); settle compares against the quiet-window reference. Fingerprint hashes, policy and contract unchanged; no database change.
- r14b: observe/prepare compare against the held state (`held.fingerprint === expected && equivalentState`), and `force` click only for an eligible infinite-animation target after hit test and exact-node verify.
- Files: `workers/playwright/src/{vision-checkpoints,vision-dom,vision-operations}.ts`, specs `vision-settle-animation.spec.ts` (14) and `.qa.spec.ts` (24), fixture `fixtures/settle-animated-control.ts`, `docs/vision-agent-operations.md`, `docs/graphs/playwright-vision-worker.md`.
- Tests (offline, fixtures): settle dev + QA `34 passed`, QA `24 passed` x3, regression `145 passed`, `vision-operations.spec.ts` `99 passed`, `tsc` exit 0, `hgraph check` clean. Not verified live (real widget hit-test stability, iframe/shadow, Element.animate/transition).
- Review: round 1 FAIL (leader: direct hash compare in dom/prepare; QA-P1: click on pulsing target `action_outcome_unknown`), round 2 PASS (leader r7, QA r6). Details: `progress.html`.
- Debt: DOM mode grounds clicks by coordinates, so a visible control covering the target takes the click and the operation is `completed` (pre-existing, not from r14; conflicts with the "wrong target click = 0" invariant). Suggested guard: compare `dom_element_id` with the node's descriptor at the point (`dom_descriptor_mismatch`) in `groundLocator`/prepare.
- Needs rebuild of `playwright-worker` (not rebuilt; no control-plane change); no live session, no commit.
- Next r15: add an after-frame scrolled to the selected panel for tab clicks (mct-30/31), keep the oracle rule; then rebuild playwright-worker and one live A1+A3 session (expect no `settle_timeout`, no geometry-only `state_mismatch`).
- User decision 2026-11-21 (after r15): **shelve r15** (tab panel frame, ADR-043, unapproved migration `c8d0e2f4a6b8` + 5 control-plane files outside scope; ARIA-only detection would not fire on the real mct-30/31 buttons). Save it as a restorable patch, remove it from the tree, then rebuild `playwright-worker` and run one live A1+A3 session to verify ADR-042. Tab evidence revisited later.

### Agent loop round 01 r16 live handoff - 2026-11-21

- Result: **FAIL, not scored, not imported.** The one approved live session `82e22289-b52a-4fd3-b74f-633a31147214` (correlation `8cf2d7c9-ca0b-4c0b-ae46-b80778d83b75`) ended `unavailable` / `visual_exploration_unavailable` at worker `session_open` (HTTP 422 `visual_request_rejected`, `error_type=unexpected_error`, 3,787 ms, 13:09:15 UTC), before any operation or bridge call: 0 operations, 0 of 20 calls. ADR-042 and prompt v2 were NOT exercised; no claim about them.
- Identity: `agent_loop_round.py check` 0 mismatches (163/163/163/52) at 20:07; flags loop + A1 + A3 on, A2 off; oracle, `metrics.py`, thresholds, policy, prompt untouched; no source change.
- Cause not established: the worker logs only the category `unexpected_error` (messages deliberately not logged). Container healthy (no OOM, 0 restarts, target reachable); the same tree passes locally (`vision-agent-mode.spec.ts` + `vision-settle-animation.spec.ts`: 45 passed). Hypothesis only: cold-start Chromium launch in the freshly recreated, read-only worker. Provider `claude_cli` showed `online=false` for about the first minute after recreate.
- Comparison: r6 5/47 official, r10 1/47 official, r12 diagnostic only, r16 none.
- Artifacts: `.pytest-artifacts/agent-loop-r16-{trace,result,locators}.json`, `agent-loop-session.json` (r16), `agent-loop-session.r12.json`; `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md` (r16 section); report `reports/phase-04/be-developer-r16.md`. `runs/` untouched. Stack up unchanged, no process left.
- Next (needs a new user approval, one session): first verify the worker open path without the LLM (or add a log of the error class for `unexpected_error`), hold until provider `online=true` for 60 s, then one live A1+A3 session to test ADR-042 + prompt v2; A2 stays off.
- r16/r17 (2026-11-21): live session `82e22289-...` failed at worker `session_open` (`unexpected_error`). r17 root cause: r14's named nested closure inside a `page.evaluate` callback in `vision-checkpoints.ts` gets an esbuild `__name(...)` call under tsx (worker runtime), which the browser lacks: every session breaks at open since r14; Playwright specs did not catch it. User decision: fix at the root (no named functions in evaluate callbacks) + `__name` init-script shim as defence + a test running open under tsx + safe error-name logging; review; rebuild worker; one no-LLM open/close check; then one live A1+A3 session.

### Agent loop round 01 r19 live handoff - 2026-11-21

- Result: **not scored, not imported** (invalid terminal). The one approved live session `6eef105a-ae98-44cf-9b09-e5a6d0ad1262` (correlation `5075d594-b471-49d7-8366-4583bb4fc797`, prompt v2, A1+A3 on, A2 off) opened (r18 `__name` fix confirmed live, 0 `unexpected_error`), ran 14 operations and ended `unavailable` / `settle_timeout` at 13:55:38 UTC. 8 of 20 model calls, 0 `bridge_policy_revoked`.
- Behaviour: scroll to y=600, then 6 clicks on the oracle page (Su Kien, Cam Nang, Tin Tuc, NHAN VAT, THU CUOI = oracle mct-19, 20, 18, 30, 31; plus TOP, not an oracle target). All settled (ADR-042 effective live for these; r12 failed here). No force click; all 6 clicks hit the intended control (name + box + after frame); the r14 covered-control debt was not exercised. The agent never left the oracle page.
- Blocker remains: after TOP scrolled the page back to the top, scroll seq 9 failed `settle_timeout` (52 state changes in 10 s, longest stable 240 ms), then wait / scroll hit geometry-only `state_mismatch` (18 controls, 1-3 moved, held state aged 7-20 s) and the setup wait `settle_timeout` ended the session.
- Diagnostic only (scratch dir): strict 3/47 (6.38%), lenient 5/47 (10.64%), A 3/6 or 5/6, P 14/35, R 14/47, inventory incomplete, passed=false; `none`/`inventory` refuse (`no_oracle_match`). Same C/P/R as r12; no improvement claimed over r6 (5/47, no page check) or r10 (1/47 official).
- Artifacts: `.pytest-artifacts/agent-loop-r19-{trace,result,locators}.json`, `agent-loop-session.json` (r19), `agent-loop-session.r16.json`; `AGENT-LOOP-01-20261120.md` (r19 section); report `reports/phase-04/be-developer-r19.md`. `runs/` untouched. Stack up unchanged, no process left, no source change, no commit.
- Next (needs a user decision; the approved session is used): diagnose offline why the page top after scroll back / TOP never settles (not isolated; extend ADR-042 or a bounded recovery), consider steering the agent away from the back-to-top control, then one new live run. A2 stays a separate session.
- User decision 2026-11-21 (after r19): diagnose offline why the homepage does not settle on the scroll after the TOP button returns to the top (r19 seq 9); read-only probe, no gate change, no live session in this step.

### Agent loop round 01 r20 diagnosis handoff - 2026-11-21

- Scope: offline, read-only (phase-04 step 1-2). No live session, no bridge/model call, no docker action, no source or gate change, no commit.
- Result: the TOP click is not the cause (instant scroll, settles in about 1 s; TOP then +600 is calm in 4 replicas, incl. the r19 wall-clock timeline with 5 tab clicks). r12 (no TOP) fails with the same signature. Mechanism reproduced: at y about 1200 with the NHAN VAT / THU CUOI tabs active, the `mount-switcher` widget produces hit-test/box churn every sample in 25.5 s bursts (period about 36 s); finite timer-restarted animations, so ADR-042 A (3 px / IoU 0.8) and B (infinite scale/rotate/opacity) do not absorb it. A scroll whose 10 s window lands in a burst ends `state_kept_changing`.
- Open: the `delta_y` of r19 seq 9 (operation `cb145ad0`) is not in the dumps (+600 from y=0 lands on a calm y=600); a full local 10 s timeout was not reproduced (worst local settle 4.2 s, throttled 6.6 s, r19-timeline replicas 8.4-8.6 s).
- Spec: `workers/playwright/src/vision-settle-switcher.spec.ts` (3 passed, one `test.fail()` documenting the defect); `npx tsc --noEmit` exit 0; `hgraph check` clean (graph `playwright-vision-worker`, +1 file).
- Proposals (not implemented, need your choice): A longer settle budget for scroll ops and recovery (gate unchanged, does not fix the later `prepare` mismatch inside a burst); B scoped equivalence / ambient-motion class (relaxes the gate, ADR-043 candidate); C calm the page during settle (needs a live-site probe first, may not help). Prompt steering away from TOP is not useful.
- Artifacts: `.pytest-artifacts/r20-*` (probes `r20-top-probe.mts`, `r20-phase-sweep.mts`, JSON outputs); `AGENT-LOOP-01-20261120.md` (r20 section); report `reports/phase-04/be-developer-r20.md`. No process left.
- Next (needs a user decision): first read the r19 seq 9 `delta_y` (read-only), then choose A or B (B needs an ADR) or an offline probe of C; one new approved live run only after a worker fix. A2 stays a separate session.
- User decision 2026-11-21 (after r20): option **C** — first probe the real site read-only to see whether suppressing/pausing animations during settle makes the `mount-switcher` hit-test and boxes stable (z-index may still change); no source change in this step.

### Agent loop round 01 r21 probe handoff - 2026-11-21

- Scope: offline, read-only probe of option C (user decision after r20). No live session, no bridge/model call, no docker action, no source or gate change, no commit.
- Result: on the real site, in one burst at y=1200, a page-wide rule `animation/transition-duration:1ms` (`b2`, 2 runs) stabilises the `mount-switcher` (1-2 changes per 5 s versus 22-30, `settleState` ok about 0.9 s versus fail). `transition:none` + paused (`b`) and a looping `pause()` (`a2`) also stabilise but swallow `transitionend`/freeze a mid-frame. One-shot pause, `finish()`, scoped subtree pause/CSS and CDP playback rate do not help.
- Limits: page JS timers still change the DOM (carousel hops, 1-2 changes per 5 s), so a hop between settle and prepare still gives `state_mismatch`; the churn returns at baseline as soon as the rule is removed, so the calm must last through prepare, dispatch and the after-capture. The r19 seq 9 `delta_y` is still unread.
- Spec: `workers/playwright/src/vision-settle-suppression.spec.ts` (6 passed, local fixture); `npx tsc --noEmit` and eslint clean; `hgraph check` clean (graph `playwright-vision-worker`, +1 file).
- Design (not implemented): new `workers/playwright/src/vision-calm.ts` (enable/disable/withCalm), called at `vision-operations.ts` about lines 887 and 552, kept session-level through prepare/dispatch, restored in `finally`, worker flag default off; ADR 043 proposed; combine with A-lite (one re-settle on a single-hop `state_mismatch`) or B (scoped equivalence ADR).
- Artifacts: `.pytest-artifacts/r21-*` (probe `r21-suppress-probe.mts`, JSON, paused screenshots); `AGENT-LOOP-01-20261120.md` (r21 section); report `reports/phase-04/be-developer-r21.md`. No process left.
- Next (needs a user decision): approve B2 implementation (flag, ADR 043) plus A-lite or B for the residual hop, then one approved live run; or read the r19 seq 9 `delta_y` first.
- User decision 2026-11-21 (after r21): implement **calm mode** in a fresh session: `vision-calm.ts` page-wide 1 ms animation/transition style held through settle → prepare → dispatch → after-capture, restored in `finally`, behind a worker flag (default off), new ADR-043; residual JS-timer carousel hops handled by a bounded re-settle (no scoped-equivalence gate change). Then leader + QA, refresh the bridge token (`scripts/export_claude_bridge_token.py`, expired ~22:10), rebuild `playwright-worker` (+ temporal-worker if the flag is read there), no-LLM open/close check, one live A1+A3 session. Next command: `/clear` then `/h-cook auto-at-ui/plan/09112026103202-vision-accuracy-loop`.
