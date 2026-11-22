# Nhật ký sprint (phase 06)

Lịch sử trước 2026-11-22: `history/README-rounds-01-21-until-20261121.md`.

## 2026-11-22 — ngày 1 (offline + probe chỉ đọc), 0/8 live run

- Đánh giá lại plan; người dùng chọn: quay về v4 + Claude, đóng lỗi r21, sprint 3 ngày; agent loop đóng băng.
- 3 key lạ r21 = khung video mct-47 slot 4/1/2 (dò ngược `descriptor_key`). Probe live chỉ đọc
  (`.pytest-artifacts/s1-video-probe.mts`, `s1-video-click-probe.mts`): một swiper/nhân vật, cùng video
  `_llS1gbeknQ`, click → `#true` + iframe embed đúng video.
- Oracle v2 `2795c44f…` (alternate_paths mct-47), harness + `rescore.py`, 16 test mới; 96 accuracy tests
  passed, Ruff toàn repo sạch.
- r21 chấm lại theo v2: C=A=46/47, P=R=47/47, passed (lượt cũ, không phải qualification).
- Phát hiện: ADR-042 áp dụng cả v4 → lượt live đầu ngày 2 là lượt thử cho source mới.
- Người dùng: cho commit, tiêu chí 4/5, cho live ngày 2. Commit `d351561` (agent loop trước sprint);
  `qualify_batch` 4/5 + 9 test (104 accuracy tests passed, Ruff sạch).

## 2026-11-22 — ngày 2 (chuẩn bị)

- Runner có theo dõi `benchmark/vision/accuracy/round_v4.py`: `preflight` (smoke gate: không session active,
  bridge Claude ready, cờ agent loop tắt, checksum image = tree, worker 401, token ≥3 h + export, worker
  open/close không LLM) → `start` (chặn nếu không có preflight pass ≤20 phút cùng source) → `wait` →
  `collect` (evidence, frame verify, inventory, state page_url, download, usage) → `auto` → `score`.
- Chấm tự động: quy tắc page_url (bỏ query) = URL khai báo hoặc chuỗi redirect đã review; download chain
  bắt đầu đúng hash khai báo; mct-47 `#true`. Trên r21: 28 machine credit, 0 lệch với review tay; 19 lượt
  hiển thị (tab/nhân vật/carousel/TOP/search) vẫn review ảnh. Test `tests/test_vision_accuracy_round_v4.py`.
- Recreate `control-plane` + `temporal-worker` không dùng override agent loop → `VISION_AGENT_*` unset.
- Regression v4 trên tree hiện tại: worker 143/143 passed (7,1 phút); Python cô lập 202 passed + 1 fail
  manifest hash drift → refresh 18 hash trong `benchmark/vision/codex/manifest.json`, test pass. Commit `20ba984`.
- Preflight lần 1 fail do lỗi của chính checker (image CRLF; payload smoke thiếu `contract_version: v4`) →
  sửa (`f4bd0b7`); preflight lần 2 pass 9/9, token 6,8 h; claude-bridge khớp tree.

## Live 1/8 (lượt thử) — iteration `6b68fe65-b274-45b5-968c-ee1825b3692f`, session `4a1f649e-ec7a-4980-8bef-4fb7cccbb855`

- Submitted 2026-11-22; source = HEAD `f4bd0b7`, oracle v2, `claude_cli / claude-opus-5-5`, caps r21.
- Terminal `unavailable / unsafe_replay`: 121 operations, 32 explore clicks (all completed, 0 rejected/unknown),
  19 model jobs, 240/242 frames. Coverage ceiling **32/47 = 68,1% → FAIL** (không cần review ảnh).
  Thiếu mct-01…08, 10…16 (menu đầu trang + panel "TẢI GAME" bên phải). Machine rules: 13 credit, 19 cần ảnh.
- Nguyên nhân: model đi thân trang trước; BFS xếp nhánh scan-cuộn của state `bfb9ae9e` (hop 8, sau các click
  cùng URL, `url_restore_allowed=false`, không có history entry) rồi quay lại sau → scroll restore (op 120) →
  `back` bị worker từ chối trước dispatch `history_checkpoint_unavailable` (op 121; `validateHistory` cần
  entry < current) → controller dừng cả session `unsafe_replay` thay vì bỏ nhánh đó. Link gốc vẫn
  `navigate` được nhưng không còn lượt. Cùng họ lỗi restoration (r19, r21 ở cuối lượt).
- Đánh giá sai ở plan sprint: restoration terminal "không ảnh hưởng điểm" chỉ đúng khi nó xảy ra cuối lượt.
- Dừng live, chờ quyết định cách sửa (1/8 lượt đã dùng).

## ADR-044 (duyệt 2026-11-22) — bỏ nhánh không khôi phục được

