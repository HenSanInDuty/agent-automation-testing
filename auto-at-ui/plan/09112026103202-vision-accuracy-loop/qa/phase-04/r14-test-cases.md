# Phase 04 r14 - test cases (QA r5)

Automation: `workers/playwright/src/vision-settle-animation.qa.spec.ts` (fixture cục bộ, không mạng) + hồi quy các spec có sẵn.

| ID | Nhóm | Mô tả / dữ liệu | Mong đợi | Thực tế | KQ |
|---|---|---|---|---|---|
| QA-B1 | Biên | Control tĩnh lệch tâm đúng 3 px (trục x, trục y); 4 px; -4 px | 3 px equivalent; 4 / -4 px không | đúng | PASS |
| QA-B2 | Biên | Cùng tâm, rộng 200->250 (IoU 0.8), 200->254 (IoU 0.787), co 250->200 | 0.8 equivalent; 0.787 không; co đối xứng | đúng | PASS |
| QA-D1 | Biên/drift | Control trôi 1 px / 40 ms, cửa sổ 2.5 s, quiet 800 ms | settled=false, `state_kept_changing` | đúng | PASS |
| QA-D2 | Biên/drift | Trôi 2 px rồi dừng; trôi 10 px (40 ms/bước) rồi dừng | cả hai settled (reference reset sau khi vượt 3 px), không log | đúng | PASS |
| QA-S1 | Biên | Hai button cùng label "Play" hoán đổi vị trí | không equivalent | đúng | PASS |
| QA-S2 | Biên | List reorder (đẩy item đầu xuống cuối); đổi label một twin | không equivalent | đúng | PASS |
| QA-O1 | Đường lỗi | Link mới cùng label che đúng lên control pulse | không equivalent | đúng | PASS |
| QA-O2 | Đường lỗi | Overlay fixed opacity 0 bắt pointer phủ trang | không equivalent (hit tâm) | đúng | PASS |
| QA-O3 | Đường lỗi | Pulse 1.06 và 1.5 + đổi aria-label đồng thời | không equivalent | đúng | PASS |
| QA-M1 | Biên | Marquee `transform` vô hạn trên track link | không equivalent, settle `state_kept_changing` | đúng | PASS |
| QA-M2 | Đường lỗi | Pulse nằm trong wrapper bị script translate | không được miễn: wrapper dời 40 px -> không equivalent | đúng | PASS |
| QA-A1 | Happy | Animation opacity vô hạn trên chính button | equivalent giữa hai pha; settled | đúng | PASS |
| QA-A2 | Biên | Animation pause giữa chừng (700 ms), rồi cancel | settled; state dừng equivalent state settle; sau cancel vẫn equivalent | đúng | PASS |
| QA-N1 | Hồi quy | Trang không animation | fingerprint giống hệt, settle ngay, không log; đổi giá trị form -> khác | đúng | PASS |
| QA-P0 | Nguyên nhân | `locator.click` thường trên control pulse vô hạn | bị từ chối "element is not stable"; `force` thì click được | đúng như mô tả | PASS (chứng cứ cho P1) |
| QA-P1 | Happy/e2e | prepare -> chờ 700 ms (pulse chạy tiếp) -> execute click vào tâm link pulse | operation `completed`, `data-clicked=1` | `status=unknown`, `outcome_code=action_outcome_unknown`, `executed_click=null`, `data-clicked` không có; ~4 s sau start (hết `timeout` click). Cùng trang không animation: `completed`, clicked=1 | **FAIL** (khoá bằng `test.fail`) |
| REG-1 | Hồi quy | `npx tsc --noEmit` | exit 0 | exit 0 | PASS |
| REG-2 | Hồi quy | settle (dev), settle-observability, dom, history, readiness, target-preflight, sample-guard, visual-buttons, observability | xanh | 111 passed | PASS |
| REG-3 | Hồi quy | `vision-operations.spec.ts` | xanh | 99 passed | PASS |
| REG-4 | Hồi quy | agent-mode, agent-mode.qa, agent-evidence, outcome-capture | xanh | 66 passed (flaky `outcome-capture.spec.ts:10` không xuất hiện) | PASS |
| GR-1 | Graph | `hgraph add` file QA; `hgraph check` | sạch | "Không có vấn đề." exit 0 | PASS |

Stress test: không cần - thay đổi chỉ thêm so sánh in-memory theo từng entry và một lần `document.getAnimations()` mỗi lần inspect; không đụng vòng lặp tập lớn, query, job hàng loạt hay lock.

## r2 (QA r6) - kiểm r14b (QA-P1 + leader BLOCKING)
| ID | Nhóm | Bước | Mong đợi | Thực tế | Kết quả |
|---|---|---|---|---|---|
| QA-P1 | Fix/e2e | prepare -> chờ 700 ms -> execute click link pulse (đã bỏ `test.fail`) | `completed`, `data-clicked=1` | xanh, 2 lần | PASS |
| R2-1 | Happy | observe -> chờ 450 ms -> prepare -> chờ 450 ms -> execute, 3 vòng trên pulse 1.5 | không `state_mismatch`, click đúng mỗi vòng | xanh | PASS |
| R2-2 | Biên | observe baseline, dời `.widget` 1..6 px (1 px/vòng, không execute), observe mỗi vòng | trong 3 px: snapshot mang hash held; >=4 px bị bắt và giữ bị bắt (không trôi baseline) | bắt từ 4 px, 5/6 vẫn bắt | PASS |
| R2-3 | Biên | prepare sau dời 1 px OK; dời 10 px rồi observe | 1 px `prepared`; 10 px bị từ chối | đúng | PASS |
| R2-4 | Đường lỗi | observe/prepare với fingerprint kỳ vọng sai (đúng dạng, đổi 1 ký tự) | `state_mismatch`; fingerprint đúng thì `prepared` | đúng | PASS |
| R2-5 | Đường lỗi | `isPresentationOnlyAnimated`: Element.animate scale vô hạn, Element.animate translate, CSS transition đang chạy, pulse trong wrapper translate tĩnh; ma trận có sẵn (static/marquee/left/width/carousel/bị che) | false (pulse/strong/spin = true) | đúng | PASS |
| R2-6 | Đường lỗi | marquee e2e; pulse bị che e2e | link không bị click | đúng | PASS |
| R2-7 | Ổn định | `vision-settle-animation.qa.spec.ts` + `vision-settle-animation.spec.ts` `--workers=1` x2 | xanh cả 2 lần | 34 passed (52.8s), 34 passed (51.0s) (trước khi thêm case); qa spec sau khi thêm: 24 passed x3 (~50s) | PASS |
| REG-1 | Hồi quy | `npx tsc --noEmit` | exit 0 | exit 0 (sau khi sửa 1 lỗi kiểu trong spec QA vừa thêm) | PASS |
| REG-2 | Hồi quy | agent-evidence, agent-mode(+qa), click-evidence, dom, history, outcome-capture, readiness, target-preflight, settle-observability | xanh | 145 passed (6.2m) | PASS |
| REG-3 | Hồi quy | `vision-operations.spec.ts` | xanh | 99 passed (6.3m) | PASS |
| GR-1 | Graph | `hgraph check` | sạch | "6 graph, 464 file source. Không có vấn đề." | PASS |
| OBS-1 | Observation | `.qa.spec.ts` pulse bị che: DOM mode click theo toạ độ | không FAIL | control che nhận click, op `completed`, link bên dưới không bị click xuyên; có sẵn từ trước, không do force | OBSERVATION |
