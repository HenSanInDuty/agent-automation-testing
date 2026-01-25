# API Documentation - Todo Application

This document provides a detailed overview of the API endpoints available in the Todo application backend. All endpoints are prefixed with `/api`.

## Data Models

### Task
Represents a todo item.
| Field | Type | Description | format |
| :--- | :--- | :--- | :--- |
| `id` | `uint` | Primary key | |
| `title` | `string` | Task title | |
| `is_done` | `bool` | Completion status | |
| `start_time` | `string` | Start time | `HH:mm` |
| `end_time` | `string` | End time | `HH:mm` |
| `date` | `string` | Task date | `YYYY-MM-DD` |

### Goal
Represents a goal (daily, monthly, or yearly).
| Field | Type | Description | format |
| :--- | :--- | :--- | :--- |
| `id` | `uint` | Primary key | |
| `title` | `string` | Goal title | |
| `type` | `string` | Goal type | `day`, `month`, or `year` |
| `date` | `string` | Date for 'day' goals | `YYYY-MM-DD` |
| `month` | `string` | Month for 'month' goals | `YYYY-MM` |
| `year` | `string` | Year for 'year' goals | `YYYY` |
| `is_done` | `bool` | Completion status | |

---

## Endpoints

### 1. Tasks

#### Get All Tasks
- **URL**: `GET /api/tasks`
- **Query Parameters**:
    - `date` (optional): Filter tasks by date (`YYYY-MM-DD`)
- **Response**: `200 OK`
- **Example Response**:
  ```json
  [
    {
      "id": 1,
      "title": "Làm bài tập",
      "is_done": false,
      "start_time": "08:00",
      "end_time": "09:00",
      "date": "2026-01-25"
    }
  ]
  ```

#### Create Task
- **URL**: `POST /api/tasks`
- **Body**:
  ```json
  {
    "title": "Đi chợ",
    "is_done": false,
    "start_time": "10:00",
    "end_time": "11:00",
    "date": "2026-01-25"
  }
  ```
- **Response**: `200 OK` (returns the created object)

#### Update Task
- **URL**: `PUT /api/tasks/:id`
- **Body**: Partial Task object
  ```json
  {
    "is_done": true
  }
  ```
- **Response**: `200 OK` (returns the updated object)

#### Delete Task
- **URL**: `DELETE /api/tasks/:id`
- **Response**: `200 OK`
  ```json
  {
    "message": "Task deleted"
  }
  ```

---

### 2. Goals

#### Get Goals
- **URL**: `GET /api/goals`
- **Query Parameters**:
    - `type` (optional): `day`, `month`, or `year`
    - `date` (optional): `YYYY-MM-DD`
    - `month` (optional): `YYYY-MM`
    - `year` (optional): `YYYY`
    - **Note**: If `date`, `month`, and `year` are all provided, it fetches all relevant goals for that specific date context across types.
- **Response**: `200 OK`

#### Create Goal
- **URL**: `POST /api/goals`
- **Body**:
  ```json
  {
    "title": "Học tiếng Anh mỗi ngày",
    "type": "month",
    "month": "2026-01"
  }
  ```
- **Response**: `200 OK`

#### Delete Goal
- **URL**: `DELETE /api/goals/:id`
- **Response**: `200 OK`
  ```json
  {
    "message": "Goal deleted"
  }
  ```

---

### 3. Statistics

#### Get Stats
- **URL**: `GET /api/stats`
- **Query Parameters**:
    - `date` (optional): `YYYY-MM-DD` (defaults to today)
    - `month` (optional): `YYYY-MM` (for success days list)
- **Response**: `200 OK`
- **Example Response**:
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
