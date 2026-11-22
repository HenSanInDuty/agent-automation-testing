STATUS: DONE

# Agent loop round 01 r6 - be-developer r5 (live session, import, collect, review, evaluate)

```
CONTEXT_CHECK
- conventions: docs/code-standards.md -> AGENTS.md (round handoff, token budget, polling by one script)
- graphs: không graph nào phủ benchmark/vision/accuracy (hgraph brief); không sửa source nên không đổi graph
- blast radius: 0 file bị phụ thuộc / 0 file phụ thuộc (hgraph brief benchmark/vision/accuracy)
```

Terminal hợp lệ (`agent_stopped`), chấm xong, KHÔNG đạt gate -> DONE.

## Các bước
1. `agent_loop_round.py check`: exit 0, mismatches `[]` (control-plane 163, temporal-worker 163, claude-bridge 163, playwright-worker 48). Bridge `/codex-jobs/.heartbeat.json` recorded_at 00:42:00Z, `online:true, authenticated:true, capabilities_qualified:true`, model claude-opus-5-5. Không session non-terminal (108 unavailable, 8 completed), không bridge job non-terminal.
2. `mv agent-loop-session.json agent-loop-session.r5.json`; `submit` đúng một lần: HTTP 202, session `fa802b9c-3a3f-4de9-be54-08824014fe08`, correlation `2d8efeb7-2737-450a-bf80-a3de68a31c87`.
3. Poll bằng `scripts/watch_vision_session.py --changes` (một lệnh): `running` -> `terminal unavailable`. Không sửa code/restart/đổi policy/prompt/oracle.
4. Terminal: state `unavailable`, reason `agent_stopped` (model stop `unsupported_state` ở step 20) - lý do agent hợp lệ -> `run.py import` (iteration `1c56623e-8f37-4705-946b-5f1a6752f81c`), `collect`, review frame, `evaluate` (qua `.pytest-artifacts/score_r6.py`).

## Kết quả

| Mục | Giá trị |
| --- | --- |
| Model calls | 20 bridge jobs, tất cả completed, 0 schema rejection |
| Token in / out | 107,235 / 8,976 (cached 1,534 x 20 = 30,680) |
| Thời gian | khoảng 4 phút 37 giây (tạo 00:42:07Z, call cuối kết thúc 00:46:44Z) |
| Operations | 30: 24 completed, 6 rejected `state_mismatch` (seq 16, 19, 21, 24, 27, 29) |
| Loại op | click explore 12 (8 ok, 4 rejected), back 1, close_popup 3, scroll 2 (1 ok, 1 rejected), setup navigate 1, setup wait 10, explore wait 1 (rejected) |
| Blocked theo code | 0 (`sensitive_action_blocked` 0, không trên target oracle; `stale_ref`/`invalid_ref` 0) |
| Unsafe / unsettled | 0 / 0 |
| C (chính thức) | 0/47 = 0% |
| A (chính thức) | 0/12 = 0% |
| Detection | R 0/47; P n/a (0 key báo cáo); inventory không đầy đủ (`pages=[]`) |
| passed | false |
| ID oracle thiếu | 47/47 (xem lý do bên dưới); 42 target chưa từng bị chạm |
| Review thủ công (không do harness chấm) | 5/5 click map vào oracle đều đúng: C trần 5/47 = 10.64%, A 5/12 = 41.67% |

### Vì sao điểm chính thức bằng 0
`run.py` evaluate (`benchmark/vision/accuracy/run.py:283-287`) chỉ ghi điểm khi `binding["path"] == target["reference_path"]` (dom_path). Locator của agent_loop dùng strategy `role` nên `path=null` (`evidence.py:56-62`), và `GET .../result` trả `pages=[]` (không có inventory toàn trang) nên detection không có key. Thử ghi 5 target đã review thì `evaluate` ném `ValueError: assessment binding does not match oracle`. Không sửa `run.py`/`metrics.py`/oracle; điểm chính thức được ghi với tất cả `target_verdict/outcome_verdict = unverified`. Đây là khoảng trống đo lường cần quyết định, không phải kết quả model.

### Review thủ công (độc lập, ảnh before/after lưu trong `.pytest-artifacts/1c56623e-<seq>-*.png`, mỗi lượt <= 2 ảnh)
Map theo label + role + hộp (hộp locator trùng `reference_box` của oracle):
| seq | locator | oracle | ảnh sau click | verdict |
| --- | --- | --- | --- | --- |
| 2 | link SU KIEN | mct-02 | trang Su Kien, nav tô sáng; khớp mongchiton.vn/su-kien (HEAD 200) | đúng |
| 6 | link DIEU KHOAN | mct-04 | Tepaylink Terms of Service; khớp 301 id.tepaylink.vn/site/rules -> id.tpl.vn/rules (`redirect-review-20261117.json`) | đúng |
| 9 | link CONG DONG | mct-05 | nhóm Facebook VLCM Origin sau hộp thoại đăng nhập; khớp facebook.com/groups/mongchiton.vn; không đăng nhập | đúng |
| 11 | link HO TRO | mct-06 | Tepaylink Trung tam ho tro; khớp 301 support.tepaylink.vn -> support.tpl.vn | đúng |
| 14 | link TRANG CHU | mct-01 | về trang chủ, TRANG CHU tô sáng | đúng |

