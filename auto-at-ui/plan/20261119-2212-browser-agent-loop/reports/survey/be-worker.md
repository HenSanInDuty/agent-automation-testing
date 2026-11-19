STATUS: DONE

# Survey: Playwright worker cho Browser agent loop (khảo sát, không sửa code)

CONTEXT_CHECK
- conventions: AGENTS.md (đọc). Repo không có docs/api-conventions.md / docs/code-standards.md (hgraph brief xác nhận) -> bám pattern vision-*.ts hiện có. Không đọc lại docs/vision-agent-operations.md và các ADR 024/030/033-036 (chỉ đọc code, contract.md); ADR 027 chưa đọc.
- graphs: không graph nào phủ workers/playwright/src (docs/graphs có 0 graph). Đề xuất `/h-graph` tên `playwright-vision-worker`.
- blast radius: hgraph không index workers/playwright/src (0 phụ thuộc). Blast radius thực lấy từ import: vision-operations.ts import vision-dom, vision-checkpoints, vision-locators, vision-history, vision-revalidation, vision-screen, vision-click-evidence, vision-button-semantics, vision-contract(.generated); vision-http.ts import vision-operations. vision-contract.generated.ts SINH TỪ Python (packages/contracts) -> đổi enum action/field phải đổi phía Python rồi regenerate, không sửa tay.

## Impact inventory (cho phần sẽ làm sau khảo sát)
### Database
Database: không đụng (worker giữ mọi thứ trong RAM theo session: vision-operations.ts:31-44; frame PNG ghi đĩa tạm tới ACK, :312-317, :923).

### File và contract dự kiến (chưa sửa gì)
| File | Tạo/Sửa | Lý do |
|---|---|---|
| workers/playwright/src/vision-operations.ts | sửa | latest-snapshot-only + evict, action kinds mới, origin enforce, policy mode, nới guard cho engine mới |
| workers/playwright/src/vision-dom.ts | sửa (nhỏ) | thêm ordinal/ref + (tuỳ chọn) text/heading context, total count cho marker trimmed |
| workers/playwright/src/vision-http.ts | không/sửa nhỏ | nếu thêm endpoint snapshot-range (khuyến nghị: không thêm) |
| packages/contracts (Python) + vision-contract.generated.ts | sửa/regenerate | VisualWorkerAction.kind + field mới, capability mới, open field origin_policy; ngoài phạm vi worker, cần phase Python |
| workers/playwright/src/vision-agent-*.spec.ts, fixtures/agent-loop-target.ts | tạo | test mới (xem Q7) |
Caller của hàm bị đổi chữ ký: chưa đổi chữ ký nào; `observeDom`/`resolveDomTarget` được gọi tại vision-operations.ts:281, :495, :535; spec vision-dom.spec.ts. Public contract chạm: VisualWorkerAction (generated:20), VisualWorkerPrepare (:30), VisualWorkerOpen (:27, capabilities list :185), VisualWorkerObserveDom (:~28), CodexBoundObservation, mã lỗi (outcome_code).
Test hiện có phủ vùng này: xem Q7. Chưa có test cho: nhiều bước tuần tự không checkpoint, eviction snapshot, allowlist chặn, hover/press/select.