- `restore()` ném `BranchUnreachable` (vẫn mã `unsafe_replay`) đúng chỗ từ chối replay path không replay được;
  với frozen input, vòng BFS retire việc trên cùng state (edge terminal, target chưa dispatch → pending), refresh
  đọc trang rồi đi tiếp. Visual_buttons propose quét lại DOM khi document đổi (navigate/back) — bản đầu so mọi
  revision gây `dom_snapshot_limit` ở test "home" nên thu hẹp.
- Red/green: fixture `/coverage-history-overwritten-unreachable` — đỏ trên HEAD cũ (dừng ở back op 6), xanh sau
  sửa ("Top action" click sau skip, Sibling pending, không replay click). 12 biến thể restore cũ giữ nguyên.
  Suite cô lập 204/204; activity 49 passed; dashboard 5/5 + tsc; reviewer độc lập PASS (2 ghi chú thấp, ghi ADR).
- Commit `84213bd`; rebuild + deploy `control-plane`, `temporal-worker`; preflight 9/9 (token 5,4 h).

## Live 2/8 — iteration `5dca0c79-01b7-40dd-8b8a-b6396bcb5341`, session `9a6be948-96dc-4ca4-a378-a68a0463e18f`

- Submitted; source HEAD `84213bd`, oracle v2, `claude_cli / claude-opus-5-5`, caps r21.
- Terminal `unavailable / exploration_coverage_incomplete` (runtime partial do 2 nhánh bị bỏ; benchmark độc lập):
  170 operations, **47 explore clicks, tất cả completed**, 20 model jobs, 336/340 frames, 2 download.
  ADR-044 chạy thật: 2 `back` bị worker từ chối (op 154, 156, `history_checkpoint_unavailable`) → bỏ nhánh, đi tiếp.
- 47/47 click trỏ tới 47 mục tiêu khác nhau (có mct-47), 0 trùng, 0 nhãn âm, 0 click ngoài oracle.
- Chấm: 28 luật máy + 19 review ảnh (`runs/5dca0c79…/visual-findings-20261122.json`), mct-57 lùi đúng 2→1.
- **Điểm oracle v2: C=47/47, A=47/47, P=47/47, R=47/47, inventory complete, unsafe 0, unsettled 0 → PASSED**
  (`runs/5dca0c79…/rescore-2795c44ffdcc/score.json`). Đây là lượt thử, chưa phải qualification.
- Lưu ý phương pháp: 19 kết quả hiển thị do Claude (phiên điều phối) review — cùng họ model với model đề xuất
  `claude-opus-5-5`, dù khác vai trò/không thấy lập luận của nó. 28 kết quả còn lại chấm bằng luật máy.
  Đề xuất người dùng soát lại ngẫu nhiên các ảnh ghép trước khi chốt qualification.

## Qualification (ngày 3, người dùng duyệt cả loạt 2026-11-22) — khai báo trước

- Khai báo: `benchmark/vision/accuracy/qualification-sprint-20261122-declaration.json` — candidate = lượt 2
  (source `53c575f6…`, config `e3039b74…`, oracle v2 `2795c44f…`, 3 image digest), luật `qualify_batch` 4/5.
- Driver `.pytest-artifacts/s3_qual_batch.py`: preflight → start → wait → collect → auto cho 5 lượt liên tiếp;
  dừng nếu preflight trượt 2 lần hoặc hash lệch khai báo. Trang ảnh ghép: https://claude.ai/artifact/PrBkAREq2f93MNM9pfh725

### Q1/5 (live 3/8) — iteration `474faf80-135d-47d6-a8a0-025cadad364f`, session `9ea507ff-7de9-4634-8700-b59c0d63cf76`

- `unavailable / exploration_coverage_incomplete`; 176 operations, 47/47 mục tiêu khác nhau có click completed, 19 model jobs,
  348/352 frames, 2 download. 26 luật máy + 21 review ảnh (`visual-findings-20261122.json`).
- **TRƯỢT**: C=A=44/47 (93,6%), P=R=47/47, unsafe 0, unsettled 0, inventory_complete=false (state `bbeddbbc`, skipped_count 1).
- Thiếu: mct-05, mct-15 — Facebook trả `facebook.com/login/` (cùng checksum ảnh với vòng 10, chấm unverified như vòng 10);
  mct-58 — mũi tên tới, ảnh sau ở chỉ báo 6 thay vì 5 (autoplay chen; chấm như r17 op 26).

### Q2/5 (live 4/8) — iteration `69a5ecc4-4eff-447d-9a52-b1ed6a10b4b1`, session `1eecc684-a049-4165-9b5e-d3f1a91e9856`

