# task-ui fixture

Deterministic local web UI for testing the `agent_loop` task-testing engine (ADR-046). It replaces the
live third-party site as a test target: no animations, timers, randomness or external requests.
Dependency-free Node server, plain server-rendered HTML with a little inline JavaScript.

Run: `node server.mjs` (port `7300`, override with `PORT=...`). In compose it is the `task-target`
service from `docker-compose.agent-loop.yml`, reachable as `http://task-target:7300`.

State lives in the server process. `POST /__reset` restores the initial state (todos, login sessions).

## Pages (all linked from the nav bar)

| Path | What it has |
|---|---|
| `/` | Heading and a "Mở hộp thoại giới thiệu" button that opens a modal dialog (`role="dialog"`) with a "Đóng hộp thoại" button |
| `/login` | Username and password form. Valid -> redirect to `/dashboard` ("Xin chào, demo", "Đăng xuất" button). Wrong -> "Sai tên đăng nhập hoặc mật khẩu". Empty -> "Vui lòng nhập tên đăng nhập và mật khẩu" |
| `/dashboard` | Needs the login cookie, otherwise redirects to `/login` |
| `/todos` | Add form ("Thêm"), items with a "hoàn thành" checkbox and "Xoá" button, counter such as "2 việc, 1 đã xong". Seeded with "Học bài" (open) and "Đi chợ" (done) |
| `/tabs` | Three tabs (Tổng quan, Chi tiết, Cài đặt) with `role="tablist"/"tab"/"tabpanel"` and `aria-selected` |
| `/search` | Text input plus "Tìm" button over 8 seeded products; live filtering while typing; empty state "Không tìm thấy sản phẩm" |
| `/broken` | Intentionally defective page, see below |

## Test account

`demo` / `Demo1234`. It is a public fixture credential, not a secret.

## Intentional defects (`/broken`)

Do not fix these. They give negative tasks a known ground truth (`expected_status: not_achieved`).

1. "Lưu thay đổi" does nothing: no message, no navigation, no state change.
2. The "Đếm" button never changes the displayed number ("Số lần đếm: 0").

## Notes for agent tasks

Forms use ordinary `POST` plus `303` redirects. Controls are real `<button>`/`<input>`/`<label for>`
elements, so the agent finds them by accessible role and name. On a project that is not marked
`vision_owned_test_target`, the engine's safety rules block submit-type buttons and names such as
"Xoá" and "Đăng xuất"; run `scripts/run_task_stability.py prepare` first.