## Q1. Snapshot version + ref
- Node identity đã có: mỗi phần tử có `element_id = e_<uuid>` tạo mỗi lần quan sát (vision-dom.ts:186), kèm binding descriptor (:196) và giữ ElementHandle sống trong `anonymousTargets` (vision-dom.ts:16, :200). Version đã có: `snapshot_id` do caller đặt (VisualWorkerObserveDom.snapshot_id; vision-dom.ts:136), session lưu `domSnapshots: Map<snapshot_id, DomSnapshot>` (vision-operations.ts:42, set :289). Vậy ref `snapshotVersion:ref` = (`dom_snapshot_id`, `dom_element_id`) ở prepare (generated:30) -> đã tồn tại, chỉ thiếu ref ngắn (uuid 32 hex tốn token; nên map ordinal `e12` ở control plane hoặc thêm `ref` ordinal trong DomSnapshot).
- State fingerprint: `inspectState()` (vision-checkpoints.ts:16-146) = hash(url, interaction controls+hit-test, form presence, scroll) (:145); `equivalentState` thêm privateForms (giá trị form chỉ trong RAM, :147). Snapshot mang `state_fingerprint` (vision-dom.ts:136) và `state` (RuntimeState).
- Kiểm tra mismatch đã có sẵn, không cần mã mới: prepare :492-495 -> `unknown_dom_snapshot` / `stale_dom_snapshot` (fingerprint snapshot != expected) ; `resolveDomTarget` vision-dom.ts:249 (`stale_dom_snapshot` nếu state hiện tại không equivalent), :251 `unknown_dom_element`, :253 `stale_dom_target`; execute :656 `stale_locator` (node hit-test khác node đã ground). Tất cả bị bắt ở prepare catch :573-579 -> operation `rejected`, `after_unavailable_reason=action_not_executed`, không có hành động trình duyệt. `before_ack_mismatch` (:592) là lỗi handshake frame, KHÔNG dùng cho version.
- Thiếu: "chỉ snapshot mới nhất". Hiện mọi snapshot cũ còn trong map và ref cũ vẫn dùng được nếu state còn equivalent. Cần `session.latestSnapshotId` và reject `stale_dom_snapshot` khi `dom_snapshot_id !== latest` (thêm tại prepare ~:493, bật theo engine). Cũng PHẢI evict + dispose handle cũ: map không bao giờ bị xoá trước expire (:108) và bị chặn bởi `dom_snapshot_limit` (:279, `size < max_states`, schema max_states <= 200) -> loop dài sẽ chết ở snapshot thứ max_states và rò ElementHandle.
- Native ladder (Playwright 1.50.1 thật): `locator.ariaSnapshot()` chỉ trả YAML string, option duy nhất `timeout` (node_modules/playwright-core/types/types.d.ts:12471); không có ref, không có `_snapshotForAI` trong lib (grep rỗng). `page.accessibility.snapshot` (types.d.ts:5143, đã deprecated) không gắn được handle sống, không lọc sensitive. Kết luận: native KHÔNG đủ làm ref (không bind node để click an toàn) -> giữ observeDom làm nguồn ref. Dùng được ariaSnapshot như văn bản ngữ cảnh phụ (heading/landmark/static text mà observeDom không có: observeDom chỉ liệt kê control, vision-dom.ts:74) nhưng phải qua cùng regex redaction (vision-dom.ts:126) vì ariaSnapshot không lọc email/số dài/token; hành vi iframe/shadow chưa kiểm chứng. Đề xuất: pha 1 không dùng; nếu goal cần đọc nội dung, thêm trường `text`/heading bị cap từ page.evaluate trong observeDom thay vì ariaSnapshot.
- Hạn chế quan trọng của observeDom cho agent tổng quát: chỉ phần tử TRONG viewport (vision-dom.ts:62-64), tối đa 5000 node duyệt (:59), depth 8 (:54), role phải thuộc selector (:74), bỏ password/hidden (:87), disabled (:88), tên >120 ký tự (:97), identity nhạy cảm (:95). `nextScrollDelta` chỉ có ở scope visual_buttons (:36). Agent cần tool scroll + snapshot lại.
- Ref map RAM: `session.domSnapshots` (:42) + `snapshot.anonymousTargets` (vision-dom.ts:16) + `bindings` (data.bindings). Tái dùng; không tạo map mới.

