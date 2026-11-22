# Test cases - Phase 2 (Worker agent mode)

"dev" = `workers/playwright/src/vision-agent-mode.spec.ts` (23 test). "qa" = `workers/playwright/src/vision-agent-mode.qa.spec.ts` (18 test, QA viet). Tat ca chay Chromium that, `--workers=1`.

| ID | Nhom | Tien dieu kien | Buoc / du lieu | Mong doi | Thuc te | Ket qua |
|---|---|---|---|---|---|---|
| T01 | Happy (AC2) | agent_mode | observe 2 lan, prepare bang snapshot cu | map chi con snapshot moi; `stale_dom_snapshot`, khong click, DOM khong doi (dev) | dung | PASS |
| T02 | Bien | agent_mode | element id cua snapshot moi + snapshot id cu (qa W01) | `stale_dom_snapshot`, `executed_click=null` | dung | PASS |
| T03 | Bien | agent_mode | snapshot id UUID la (qa W02) | rejected, `stale_dom_snapshot` hoac `unknown_dom_snapshot`, khong click | dung | PASS |
| T04 | Bien | agent_mode, blocklist ["xoa"] | ref snapshot cu vs moi (qa W14) | cu: `stale_dom_snapshot`; moi: `sensitive_action_blocked`; session dung tiep | dung | PASS |
| T05 | Happy (AC2) | agent max_states=3,max_hops=2 | 1 setup + 20 vong observe/click explore (dev) | khong `dom_snapshot_limit`/`hop_limit`/`state_limit`; handle cu da dispose; size map = 1 | dung | PASS |
| T06 | Hoi quy v4 | v4 cung limit | lap observe/click (dev) | cham `dom_snapshot_limit`/`hop_limit`/`state_limit` | dung | PASS |
| T07 | Happy | agent | click trang ke, `back`, `navigate` purpose explore (dev) | completed, url_change changed; v4: `invalid_restore_purpose`/`invalid_navigation_purpose` | dung | PASS |
| T08 | Happy (K3) | agent | click link target=_blank sang origin ngoai (dev) | popup mo, `observed`; anh origin ngoai tai (`GET /pixel.png`, naturalWidth 1) | dung | PASS |
| T09 | Loi (K3) | dang o popup ngoai | click/type/scroll/navigate (dev) ; wait/scroll/navigate/type/click tren trang ngoai cung tab (qa W10) | `origin_blocked`, `executed_click=null` | dung | PASS |
| T10 | Happy (K3) | popup ngoai | `close_popup` (dev, qa W11); `back` tu trang ngoai cung tab (qa W10) | completed; ve origin chinh; observe + click tiep OK | dung | PASS |
| T11 | Loi (AC3) | agent, terms [xoa tai khoan, xoa, delete] | "Gui di"(submit), "Tiep tuc"(button khong type trong form), "Tai ve"(a[download]), "Xoa tai khoan", "XOA" NFD (dev) | `sensitive_action_blocked`, 0 POST/file.bin request, 0 data-clicked | dung | PASS |
| T12 | Bien | agent, terms rong | control cau truc `button[type=submit]` ngoai form `form=`, `button[type=submit][aria-label]` (qa W06) | van `sensitive_action_blocked` (khong can tu khoa); 0 POST | dung | PASS |
| T13 | Bien | agent | tu khoa khop qua aria-label ("thanh toan"), title ("huy vinh vien"); type=button trong/ngoai form khong bi chan (qa W05) | bi chan voi aria-label/title; type=button duoc phep; 0 POST, 0 click | dung | PASS |
| T14 | Bien (dau) | terms upper-case NFD "XOA TAI KHOAN"+"nap the" khong dau (qa W03/W04) | label NFC "Xoa tai khoan" / "Nap the" | co dau NFD/hoa -> chan; tu khoa khong dau KHONG chan nhan co dau (worker chi NFC+lowercase) | dung - hanh vi nay duoc ghi nhan (ghi chu 5 cua dev) | PASS (hanh vi ghi nhan) |
| T15 | Bien | agent | "NAP THE", "DANG KY" khong nam trong terms (dev) | khong bi chan, completed | dung | PASS |
| T16 | Hoi quy v4 | v4 (agent_mode omitted va false), terms co "xoa tai khoan" (dev + qa W12) | click "Xoa tai khoan", "Gui ngoai form" | khong `sensitive_action_blocked` | dung | PASS |
| T17 | Bien (AC3 Enter) | agent | `type` text `a\nb`, `a\rb`, `a\r\nb`, `\nabc`, `\n` (qa W07 x5; dev `a\nb`) | `sensitive_action_blocked`, o nhap van rong, 0 POST | dung | PASS |
| T18 | Bien | agent | type tieng Viet co dau + tab; 1000 ky tu (max); 1001 ky tu (qa W08) | 1000 nhap het, 0 POST; 1001 bi `invalid_contract` tai validate | dung | PASS |
| T19 | Happy (re-baseline) | agent | type A, type B, type C cung snapshot (dev); A, B roi click "Doi noi dung" (qa W09) | ca ba/ba op completed; gia tri A,B,C; 0 POST | dung | PASS |
| T20 | Bien | agent | sau click doi DOM, observe moi; ref snapshot cu (qa W09) | snapshot cu `stale_dom_snapshot`; snapshot moi prepared | dung | PASS |
| T21 | Hoi quy v4 | v4 | type A roi type B cung snapshot (dev) | `stale_dom_snapshot` (re-baseline chi o agent) | dung | PASS |
| T22 | Happy (K4) | agent | confirm/alert/prompt do click (dev) | `dialog_unsupported`, status failed, `policyFailure=null`, op ke completed | dung | PASS |
| T23 | Happy (K4) | agent | 2 dialog lien tiep, op thuong o giua (qa W13) | op giua `completed/observed` (recovered duoc xoa moi op); dialog 2 bao lai; policyFailure null; observe duoc | dung | PASS |
| T24 | Happy (K4) | agent | beforeunload do click (dev) | `dialog_unsupported`, url giu, observe OK | dung | PASS |
| T25 | Happy (K4) | agent | download do click (dev) | `download_started` completed, policyFailure null, op ke chay | dung | PASS |
| T26 | Happy (K4) | agent vs v4 | download trong op `wait` dang chay (dev) | agent: `download_unsupported`, khong khoa; v4: khoa | dung | PASS |
| T27 | Loi / Hoi quy v4 | ca hai mode | download ngoai op; `action_outcome_unknown` (dev) | khoa session nhu v4 | dung | PASS |
| T28 | Hoi quy v4 | v4 | dialog/beforeunload (dev x4) | `policyFailure` set, observe bi tu choi | dung | PASS |
| T29 | Hoi quy | worker | `vision-operations.spec.ts` | 99 pass (baseline phase 0 r2: 99 pass) | 99 passed (6.2m) | PASS |
| T30 | Hoi quy | worker | dom, history, locators, target-preflight, visual-buttons, readiness, outcome-capture, contract, vision, observability, click-evidence, sample-guard, settle-observability, observability.spec | khong fail | 140 passed, 1 skipped (contract.spec.ts:120, chi chay trong image) | PASS |
| T31 | Tinh | worker | `npm.cmd run typecheck` | exit 0 | exit 0 | PASS |
| T32 | Tinh | worker | `npm.cmd run lint` | khong loi moi; baseline do san | 22 error / 6 file khong dung toi (git status sach) ; file phase 2 + QA spec khong loi | PASS (baseline do) |
| T33 | Flaky | | `vision-agent-mode.qa.spec.ts` 3 lan, dev spec 1 lan o QA (dev da bao 3 lan) | on dinh | 18/18 x3; 23/23 | PASS |
