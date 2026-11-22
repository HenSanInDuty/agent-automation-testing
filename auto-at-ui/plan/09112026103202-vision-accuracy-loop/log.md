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