## Q2. Trimming
- Caps hiện có: schema `max_elements` <= 100, `max_bytes` <= 65536 (generated ~1331, ~1338); vision-dom.ts:59 (`candidates.length >= limit` -> truncated), :191-194 (vượt max_bytes -> `truncated=true; break collection`), :218 `dom_byte_limit`, `skipped_count`/`unsupported` (:137, :183). Thứ tự = document order, tail bị cắt; không biết tổng số ứng viên và không có marker.
- Đề xuất marker: KHÔNG thêm endpoint snapshot(startRef,endRef). Lý do (ladder): elements đã nằm trong `snapshot.data` (RAM worker và trace control plane); render có cap + marker `[refs e41-e100 trimmed]` là việc của lớp prompt/application Python; "lấy range" = đọc lại snapshot đã lưu, không cần gọi worker. Worker chỉ cần (a) nâng/bỏ trần `max_elements` 100 và `max_bytes` 64KiB cho engine mới nếu cần (đổi schema Python), (b) trả `trimmed_count`/`total_candidates` (có sẵn `found.candidates` chưa cap grounding; hiện cap ở :59 trong page.evaluate nên phải đếm tiếp sau limit, chi phí rẻ vì chưa ground).
- Chi phí grounding là điểm nghẽn thật: 8 song song (:168), mỗi ứng viên 1-2 lần groundLocator + 2-3 evaluate. Chưa đo; cần benchmark trước khi nâng cap lên >100.

## Q3. Tool theo paper vs action kinds hiện có
Enum `VisualWorkerAction.kind` = click|type|scroll|wait|navigate|back|close_popup (generated:20); field: x,y,text,delta_y,duration_ms.
| Tool paper | Hiện có | Chi phí thêm |
|---|---|---|
| click | có, execute :684-734 (chỉ qua dom_snapshot_id ở scope buttons/visual_buttons bắt buộc :501) | S: scope `all` đã cho click mọi control; kiểm tra :557-564 chỉ áp scope hẹp |
| type | có :735-738 (append, không clear, không Enter); bị chặn ở scope hẹp (:558) | S: thêm `clear`/fill; Enter = press_key |
| scroll | có :739 `mouse.wheel(0, delta_y)`, không có vị trí chuột/ngang | S |
| wait_for | chỉ `wait` duration (:740, `duration_ms < deadline`) | M: thêm `wait_text`/`wait_gone` (field text đã có) với timeout bị chặn bởi step deadline; hoặc chỉ dùng wait + snapshot lại |
| navigate | chỉ tới `target_url` hoặc URL checkpoint (:673), purpose chỉ setup/replay/restore (:523-527) | M: URL tuỳ ý từ model phải qua allowlist trước goto; thêm purpose hoặc nới :523 cho engine mới |
| navigate_back | có :676-679 (`page.goBack`) nhưng bắt buộc purpose=restore (:528) | S: nới purpose |
| hover | THIẾU | S: dùng grounded locator như click, `target.hover()`; thêm vào `["click","type"]` ở :531 |
| press_key | THIẾU | M: allowlist phím (Escape/Tab/Arrow/Enter?); Enter trong form = submit -> phải qua form protection |
| select_option | THIẾU | S-M: `locator.selectOption` theo label/value; state tracking đã có selectedIndex (checkpoints.ts:123) |
| screenshot / snapshot | before/after frame tự động mỗi op (:530, :826); GET /screen preview (vision-http.ts:90, operations.ts:295); snapshot = POST observations/dom | S: không cần tool mới ở worker |
Mỗi kind mới cần: enum + field ở Python contract (regenerate TS), xử lý trong prepare (:531 vùng ground) và execute (:669-740), settle/fingerprint không đổi, log `action_kind` (vision-http.ts:130). `operation.action_kind` cũng là enum (VisualOperation) -> đồng bộ Python.

