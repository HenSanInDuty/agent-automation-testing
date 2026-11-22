STATUS: DONE (instrumentation only; root cause partly proven, element-level cause NOT isolated offline; gate deliberately unchanged)

# be-developer r6b - homepage `state_mismatch` drift (hướng B)

CONTEXT_CHECK
- conventions: docs/code-standards.md (chỉ mục) -> AGENTS.md (đọc nguyên văn). docs/api-conventions.md không tồn tại; không bịa convention.
- graphs: playwright-vision-worker, vision-agent-loop (đọc nguyên văn). vision-exploration/codex-bridge liệt kê nhưng không đụng.
- blast radius: vision-operations.ts 17 file bị phụ thuộc / 28 file phụ thuộc (hgraph brief). vision-checkpoints.ts nằm trong cùng graph; mọi spec `vision-*.spec.ts` import nó gián tiếp.

## Impact inventory
- Database: không đụng. Contract (`packages/contracts/**`), API, env, schema: không đụng. Control-plane Python: không sửa file nào.
- Sửa:
  - `workers/playwright/src/vision-checkpoints.ts`: `RuntimeState` thêm `privateInteractions` (digest, không text) + `capturedAt`; thêm `interactionDiff`; `logStateMismatch` phát thêm `state_age_ms`, `interaction_*`.
  - `workers/playwright/src/vision-operations.ts` (observeDom, 1 chỗ): ghi log `vision.state.mismatch` (`failure_stage=observe_start`) trước khi từ chối `state_mismatch`; trước đây nhánh này từ chối im lặng (đúng cái thiếu trong evidence: dòng 9/17/24... của log r6 không có diag đi kèm).
  - `workers/playwright/src/vision-observability.spec.ts`: +1 test (diag phân biệt control di chuyển/bị thay/bị đổi nhãn, không lộ text).
  - `workers/playwright/src/vision-agent-mode.spec.ts`: +7 test (1 tái hiện autoplay + hồi phục, 6 test âm).
  - `docs/graphs/playwright-vision-worker.md`: 1 bullet mô tả diag (phần viết tay, không đụng khối auto).
- Caller đổi chữ ký: không (`RuntimeState` chỉ thêm field; mọi nơi dùng spread/trả về từ `inspectState`; `tsc` sạch).
- Không đụng: `benchmark/vision/accuracy/**`, oracle, README plan, prompt (không thêm gợi ý prompt vì chưa chứng minh).

## Kết luận nguyên nhân

### Đã chứng minh (code + log r6)
1. Cổng bị từ chối là fingerprint tương tác của scope `all` (control-plane mở session với `interaction_scope="all"`, `vision_agent_loop.py:369`). `fingerprint = digest(policy, url_fp, interaction_fp, form_presence_fp, scroll)` (`vision-checkpoints.ts` inspectState) và `equivalentState` thêm `privateForms`. Cả 6 lần `vision.state.mismatch` có `url_changed=false, scroll_changed=false, form_presence_changed=false, form_values_changed=false` => chỉ có thể `interaction_fingerprint` đổi (`visual_semantics_changed=true` đồng hành nhưng KHÔNG tham gia fingerprint).
2. Đây là drift thụ động trong cửa sổ nghỉ của worker, không phải race vi mô. Mỗi chu kỳ: `observe_dom` thành công (log `vision.dom.coverage_limited`) -> model nghĩ -> prepare bị từ chối. Khoảng observe-thành-công -> prepare-bị-từ-chối, tính từ timestamp log: 8.03 s, 9.10 s, 7.95 s, 6.86 s, 6.32 s, 9.56 s (ops 16, 19, 21, 24, 27, 29). Trong khoảng đó worker rảnh (`pending` null), nên mọi thay đổi là do trang tự đổi.
3. Cùng drift xuất hiện ngắn hơn: 3/6 lần `observe_dom` ngay sau refresh (đã có cửa sổ yên 800 ms của `settleState`) vẫn đổi trong lúc grounding ~1.6-2.1 s (`state_changed_during_observation`, duration 1733/1630/2111 ms). Tức trạng thái tương tác yên >= 800 ms rồi đổi rời rạc trong vài giây (không phải đổi liên tục từng frame, vì như vậy settle 800 ms không bao giờ đạt).
4. Loại trừ (b) "agent loop dùng snapshot/ref cũ sau refresh": cả 6 từ chối đều `outcome_code=state_mismatch` ở `failure_stage=prepare_start`, chạy TRƯỚC kiểm tra snapshot (`vision-operations.ts` prepare: state check ở trước `dom_snapshot_id`); 0 `stale_dom_snapshot`, 0 `stale_ref`/`invalid_ref` trong evidence. Mỗi vòng `_loop` gọi `_observe` mới rồi mới hỏi model (`vision_agent_loop.py:548`); refresh `wait` chỉ nằm trong `_observe` và vòng `for attempt` quan sát lại sau đó. Giả thuyết "ref cũ" của báo cáo r5 sai: ref luôn mới, nhưng trang tự đổi sau khi ref được cấp.
5. Loại trừ (c) race vi mô observe->dispatch: khoảng cách 6-10 s, không phải mili-giây. Đây là cửa sổ latency model.
6. Gate toàn cục áp cả action không có target (`wait` op 24, `scroll` op 29 cũng bị từ chối): đúng thiết kế (gate đứng trước mọi action), nên một vùng động trong viewport đủ chặn mọi hành động.

