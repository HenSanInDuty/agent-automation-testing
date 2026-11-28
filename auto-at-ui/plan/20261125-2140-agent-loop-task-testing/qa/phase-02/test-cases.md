# QA phase 02 — test cases (page-text-v1)

Automation: `W*` = `workers/playwright/src/qa-page-text.spec.ts` (worker thật + Chromium, trang dựng trong spec); `C*` = `tests/test_qa_p2_page_text.py`; `DEV` = spec/test của developer chạy lại; `CMD` = lệnh.

| ID | Tiêu chí | Bước | Kỳ vọng | Automation | Kết quả |
|---|---|---|---|---|---|
| T-DEV-1 | 4 (happy) | Mở `/page-text` agent+cap, observe | alert/status/heading/đoạn thấy được; ẩn (display/hidden/aria/visibility/opacity/sr-only/ngoài màn hình), script/style, input/textarea/password, contenteditable, nút không có | DEV vision-agent-mode.spec "page text is read..." | PASS |
| W01 | 5 biên | Chữ nhạy cảm trong h1/h2/alert | bị bỏ, `skipped`=3, không còn trong JSON; mục an toàn còn | W01 | PASS |
| W02 | 5 biên | Đoạn >160 ký tự: từ nhạy cảm trong cửa sổ / sau ký tự 160 / sát biên | cắt TRƯỚC khi lọc; phần sau 160 không rời worker; trong cửa sổ thì bỏ + đếm | W02 | PASS |
| W03 | 4 biên | unicode/emoji/RTL, khoảng trắng, xuống dòng, tab, `<br>`, span liền, NBSP, ký tự điều khiển, 200 emoji | chuẩn hoá một dấu cách, trim, không rỗng, cắt đúng 160 code point + "…", không surrogate mồ côi | W03 | PASS (ghi chú: U+200B giữ nguyên, vô hại) |
| W04 | 4 biên | Cùng chữ ở alert/h1/p/p, "Khác" và " Khác " | còn một mục, loại đầu thắng (alert) | W04 | PASS |
| W05 | 4 | Alert chứa input/select/textarea/button; `title`/`alt`; noscript, template, svg, details đóng, contenteditable, iframe, shadow đóng; ô mật khẩu có giá trị | chỉ "Lỗi gõ", "Có tooltip"; không giá trị ô, không title/alt | W05 | PASS (không gõ trực tiếp vào ô: gõ làm đổi fingerprint -> `state_mismatch`; giá trị đặt bằng thuộc tính `value`) |
| W06 | 5 | Đoạn có số Ả Rập 8 chữ số, `đ@example.com` | worker KHÔNG được để lọt chữ mà Python từ chối | W06 + C08 + C09 | **FAIL** (xem F1) |
| W07 | 4 trần | 1500 `<p>` | ≤24 mục, `page_text_truncated`, observation ≤65536, nhanh | W07 | PASS (123 ms) |
| W08 | 4 trần | 40 nút + 60 đoạn; `max_bytes` hẹp | element list y hệt bản không chữ; chữ bị bớt + cờ; ≤ max_bytes | W08 | PASS |
| W09 | 3 | Ma trận: agent+cap, agent, cap, không gì, agent+cap khác, agent+cap+owned | chỉ khi agent VÀ cap; `open` luôn khai `page-text-v1`; owned không đổi lọc | W09 | PASS |
| T-DEV-2 | 5 | `/page-text-sensitive` thường và owned | 6 mục bị lọc, chữ không trong JSON | DEV spec "sensitive page text..." | PASS |
| T-DEV-3 | 4 trần | 30 đoạn; 12 đoạn 450 byte; `max_bytes` nhỏ | 24+cờ; 9 mục; bớt chữ | DEV spec "page text is capped..." | PASS |
| C01 | 1 | Fixture cũ không chứa `page_text`; serialize observation không chữ | khoá cũ đúng, không có 3 khoá mới | C01 | PASS |
| C02 | 1 | Khoá mới chỉ xuất hiện khi khác mặc định | đúng | C02 | PASS |
| C03 | 1 | Khai báo mặc định tường minh | canonical bytes + hash bằng bản không khai; có chữ thì hash khác | C03 | PASS |
| C04 | 5 | Python nhận 14 chữ xấu (e-mail, password=, token, 8 chữ số, URL, `[redacted]`, api key, khoảng trắng đầu/cuối, tab, xuống dòng) | ValidationError (cả `CodexPageTextItem`) | C04 x14 | PASS |
| C05 | 4 | 24/25 mục; 160/161/0 ký tự; kind lạ; extra field; 9 vs 10 mục theo 4096 byte; skipped âm | biên đúng | C05 | PASS |
| C06 | 4 biên | emoji/RTL/tiếng Việt roundtrip JSON | giữ nguyên | C06 | PASS |
| C07 | 2 | Fixture `page-text.accepted` parse | OK | C07 | PASS |
| C08 | 5 | Python có nhận các chuỗi worker để lọt (số Ả Rập, `đ@`) | nhận (hoặc worker đã bỏ) | C08 x2 | **FAIL** (F1) |
| C09 | 5 | Parse JSON observation thật của worker (W06) bằng Python | parse được | C09 | **FAIL** (F1) |
| C10 | 1 | Observation thật của worker không capability, parse khi có/không 3 khoá mặc định | canonical bytes + hash bằng nhau, không khoá mới sau serialize | C10 | PASS |
| R1 | 2 | `export_vision_worker.py --check` | exit 0 | CMD | PASS |
| R2 | 1,2 | pytest vision_worker/codex_bridge contracts, dom_transport, agent_loop x2, benchmark | pass | CMD | PASS |
| R3 | 6 | `npm.cmd run typecheck` | sạch | CMD | PASS |
| R4 | 6 | playwright vision-dom + vision-agent-mode | pass | CMD | PASS (87) |
| R5 | hồi quy | vision.spec, visual-buttons, target-preflight, agent-mode.qa, locators | pass | CMD | PASS (49) |
| R6 | hồi quy | vision-operations, click-evidence, agent-evidence, readiness | pass | CMD | PASS (124) |
| R7 | 6 | `uv run ruff check .` | sạch | CMD | PASS |
| R8 | fixture cũ | `git status packages/contracts/fixtures` | chỉ file mới `??` | CMD | PASS |
| R9 | validateVision TS | Có đường nào chữ nhạy cảm lọt khỏi worker? | xem F2 | W01/W02/W06 | Rủi ro, xem F2 |
| S1 | stress | Trang 1500 `<p>` (W07) | đủ nhanh, bị chặn | W07 | PASS |