## Q4. Bulk actions
- Khuyến nghị: GIỮ per-op (prepare -> persist before frame -> execute -> ack), điều phối batch ở control plane. Lý do: benchmark cần frame before/after + locator evidence mỗi op (:530, :826, :546-552); lock tuần tự `serialized` (:72) và `session.pending` (:449) chỉ cho một op; batch endpoint chỉ tiết kiệm vài HTTP round trip, không tiết kiệm settle/screenshot (settle 160ms, 800ms khi điều hướng, tới 10s: :785-786). Không thêm endpoint.
- Dừng batch khi trang đổi: worker ĐÃ tự an toàn: sau mỗi op `session.state` cập nhật (:798, :833); op kế dùng snapshot cũ thì prepare đòi `expected_state_fingerprint == session.state.fingerprint` (:488) và `snapshot.state_fingerprint == expected` (:494) -> reject, không action. Control plane nên dừng chủ động bằng dấu hiệu có sẵn trong OperationResult: `state_fingerprint` khác expected (fingerprint chỉ gồm url/control/form-presence/scroll, :145 -> ít nhiễu), `operation.url_change` (:800, :837), `outcome_code=download_started` (:762, :795), popup (afterPage != page, :768, :782), `status != completed`. `semantic_change` (:799) nhạy với mọi thay đổi hiển thị (đồng hồ, carousel) nên không dùng làm điều kiện dừng chính; `visual_change` (:830) tương tự. ADR 027 chưa đọc; tương đương trong code là `sampleClickOutcome` (:318) chỉ làm bằng chứng, không quyết định.
- VẤN ĐỀ lớn cho bulk: gõ vào ô form làm đổi `privateForms` (checkpoints.ts:123, :147) nên `equivalentState(snapshot.state, current)` (vision-dom.ts:249) fail -> batch "type A; type B" thất bại ở op thứ 2 dù trang không đổi. Cần cơ chế re-baseline cho engine mới: sau action thuộc batch mà URL + interaction fingerprint không đổi (chỉ privateForms đổi do chính action), cập nhật `snapshot.state`/`session.state` (hiện :798 chỉ cập nhật session.state, snapshot.state giữ cũ). Chi phí M, rủi ro vừa; phải gắn cờ theo engine để v4 không đổi. Click liên tiếp trên trang tĩnh (không đổi form) chạy được ngay.

## Q5. Safety bằng code: đã có / chỗ thêm
Đã có:
- Bỏ control nhạy cảm: password/hidden vision-dom.ts:87; disabled :88; identity/name khớp regex secret/email/số>=7/URL/[redacted] hoặc ký tự điều khiển :94-95, regex :126; tên quá dài :97; locator value kiểm `safeLocatorValue` :139 (vision-contract.ts:~28). Giá trị form chỉ ở RAM: checkpoints.ts:11, :123, :137-145.
- Download: context `acceptDownloads:false` + `serviceWorkers:"block"` vision-operations.ts:127; `page.on("download")` cancel :159-163; `policyFailure="download_unsupported"` nếu không do click đang chạy :160, owner :628-637; outcome `download_started` :762, :795; đóng tab rỗng :760, :792.
- Dialog: dismiss + `dialog_unsupported` :158. Popup: `unattributed_popup` :168, `multiple_popups_unsupported` :766, `popup_open_timeout` :765, close_popup chỉ restore :528, :680-683.
- `out_of_scope_target` :557-564, :657-659 (chỉ scope buttons/visual_buttons).
- Form protection: gần như không có chặn; chỉ `navigable` loại trang có input (:849-850), `replayable` chỉ anchor thuần (:565-566), form submit nằm trong `targetActionSignature` (revalidation.ts:5-13) để so sánh. KHÔNG có denylist keyword hành động nhạy cảm (delete/pay/submit) và không chặn `button[type=submit]`/`form.submit`. Cần thêm trong prepare ngay sau ground (cạnh :557), kiểm `el.form`, `type=submit`, `a[download]`, role/name theo keyword. Chi phí S-M.
- Chính sách sai: `policyFailure` DÍNH vĩnh viễn (:473, :277, :641, :861, :778): một dialog/download không rõ chủ hoặc outcome unknown khoá cả session. Với agent goal-driven cần chế độ "ghi nhận + báo model" cho lỗi có thể hồi phục (dialog, download) nhưng vẫn khoá với `unknown`. Quyết định nghiệp vụ, gắn cờ theo engine.
Domain allowlist (chưa enforce): `VisualWorkerOpen.allowed_origins` (generated:27) được nhận nhưng `open()` chỉ kiểm target_url với `["*"]` (:118); `observeOrigin` (:190-198) chỉ GHI origin ngoài (cap 100) và `route.continue()` luôn (:149); WebSocket cũng chỉ ghi rồi `connectToServer()` (:151-155). Helper `allowedOrigin(url, origins)` đã có (vision-contract.ts:178-184). Chỗ thêm: chính `context.route("**/*")` (:138) — áp cho mọi page/popup/iframe của context, không cần `page.route`: nếu enforce và `!allowedOrigin(request.url(), allowed_origins)` thì ghi nhận + `route.abort("blockedbyclient")` (navigation top-level/popup chắc chắn chặn; sub-resource CDN: cần quyết định cho phép/chặn); WebSocket `socket.close()` thay `connectToServer()` (:154); `navigate` tuỳ ý validate bằng allowedOrigin trước `goto` (:673). Bật theo field mới (vd. `origin_policy: observe|enforce`, mặc định observe để v4 không đổi). Chưa kiểm chứng: route handler có được gọi lại cho từng hop redirect trên Chromium 133 (cần test).
- Trong prepare cũng nên chặn click vào `<a href>` tới origin ngoài allowlist trước khi dispatch (có `href` trong `targetActionSignature`) để lỗi sớm không cần abort mạng.

