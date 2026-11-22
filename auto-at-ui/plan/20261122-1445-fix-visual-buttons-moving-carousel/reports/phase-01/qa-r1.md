STATUS: PASS

QA VERDICT: PASS (rủi ro còn lại: miss im lặng hiếm, xem dưới)
GRAPH: `hgraph check` sạch (6 graph, 474 file); `hgraph check --changed` báo uncovered-changed hai file vision-dom (lệch tiền tố, đã biết).
Đã test: 20 case — pass 19 / fail 0 / 1 không kết luận (A2-12, rủi ro).

Chi tiết đầy đủ và output thật: `qa/phase-01/test-report.md`, `qa/phase-01/test-cases.md`.

Kết quả chính:
- tsc exit 0; vision-dom.spec 46/46; chuyển động + T-loop 160/160 (--repeat-each=20 --workers=4); visual-buttons 3/3; settle-animation 14/14; operations 99/99; manifest 1 passed.
- Harness live lần 2: `AB SUMMARY {"observations":40,"withSkip":0,"errors":0,"videoVisibleButUnbound":0}` (lần 1: 0 skip, 1 visible-but-unbound).
- Dòng visible-but-unbound: không kết luận được nguyên nhân. Đo trễ là có (6/40 lần carousel trượt trong lúc observe, vẫn bind). Miss thật chỉ xảy ra nếu walk không thấy bản nào trọn viewport lúc trượt (có ở cả code cũ), hoặc nếu duyệt lại gán `skipped = found.skipped` (vision-dom.ts:293) xoá dấu skip của walk 1. Trước A2 mọi miss đều có skip; A2 giảm miss 1/30 -> 1/80 nhưng miss còn lại không có tín hiệu. Không phải lỗi đã chứng minh nên không FAIL; đề xuất giữ skip walk 1 hoặc báo coverage_limited khi walk 2 ít ứng viên hơn.

Chưa test được: đỏ của T-loop trên code A (dựa bằng chứng dev), --workers=1 lặp (dựa dev), assertion rò handle, full Python suite.
