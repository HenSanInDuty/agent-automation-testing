# docs/graphs — bản đồ quan hệ file

Mỗi file dưới đây là **một chức năng lớn**: danh sách file ảnh hưởng lẫn nhau, ranh giới blast radius, và sơ đồ.
File này do `hgraph` tự sinh — đừng sửa tay.

> Trước khi code: `hgraph brief <file...>` · Sau khi thêm file: `hgraph add <slug> <file...>` · Kiểm tra: `hgraph check --changed`

| Graph | Chức năng | Owner | Số file | Cập nhật |
|---|---|---|---|---|
| [`codex-bridge`](codex-bridge.md) | Bridge Codex/Claude local | be | 28 | 2026-11-26 |
| [`playwright-vision-worker`](playwright-vision-worker.md) | Worker Playwright Vision | be | 38 | 2026-11-21 |
| [`task-ui-stability`](task-ui-stability.md) | Fixture task-ui và bộ đo ổn định agent loop theo task (ADR-046) | be | 4 | 2026-11-26 |
| [`vision-accuracy-harness`](vision-accuracy-harness.md) | Harness chấm điểm benchmark độ chính xác Vision (collect, ground, evaluate) | be | 7 | 2026-11-21 |
| [`vision-agent-loop`](vision-agent-loop.md) | Vòng agent loop Vision | be | 29 | 2026-11-26 |
| [`vision-dashboard`](vision-dashboard.md) | Dashboard Vision | fe | 32 | 2026-11-26 |
| [`vision-exploration`](vision-exploration.md) | Khám phá Vision (control-plane) | be | 61 | 2026-11-26 |