### Chỉ là giả thuyết (CHƯA chứng minh)
- Phần tử nào đổi, và đổi kiểu gì. Scope `all` nhạy với: identity/label/bounds làm tròn/hit-test của mọi control hiển thị trong viewport (`vision-checkpoints.ts:53-112`); một carousel tự chạy (slide link rời/vào hoặc `aria-selected`/`tabindex`/`data-state` của chấm điều hướng), ticker, hay control bị lazy-load đều đủ làm đổi. Evidence r6 không lưu DOM/diag theo thành phần (log cũ chỉ có 4 cờ boolean), và frame duy nhất của trang chủ sau TRANG CHU (`1c56623e-14-after.png`) là hero tĩnh trông giống ảnh/animation nền, KHÔNG thấy carousel hay video trong viewport đầu trang. Vì vậy "hero/news carousel hoặc video" chưa được xác nhận, thậm chí chưa có bằng chứng thấy nó ở viewport đó.
- Vì sao lần đầu vào trang chủ (1 chu kỳ observe->click, op 2) không bị mà lần quay lại (sau op 14 TRANG CHU) bị 6 lần liên tiếp: không giải thích được từ evidence (khác biệt khả dĩ: trạng thái hero/animation sau điều hướng, lazy-load, widget bên thứ ba). Không đoán.
- Không có cách offline chứng minh gì thêm: không có DOM trang, và tải mongchiton.vn bằng trình duyệt là chạm hệ thống ngoài ngoài phạm vi (AGENTS.md "Boundaries requiring user direction"; task cấm live). 

## Vì sao KHÔNG sửa cổng (quyết định)
Mọi cách nới cổng là đoán trên cái chưa cô lập và làm yếu kiểm soát an toàn:
- Bỏ geometry khỏi fingerprint scope `all`: không giúp nếu drift là slide link thay nội dung/aria (content, không phải geometry).
- Chỉ so sánh vùng quanh target ("scroll"/"wait" không có target; xác định "vùng liên quan" mà không biết phần tử nào đổi là đoán), hoặc chạy lại `revalidateDom` trong prepare: đổi ngữ nghĩa cổng an toàn + cần hiểu hệ quả với `run.fingerprint` phía control-plane; phải qua quyết định người dùng/leader và có số liệu thật.
- Tăng timeout/retry, tắt carousel: bị cấm trong yêu cầu.
- Retry action đã bị từ chối ở prepare: không thêm (không retry side effect; không đụng).
- Gợi ý prompt cho `state_mismatch`: chưa chứng minh model xử lý khác đi sẽ có ích (model không thể ngăn trang tự đổi) => không thêm, không đổi version prompt.