Các click seq 3, 4, 5 (tab Tin Tuc / Su Kien / Cam Nang trên /su-kien, /tin-tuc, /cam-nang) nằm ngoài phạm vi oracle (chỉ trang chủ), không tính. Review/finding lưu ở `runs/1c56623e.../manual-findings.json` và 5 `review-*.json` content-addressed.

## Fix r6 có chạy thật không: CÓ
- 10 `wait` refresh `purpose=setup` (seq 12, 17, 18, 20, 22, 23, 25, 26, 28, 30), tất cả `completed`.
- seq 12 là đúng tình huống r5: click HO TRO (op 11) rời origin sang `support.tpl.vn`; `dom_observation` trả `state_mismatch` (422, 00:44:26.9Z); loop phát refresh `wait` off-origin; worker chấp nhận (`vision-operations.ts:521-529`); sau đó `close_popup` (op 13) và phiên tiếp tục. `origin_blocked` xuất hiện 0 lần trong log.
- Các refresh còn lại (17+) trên trang chủ, on-origin.

## Nguyên nhân terminal (không phải lỗi tích hợp; kết quả hành vi)
Sau step 14 (scroll trang chủ) mọi action trên trang chủ bị worker từ chối `state_mismatch` 6 lần liên tiếp (steps 14-19; worker `vision.state.mismatch` ở `operation_prepare`: `interaction_changed=true, visual_semantics_changed=true, url_changed=false, scroll_changed=false`; một lần `state_changed_during_observation`). Refresh wait hoàn tất nhưng ref kế tiếp lại cũ. Giả thuyết (chưa cô lập): hero/news carousel hoặc video làm fingerprint đổi giữa observe và dispatch. Model dừng ở step 20 với `unsupported_state`.

K1 (20 call đủ?): không. 20 call chạm 5/47 target oracle: 4 call dành cho hồi phục trang ngoài (steps 6, 7, 9, 11), 6 call cho vòng `state_mismatch` (steps 14-19), 3 click tab ngoài phạm vi.

## Evidence
- `.pytest-artifacts/agent-loop-r6-evidence.log` (254 dòng: playwright-worker, control-plane, temporal-worker).
- `benchmark/vision/accuracy/runs/1c56623e-8f37-4705-946b-5f1a6752f81c/` (manifest, evidence, oracle, assessments, detection, score, usage, inventory-evidence, manual-findings, 5 review).
- DB (đọc-chỉ): `visual_operations`, `visual_agent_steps`, `codex_bridge_jobs` cho session.
- Script: `.pytest-artifacts/score_r6.py`, `review_r6_list.py`, `review_r6_map.py`, `review_r6_frames.py`.

## File đã ghi
- Báo cáo này và `.log`.
- `benchmark/vision/accuracy/AGENT-LOOP-01-20261120.md` (mục r6 + bảng, Edit).
- `plan/09112026103202-vision-accuracy-loop/README.md` ("Agent loop round 01 r6 handoff - 2026-11-21", Edit).
- `benchmark/vision/accuracy/runs/1c56623e-.../` (do run.py + score_r6.py sinh).
- `.pytest-artifacts/`: `agent-loop-session.r5.json` (đổi tên, giữ), `agent-loop-session.json` (r6), evidence log, scripts, ảnh review.
- Không sửa source/oracle/metrics/run.py/policy/.env/compose/graph. Không commit/push.
- Quy trình: tất cả ghi file bằng Write/Edit. Có một lệnh Bash `python -` với heredoc rỗng do nhầm làm sinh 2 tiến trình REPL treo; đã `taskkill` (PID 21100; PID 1716 đã tự thoát), không còn tiến trình python của tôi.

## Đề xuất (cần quyết định người dùng)
1. Cách harness ghi điểm agent_loop: bind locator `role` theo label+hộp với oracle và nguồn detection/inventory cho agent_loop mà không đổi oracle hay nới luật.
2. Điều tra `state_mismatch` trên trang chủ sau scroll (fingerprint prepare vs vùng động) và có thể thêm gợi ý prompt khi gặp `state_mismatch`.

## Tiến trình / stack
Không mở tiến trình/container nào. Stack compose của dự án giữ nguyên chạy (control-plane, temporal-worker, claude-bridge, playwright-worker, dashboard, rustfs, temporal, postgres, redis).

```
GRAPH_UPDATE
- graph đã cập nhật: không cần — không thêm/xoá file mã nguồn, không đổi quan hệ import
- file mới đã đưa vào graph: không có
- hgraph check --changed: không chạy (không sửa source; chỉ markdown/artifact)
```
