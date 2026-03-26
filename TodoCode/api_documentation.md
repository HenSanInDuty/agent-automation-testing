# Tài liệu API — Todo Application

Tài liệu này mô tả các endpoint của backend Todo. Tất cả endpoint bắt đầu bằng tiền tố `/api`.

**Lưu ý**: backend hiện tại trả về `200 OK` cho các thao tác tạo, cập nhật và xóa; phản hồi JSON chứa đối tượng tạo/cập nhật hoặc thông báo lỗi tương ứng.

## Mô hình dữ liệu

### Task
Trường theo `backend/models/models.go`:

| Trường | Kiểu | Mô tả | Định dạng |
| :--- | :--- | :--- | :--- |
| `id` | `uint` | Khóa chính |
| `title` | `string` | Tiêu đề công việc |
| `is_done` | `bool` | Trạng thái hoàn thành |
| `start_time` | `string` | Thời gian bắt đầu | `HH:mm` |
| `end_time` | `string` | Thời gian kết thúc | `HH:mm` |
| `date` | `string` | Ngày công việc | `YYYY-MM-DD` |
| `created_at` | `time` | Thời điểm tạo (ISO timestamp) |
| `updated_at` | `time` | Thời điểm cập nhật (ISO timestamp) |
| `deleted_at` | `gorm.DeletedAt` | Xóa mềm (nullable) |

### Goal

| Trường | Kiểu | Mô tả | Định dạng |
| :--- | :--- | :--- | :--- |
| `id` | `uint` | Khóa chính |
| `title` | `string` | Tiêu đề mục tiêu |
| `type` | `string` | `day`, `month`, hoặc `year` |
| `date` | `string` | Dùng cho `day` goals | `YYYY-MM-DD` |
| `month` | `string` | Dùng cho `month` goals | `YYYY-MM` |
| `year` | `string` | Dùng cho `year` goals | `YYYY` |
| `is_done` | `bool` | Trạng thái hoàn thành |
| `created_at` | `time` | Thời điểm tạo |
| `updated_at` | `time` | Thời điểm cập nhật |

---

## Endpoints

### Tasks

- Get all tasks
  - URL: `GET /api/tasks`
  - Query params: `date` (optional, `YYYY-MM-DD`)
  - Response: `200 OK` — mảng JSON các `Task`.

  Example response:
  ```json
  [
    {
      "id": 1,
      "title": "Làm bài tập",
      "is_done": false,
      "start_time": "08:00",
      "end_time": "09:00",
      "date": "2026-01-25",
      "created_at": "2026-01-25T08:00:00Z",
      "updated_at": "2026-01-25T08:00:00Z"
    }
  ]
  ```

- Create task
  - URL: `POST /api/tasks`
  - Body: JSON với các trường `title` (string), `is_done` (bool), `start_time` (HH:mm), `end_time` (HH:mm), `date` (YYYY-MM-DD)
  - Nếu `date` không cung cấp, backend sẽ gán ngày hiện tại tự động.
  - Response: `200 OK` — trả về đối tượng `Task` vừa tạo.

- Update task
  - URL: `PUT /api/tasks/:id`
  - Body: Partial JSON (chỉ gửi các trường cần cập nhật)
  - Response: `200 OK` với đối tượng `Task` sau khi cập nhật; `404` nếu không tìm thấy.

- Delete task
  - URL: `DELETE /api/tasks/:id`
  - Response: `200 OK` — `{ "message": "Task deleted" }`.

### Goals

- Get goals
  - URL: `GET /api/goals`
  - Query params (optional): `type` (`day|month|year`), `date` (`YYYY-MM-DD`), `month` (`YYYY-MM`), `year` (`YYYY`).
  - Nếu `date`, `month` và `year` cung cấp đồng thời, backend sẽ tìm các goal phù hợp trong ngữ cảnh ngày đó.
  - Response: `200 OK` — mảng `Goal`.

- Create goal
  - URL: `POST /api/goals`
  - Body: `title`, `type` (required), và trường tương ứng (`date`/`month`/`year`) nếu cần. Backend có thể tự gán `date`/`month`/`year` theo `type` nếu không truyền.
  - Response: `200 OK` — đối tượng `Goal` đã tạo.

- Delete goal
  - URL: `DELETE /api/goals/:id`
  - Response: `200 OK` — `{ "message": "Goal deleted" }`.

### Statistics

- Get stats
  - URL: `GET /api/stats`
  - Query params: `date` (optional, `YYYY-MM-DD`), `month` (optional, `YYYY-MM`)
  - Response: `200 OK` — object JSON có các trường:
    - `daily_goal`: float (tỉ lệ % hoàn thành cho ngày được chọn hoặc ngày hiện tại)
    - `last_5_days`: array of `{ "date": "YYYY-MM-DD", "rate": float }`
    - `success_days`: array of `YYYY-MM-DD` (các ngày trong tháng có tỉ lệ >= 80%)

  Example response:
  ```json
  {
    "daily_goal": 80.0,
    "last_5_days": [
      {"date": "2026-01-21", "rate": 100.0},
      {"date": "2026-01-22", "rate": 60.0},
      {"date": "2026-01-23", "rate": 90.0},
      {"date": "2026-01-24", "rate": 80.0},
      {"date": "2026-01-25", "rate": 80.0}
    ],
    "success_days": ["2026-01-01", "2026-01-02", "2026-01-05"]
  }
  ```

---

File đã cập nhật: [api_documentation.md](api_documentation.md)

Bạn muốn tôi thêm ví dụ lỗi (400/404/500) cho từng endpoint không?
