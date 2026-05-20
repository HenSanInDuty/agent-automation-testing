---
phase: 2
title: "MD Spec Verifier tool"
status: pending
priority: P1
effort: "1d"
dependencies: [1]
---

# Phase 2: MD Spec Verifier tool

## Overview

Implement tool pure-python kiểm tra file MD có đúng contract Phase 1 không, đăng ký thành agent (`md_api_spec_verifier`) để dùng làm node `pure_python` đầu chuỗi DAG. Nếu fail → raise structured error, runner mark `run.failed` với `error_type=md_spec_validation`.

## Requirements

**Functional**
- Nhận `document_content` (đã parse từ `parse_document`) hoặc `file_path` `.md`.
- Trả `{ valid: bool, missing_sections: [...], missing_fields: [...], parsed: { endpoint: {...}, request: {...}, responses: [...] }, warnings: [...] }`.
- Output `parsed` được forward downstream để testcase generator tận dụng (đỡ phải LLM-parse lại).
- Strict mode (default ON) → fail-fast. Non-strict → warnings only.

**Non-functional**
- < 200 LOC cho main module.
- Không phụ thuộc LLM (rule-based hoàn toàn) → chạy nhanh, deterministic.
- Cover các synonym phổ biến của heading (EN/VN).

## Architecture

Module tổ chức theo pattern hiện tại trong `app/tools/`:

```
app/tools/md_api_spec_validator.py     # core function validate_md_api_spec()
app/tools/md_api_spec_validator_tool.py # CrewAI BaseTool wrapper (optional)
```

Đăng ký vào `app/tools/registry.py` với tên `md_api_spec_validator`.

Tạo agent_config `md_api_spec_verifier` trong `app/db/seed.py` (stage = `ingestion`, `node_type=pure_python` trong template). Crew wrapper mới `MDSpecVerifierCrew` đặt ở `app/crews/md_spec_verifier_crew.py`.

Error class:

```python
# app/core/errors.py
class MDSpecValidationError(Exception):
    def __init__(self, code: str, missing: list[str], detail: str):
        self.code = code
        self.missing = missing
        self.detail = detail
```

Trong `DAGPipelineRunner._run_agent_node()` bắt `MDSpecValidationError` → set `error_type="md_spec_validation"` + đẩy `missing` lên `error_message` để API trả về client. Không retry khi gặp lỗi này.

## Related Code Files

- Create: `backend/app/tools/md_api_spec_validator.py`
- Create: `backend/app/crews/md_spec_verifier_crew.py`
- Create: `backend/app/core/errors.py`
- Modify: `backend/app/tools/registry.py` — đăng ký tool mới
- Modify: `backend/app/tools/__init__.py` — export
- Modify: `backend/app/db/seed.py` — thêm `md_api_spec_verifier` vào `DEFAULT_AGENT_CONFIGS`
- Modify: `backend/app/core/dag_pipeline_runner.py` — handle `MDSpecValidationError` riêng
- Modify: `backend/app/core/agent_factory.py` — route `agent_id="md_api_spec_verifier"` → crew pure-python
- Modify: `backend/app/crews/__init__.py` — export `MDSpecVerifierCrew`
- Read (context): `backend/app/crews/ingestion_crew.py` (pattern pure-python crew)

## Implementation Steps

1. Tạo `md_api_spec_validator.py` với:
   - `_extract_sections(md_text) -> dict[str, str]` (split theo H2 + normalize heading)
   - `_parse_endpoint(section) -> dict` (regex `Method:` / `Path:` / `Auth:`)
   - `_parse_request(section) -> dict` (parse bảng markdown → `body_fields[]`)
   - `_parse_responses(section) -> list[dict]` (regex `\b[1-5]\d{2}\b` → status + payload)
   - `validate_md_api_spec(text, strict=True) -> ValidationResult` (Pydantic model)
2. Define `MDSpecValidationError` trong `app/core/errors.py`.
3. Wrap thành `MDSpecVerifierCrew(BaseCrew)` → `.run({"document_content": ..., "strict": bool})`; raise `MDSpecValidationError` khi `strict and not valid`.
4. Đăng ký vào `ToolRegistry`; sửa `AgentFactory.build()` để khi `agent_id == "md_api_spec_verifier"` thì dispatch sang crew pure-python (mô phỏng cách `ingestion_pipeline` được handle trong `DAGPipelineRunner`).
5. Seed agent_config — `stage="ingestion"`.
6. Trong `DAGPipelineRunner`, khi node raise `MDSpecValidationError`, **bypass retry**; mark `failed` ngay với error JSON có cấu trúc:
   ```json
   {"error_type": "md_spec_validation", "code": "MD_SPEC_MISSING_ENDPOINT", "missing_sections": [...], "missing_fields": [...], "detail": "..."}
   ```
7. Đảm bảo error JSON này được serialize lên WS event `node.failed` + lưu vào `PipelineRunDocument.error` để FE đọc được.

## Success Criteria

- [ ] `pytest backend/tests/test_md_api_spec_validator.py` xanh với 4 fixture Phase 1.
- [ ] Khi MD thiếu Endpoint, GET `/pipeline/runs/{id}` trả `error_message` JSON có `missing_sections=["endpoint"]`.
- [ ] Khi MD valid, output `parsed` lưu vào `PipelineResultDocument` và visible khi `include_results=true`.
- [ ] Không retry khi `MDSpecValidationError` (node.failed emit 1 lần duy nhất).

## Risk Assessment

- **Risk:** Markdown table parsing edge case (escape pipe `\|`). **Mitigation:** Parse line-by-line, fixture cover edge case.
- **Risk:** AgentFactory hiện chỉ build CrewAI Agent. **Mitigation:** Đọc `agent_factory.py` để áp dụng đúng pattern `ingestion_pipeline` đã có.

## Security Considerations

- Tránh regex catastrophic backtracking: pattern an toàn, không quantifier lồng nhau.
- File size đã được guard bởi upload helper (`MAX_FILE_SIZE_MB`).

## Next Steps

Phase 3 dùng `parsed.endpoint` + `parsed.responses` để gán `test_level` chính xác (có URL → integration; chỉ có rule → unit).
