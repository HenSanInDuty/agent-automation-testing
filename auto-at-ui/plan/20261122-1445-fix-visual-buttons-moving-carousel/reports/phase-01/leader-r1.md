STATUS: PASS

VERDICT: PASS
CONVENTION: AGENTS.md (docs/code-standards.md chi la chi muc; docs/api-conventions.md khong co) - khop. Khong dung control-plane/contract; co test kem hanh vi. Comment "ponytail:" khop pattern san co (vision-dom.ts:16).
GRAPH: hgraph check = "6 graph, 493 file source / Khong co van de." Khong co file moi. (`--changed` lech tien to duong dan la no da biet trong plan.)

## Doi chieu A2
1. Reground khi moving||displaced + kiem hop cuoi tron viewport: vision-dom.ts ~221-231 (`moved = moving || displaced`; `still && moved`; invalidated chi khi khong verified va hop ngoai viewport, cung tieu chi walk). Dung.
2. Duyet lai mot lan: `for(;;)` boc `collection`; sau vong `if (!motion.invalidated || motion.retraversals > 0) break`, roi dispose moi anonymousTargets, clear elements/bindings/signatures, retraversals++, traverse(), nap lai scrollable/unsupported/truncated/skipped/skipReasons. Lan 2 khong lap nua. `equivalentState(before, after)` + `contextSignature` chay sau vong, mot lan cho lan cuoi (~293-296). Dung.
3. `motion_retraversals` o coverage_limited va motion_regrounded. Dung.
4. Gioi han: cho chi khi `motion.retraversals === 0` => toi da mot lan cho <=1,2 s/batch + mot lan duyet lai. Chuyen dong lien tuc va node bien mat khong dat co (test "never stops" walks===1; "removed" nhanh). Dung.

## Dispose
- Moi batch: finally dispose handle khong retained (cu, giu nguyen).
- Nhanh duyet lai: dispose moi handle retained truoc khi clear; neu traverse() nem loi thi anonymousTargets da rong, `finally` ngoai (`!completed`) van dispose documentRoot. Khong ro. `break collection` do truncated roi invalidated cung dung duong.
- Closure: `skip` doc `skipped`/`skipReasons` la `let` nen thay gia tri gan lai; `base.elements` cung mang (`length = 0` giu tham chieu). `base.skipped_count/truncated/unsupported` cu chi dung de uoc byte va bi ghi de o du lieu cuoi. Khong co race that (ground song song chi doc retraversals, dat co).

## Browser callback / tsx __name
Callback evaluate van la arrow noi tuyen nhu cu, khong them ham dat ten ben trong callback; `traverse` chi la arrow phia Node boc hai lenh evaluate. Chu ky export, DomSnapshot, contract khong doi.

## Test
- T-loop-out/T-loop-jump mo phong that loop swiper: 3 slide 700 px, link giong het, lop phu hai mep, translateX 600 ms; trigger chay ngay sau khi walk tra candidates + 80 ms nen grounding roi giua luc truot duoi lop phu; "jump" reset transition none o transitionend. Walk thay dung 1 ung vien (hai ban kia ngoai viewport). Phan tich tay tren code A: out -> hop -400, khong invalidate -> skip; jump -> displaced=false -> khong ground lai -> skip. Khop bao cao dev (do voi elements rong). Toi khong dung lai A de chay, dua vao bao cao + suy luan.
- TC-03 ky vong cu the, khong "hoac": `walks === 2`, khong snapshot, loi chua `state_changed_during_observation`. Hop ly: link duy nhat mat khoi tap, sau walk 2 khong ung vien/skip, equivalentState quyet dinh reject.
- Chua co test cho nhanh "lan duyet lai van loi -> skip, khong lan 3" (cap ponytail). Optional.

## Diem mo :203 (luot walk thu hai khong cho)
Dong y giu nhu hien tai. Co chi dat khi hop da still, nen luc duyet lai trang vua dung, con ~2,9 s toi slide ke; cho them 1,2 s o luot hai chi cong thoi gian xau nhat ma khong giai quyet ca nao trong log chan doan. Chi can doi neu harness live cho thay skip con lai do luot hai.

## OVER-ENGINEERING (ponytail-review)
- Khong co delete:/yagni:/stdlib:/native: va khong co dependency moi. Khong co shrink: chan.
- vision-dom.ts:49-52: shrink: than `traverse` khong thut le (giu diff nho, doc lech). Thut 2 space khi cham file lan sau; khong doi hanh vi.
- vision-dom.spec.ts ~252 va ~345: shrink: wrapper `page.evaluate` bat walk lap o hai helper (observeSliding, observeLoopSwiper). Co the gom mot helper nho. Ghi chu, khong chan.
- vision-dom.ts:241: for(;;) thut lai ~50 dong lam diff lon; chap nhan vi tai dung logic. Goi y ngoai diff: sau nay tach `collectBatch`.

## BLOCKING
Khong co.

## OPTIONAL
- Them test "lan duyet lai van skip, khong lan 3" (fixture hai lan truot).
- No ngoai pham vi (boundingBox dau tien khong timeout, hgraph --changed) giu nguyen nhu plan.
- Cong chinh van la harness live ab.mts (0 skip/>=30 lan quet): phien chinh chay; PASS nay chi la offline.

## EVIDENCE
- `npx tsc --noEmit` (workers/playwright): exit 0, khong output.
- `npx playwright test src/vision-dom.spec.ts --workers=2`: `46 passed (27.9s)`.
- `npx eslint src/vision-dom.ts`: khong output (0 loi). (6 loi no-explicit-any o spec la test cu theo bao cao dev, ngoai diff.)
- `hgraph check`: `6 graph, 493 file source / Khong co van de.`
- Manifest: hash trong diff khop bao cao dev (dev da chay 1 passed); toi khong chay lai.
- Khong chay ab.mts, khong chay --repeat-each.