- `unavailable / exploration_coverage_incomplete`; 169 operations, 47/47 mục tiêu có click completed, 18 model jobs, 336/338 frames.
- **TRƯỢT (chỉ do inventory)**: C=A=46/47 (97,9%), P=R=47/47, unsafe 0, unsettled 0, inventory_complete=false
  (state `81878709`, 1 control `unbound_target`). Facebook lần này đúng group (luật máy). Thiếu: mct-58 (6 → 2, autoplay).
- Log worker `vision.dom.coverage_limited`: live 1, Q1, Q2 và Q3 (đang chạy) đều có đúng 1 control không ground được trong một
  lần quét `visual_buttons` (17 quan sát); live 2 không có → lượt thử đạt một phần nhờ may. Sau Q3 loạt không thể đạt 4/5.
  Vẫn chạy đủ 5 lượt như đã duyệt: ngân sách còn lại (8 − 7) không đủ cho loạt mới, dừng sớm không đổi được gì.

### Q3/5 (live 5/8) — iteration `c9dbe0f7-7e6d-48da-82ff-2350965d6346`, session `abaeab9c-051c-476c-bbdf-0b59118781a7`

- `unavailable / exploration_coverage_incomplete`; 148 operations, 47/47 mục tiêu có click completed, 16 model jobs, 291/296 frames.
- **TRƯỢT (inventory)**: C=A=45/47 (95,7%), P=R=47/47, unsafe 0, unsettled 0, inventory_complete=false (state `5a467b59`,
  `unsupported_target`). Thiếu: mct-05, mct-15 (Facebook lại trả trang login). mct-58 lần này đúng 1 bước.
- Ca biên: op 29 mct-46 (Cổ Mộ đã active, panel chỉ lộ phần chân) — tính credit, đánh dấu để người dùng soát.
- Sau Q3: 3/5 trượt → loạt **không đạt** `qualify_batch` bất kể Q4–Q5.

### Q4/5 (live 6/8) — iteration `342e27fa-b6d8-434e-be70-adf735c9b545`, session `bbea4d22-0544-4c15-a114-fab90154d1cd`

- `unavailable / bridge_io_error` sau 66 operations, 4 model jobs: temporal-worker đọc spool `events.jsonl` gặp `ENODATA`
  (errno 61) ngay khi bridge vừa ghi đề xuất (job 4). Chưa từng gặp trong lịch sử. Từ 07:24:00 worker bắt đầu screenshot timeout.
- C=20/47, A=20/22, P=R=47/47, inventory đủ, safety 0. Không credit: mct-56 (6 → 1, autoplay), mct-40 (Facebook login).

### Q5/5 (live 7/8) — iteration `a775347c-e57f-46d5-a6bb-9361a23f823d`, session `712f4d9d-0e2c-4203-a25b-3dc2fd690639`

- Preflight 9/9 nhưng `unavailable / initial_capture_failed` sau 22 s (CDP session timeout, after capture contract_rejection).
  C=0/47. Smoke gate không có bước chụp ảnh nên không bắt được lỗi này. Preflight sau loạt vẫn 9/9.

### Kết quả loạt — KHÔNG ĐẠT

- `qualify_batch`: 0/5 lượt đạt, cùng candidate, safety 0 cả 5 lượt, 163 attempts. `qualify` (3 liên tiếp) không đạt.
- Báo cáo `benchmark/vision/accuracy/QUALIFICATION-20261122-sprint.md` + `qualification-sprint-20261122.json`.
- Ngân sách 7/8 đã dùng → không còn đủ cho loạt mới; sprint dừng theo điểm dừng, chờ người dùng quyết định.

## 2026-11-22 — tìm control bị skip + plan sửa (h-fix, không tốn live run)

- Control bị skip ở Q1–Q3 và live 1 = **mct-47** (khung video). Nguyên nhân: swiper nhân vật autoplay (3000/600 ms, `loop`)
  trượt đúng lúc `observeDom`; grounding lấy tâm lúc đang trượt, nằm dưới lớp khác. Không phải hồi quy (A/B r21 = hiện tại).
- Hướng A (chờ đứng yên + ground lại) đã qua leader/QA nhưng harness trên site vẫn skip 7/30 → chưa đạt.
- Người dùng: ghi A2 vào plan, làm tiếp tối nay. Plan: `plan/20261122-1445-fix-visual-buttons-moving-carousel/plan.md`.
  Code A chưa commit trong cây làm việc (vision-dom.ts, vision-dom.spec.ts, ADR-045, manifest).
- Kết quả (h-cook, cùng ngày): A2 + phase-02 xong, leader/QA PASS. Harness trên site 0 skip/160 lần quét tới 1152
  (code A 7/40, code cũ 1/30). Còn 2/160 miss khi lần duyệt rơi giữa lúc trượt (không bản sao nào nằm trọn viewport),
  là giới hạn đã ghi trong ADR-045. Worker đã rebuild, preflight passed. Chưa chạy qualification mới (ngân sách 1/8).
