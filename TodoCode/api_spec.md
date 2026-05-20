# TodoCode Backend API Spec

> Đặc tả API cho backend TodoCode (Gin + GORM + SQLite). Tất cả endpoint đều
> public (chưa có auth) và chạy tại `http://localhost:8080`. Tuân theo contract
> `docs/Flow/automation-testing-api-md-contract.md` (v1).

Base URL: `http://localhost:8080`
Content-Type mặc định: `application/json`

---

## API: List Tasks

Lấy danh sách task, sắp xếp theo `id DESC`. Có thể lọc theo ngày.

### Endpoint

- Method: GET
- Path: /api/tasks
- Auth: None

### Request

- Query params:

| field | type   | required | rules                                          |
| ----- | ------ | -------- | ---------------------------------------------- |
| date  | string | no       | `YYYY-MM-DD`. Nếu có, lọc task theo ngày này  |

### Response

- 200 OK: `[ { "id": 1, "title": "string", "is_done": false, "start_time": "08:00", "end_time": "09:00", "date": "2026-01-25", "created_at": "2026-01-25T08:00:00Z", "updated_at": "2026-01-25T08:00:00Z" } ]`

> Backend trả về mảng rỗng `[]` (không phải 404) khi không có task khớp filter.

---

## API: Create Task

Tạo task mới. Nếu thiếu `date`, backend tự gán ngày hiện tại (server local time).

### Endpoint

- Method: POST
- Path: /api/tasks
- Auth: None

### Request

- Content-Type: application/json
- Body schema:
****
| field      | type   | required | rules                                            |
| ---------- | ------ | -------- | ------------------------------------------------ |
| title      | string | yes      | Không rỗng                                       |
| is_done    | bool   | no       | default `false`                                  |
| start_time | string | no       | format `HH:mm`                                   |
| end_time   | string | no       | format `HH:mm`, phải ≥ `start_time` cùng ngày    |
| date       | string | no       | `YYYY-MM-DD`. Nếu thiếu, backend gán today       |

### Response

- 200 OK: `{ "id": 1, "title": "string", "is_done": false, "start_time": "08:00", "end_time": "09:00", "date": "2026-01-25", "created_at": "...", "updated_at": "..." }`
- 400 Bad Request: `{ "error": "string" }` — JSON binding lỗi (sai kiểu, malformed JSON)

---

## API: Update Task

Cập nhật một phần (partial update) các trường của task theo `id`.

### Endpoint

- Method: PUT
- Path: /api/tasks/{id}
- Auth: None

### Request

- Content-Type: application/json
- Path params: `id` (uint) — ID của task cần cập nhật.
- Body schema (partial, chỉ truyền field cần đổi):

| field      | type   | required | rules                       |
| ---------- | ------ | -------- | --------------------------- |
| title      | string | no       | Không rỗng nếu được truyền  |
| is_done    | bool   | no       | toggle trạng thái           |
| start_time | string | no       | format `HH:mm`              |
| end_time   | string | no       | format `HH:mm`              |
| date       | string | no       | `YYYY-MM-DD`                |

### Response

- 200 OK: `{ "id": 1, "title": "string", "is_done": true, ... }`
- 400 Bad Request: `{ "error": "string" }` — JSON binding lỗi
- 404 Not Found: `{ "error": "Task not found" }`
- 500 Internal Server Error: `{ "error": "string" }` — lỗi GORM khi update

---

## API: Delete Task

Xóa mềm (soft delete) task theo `id` (cột `deleted_at` được set bởi GORM).

### Endpoint

- Method: DELETE
- Path: /api/tasks/{id}
- Auth: None

### Request

- Path params: `id` (uint) — ID của task cần xóa.

### Response

- 200 OK: `{ "message": "Task deleted" }`
- 500 Internal Server Error: `{ "error": "string" }`

> Backend hiện không phân biệt 404: gọi DELETE với `id` không tồn tại vẫn trả
> `200 OK` (GORM `Delete` không raise lỗi cho missing row).

---

## API: List Goals

Lấy danh sách goal, sắp xếp theo `id DESC`. Hỗ trợ 2 chế độ lọc.

### Endpoint

- Method: GET
- Path: /api/goals
- Auth: None

### Request

- Query params:

| field | type   | required | rules                                                         |
| ----- | ------ | -------- | ------------------------------------------------------------- |
| type  | string | no       | `day` \| `month` \| `year`                                    |
| date  | string | no       | `YYYY-MM-DD`                                                  |
| month | string | no       | `YYYY-MM`                                                     |
| year  | string | no       | `YYYY`                                                        |

