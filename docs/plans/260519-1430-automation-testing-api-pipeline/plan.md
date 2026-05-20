---
title: "Automation Testing API Pipeline"
description: "Pipeline DAG nhận Markdown spec API, verify request/response/endpoint, sinh Unit/IT test cases tối đa coverage, execute case khả thi, sinh report HTML/DOCX và verify trước khi trả người dùng."
status: in_progress
priority: P1
branch: "develop"
tags: ["pipeline", "automation-testing", "md-spec", "backend", "dag"]
blockedBy: []
blocks: []
created: "2026-05-19T15:56:25.258Z"
createdBy: "ck:plan"
source: skill
---

# Automation Testing API Pipeline

## Overview

Tạo **pipeline template mới** `automation-testing-api` trong hệ thống Auto-AT v3 (DAG-based).
Luồng: upload file `.md` mô tả API → guard verify (endpoint + request + response) → ingestion → testcase generation (gắn tag `test_level=unit|integration|e2e`, tối đa coverage) → artifact crew sinh file unit test → execution crew chạy chỉ những case `executable=true` → reporting crew + export HTML/DOCX → report verifier kiểm tra report đủ 3 thành phần (test case info / kết quả / unit test files) trước khi user tải xuống.

Các thành phần **mới** cần thêm vào source hiện tại:

1. Tool `md_api_spec_validator` (pure-python) + agent_config `md_api_spec_verifier`.
2. Tag `test_level` trong `TestCase` schema + prompt update cho `test_case_generator` & node mới `test_level_classifier`.
3. Cờ `executable: bool` trong `TestCase` + filter trong `ExecutionCrew._real_run` / `_mock_run`.
4. Tool `report_verifier` + agent_config `report_verifier` + endpoint `POST /pipeline/runs/{run_id}/report/verify`.
5. Pipeline template `automation-testing-api` seed mới (vẫn theo `PipelineTemplateDocument`).
6. Custom error class `MDSpecValidationError` + propagation qua `DAGPipelineRunner` → HTTP 422 cho user.

Tuyệt đối **không** ghi đè agent / template / tool hiện có; mọi thứ thêm mới hoặc mở rộng tương thích ngược (additive).

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Research MD spec contract](./phase-01-research-md-spec-contract.md) | Complete |
| 2 | [MD Spec Verifier tool](./phase-02-md-spec-verifier-tool.md) | Complete |
| 3 | [Test-level tagging (Unit/IT)](./phase-03-test-level-tagging-unit-it.md) | Complete |
| 4 | [Executable filter in Execution](./phase-04-executable-filter-in-execution.md) | Complete |
| 5 | [Report Verifier tool](./phase-05-report-verifier-tool.md) | Complete |
| 6 | [Seed Automation Testing API template](./phase-06-seed-automation-testing-api-template.md) | Complete |
| 7 | [API + Frontend integration](./phase-07-api-frontend-integration.md) | Complete (BE + shared FE) |
| 8 | [Tests and docs](./phase-08-tests-and-docs.md) | Complete (30 unit tests pass; e2e + Playwright pending) |

## Key Dependencies

- **Phase 2** blocks Phase 6 (verifier tool phải sẵn trước khi seed template).
- **Phase 3** blocks Phase 4 (cần field `test_level` & `executable` trên TestCase trước khi filter).
- **Phase 5** blocks Phase 6 và Phase 7.
- **Phase 6** blocks Phase 7 (template tồn tại → FE chọn được).
- **Phase 8** chạy sau toàn bộ.

## Architecture Sketch

```
INPUT (md file)
  → md_api_spec_verifier (guard: pass/fail with structured error)
  → ingestion_pipeline (parse + extract requirements)
  → requirement_analyzer → rule_parser → scope_classifier → data_model_agent
  → test_condition_agent → dependency_agent → test_case_generator
  → test_level_classifier            [NEW: tag unit / integration / e2e]
  → automation_agent → coverage_agent_pre → report_agent_pre
  → execution_orchestrator → env_adapter
  → test_runner                      [filter: executable=true only]
  → execution_logger → result_store
  → artifact_crew (sinh file unit test)
  → coverage_analyzer → root_cause_analyzer → report_generator
  → export_html_docx                 [NEW node: gọi ExportService → MinIO]
  → report_verifier                  [NEW guard: 3-component check]
  → OUTPUT (download link + verification summary)
```

## Risks

- Schema MD spec không chuẩn → verifier quá strict gây false-negative. Mitigation: rule-based + LLM-assist fallback, lỗi rõ ràng kèm field thiếu.
- Token cost tăng do thêm classifier. Mitigation: `test_level_classifier` chạy rule-first (URL/method có → integration), LLM-fallback nếu thiếu thông tin.

## Cross-Plan Dependencies

Không có plan đang chạy chồng lấn (`260518-1100-split-user-pipeline-fe` chỉ động đến FE user-app, không sửa backend pipeline core).
