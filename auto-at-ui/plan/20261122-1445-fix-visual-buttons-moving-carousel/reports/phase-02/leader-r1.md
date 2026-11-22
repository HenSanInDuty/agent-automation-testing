STATUS: PASS

VERDICT: PASS (phase-02, delta only)
CONVENTION: docs/code-standards.md -> AGENTS.md; khop. Khong doi convention.
GRAPH: khong co file moi, khong doi import (dev: hgraph check sach; toi khong chay lai).

BLOCKING: khong co.

Kiem trong tam
- Luat cong skip: vision-dom.ts nhanh skip trong vong collection chi push `lost` khi `item.value.invalidates && motion.retraversals === 0`. `invalidates` chi dat cung cho `motion.invalidated`. Sau vong for(;;), moi `lost` ghep voi mot element da bind cung role+name+button_kind (multiset indexOf+splice); khong co twin thi skip(reason) + unsupported.add("unbound_target"). Dung luat.
- Khoa tuong duong thu gon role+name+button_kind cai dung (element dung tu cung candidate.role/name/button_kind). ADR A2.5 va Limits mo ta dung khe href, khop quyet dinh user.
- T-loop-out/jump: 0 skip, xanh.
- Khong dem trung: chi thu o luot dau; luot hai tu skip nhu thuong, luot dau bi thay boi found.skipped cua luot hai. Skip them xay ra truoc `data` va log nen skipped_count va coverage_limited thay no.
- Ly do goc vao skip_reasons/unsupported (T-loop-lost kiem skip_reasons.unsupported_target, unsupported chua unbound_target).
- Contract: chu ky observeDom/DomSnapshot khong doi; chi them field log motion_*.
- Dispose: khong handle moi; handle luot dau dispose truoc luot hai nhu phase-01.
- T-loop-lost tai hien that: dev ghi do tren code A2 (Expected 1, Received 0), xanh sau sua; test "between" ghi gioi han (0 ung vien, 0 skip), ADR noi ro.
- Manifest: hash (LF-normalised) khop: vision-dom.ts 25a85fcc..., spec 77688727....

Over-engineering (ponytail-review): khong co delete/yagni/stdlib/native, khong dependency moi.
- vision-dom.ts ~L292-297: shrink (ghi chu) - khoa twin noi chuoi bang dau cach co the va cham neu name chua khoang trang dac biet; rui ro rat thap.

OPTIONAL
- Khe href: dong bang export khoa tu vision-checkpoints.ts (user da quyet hoan).

EVIDENCE (cwd workers/playwright)
- npx tsc --noEmit: exit 0, khong output.
- npx playwright test src/vision-dom.spec.ts: 48 passed (31.9s).
- Hash manifest tinh lai (LF-normalised) khop manifest.json dong 32 va 56.
- Khong chay --repeat-each, khong chay ab.mts; so lieu lap 200/200 la cua dev (chua tu kiem).