Quy tắc combine:
- Khi `date` + `month` + `year` đồng thời truyền: trả về tất cả goal khớp ngữ
  cảnh ngày đó (OR giữa `day=date`, `month=month`, `year=year`).
- Ngược lại: AND giữa các filter có giá trị.

### Response

- 200 OK: `[ { "id": 1, "title": "string", "type": "day", "date": "2026-01-25", "is_done": false, "created_at": "...", "updated_at": "..." } ]`

> `month` và `year` trong response sẽ bị omit nếu rỗng (`json:",omitempty"`).

---

## API: Create Goal

Tạo goal mới. Nếu không truyền trường tương ứng `type`, backend tự gán theo
thời điểm hiện tại.

### Endpoint

- Method: POST
- Path: /api/goals
- Auth: None

### Request

- Content-Type: application/json
- Body schema:

| field   | type   | required | rules                                                       |
| ------- | ------ | -------- | ----------------------------------------------------------- |
| title   | string | yes      | Không rỗng                                                  |
| type    | string | yes      | `day` \| `month` \| `year`                                  |
| date    | string | no       | `YYYY-MM-DD`. Auto-fill nếu `type=day` mà thiếu             |
| month   | string | no       | `YYYY-MM`. Auto-fill nếu `type=month` mà thiếu              |
| year    | string | no       | `YYYY`. Auto-fill nếu `type=year` mà thiếu                  |
| is_done | bool   | no       | default `false`                                             |

### Response

- 200 OK: `{ "id": 1, "title": "string", "type": "day", "date": "2026-01-25", "is_done": false, "created_at": "...", "updated_at": "..." }`
- 400 Bad Request: `{ "error": "string" }` — JSON binding lỗi

---

## API: Delete Goal

Xóa goal theo `id`.

### Endpoint

- Method: DELETE
- Path: /api/goals/{id}
- Auth: None

### Request

- Path params: `id` (uint) — ID của goal cần xóa.

### Response

- 200 OK: `{ "message": "Goal deleted" }`
- 500 Internal Server Error: `{ "error": "string" }`

> Tương tự `Delete Task`: gọi với `id` không tồn tại vẫn trả `200 OK`.

---

## API: Get Stats

Lấy thống kê hoàn thành task: tỉ lệ ngày được chọn, 5 ngày gần nhất (tính từ
hôm nay thực), và danh sách "success days" trong tháng.

### Endpoint

- Method: GET
- Path: /api/stats
- Auth: None

### Request

- Query params:

| field | type   | required | rules                                                 |
| ----- | ------ | -------- | ----------------------------------------------------- |
| date  | string | no       | `YYYY-MM-DD`. Mặc định là hôm nay nếu thiếu/parse fail |
| month | string | no       | `YYYY-MM`. Bắt buộc để tính `success_days`           |

### Response

- 200 OK: `{ "daily_goal": 80.0, "last_5_days": [ { "date": "2026-01-21", "rate": 100.0 } ], "success_days": ["2026-01-01"] }`

Cấu trúc field:

| field         | type     | mô tả                                                                  |
| ------------- | -------- | ---------------------------------------------------------------------- |
| daily_goal    | float    | % task hoàn thành trong `date` (0–100). `0` nếu không có task hôm đó. |
| last_5_days   | array    | 5 phần tử `{ date, rate }`, theo thứ tự cũ → mới, anchor real-today.  |
| success_days  | string[] | Các ngày trong `month` có `rate ≥ 80%`. `[]` nếu thiếu `month`.       |

---

## Errors

Backend hiện trả về error chung dạng `{ "error": "<message>" }`. Các tình
huống đã gặp:

| HTTP | Khi nào                                                                    |
| ---- | -------------------------------------------------------------------------- |
| 400  | Body JSON malformed hoặc sai kiểu (gin `ShouldBindJSON` fail)              |
| 404  | `PUT /api/tasks/{id}` với `id` không tồn tại                               |
| 500  | Lỗi DB (GORM raise) trong update task, delete task/goal                    |

## Notes

- CORS: chỉ cho `http://localhost:3000` (frontend Next.js), methods `GET POST
  PUT DELETE OPTIONS`, headers `Origin, Content-Type`, credentials enabled.
- Soft delete: model `Task` có `deleted_at` (GORM `DeletedAt`); query mặc định
  filter out các row đã xóa. Model `Goal` xóa cứng (hard delete).
- Date math trong stats dùng server local time, không tôn trọng timezone của
  client.
- Tất cả endpoint đều trả `200 OK` cho create/update/delete (không dùng 201).
