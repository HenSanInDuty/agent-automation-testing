---
phase: 9
title: "Backend Adjustments (RBAC tightening)"
status: pending
priority: P1
effort: "4h"
dependencies: [1]
---

# Phase 9: Backend Adjustments (RBAC tightening)

## Overview
Vì user-app sẽ public hơn admin-app, cần đảm bảo backend **enforce** mọi endpoint write template/LLM/agent/user chỉ cho phép `ADMIN`. Đồng thời thêm origin `http://localhost:3002` (và prod URL) vào CORS, và (tùy) lưu `user_id` của run để hỗ trợ "my runs" về sau.

## Requirements
- Functional:
  - Mọi endpoint `POST/PUT/DELETE /api/v1/pipeline-templates*` đều có `Depends(require_admin)`.
  - Endpoint `POST/PUT/DELETE /api/v1/admin/*` đã có `require_admin` (verify).
  - `POST /api/v1/pipeline/runs` cho phép `QA` + `ADMIN`; `GET` cho `VIEWER` trở lên.
  - `POST /api/v1/pipeline/runs/{id}/pause|resume|cancel` chỉ `QA`+`ADMIN`.
  - CORS `ALLOWED_ORIGINS` thêm `http://localhost:3002`.
  - (Optional) `PipelineRun` Beanie model thêm `triggered_by: str` (= username) — populate khi tạo run.
- Non-functional:
  - Audit log Kafka topic `api_requests` đã capture user_id (từ ObservabilityMiddleware). Verify.

## Architecture
Áp dụng dependency `require_admin()` đã có:
```python
from app.auth.deps import require_admin, require_qa, get_current_user

@router.post("/pipeline-templates", dependencies=[Depends(require_admin)])
async def create_template(...): ...
```

## Related Code Files
- Modify:
  - `backend/app/api/v1/pipeline_templates.py` — thêm `require_admin` cho mọi write
  - `backend/app/api/v1/pipeline.py` — verify `require_qa` cho start/pause/resume/cancel
  - `backend/app/api/v1/admin/*.py` — verify
  - `backend/app/main.py` — thêm origin 3002 vào CORS default
  - `backend/app/models/pipeline_run.py` (nếu thêm `triggered_by`)
  - `docker-compose.yml` — `ALLOWED_ORIGINS` env include 3002
- Read:
  - `backend/app/auth/deps.py` để hiểu RBAC hiện tại
  - `backend/app/api/v1/**` để inventory endpoint

## Implementation Steps
1. Grep tất cả `@router.post`, `@router.put`, `@router.delete` trong `backend/app/api/v1/` — list nào thiếu `require_admin`/`require_qa`.
2. Áp `Depends(require_admin)` cho mọi write template/LLM/agent/user.
3. Áp `Depends(require_qa)` cho start/pause/resume/cancel run.
4. Cập nhật `ALLOWED_ORIGINS` default trong `app/config.py` (nếu có) — `["http://localhost:3001","http://localhost:3002"]`.
5. Cập nhật `docker-compose.yml` env `ALLOWED_ORIGINS=http://localhost:3001,http://localhost:3002`.
6. (Optional) Thêm field `triggered_by` vào `PipelineRun`:
   ```python
   triggered_by: str | None = None  # username từ get_current_user
   ```
   Update endpoint `POST /pipeline/runs` populate field này.
7. Viết test pytest:
   - viewer login → POST pipeline-templates → expect 403.
   - qa login → POST pipeline/runs → expect 201.
   - admin → write template → expect 200.

## Success Criteria
- [ ] pytest RBAC suite pass cho 3 roles trên các endpoint quan trọng.
- [ ] User-app gọi được API từ port 3002 (CORS OK).
- [ ] Endpoint write template từ user-app (mô phỏng) trả 403.

## Risk Assessment
- **R**: Sót endpoint write — user-app có thể vô tình PATCH template.
  **Mitigation**: dùng integration test gọi tất cả write endpoint với token viewer; assert 403.
- **R**: Thêm `triggered_by` mà chưa migrate document cũ → BSON missing field OK với Beanie, nhưng UI có thể vỡ.
  **Mitigation**: field optional `str | None`; UI fallback "Unknown".