## Q6. Guard cản kiểu "đi tiếp tuần tự" và cách nới (không đụng v4)
Chạy tuần tự click -> observe -> click từ trang hiện tại KHÔNG cần restore/replay: `session.state` luôn bám trang hiện tại (:798, :833), `observeDom` chỉ đòi state hiện tại == session.state (:280), checkpoint_id/restore/history đều nullable (generated:30) nên validateHistory (:511) không chạy. Các guard cản:
1. `state_limit` (`exploredStates < max_states`, :505, tăng ở :665) và `hop_limit` (`ancestry.length <= max_hops`, :504; ancestry tăng mỗi op explore :803) -> loop dài vướng; schema max_states <= 200, max_hops <= 20 (generated 1219-1226). Nới: engine mới dùng purpose/cờ không đếm hop (vd. không push ancestry, hop_limit bỏ), state_limit thay bằng step budget của agent; cần mở trần schema hoặc purpose mới.
2. `operation_budget_exhausted` (:449, = 1 + max_states*(2*max_hops+3)) -> OK nếu max_states lớn.
3. `dom_snapshot_limit` (:279) -> phải evict (Q1).
4. `navigate`/`back` bị khoá purpose (:523-528) -> thêm purpose cho agent (Python enum) hoặc nới.
5. `policyFailure` dính (Q5).
6. Chuyển tiếp form: `privateForms` (Q4).
7. `live_node_binding_required` (:501) chỉ cho dom_path buttons; scope `all` dùng descriptor role/label/test_id/css (locators) vẫn qua groundLocator.
8. Mỗi op: before capture (:530) + settle after (:786) + after capture (:826): ~vài giây/op; step_timeout bắt buộc `step_deadline` mỗi prepare (:465-472).
Không nới trong code dùng chung cho v4: mọi nới phải đặt sau cờ engine (field mới trong VisualWorkerOpen) để các test v4 (Q7) giữ nguyên.

