# Automation Testing API — MD Spec Contract (v1)

> Contract chính tắc cho file `.md` mô tả API mà user upload vào pipeline
> `automation-testing-api`. Là input cho tool `md_api_spec_validator` (Phase 2)
> và classifier `test_level_classifier` (Phase 3).

---

## 1. Mục tiêu

- Đủ thông tin để verifier phát hiện sớm spec thiếu/sai → fail-fast trước khi vào DAG.
- Đủ structure để testcase generator sinh được unit + integration cases.
- Dev viết tay được, không bắt YAML/OpenAPI lồng.
- Hỗ trợ 1 endpoint/file và nhiều endpoint/file.

## 2. Required sections (H2 level)

Mỗi file MD spec **phải** chứa **ít nhất** 3 H2 section sau (heading
case-insensitive; synonym được chấp nhận):

| Canonical name | Synonyms (regex, case-insensitive) | Required keys bên trong |
|----------------|-----------------------------------|-------------------------|
| `## Endpoint`  | `endpoint`, `api endpoint`, `api`  | `Method:`, `Path:`      |
| `## Request`   | `request`, `req`, `request payload`| Bảng body khi method ∈ POST/PUT/PATCH |
| `## Response`  | `response`, `responses`, `resp`    | ≥ 1 status code (regex `\b[1-5]\d{2}\b`) |

> Một số section khác (`## Auth`, `## Examples`, `## Errors`, `## Notes`) là
> optional — verifier không reject nếu thiếu.

## 3. Section formatting rules

### 3.1 `## Endpoint`

Tối thiểu 2 line bullet hoặc key-value pair, regex được chấp nhận:

```
- Method: POST
- Path: /api/v1/users
- Auth: Bearer            # optional
```

- `Method:` phải là 1 trong `GET | POST | PUT | PATCH | DELETE | HEAD | OPTIONS`.
- `Path:` bắt đầu bằng `/`. Hỗ trợ path param `{id}` hoặc `:id`.
- `Auth:` optional.

### 3.2 `## Request`

Bắt buộc khi `Method ∈ {POST, PUT, PATCH}`. Hỗ trợ 2 format:

**A. Markdown table** (recommended):

```
| field    | type   | required | rules                       |
| -------- | ------ | -------- | --------------------------- |
| username | string | yes      | 3-32 chars, alphanumeric    |
| password | string | yes      | min 8                       |
```

Yêu cầu cột: `field`, `type`, `required` (3 cột bắt buộc). Cột `rules`,
`description`, `example` là optional.

**B. JSON schema block**:

```
- Content-Type: application/json
- Body schema:
  ```json
  {
    "username": "string (3-32, alphanumeric, required)",
    "password": "string (min 8, required)"
  }
  ```
```

> Khi method ∈ `{GET, DELETE, HEAD, OPTIONS}` thì `## Request` có thể trống
> hoặc chỉ chứa `Query params:` — verifier sẽ không bắt body.

### 3.3 `## Response`

Bắt buộc ≥ 1 status code dạng `### 201 Created` hoặc `- 201 Created: { ... }`.

```
- 201 Created: { "id": "string", "username": "string" }
- 400 Bad Request: { "error": "string" }
- 401 Unauthorized
```

Status code: regex `\b[1-5]\d{2}\b` (100–599).

## 4. Multi-endpoint files

Mỗi endpoint phải có nhóm 3 H2 (`## Endpoint`, `## Request`, `## Response`) hoặc
được wrap dưới `## API: <name>` (H2) + 3 H3 (`### Endpoint`, `### Request`,
`### Response`). Verifier tự suy biến theo cấu trúc heading.

```
## API: Create User

### Endpoint
- Method: POST
- Path: /api/v1/users

### Request
| field    | type   | required |
| -------- | ------ | -------- |
| username | string | yes      |

### Response
- 201 Created
- 400 Bad Request

## API: Get User

### Endpoint
- Method: GET
- Path: /api/v1/users/{id}

### Response
- 200 OK
- 404 Not Found
```

## 5. Error codes — verifier output

Verifier output `code` (1 lỗi đầu tiên gặp được, ưu tiên Endpoint → Request → Response):

| Code                                  | Khi nào |
|---------------------------------------|---------|
| `MD_SPEC_MISSING_ENDPOINT`            | Không tìm thấy section Endpoint hoặc thiếu `Method:` / `Path:` |
| `MD_SPEC_MISSING_REQUEST_BODY`        | Method ∈ {POST,PUT,PATCH} mà thiếu Request section / body schema |
| `MD_SPEC_MISSING_RESPONSE_STATUS`     | Section Response không có status code nào |
| `MD_SPEC_INVALID_METHOD`              | `Method:` không thuộc whitelist HTTP method |
| `MD_SPEC_INVALID_PATH`                | `Path:` không bắt đầu bằng `/` |
| `MD_SPEC_MULTIPLE_ENDPOINTS_AMBIGUOUS`| File có ≥ 2 nhóm endpoint nhưng không wrap bằng `## API: <name>` |

## 6. Strict mode vs warn mode

Verifier nhận `strict: bool = True`.
- `strict=True` (default): bất kỳ lỗi nào ở §5 → raise `MDSpecValidationError`.
- `strict=False`: ghi vào `warnings[]`, vẫn forward `parsed` xuống stage tiếp.

Toggle qua `run_params.strict_md_spec` khi POST `/pipeline/runs`.

## 7. Versioning

- `v1` (this doc) — initial release 2026-05-19.
- Mỗi bump version → thêm field `version: 1` ở YAML frontmatter của MD spec.
  Nếu thiếu → assume v1.

## 8. Reference fixtures

Tham chiếu `backend/tests/fixtures/md_specs/`:

| File                                | Mô tả                              |
|-------------------------------------|------------------------------------|
| `valid_login.md`                    | 1 endpoint POST /login đầy đủ      |
| `invalid_missing_endpoint.md`       | Thiếu section Endpoint             |
| `invalid_missing_request.md`        | POST method nhưng không có Request |
| `invalid_missing_response.md`       | Thiếu section Response             |

## 9. Synonym list (configurable)

Heading synonym được nhận tại verifier (định nghĩa trong
`app/tools/md_api_spec_validator.py` constant `_SECTION_SYNONYMS`):

```python
_SECTION_SYNONYMS = {
    "endpoint": ["endpoint", "api endpoint", "api", "route", "uri"],
    "request":  ["request", "req", "request payload", "input", "body"],
    "response": ["response", "responses", "resp", "output", "result"],
}
```

User có thể custom thêm synonym qua `run_params.md_spec_synonyms` nếu cần.