## Instrumentation đã thêm (kết quả hợp lệ, có test)
`vision.state.mismatch` nay có thêm (chỉ số đếm + tên tag HTML, KHÔNG nhãn/attr/path/fingerprint):
- `state_age_ms`: tuổi của trạng thái cũ khi so (phân biệt race ms với drift nghỉ 6-10 s).
- `interaction_count_before/after`.
- `interaction_content_added/removed`: control mà identity/label/state đổi (slide bị thay, nhãn đổi, aria đổi).
- `interaction_geometry_only`: control cùng nội dung nhưng bounds/hit/transparent đổi (carousel trượt/animation).
- `interaction_changed_tags`: tối đa 5 tag (ví dụ `{A: 2}`, `{BUTTON: 2}`, `{DIV: 1}`; không hợp lệ -> `OTHER`).
- `failure_stage` mới `observe_start` (nhánh `observe_dom` từ chối khi trạng thái đã đổi từ lần action trước; trước đây không có diag).
Bộ nhớ: `privateInteractions` chỉ giữ 2 sha256 + tag mỗi control (không text), không đi qua transport hay đĩa; chi phí tính digest vài trăm control mỗi `inspectState` không đáng kể.

Bước đo kế tiếp (cần user quyết, có chi phí): một live session ngắn trên mongchiton.vn với worker đã rebuild; sau khi gặp `state_mismatch` đọc `vision.state.mismatch` (`playwright-worker` log): `interaction_changed_tags`/`content` vs `geometry_only` cho biết (i) A/IMG/BUTTON nào thay, (ii) chỉ trượt hay đổi nội dung, (iii) `state_age_ms`. Từ đó mới quyết sửa đúng (ví dụ bỏ nội dung/geometry của một lớp control cụ thể khỏi fingerprint, hay revalidate theo target). Nếu cần tách hơn nữa (control nào, vị trí), thêm diag có test ở phase sau.

## Test: red -> green
Red (đã chạy thật): tạm bỏ `state_age_ms`+`interactionDiff` khỏi `logStateMismatch` rồi chạy `vision-agent-mode.spec.ts vision-observability.spec.ts -g "state mismatch|state_mismatch|autoplay"` -> `5 failed, 4 passed`: fail đúng lý do là thiếu trường diag (`Expected - 6/3/3/3/9` dòng `interaction_*`/`failure_stage`); 3 test âm URL/scroll/form pass cả trước lẫn sau (khoá hành vi cũ, không phải thay đổi). Đã khôi phục.
Green (sau khôi phục):
```
Running 9 tests using 2 workers
  ok state mismatch logs changed components without form values or fingerprints
  ok state mismatch tells a moved control from a swapped one with counts and tags only
  ok an autoplay slide change during the model idle window rejects before dispatch and the refresh recovers (7.2s)
  ok still state_mismatch before any click when the target itself is relabelled
  ok ... when a control in the target region is replaced
  ok ... when a modal appears
  ok ... when the URL changes
  ok ... when the page scrolls
  ok ... when a form value changes
```
Test tái hiện cơ chế: autoplay slide đổi trong cửa sổ nghỉ => prepare `rejected state_mismatch`, `executed_click=null`, `#out` không đổi, diag `{prepare_start, content_added 1, removed 1, geometry_only 0, tags {A:2}}`; sau đó `observe` bị từ chối (`observe_start`), refresh `wait` resync, click mới `completed` (đúng cách loop control-plane hồi phục).
Test âm (phải còn bị từ chối `state_mismatch`, không click, không POST): target bị đổi nhãn; control vùng target bị đổi href; modal `role=dialog` xuất hiện; URL đổi (`url_changed`); scroll (`scroll_changed`); giá trị form đổi (`form_values_changed`).
Không đổi: timeout/calls/states/caps, không retry side effect (không đụng code dispatch), không tắt carousel/autoplay, không đụng oracle/harness.

## Kiểm chứng (output thật)
- `node node_modules/typescript/bin/tsc --noEmit` (workers/playwright): exit 0, không output. (`npm.cmd` từ Git Bash lỗi `'C:\Program' is not recognized` do khoảng trắng đường dẫn Node; chạy trực tiếp `node node_modules/...`.)
- eslint: không chạy được; `workers/playwright` không có `eslint` trong devDependencies (script `lint` hỏng sẵn, không do thay đổi này).
- Toàn bộ worker suite (`playwright test`, 6.5 min): `1 failed, 62 skipped, 293 passed`. Fail duy nhất `vision-outcome-capture.spec.ts:10 local click outcome capture preserves passive behavior` (`expected '4' got '5'`), timing-flaky dưới tải song song (test đếm tick carousel theo thời gian thực); chạy riêng 2 lần: `9 passed` cả hai. Không liên quan thay đổi (test không dùng diag). QA-W08 không fail lần này.
- `uv run ruff check .`: `All checks passed!`
- `uv run pytest tests/test_vision_agent_loop.py tests/test_vision_agent_loop_qa.py -q`: `141 passed, 51 skipped, 1 warning in 106.94s` (Python không sửa; chạy theo yêu cầu).