## Q7. Test và fixture
- `npm test` = `playwright test` (package.json), KHÔNG có playwright.config; chạy `npm.cmd test -- src/vision.spec.ts src/vision-locators.spec.ts src/vision-operations.spec.ts --workers=1` (README.md:64-65), cộng `npm run typecheck`, `npm run lint`. Spec: contract, dashboard-auth, generation-provider-settings, observability, vision, vision-click-evidence, vision-dashboard (932 dòng), vision-dom (359), vision-history, vision-locators, vision-observability, vision-operations (1290 dòng, 61 test), vision-outcome-capture, vision-readiness, vision-sample-guard, vision-settle-observability, vision-target-preflight, vision-visual-buttons. Chưa chạy thật trong khảo sát này (không sửa code).
- Hồi quy bắt buộc cho thay đổi worker: vision-operations, vision-dom, vision-history, vision-locators, vision-target-preflight, vision-visual-buttons, vision-readiness, vision-outcome-capture, vision-dashboard, contract.
- Nơi đặt spec mới: `workers/playwright/src/vision-agent-*.spec.ts`, cùng khuôn beforeEach/command()/executeCommand()/run() của vision-operations.spec.ts:20-50.
- Fixture: `src/fixtures/vision-target.ts` (server loopback http, startVisionTarget; dùng bởi operations spec; dùng chung nên không nhồi route agent vào) và `fixtures/visual-buttons-dataset.ts` (trang tổng hợp kiểu mongchiton, route `/visual-buttons-dataset`, dùng cho test click-all-controls offline). Thêm `fixtures/agent-loop-target.ts` mới (form nhiều field, link ngoài origin, popup ngoài, download, dialog, trang đổi sau click, select/hover/key). `benchmark-target` container (benchmarks/targets/web-ui/server.mjs) chỉ là trang login/dom cho runner cũ, KHÔNG phù hợp; trang mongchiton thật là site ngoài (oracle benchmark/vision/accuracy/oracle-mongchiton-1280-v1.json), không dùng cho unit test.

## Ladder cho mọi thứ định tạo mới
| Thứ dự kiến | Đã tìm chỗ tái dùng | Vì sao chưa đủ |
|---|---|---|
| ref `version:ref` | snapshot_id + element_id (vision-dom.ts:136,186; ops:42) | thiếu latest-only/evict; ref dài (ordinal ở Python) |
| native ariaSnapshot làm ref | types.d.ts:12471 | không ref, không handle, không redaction |
| endpoint snapshot range | snapshot.data đã trong RAM/trace | không cần, render ở Python |
| endpoint batch | per-op prepare/execute/ack | cần frame mỗi op; không tiết kiệm settle |
| action hover/press/select/wait_text | nhánh click/type grounding (ops:531-567) | enum/field chưa có |
| allowlist | context.route (:138), allowedOrigin (contract.ts:178), allowed_origins (generated:27) | mới chỉ observe; thiếu enforce |
| denylist hành động nhạy cảm | regex sensitive (dom.ts:126), out_of_scope_target (:557) | không phủ submit/keyword |
| re-baseline form | session.state cập nhật (:798) | snapshot.state không cập nhật (vision-dom.ts:249) |
| dependency mới | không cần | n/a |

## Rủi ro / câu hỏi mở
- Cần quyết định nghiệp vụ: policyFailure có hồi phục được không cho agent (dialog/download); chặn hay cho sub-resource ngoài allowlist; Enter/press_key có được submit form.
- Cần đo: chi phí grounding khi nâng cap >100 phần tử; route handler trên redirect.
- Contract Python phải đổi trước (action kinds, capability, origin_policy, trần max_states/max_hops/max_elements) -> phụ thuộc phase Python.

GRAPH_UPDATE
- graph đã cập nhật: không cần — khảo sát, không thêm/xoá file
- file mới đã đưa vào graph: không
- hgraph check --changed: không chạy (không có thay đổi code); `hgraph brief workers/playwright/src` -> 0 graph, thư mục chưa index. Đề xuất `/h-graph` slug `playwright-vision-worker`.
