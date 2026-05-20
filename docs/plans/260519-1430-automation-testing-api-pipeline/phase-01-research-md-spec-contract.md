---
phase: 1
title: "Research MD spec contract"
status: pending
priority: P1
effort: "4h"
dependencies: []
---

# Phase 1: Research MD spec contract

## Overview

Định nghĩa **contract chính tắc** cho file `.md` mô tả API mà người dùng upload: cần section nào, cần key gì, mức độ "đủ thông tin" để pipeline tiếp tục. Đây là input cho Phase 2 (verifier tool) và Phase 3 (test_level classifier).

## Requirements

**Functional**
- Định nghĩa rõ ràng các trường bắt buộc và optional, có version cho contract.
- Có ít nhất 2 mẫu MD reference: 1 mẫu valid, 1 mẫu invalid với từng loại lỗi.
- Xác định mapping `MD section → RequirementItem` để ingestion crew tận dụng được.

**Non-functional**
- Format MD phải đủ đơn giản cho dev viết tay (không bắt OpenAPI YAML lồng).
- Hỗ trợ cả 1 endpoint/file và nhiều endpoint/file.

## Architecture

Contract đề xuất (v1) — tối thiểu **3 section** với heading chuẩn:

```
# <API name>

## Endpoint
- Method: POST
- Path: /api/v1/users
- Auth: Bearer

## Request
- Content-Type: application/json
- Body schema:
  | field    | type   | required | rules                       |
  | -------- | ------ | -------- | --------------------------- |
  | username | string | yes      | 3-32 chars, alphanumeric    |
  | password | string | yes      | min 8                       |

## Response
- 201 Created: { "id": "string", "username": "string" }
- 400 Bad Request: { "error": "string" }
- 401 Unauthorized
```

Verifier sẽ check **structural rules**:
- ít nhất 1 H2 `## Endpoint` chứa `Method:` + `Path:` (regex case-insensitive).
- ít nhất 1 H2 `## Request` (nếu method ∈ POST/PUT/PATCH bắt buộc có body schema).
- ít nhất 1 H2 `## Response` với ít nhất 1 status code (regex `\b[1-5]\d{2}\b`).

Thiếu bất kỳ section nào → trả `MDSpecValidationError` với `missing_sections=[...]`, `missing_fields=[...]`.

## Related Code Files

- Read: `backend/app/tools/document_parser.py` (đã hỗ trợ `.md`)
- Read: `backend/app/crews/ingestion_crew.py` (để biết RequirementItem schema)
- Read: `docs/document_test/oauth_pkce_flow.md`, `docs/document_test/mobile-sso.md` (sample format hiện tại)
- Create: `docs/Flow/automation-testing-api-md-contract.md` (contract chính thức v1)
- Create: `backend/tests/fixtures/md_specs/valid_login.md`, `.../invalid_missing_response.md`, `.../invalid_missing_endpoint.md`, `.../invalid_missing_request.md`

## Implementation Steps

1. Đọc 2 sample hiện có trong `docs/document_test/` để xác định convention thực tế đã dùng.
2. Viết `automation-testing-api-md-contract.md` mô tả:
   - Required H2 sections + tên chuẩn.
   - Regex/keyword chấp nhận biến thể (e.g. `## Endpoint` ≈ `## API Endpoint`).
   - Cách viết bảng request body / response schema.
3. Tạo 4 fixture `.md`: 1 valid, 3 invalid (mỗi loại thiếu 1 section).
4. Document lỗi mã chuẩn:
   - `MD_SPEC_MISSING_ENDPOINT`
   - `MD_SPEC_MISSING_REQUEST_BODY`
   - `MD_SPEC_MISSING_RESPONSE_STATUS`
   - `MD_SPEC_MULTIPLE_ENDPOINTS_AMBIGUOUS` (nếu cần)
5. Review với chính người dùng (output: contract file checked into repo).

## Success Criteria

- [ ] `docs/Flow/automation-testing-api-md-contract.md` tồn tại, được commit.
- [ ] 4 fixture MD trong `backend/tests/fixtures/md_specs/` đã được commit.
- [ ] Mỗi mã lỗi có 1 fixture tương ứng để Phase 2 dùng làm test case.
- [ ] Reviewer xác nhận contract đủ chặt nhưng không cản trở dev viết MD tay.

## Risk Assessment

- **Risk:** Contract quá ngặt → user phải sửa MD mỗi lần. **Mitigation:** Phase 2 cho phép `--strict-mode` off (chỉ warning) qua `run_params`.
- **Risk:** Heading tiếng Việt khác convention. **Mitigation:** Cho phép synonym list cấu hình được trong tool.

## Next Steps

Đưa contract vào Phase 2 implementation; fixture được test trực tiếp bởi `pytest` ở Phase 8.
