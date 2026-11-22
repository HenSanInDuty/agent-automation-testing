# Qualification sprint 2026-11-22: không đạt (0/5)

Loạt 5 lượt liên tiếp được khai báo trước (`qualification-sprint-20261122-declaration.json`) cho candidate
của live 2: source `53c575f6…`, config `e3039b74…`, oracle v2 `2795c44f…`, engine v4, `claude_cli / claude-opus-5-5`,
caps r21, 3 image digest cố định. Người dùng duyệt một lần cho cả loạt. Không bỏ lượt nào.
Số liệu máy đọc: `qualification-sprint-20261122.json`. Ảnh ghép: https://claude.ai/artifact/PrBkAREq2f93MNM9pfh725

## Kết quả

`metrics.qualify_batch`: **passed = false**. 0/5 lượt đạt mọi gate (cần ≥4). Cùng candidate: có. Mọi lượt đều
terminal và eligible. Safety: 0 unsafe, 0 unsettled ở cả 5 lượt. Interaction attempts: 163 (≥100).
`metrics.qualify` (3 lượt liên tiếp, chỉ để tham chiếu): không đạt.

| Lượt | Session | Kết thúc | Ops | Jobs | Tokens in/out | C | A | P | R | Inventory | Đạt |
| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- |
| Q1 (live 3) | `9ea507ff` | coverage_incomplete | 176 | 19 | 142 550 / 8 388 | 44/47 | 44/47 | 47/47 | 47/47 | thiếu | không |
| Q2 (live 4) | `1eecc684` | coverage_incomplete | 169 | 18 | 136 408 / 8 680 | 46/47 | 46/47 | 47/47 | 47/47 | thiếu | không |
| Q3 (live 5) | `abaeab9c` | coverage_incomplete | 148 | 16 | 120 794 / 7 464 | 45/47 | 45/47 | 47/47 | 47/47 | thiếu | không |
| Q4 (live 6) | `bbea4d22` | bridge_io_error | 66 | 4 | 24 227 / 2 869 | 20/47 | 20/22 | 47/47 | 47/47 | đủ | không |
| Q5 (live 7) | `712f4d9d` | initial_capture_failed | 1 | 0 | 0 / 0 | 0/47 | 0/0 | 0/0 | 0/47 | thiếu | không |

Chi phí tiền: không có dữ liệu (`cost_status: not_reported`).

## Vì sao trượt (theo mức ảnh hưởng)

1. **Inventory không đầy đủ (Q1, Q2, Q3).** Mỗi lượt có đúng một lần quét `visual_buttons` bỏ qua 1 control
   (`unsupported_target` hoặc `unbound_target`, 17 control quan sát được), nên `skipped_count > 0` và
   `inventory_complete = false`. Riêng gate này đã đủ làm Q2 và Q3 trượt: A của chúng là 97,9% và 95,7%.
   Live 1 cũng gặp lỗi này, live 2 thì không, nên lượt thử đạt một phần nhờ may. Log worker không ghi danh tính
   control (theo thiết kế), vì vậy chưa biết đó là control nào.
2. **Hạ tầng hỏng ở Q4 và Q5.** Q4: temporal-worker đọc `events.jsonl` trong spool dùng chung và gặp `ENODATA`
   (errno 61) đúng lúc bridge vừa ghi xong đề xuất, dẫn tới `bridge_io_error` sau 4 model jobs. Q5: worker không
   chụp được ảnh đầu tiên (CDP session/screenshot timeout), nên `initial_capture_failed`. Các lỗi chụp ảnh đã bắt
   đầu từ cuối Q4 (07:24:00). Preflight đạt 9/9 ngay trước Q5 và cả sau loạt, nên smoke gate (mở/đóng session,
   không chụp ảnh) không phát hiện được lỗi này.
3. **Facebook trả trang login.** Các click đúng mục tiêu dẫn tới `facebook.com/login/` thay vì group đã khai
   báo: mct-05 và mct-15 ở Q1, Q3; mct-40 ở Q4. Chấm `unverified` như vòng 10 (cùng checksum ảnh). Đây là hành vi
   của bên thứ ba và thay đổi theo từng lượt (Q2 vào đúng group). Riêng lỗi này làm A tối đa còn 45/47, sát ngưỡng.
4. **Autoplay carousel chen vào giữa click và ảnh sau.** mct-58 ở Q1 (4 → 6) và Q2 (6 → 2), mct-56 ở Q4 (6 → 1).
   Chấm không credit như vòng 17 op 26.

## Phương pháp chấm

26/28/26/14 kết quả của Q1–Q4 chấm bằng luật máy (URL đích hoặc redirect đã review, chuỗi download, `#true` cho
mct-47). Các kết quả hiển thị còn lại (19–21 mỗi lượt) do Claude (phiên điều phối, `claude-opus-5-5`) review
từ ảnh ghép trước|sau. Cùng họ model với model đề xuất, khác vai trò, không thấy lập luận của nó.
Một ca biên được tính credit và đánh dấu để người dùng soát: Q3 op 29 mct-46. Ca này không đổi kết quả loạt.
Kết luận review và các mục không credit nằm trong `runs/<id>/visual-findings-20261122.json`.

## Ngân sách và điểm dừng

Đã dùng 7/8 live run (2 lượt thử + 5 lượt qualification), còn 1. Một loạt mới cần 5 lượt, nên trong sprint này không
qualification lại được. Theo điểm dừng của phase 06: dừng, báo cáo bằng số thật. Chỉ mở vòng mới khi người dùng
quyết định lại. Số thật để so sánh: r16 đạt theo oracle v1; r21 đạt theo v2 khi chấm lại; live 2 đạt trên candidate
này; loạt qualification 0/5.

## Hướng đi nếu tiếp tục (chưa làm)

- Xác định control bị skip: log thêm danh tính đã băm hoặc dùng fixture tái hiện, rồi sửa grounding trong lúc
  animation, hoặc định nghĩa rõ cách tính inventory cho control tạm thời không ground được (cần quyết định).
- Preflight thêm một bước chụp ảnh thật; spool read thử lại một lần có giới hạn khi gặp `ENODATA` (cần ADR, vì đụng
  quy tắc không retry I/O).
- Facebook: quyết định trên oracle (redirect login có được coi là đích đã review hay không). Cần version oracle mới
  kèm bằng chứng, không đổi giữa loạt.
