---
phase: 01
title: Commit nhánh feat/agent-loop-task-testing
status: completed
owner: none
qa: skip
dependencies: []
---

# Phase 01 — Commit nhánh

## Mục tiêu

Đưa toàn bộ code agent-loop task-testing đang nằm chưa commit trên nhánh `feat/agent-loop-task-testing`
(43 file sửa, 14 file/thư mục mới) vào lịch sử git, để các phase sau có baseline sạch và để stack build từ nhánh
khớp với DB đang ở migration `c8d0e2f4a6b8`.

Phase này **không có dev, không có QA**: chỉ phiên chính (leader) chạy lệnh git sau khi user đồng ý. Agent con
không được `git add/commit/push`.

## Tiêu chí xong (kiểm chứng được)

1. User đã đồng ý bằng lời (hoặc tin nhắn) việc commit.
2. `python .pytest-artifacts/refresh_manifest.py` đã chạy ngay trước commit nếu còn file nguồn bị sửa sau lần
   refresh gần nhất; `git diff --stat benchmark/vision/codex/manifest.json` cho thấy manifest khớp source.
3. `CODEX_BRIDGE_ENABLED=false uv run pytest tests/test_codex_bridge_benchmark.py -q --basetemp=.pytest-artifacts/tmp-p1 -p no:cacheprovider`
   qua (test ghim hash trong `benchmark/vision/codex/manifest.json`).
4. Sau commit, `git status --short` **không còn** file nào ngoài (a) `benchmark/vision/visual-buttons/*.json`
   (2 file, cố ý không commit, bị test ghi đè) và (b) thứ trong `.gitignore`. Không có file `.env*`, token,
   `.pytest-artifacts/` trong commit (`git show --stat HEAD` để kiểm).
5. Commit message theo kiểu repo đang dùng (`feat:` / `fix:` / `chore:` / `docs:`, xem `git log`), kết thúc bằng
   dòng `Co-Authored-By` theo attribution của phiên. Repo này không có hook commit-msg, không cần hậu tố ticket.
6. `uv run ruff check .` sạch trước commit (đã sạch ở lần dừng 2026-11-25; chạy lại vì còn sửa sau đó thì có thể đổi).

## File liên quan (phạm vi được đụng; ngoài đó cấm)

- Được `git add`: toàn bộ file sửa/mới trong `git status` của nhánh, bao gồm file mới chưa tracked:
  `apps/control-plane/domain/vision_task_assessment.py`, `apps/dashboard/app/components/vision-task-assessment*.ts(x)`,
  `benchmark/task_ui/`, `benchmarks/targets/task-ui/`, `benchmarks/task-ui/`, `docker-compose.agent-loop.yml`,
  `docker-compose.spool-volume.yml`, `docs/adr/046-agent-loop-task-testing.md`,
  `migrations/versions/c8d0e2f4a6b8_agent_task_assessment.py`, `plan/20261125-2140-agent-loop-task-testing/`,
  `scripts/run_task_stability.py`, `tests/test_task_stability.py`, `tests/test_vision_agent_task_assessment.py`.
- Được chạy: `.pytest-artifacts/refresh_manifest.py` (ghi `benchmark/vision/codex/manifest.json`).
- **Cấm** `git add`: `benchmark/vision/visual-buttons/*.json`; `.pytest-artifacts/`; mọi `.env*`, `*.pem`,
  `*.key`, thư mục token bridge (`C:/Users/hen/.auto-at/claude-bridge-secrets`).
- Không sửa source ở phase này. Nếu `refresh_manifest.py` hoặc test lộ lỗi source, dừng và báo user.
- Convention: `AGENTS.md` (Required checks before helping: `uv run ruff check .`, `uv run pytest`). Graph: không
  đọc/không cập nhật graph ở phase này.

## Không làm

- Không push, không tạo PR (user chưa yêu cầu). Không merge vào `develop`.
- Không chạy trọn bộ `uv run pytest` trong phase này (hơn 40 phút, vượt trần lệnh); chỉ chạy nhóm test liên quan
  nếu user muốn thêm độ chắc, chia nhóm mỗi nhóm ≤ 9 phút.
- Không downgrade migration của DB cục bộ.
- Không gộp phase 2/3 vào cùng commit.

## Rủi ro / việc cần user duyệt

- **Phải hỏi user trước khi commit**: (1) đồng ý commit chưa (plan.md ghi "người dùng chưa yêu cầu commit");
  (2) một commit hay tách nhiều (đề xuất: tách theo chủ đề, vd "bridge/spool/doctor
  fixes", "agent-loop task assessment + migration", "dashboard", "fixture + stability harness"; nếu user không có
  ý kiến thì một commit).
- Bộ test Python chưa từng chạy trọn một lượt (dừng ở 87%). Commit không kèm bằng chứng suite xanh toàn bộ;
  user cần chấp nhận điều này hoặc yêu cầu chạy theo nhóm trước.
- `tests/test_vision_page_batch.py` dao động có sẵn trên host Windows (`invalid_step_deadline`, HEAD trượt 4/21,
  nhánh này 9/21): không coi là chặn commit; ghi vào message nếu user hỏi.
- DB cục bộ đã ở `c8d0e2f4a6b8`; sau commit, stack build từ `develop` vẫn không chạy được cho tới khi nhánh được
  merge. Không phải việc của phase này nhưng phải nhắc user khi chuyển nhánh.
