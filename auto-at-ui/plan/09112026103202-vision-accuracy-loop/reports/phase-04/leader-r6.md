STATUS: FAIL

VERDICT: FAIL (1 BLOCKING)
CONVENTION: AGENTS.md, docs/code-standards.md, ADR-042 - khop. Khong co CONVENTION_CHANGE.
GRAPH: hgraph check: "Khong co van de" exit 0 - khong co file source moi.

BLOCKING
- workers/playwright/src/vision-dom.ts:33 va vision-operations.ts:552 (cung :543 cho refresh) - con so sanh fingerprint luu tru TRUC TIEP, khong qua equivalentState, trai khang dinh "moi diem so sanh deu di qua equivalentState" (be-developer-r14, ADR-042 Context).
  `requireVision(before.fingerprint === request.expected_state_fingerprint, "state_mismatch")` (dom:33) va `runtime.before.fingerprint === request.expected_state_fingerprint && equivalentState(...)` (ops:552). Fingerprint nay bam interaction_fingerprint gom bounds lam tron, hit, transparent. Trang co pulse: settle nay pass va tra state X; buoc observe/prepare ke tiep inspect lai, bounds khac pha -> fingerprint khac X -> `state_mismatch` ngay truoc dispatch. Settle duoc sua nhung chuoi observe -> prepare van hong dung tren trang r12 (home), tuc muc tieu "state_mismatch geometry-only khong con" khong dat. Spec 14 test chi goi settleState/equivalentState, khong chay luong observe/prepare voi pulse nen khong bat duoc.
  Huong sua (khong doi contract): dom:33 va ops:552 so voi state worker dang giu (session.state / state da tra) bang equivalentState, va xac nhan `held.fingerprint === expected_state_fingerprint` (hash la dinh danh cua state worker da phat). Them 1 test observe/prepare tren fixture pulse. Cap nhat ADR/ghi chu: hash exact-gate con lai o ops:949 (re-baseline, bao thu, chap nhan duoc).

OPTIONAL
- vision-checkpoints.ts (settle): state tra ve la mau cuoi, trong 3 px so voi reference; cong voi dung sai luc dispatch co the dich toi da ~6 px so voi luc model thay. Ghi vao ADR Limits.
- Control animated + transparent (opacity animation cham 0) duoc mien transparent; click van bi hit test/exact-node chan o dispatch -> chap nhan.
- over-engineering: khong co delete/yagni/stdlib/native; khong them dependency. shrink: privateInteractions mang 4 truong meta cho moi entry; chap nhan duoc.

KIEM TRONG TAM
1. Pham vi dung sai: dung. content digest (path, identity, label, role, disabled, pointer-events) phai giong het theo vi tri; so luong entry bang; hoan vi control ke nhau/list reorder khac path hoac content -> khac. Doi >3 px hoac IoU<0.8 -> khac. Hit tam luon phai khop; hit goc/transparent chi duoc mien khi CA HAI animated. Control moi che: hit tam hoac goc (khong animated) doi -> khac. Overlay che mot phan khong cham 5 diem la han che co san tu truoc. settleState so voi reference (mau mo cua so) dung; reference reset khi context bi thay; khong the bao settled khi chua tung yen vi stableSince reset moi khi changed.
2. B: chi CSSAnimation ("animationName" in animation), iterations Infinity, keyframe chi transform(khong translate/matrix/perspective)/scale/rotate/opacity; moi infinite animation khac (marquee translate, left/width, Element.animate) vao blocked; moi transform la tren chuoi to tien tat B; shadow/iframe loai. Swiper/marquee translate khong lot. Hop layout (offset chain, tru scroll, bail fixed/sticky, cat viewport) hop ly.
3. Nhat quan: xem BLOCKING. Cac cho khac (dom:237/275/288, history, ops:270/287/300/323/330/391/420/446/647/721/927/979, revalidation) dung equivalentState hoac so truong chinh xac url/scroll/forms (giu chat). Fingerprint/hash/policy/metadata khong doi -> checkpoint da persist va control-plane khong vo (grep control-plane khong so sanh hash o worker).
4. Chay that: xem EVIDENCE.
6. ADR-042: co quyet dinh, hang so (3 px, 0.8), gioi han, rui ro, rollback, test; thieu: neu ro cac exact-hash gate con lai (BLOCKING tren) va dich tich luy ~6 px.

EVIDENCE
- `npx tsc --noEmit` -> exit 0, khong output
- `npx eslint` 3 file dung -> exit 0
- `npx playwright test src/vision-settle-animation.spec.ts --workers=1` -> `14 passed (12.3s)`
- `hgraph check` -> "6 graph, 463 file source. Khong co van de." exit 0
- Khong chay lai hoi quy dai cua dev (operations 99 test ...).