## Ladder cho file/helper mới
- Không tạo file mới. `interactionDiff` + `unmatched` (2 hàm, ~20 dòng) nằm trong `vision-checkpoints.ts` cạnh `logStateMismatch` là nơi duy nhất dùng; không tách module, không abstraction thêm.
- Lựa chọn ladder cho cách giữ diff: digest theo control (không giữ text, so multiset) thay vì lưu toàn bộ interactions (rò text trang vào RAM lâu) hay chỉ log cờ boolean (đã không đủ cô lập ở r6).

## Rủi ro còn lại
- Vấn đề gốc chưa được giải: lần live tới trên trang chủ có thể lại gặp `state_mismatch` và cạn 20 call. Chỉ khác là log sẽ nói phần nào đổi.
- `vision.state.mismatch` thêm 1 điểm log (`observe_start`) nên khối lượng log error tăng (1 dòng mỗi lần `observe_dom` bị từ chối); vẫn không lộ text.
- `RuntimeState` có thêm 2 field: `exploration-strategy-benchmark.ts` và các spec chỉ đọc field cũ, `tsc` sạch; checkpoint giữ thêm digest nhỏ.
- `hgraph check --changed` exit 1 là hiện tượng sẵn có (xem GRAPH_UPDATE), không do thay đổi này.

## Ghi chú handoff cho coordinator (dán vào README, <=10 dòng)
- r6b (hướng B): sửa duy nhất worker playwright (`vision-checkpoints.ts`, `vision-operations.ts` 1 chỗ) thêm diag `vision.state.mismatch` (`state_age_ms`, `interaction_content_added/removed`, `interaction_geometry_only`, `interaction_changed_tags`, `failure_stage=observe_start`); cổng fingerprint, timeout, caps, prompt, control-plane KHÔNG đổi.
- Chứng minh: 6/6 từ chối là `interaction_fingerprint` của scope `all` đổi (url/scroll/form không đổi) trong cửa sổ nghỉ 6-10 s giữa observe và prepare; không phải ref cũ (0 `stale_*`), không phải race ms. Chưa cô lập: phần tử nào đổi (carousel/video chưa xác nhận; frame hero sau TRANG CHU trông tĩnh).
- Cần rebuild trước live session: CHỈ `playwright-worker` (`docker compose build playwright-worker` rồi up lại; kiểm `agent_loop_round.py check` 0 mismatch). KHÔNG cần rebuild control-plane/temporal-worker/claude-bridge (không sửa Python/prompt).
- Test: worker suite 293 pass / 1 fail timing-flaky `vision-outcome-capture` (solo 2/2 pass); ruff sạch; pytest agent loop 141 pass/51 skip.
- Bước kế (cần user quyết): live session ngắn sau rebuild, đọc log `vision.state.mismatch` để quyết sửa cổng (không sửa mù); đề xuất không thêm prompt hint cho `state_mismatch` cho tới khi có số liệu.

```
GRAPH_UPDATE
- graph đã cập nhật: playwright-vision-worker (thêm 1 bullet tay mô tả diag `state_mismatch`; không đổi import/file nên không cần sync/add)
- file mới đã đưa vào graph: không có (không tạo file mới)
- hgraph check --changed: exit 1 với "[uncovered-changed]" liệt kê cả file đã thuộc graph (vd vision-checkpoints.ts, vision-operations.ts, apps/control-plane/config.py) vì repo git root là thư mục cha nên đường dẫn có tiền tố `auto-at-ui/`; `hgraph which` xác nhận 4 file đã sửa thuộc playwright-vision-worker; `hgraph check` (không --changed): "✔ Không có vấn đề." exit 0.
```