## Vòng 2 (delta sau be-developer-r2)

| ID | Tiêu chí | Bước | Kỳ vọng | Automation | Kết quả |
|---|---|---|---|---|---|
| C08 (sửa) | 5 | Python `CodexPageTextItem` với `Mã ١٢٣٤٥٦٧٨ ở đây`, `đ@example.com` | Python VẪN từ chối (không nới lọc); bên phải bỏ là worker | C08 x2 | PASS (kỳ vọng vòng 1 ngược, đã đổi) |
| C09 | 5 | JSON worker thật cho hai chuỗi đó parse ở Python | parse được | C09 | PASS (F1 gốc đã đóng) |
| W10/C11a/C11b | 5 tấn công | 838 chuỗi Python TỪ CHỐI (sinh từ 8 từ nhạy cảm x biến thể: hoa/Kelvin/ſ/ı/İ/ö/full-width t, ZW U+200B/C/D/FEFF/00AD/2060, NFD, dấu kết hợp; ngữ cảnh `_`,U+203F,²,Ⅷ,ª,ǅ,ʰ,ᴬ,chữ số Ả Rập; e-mail với ＠, ﹫, ．, 。, ſ, K Kelvin, local/domain Unicode; chữ số mọi hệ Nd x 10 ngữ cảnh; URL/`[REDACTED]` biến thể) qua worker thật (53 trang, 16 chuỗi/trang) | worker giữ 0 chuỗi | W10 + C11b | **FAIL**: worker giữ 48/838 (xem F3) |
| W11/C12 | 4 biên | Trang gán lone surrogate bằng JS | Python parse + canonical_bytes + hash không lỗi | W11 + C12 | PASS (Chromium đổi thành U+FFFD) |
| R2-1 | hồi quy | playwright qa-page-text + agent-mode + vision-dom | pass | CMD | PASS (99) |
| R2-2 | hồi quy | pytest qa_p2 + codex_bridge_contracts + vision_worker_contracts + dom_transport + benchmark | pass | CMD | 173 pass, 3 skip, 1 fail (C11b = F3) |
| R2-3 | hồi quy | typecheck, ruff | sạch | CMD | PASS |
| R2-4 | fixture | `git status packages/contracts/fixtures` | chỉ file mới | CMD | PASS |


## Vòng 3 (delta sau be-developer-r3, fix F3)

| ID | Tiêu chí | Bước | Kỳ vọng | Automation | Kết quả |
|---|---|---|---|---|---|
| W10/C11a/C11b (chạy lại) | 5 tấn công | 847 chuỗi Python TỪ CHỐI (838 cũ + 9 mới) qua worker thật | worker giữ 0 | W10 + C11b | PASS (`ATTACK sent 847 kept 0 skipped 847`) |
| C11 mở rộng | 5 | İ/ı trộn zero-width (U+200B/C/D/FEFF/00AD/2060), U+0307, U+0301, `_`; `i`+U+0307, `I`+U+0307; full-width ｉ/Ｉ; `maİl@example.com`, `mail@exİmple.com`, `https://exİmple.com`, `httpİ://`; từ khoá khác có İ/ı (passİwd, tokİn, secrİt...) | không lọt | C11a (danh sách sinh thêm) | PASS (những chuỗi Python từ chối đều bị worker bỏ) |
| W12 | 4 | `Işık açık`, `İstanbul ılık`, `İLK SIRA`, `Çıkış yapıldı` | giữ NGUYÊN BẢN, không đổi thành `i`, skipped 0 | W12 | PASS |
| R3-1 | hồi quy | playwright qa-page-text + agent-mode + vision-dom | pass | CMD | PASS (100) |
| R3-2 | hồi quy | pytest qa_p2 + codex_bridge_contracts + vision_worker_contracts + dom_transport + benchmark | pass | CMD | PASS (178, 3 skip) |
| R3-3 | 2,6 | export `--check`, ruff, typecheck, fixture cũ | sạch | CMD | PASS |
