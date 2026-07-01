# API Documentation — Todo Application

- Base URL: http://localhost:8080

## Headers
| Name | Value |
| :--- | :--- |
| Content-Type | application/json |

## API: Tasks

### Endpoint
- Method: GET
- Path: /api/tasks

### Request
- Query params:
  - date (optional, YYYY-MM-DD)

### Response
- HTTP Status: 200 OK
- JSON Body:
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

## API: Tasks

### Endpoint
- Method: POST
- Path: /api/tasks

### Request
- JSON Body:
  ```json
  {
    "title": "Làm bài tập",
    "is_done": false,
    "start_time": "08:00",
    "end_time": "09:00",
    "date": "2026-01-25"
  }
  ```

### Response
- HTTP Status: 200 OK
- JSON Body:
  ```json
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
  ```

## API: Tasks

### Endpoint
- Method: PUT
- Path: /api/tasks/:id

### Request
- Partial JSON Body (only fields to update):
  ```json
  {
    "title": "Làm bài tập",
    "is_done": true
  }
  ```

### Response
- HTTP Status: 200 OK
- JSON Body:
  ```json
  {
    "id": 1,
    "title": "Làm bài tập",
    "is_done": true,
    "start_time": "08:00",
    "end_time": "09:00",
    "date": "2026-01-25",
    "created_at": "2026-01-25T08:00:00Z",
    "updated_at": "2026-01-25T09:00:00Z"
  }
  ```
- HTTP Status: 404 Not Found
- JSON Body:
  ```json
  {
    "message": "Task not found"
  }
  ```

## API: Tasks

### Endpoint
- Method: DELETE
- Path: /api/tasks/:id

### Response
- HTTP Status: 200 OK
- JSON Body:
  ```json
  {
    "message": "Task deleted"
  }
  ```

## API: Goals

### Endpoint
- Method: GET
- Path: /api/goals

### Request
- Query params (optional):
  - type (`day|month|year`)
  - date (YYYY-MM-DD)
  - month (YYYY-MM)
  - year (YYYY)

### Response
- HTTP Status: 200 OK
- JSON Body:
  ```json
  [
    {
      "id": 1,
      "title": "Đọc sách",
      "type": "day",
      "date": "2026-01-25",
      "is_done": true,
      "created_at": "2026-01-25T08:00:00Z",
      "updated_at": "2026-01-25T09:00:00Z"
    }
  ]
  ```

## API: Goals

### Endpoint
- Method: POST
- Path: /api/goals

### Request
- JSON Body:
  ```json
  {
    "title": "Đọc sách",
    "type": "day",
    "date": "2026-01-25"
  }
  ```

### Response
- HTTP Status: 200 OK
- JSON Body:
  ```json
  {
    "id": 1,
    "title": "Đọc sách",
    "type": "day",
    "date": "2026-01-25",
    "is_done": false,
    "created_at": "2026-01-25T08:00:00Z",
    "updated_at": "2026-01-25T09:00:00Z"
  }
  ```

## API: Goals

### Endpoint
- Method: DELETE
- Path: /api/goals/:id

### Response
- HTTP Status: 200 OK
- JSON Body:
  ```json
  {
    "message": "Goal deleted"
  }
  ```

## API: Statistics

### Endpoint
- Method: GET
- Path: /api/stats

### Request
- Query params (optional):
  - date (YYYY-MM-DD)
  - month (YYYY-MM)

### Response
- HTTP Status: 200 OK
- JSON Body:
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