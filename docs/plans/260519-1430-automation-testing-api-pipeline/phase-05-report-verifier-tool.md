---
phase: 5
title: "Report Verifier tool"
status: pending
priority: P1
effort: "1d"
dependencies: [4]
---

# Phase 5: Report Verifier tool

## Overview

Tool + agent kiểm tra **file report** (HTML/DOCX) cuối cùng đảm bảo đủ 3 thành phần theo yêu cầu user: (1) test case info, (2) execution results, (3) unit test files sinh ra. Nếu không đủ → fail, không gửi cho user.

## Requirements

**Functional**
- Đọc artifact đã sinh:
  - Report HTML/DOCX trong MinIO `runs/{run_id}/report.html` & `report.docx`.
  - Test case JSON từ `PipelineResultDocument(stage="testcase")`.
  - Execution results từ stage `execution`.
  - Unit test files từ stage `artifact` (`unit_test_files: list[UnitTestFile]`).
- Kiểm tra 3 component:
  - **Test cases**: count > 0, mỗi case có id, title, expected_result.
  - **Results**: tỉ lệ pass_rate hiển thị, có bảng results (runnable + skipped).
  - **Unit test files**: count > 0, mỗi file có `path`, `language`, `content` non-empty và parse được (syntax-light check).
- Output verification report:
  ```json
  {
    "verified": true,
    "components": {
      "test_cases": {"ok": true, "count": 23, "issues": []},
      "results": {"ok": true, "pass_rate": 0.82, "issues": []},
      "unit_test_files": {"ok": true, "count": 8, "issues": []}
    },
    "html_url": "minio://...",
    "docx_url": "minio://...",
    "summary": "Report ready for delivery"
  }
  ```
- Nếu fail → raise `ReportVerificationError`, runner mark `failed`; HTML/DOCX vẫn upload lên MinIO (debug) nhưng không expose link tải.

**Non-functional**
- Không gọi LLM — pure check.
- Hỗ trợ verify cả file đã upload lên MinIO lẫn buffer trong-memory (testability).

## Architecture

```
report_generator → export_html_docx → report_verifier → OUTPUT
                  (NEW node)         (NEW node)
```

`export_html_docx` node là `pure_python` crew gọi `ExportService.export_html()` + `export_docx()` và upload lên MinIO via `StorageService`. Output trả paths.

`report_verifier` node `pure_python` crew gọi tool mới.

## Related Code Files

- Create: `backend/app/tools/report_verifier.py` (core function + Pydantic models)
- Create: `backend/app/crews/report_verifier_crew.py`
- Create: `backend/app/crews/export_crew.py` (wrapper cho ExportService trong DAG)
- Create: `backend/app/core/errors.py` thêm `ReportVerificationError` (cùng file Phase 2)
- Modify: `backend/app/services/storage_service.py` — method `upload_report(run_id, html_bytes, docx_bytes)` nếu chưa có
- Modify: `backend/app/db/seed.py` — thêm 2 agent_configs `export_html_docx`, `report_verifier` (stage=`reporting`)
- Modify: `backend/app/api/v1/pipeline/results.py` — endpoint `GET /pipeline/runs/{run_id}/report/verification` trả result
- Modify: `backend/app/api/v1/pipeline/results.py` — endpoint download chỉ trả file khi `verified=true` (hoặc `?force=true` cho admin)

## Implementation Steps

1. Tạo `ExportCrew(BaseCrew)`:
   - `run({"run_id":...})` → gọi `ExportService(run_id).export_html()` + `.export_docx()`
   - Upload via `storage.upload_report(...)`
   - Trả `{"html_path": "...", "docx_path": "...", "html_bytes": int, "docx_bytes": int}`.
2. Tạo `report_verifier.py`:
   - `verify_report(test_cases, results, unit_test_files, html_bytes, docx_bytes) -> VerificationResult`
   - Check 3 component như spec; syntax-light cho python = `compile(content, path, "exec")`, cho JS/TS = bracket-balance check (light).
3. Tạo `ReportVerifierCrew` wrap tool.
4. Seed 2 agent_configs mới, stage=`reporting`.
5. Endpoint download (đã có?): cập nhật `results.py` (`GET .../export/html|docx`):
   - Load latest verification result trong DB.
   - Nếu `verified=false`, trả 409 với detail từ `verification.components.*.issues`.
6. Endpoint mới `GET .../report/verification` trả raw verification JSON (UI hiển thị tóm tắt trước khi user download).

## Success Criteria

- [ ] Verification fail khi `unit_test_files=[]` → API trả 409 trên download.
- [ ] Verification pass khi đủ 3 component → HTML/DOCX download được.
- [ ] UI hiển thị badge "✅ Verified" cùng count test cases / pass rate / unit test files.
- [ ] Verification kết quả lưu trong `PipelineResultDocument(stage="reporting", agent_id="report_verifier")`.

## Risk Assessment

- **Risk:** Compile check python false-negative (syntax phụ thuộc python version). **Mitigation:** Dùng `ast.parse()` thay vì `compile()`, ignore exec warnings.
- **Risk:** MinIO down → upload fail. **Mitigation:** Verify in-memory bytes trước, upload sau; nếu upload fail thì retry separate.

## Security Considerations

- Download endpoint phải authn (đã có `get_current_user` dep) — không lộ link MinIO trực tiếp.
- Force-override download (`?force=true`) chỉ admin.

## Next Steps

Phase 6 đưa cả `export_html_docx` + `report_verifier` vào template.
