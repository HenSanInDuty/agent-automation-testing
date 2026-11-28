# Test cases: ADR-048 `agent-frozen-clock-v1` (OFFLINE)

Ghi chú: "DEV" = test của developer (`workers/playwright/src/vision-agent-mode.spec.ts`, `tests/*.py`); "QA" = test QA thêm vào `workers/playwright/src/vision-agent-mode.qa.spec.ts`. Kết quả = lần chạy toàn bộ ngày 2026-11-26 (xem test-report.md). Cột loại: A = tự động, M = thủ công/live.

| ID | Mục tiêu | Bước / dữ liệu | Kỳ vọng | Loại | Nằm ở | Kết quả |
|---|---|---|---|---|---|---|
| T01 | Tái hiện bug (không capability) | agent, /carousel, timer 1000 ms, observe, nghỉ 1,5 s, prepare | `state_mismatch` ở `prepare_start`, `interaction_changed`, không click | A | DEV `without the capability a page timer moves the state...` | PASS |
| T02 | Có capability qua nhiều chu kỳ | /carousel timer 300 ms; 2 vòng observe, nghỉ 2,5 s, prepare, nghỉ 1 s, execute | `completed/observed`, không `vision.state.mismatch` | A | DEV `with the capability the state survives...` | PASS |
| T03 | Chuỗi dài >= 10 vòng | /qa-clock timer 400 ms, 12 vòng observe, nghỉ 1,3 s, click/type; `Date.now()` trang trước/sau nghỉ | mọi op `completed/observed`, 0 sự kiện mismatch, `Date.now()` và slide không đổi khi nghỉ | A | QA C01 | PASS |
| T04 | `wait` cho thời gian trôi | /carousel timer 300 ms, `wait` 1000 ms, rồi refresh wait | fingerprint đổi, slide tiến, sau đó đứng yên; observe sau refresh nhận | A | DEV `wait lets the page's time pass...` | PASS |
| T05 | click/type/scroll/chụp ảnh khi đồng hồ dừng; timer sinh từ click vẫn chạy | /carousel; click "Chạm trễ" (setTimeout 50 ms), type, scroll, screen | mỗi op completed, `#late-out`="xong", trang đứng yên sau mỗi op | A | DEV `click, type, scroll and capture...` | PASS |
| T06 | Type tiếng Việt + điều hướng cùng origin + back + reload | /qa-clock; type "tiếng Việt có dấu"; click "Trang kế"; back; navigate | op completed, trang đứng yên sau mỗi bước, observe sau back nhận | A | QA C04 | PASS |
| T07 | Popup và document mới | click "Mở popup", close_popup, sang `/carousel-late` (timer bắt đầu 4 s sau tải) | popup/document mới dừng; sau 4,5 s slide vẫn "Slide 0" | A | DEV `a popup and a new document...` | PASS |
| T08 | Từ chối/lỗi giữa chừng, đồng hồ vẫn dừng | stale snapshot; page đổi giữa prepare và execute; `mouse.wheel` ném lỗi sau dispatch | rejected/unknown đúng mã, trang đứng yên, `Date.now()` không tiến | A | DEV `a rejected or failed operation...` | PASS |
| T09 | Op không settle được vẫn để trang dừng | /qa-raf (rAF vô hạn) và /qa-clock timer 100 ms | op `failed:settle_timeout` (ghi nhận), nhưng sau đó trang đứng yên | A | QA C06, C08 | PASS (đặc tả) |
| T10 | Không capability: không đồng hồ giả | agent không capability; v4 (không agent_mode) có xin capability | `Date.now()` chạy; open báo capability nhưng v4 không bị dừng | A | DEV `a session without the capability...` | PASS |
| T11 | Hai phiên song song, có/không capability | A có capability, B không; thao tác ở A rồi ở B; đóng B | A đứng yên, B chạy; op ở mỗi bên không đổi đồng hồ bên kia; A dùng tiếp được sau khi đóng B | A | QA C03 | PASS |
| T12 | close / hết hạn không treo gì | close phiên idle; hết hạn khi idle; hết hạn giữa lúc `wait` đang chạy đồng hồ | browser ngắt, observe sau close bị từ chối, wait không treo, không `unhandledRejection` | A | QA C02 | PASS |
| T13 | Thay đổi không do timer vẫn bị từ chối (có capability) | relabel/modal/URL/scroll/form/đổi tay link slide giữa observe và prepare | `rejected/state_mismatch`, không click, trang đứng yên | A | QA C05 (6 biến thể) | PASS |
| T14 | Thay đổi không do timer, không capability (hồi quy) | như T13, không capability | `state_mismatch` + chẩn đoán đúng | A | DEV `still state_mismatch before any click when ...` (6) + `an autoplay slide change...` | PASS |
| T15 | rAF đổi vị trí control | /qa-raf; không capability vs có capability | không capability: control di chuyển; có capability: đứng yên giữa các op | A | QA C06 | PASS |
| T16 | CSS animation vô hạn (marquee) - đặc tả giới hạn | /qa-marquee có capability | open navigate `failed:settle_timeout`, animation vẫn chạy khi đồng hồ dừng, observe `state_mismatch` (khớp ADR Limits) | A | QA C07 | PASS (đặc tả, không phải fail) |
| T17 | Contract + `worker_capabilities` | `frozen_clock=False` mặc định, thêm cuối tuple; planner không dùng; open_request agent loop xin capability cuối | tuple đúng; Python và TS contract khớp | A | `tests/test_vision_agent_loop.py::test_only_the_agent_loop_open_asks_for_the_frozen_clock`, `::test_open_request_carries_agent_mode...`, `tests/test_vision_worker_contracts.py`; `export_vision_worker.py --check` | PASS |
| T18 | Không đổi hành vi planner v4 / agent cũ | toàn bộ spec cũ trong blast radius | không hồi quy | A | toàn bộ `npx playwright test` + 11 file pytest | PASS (1 fail có sẵn, xem report) |
| T19 | Flaky | lặp 3 lần test mới của DEV và QA | 100% pass | A | `--repeat-each=3` | PASS |
| L01 | Live mongchiton.vn: tỷ lệ `state_mismatch`/`state_changed_during_observation` trong phiên agent_loop | phiên chính chạy N phiên với flag bật | giảm về ~0 so với 17/21 dừng | M | chờ phiên chính đo | CHỜ |
| L02 | Live: op `wait` thật và click trên trang có 3 Swiper vẫn settle (không `settle_timeout` do transition 300-600 ms) | như trên | settle OK | M | chờ phiên chính đo | CHỜ |
| L03 | Live: trang so `Date.now()` với giờ server / countdown | quan sát khi phiên chạy vài phút | không lỗi do đồng hồ lùi | M | chờ phiên chính đo | CHỜ |
| L04 | Live: phiên dài (hàng trăm op) - nhật ký clock/init script không làm chậm | đo thời gian/op đầu và cuối | không suy giảm đáng kể | M | chờ phiên chính đo | CHỜ |
| T20 | Delta vòng 2: trang có child frame (dừng ok, mọi frame đứng yên) | DEV `a page with child frames still opens...` | A | PASS |
| T21 | Delta vòng 2: ép pauseAt lỗi, op nói thật và hồi phục | DEV `when the page cannot be stopped...` | A | PASS |
| T22 | QA C09: trang tĩnh đọc chậm (480 ms/mẫu) có capability bị `settle_timeout` ở lần settle 1000 ms, không capability thì completed; 150 ms thì completed | QA C09 | A | PASS (đặc tả lỗi; FAIL-1) |
| T23 | QA C10: `pauseAt` báo "past" mà không dừng, đồng hồ vẫn chạy; worker chấp nhận (6/6) | QA C10 | A | PASS (đặc tả điểm yếu) |
| L01-L02 | Live mongchiton r6: 14/15 completed, 0 phiên dừng vì mã carousel (theo runs.jsonl); L03/L04 chưa đo | M | ĐẠT / chưa đo |
| T22' | Vòng 3: C09 đổi thành hồi quy (completed với trang đọc chậm) | QA C09 | A | PASS |
| T23' | Vòng 3: C10 đổi thành hồi quy (6 x failed:settle_timeout, falseAccepts=0, clockRunning=true) | QA C10 | A | PASS |
| L01-L02 r7 | Live r7: 15/15 completed, 0 mismatch/freeze_failed/settle_timeout trong worker.log | M | ĐẠT |
