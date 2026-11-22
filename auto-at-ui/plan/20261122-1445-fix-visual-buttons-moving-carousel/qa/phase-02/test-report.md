# Phase 02 — test report (QA r1)

QA VERDICT: PASS
GRAPH: `hgraph check` -> `6 graph, 474 file source / ✔ Không có vấn đề.` `hgraph check --changed` -> báo uncovered-changed hai file vision-dom (lệch tiền tố đường dẫn do git root là thư mục cha; đã biết từ phase-01, `hgraph check` đầy đủ sạch).
Đã test: 22 hàng (xem test-cases.md) — pass 21 / fail 0 / 1 không tự chạy lại (N-01).

## Môi trường
Windows 11, cwd `auto-at-ui/workers/playwright`, code phase-02 chưa commit, stack docker không đụng. Site live mongchiton.vn (chỉ đọc, qua harness).

## Output thật
- `npx tsc --noEmit` -> exit 0, không output.
- `vision-dom.spec.ts` toàn file -> `48 passed (30.9s)`.
- `-g "visual button|T-loop|static visual|no copy is fully" --repeat-each=20 --workers=4` -> `200 passed (59.6s)`.
- `vision-visual-buttons.spec.ts` -> `3 passed (2.4s)`; `vision-settle-animation.spec.ts` -> `14 passed (11.6s)`.
- `vision-operations.spec.ts --workers=4` -> `99 passed (6.1m)`.
- Manifest: `1 passed, 9 deselected in 0.16s`, summary passed 1 failed 0.

## Chẩn đoán dòng visible-but-unbound
Bản sao `fixed` trong `.probe-ab` (đã `rm -rf`) log `DIAG` sau mỗi lần duyệt, vị trí/độ trọn viewport của mọi `a.video-frame`, và ab.mts log thời điểm. 3 lần chạy: `.pytest-artifacts/s4-ab-p2-qa-{1,2,3}.log`.

| Lần | AB SUMMARY |
|---|---|
| 1 | observations 40, withSkip 0, errors 0, videoVisibleButUnbound 0 |
| 2 | observations 40, withSkip 0, errors 0, videoVisibleButUnbound 0 |
| 3 | observations 40, withSkip 0, errors 0, videoVisibleButUnbound 1 |

Bắt lại được miss ở lần 3 (`s4-ab-p2-qa-3.log` dòng 127): `scan@1152 elements 17 skipped 0 videoBound false videoVisible true`.

Chuỗi DIAG của lần duyệt đó (ms):
- walk1 (t=…544785): 17 ứng viên (lần duyệt bình thường là 18, tức video không có trong walk). Bản sao video ở l=977 r=1271 và đang trượt trái.
- end (t=…545159, +374 ms): bản sao ở l=754 r=1048, trọn viewport. Trượt 223 px trong 374 ms (~0,6 px/ms), `retr 0, waits 0, lost 0, skipped 0`.
- measure-start trễ 3 ms sau observe-returned (…545197 vs …545194): harness đo gần như ngay.

Phân tích: tại walk1 bản sao video chưa trọn viewport (còn lệch phải, cần vị trí cách l>986 px, tức ≥15 ms trước lúc diag; walk duyệt cả trang nên đủ dài), các bản sao khác ở trái ngoài màn hình, nên không bản nào qua điều kiện "trọn viewport" của walk. Video không phải ứng viên, nên không có `ground`, không có `invalidated`, không `lost`, không skip. Sau đó slide dừng và bản sao trọn viewport nhưng không có gì để bind. Đây đúng là đường "duyệt giữa lúc trượt" đã ghi trong ADR và spec đặc tả, có từ code cũ.

Kết luận: (a) duyệt giữa lúc trượt (không bản sao nào nằm trọn viewport lúc duyệt). Không phải (b) do lệch đo (đo cách observe 3 ms; bản sao đã trọn viewport từ lúc kết thúc observe, nhưng walk xảy ra trước đó) và không phải (c): code phase-01/02 không có lỗi trong đường này. Mức độ chắc: suy luận từ vị trí trước/sau walk, không đo trực tiếp vị trí bên trong callback walk (cần thêm instrument trong browser callback; hết 3 lượt cho phép). Tần suất tổng: lần trước 1/40 (`s4-ab-p2.log`) + 1/120 ở đây = 2/160 (~1,3%), trước A2 ≈1/6 và đều có skip. Tần suất này đã hạ nhiều so với trước.

Xác nhận luật phase-02 hoạt động live: 6/120 lần duyệt có `lost:1`, `retr:1`, đều bind được bản sao tương đương, `skipped:0` (DIAG end lost 1, lostReasons `unsupported_target`).

## Chưa test được
- Đỏ của T-loop-lost trên code phase-01: dựa log của dev (không có bản code cũ riêng để chạy lại).
- `--workers=1 --repeat-each=20`: không chạy lại (dựa dev: 200 passed 3,6 m); workers=4 đã chạy.
- Miss đo trực tiếp bên trong callback walk (xem trên).
- Python full suite, rebuild image worker/preflight (ngoài phạm vi theo prompt).
- Khe hở khoá twin thiếu href: user đã chấp nhận (ghi ADR), không test.

## Dọn dẹp
`.probe-ab` đã xoá (xác nhận bằng ls). Không mở tiến trình nền hay docker.
