---
phase: 6
title: "Seed Automation Testing API template"
status: pending
priority: P1
effort: "0.5d"
dependencies: [2, 3, 4, 5]
---

# Phase 6: Seed Automation Testing API template

## Overview

Build `PipelineTemplateDocument` mới `template_id="automation-testing-api"`, name **"Automation Testing API"**, là DAG kết nối toàn bộ node đã chuẩn bị ở Phase 2-5. Seed idempotent vào `app/db/seed.py`. Đây là deliverable đầu tiên user nhìn thấy trong UI list templates.

## Requirements

**Functional**
- Template seed tự động khi start backend (qua `seed_pipeline_templates`).
- Template **chỉ chấp nhận** `.md` file ở runtime: thêm validation runtime check trong `_validate_upload` hoặc trong `MDSpecVerifierCrew` (đã handle ở Phase 2).
- DAG đầy đủ: INPUT → md_api_spec_verifier → ingestion → testcase chain → test_level_classifier → automation_agent → coverage_pre → report_pre → execution chain → artifact_crew → reporting chain → export_html_docx → report_verifier → OUTPUT.
- `is_builtin=true`, `tags=["automation-testing", "api", "md"]`.

**Non-functional**
- Không xóa/thay template `auto-testing` cũ (giữ backward compat).
- Idempotent: chạy lại không tạo duplicate (đã có `get_pipeline_template` check).

## Architecture

DAG layer plan (longest path) — đại đa số sequential, có 2 nhánh có thể parallel:

```
Layer 0: [INPUT]
Layer 1: [md_api_spec_verifier]
Layer 2: [ingestion_pipeline]
Layer 3: [requirement_analyzer]
Layer 4: [rule_parser]
Layer 5: [scope_classifier]
Layer 6: [data_model_agent]
Layer 7: [test_condition_agent]
Layer 8: [dependency_agent]
Layer 9: [test_case_generator]
Layer 10: [test_level_classifier]               (NEW)
Layer 11: [automation_agent, coverage_agent_pre] (parallel)
Layer 12: [report_agent_pre]
Layer 13: [execution_orchestrator]
Layer 14: [env_adapter]
Layer 15: [test_runner]                          (filter executable)
Layer 16: [execution_logger]
Layer 17: [result_store, artifact_crew]          (parallel)
Layer 18: [coverage_analyzer]
Layer 19: [root_cause_analyzer]
Layer 20: [report_generator]
Layer 21: [export_html_docx]                     (NEW)
Layer 22: [report_verifier]                      (NEW)
Layer 23: [OUTPUT]
```

## Related Code Files

- Modify: `backend/app/db/seed.py` — thêm `AUTOMATION_TESTING_API_TEMPLATE` dict + gọi seed
- Modify: `backend/app/api/v1/pipeline/_helpers.py` — extension whitelist riêng cho template này (optional: validation runtime trong verifier crew đã đủ)
- Read: `backend/app/db/models.py` — `PipelineNodeConfig`, `PipelineEdgeConfig` shape

## Implementation Steps

1. Tạo helper `_build_automation_testing_api_template() -> dict` trong `seed.py` (giảm verbosity vs. inline dict — vẫn dưới 200 LOC nếu split).
2. Trong helper, build từng node theo `node_type`:
   - INPUT: type=`input`
   - md_api_spec_verifier, ingestion_pipeline, test_level_classifier, automation_agent, artifact_crew, export_html_docx, report_verifier: type=`pure_python` (hoặc `agent` nếu factory hỗ trợ tốt hơn)
   - Còn lại: `agent`
3. Build edges sequential theo layer plan.
4. Gọi từ `seed_pipeline_templates()` (sau template `auto-testing`).
5. Verify qua API:
   ```
   POST /pipeline-templates/automation-testing-api/validate
   ```
   trả `valid=true`.
6. Smoke test runtime: `POST /pipeline/runs` với fixture MD valid → run hoàn tất, có report verified.

## Success Criteria

- [ ] Sau khi backend startup, `GET /pipeline-templates?tag=automation-testing` trả template mới với `is_builtin=true`.
- [ ] Validate DAG passes (no cycle, 1 INPUT, 1 OUTPUT, all reachable).
- [ ] Smoke run với MD valid hoàn tất `status=completed` trong < 5 phút (mock_mode) hoặc < 15 phút (real LLM).
- [ ] Smoke run với MD thiếu Endpoint → `status=failed`, error_message JSON có `missing_sections`.

## Risk Assessment

- **Risk:** Quá nhiều layer (~24) → latency cao. **Mitigation:** Đa số node lightweight; layer 11 + 17 đã parallel sẵn.
- **Risk:** Seed run trên DB cũ có node_id trùng. **Mitigation:** Prefix `node_id` với `at-api-` để tránh đụng template cũ.

## Next Steps

Phase 7 expose template này trong FE — user chọn "Automation Testing API" từ dropdown khi tạo run.
