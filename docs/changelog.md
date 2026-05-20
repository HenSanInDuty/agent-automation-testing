19/05/2026 — Automation Testing API pipeline (plan 260519-1430):
- New pipeline template `automation-testing-api` (idempotent seed): MD-only input,
  guarded by `md_api_spec_verifier` → ingestion → testcase chain →
  `test_level_classifier` (NEW) → execution (skips non-executable cases) →
  artifact + reporting → `export_html_docx` (NEW) → `report_verifier` (NEW guard) → output.
- New tool `md_api_spec_validator` (pure-python) + structured error
  `MDSpecValidationError` (code / missing_sections / missing_fields). Runner
  bypasses retry for any `StructuredPipelineError` (`is_structured_pipeline_error`).
- `TestCase` schema gains `test_level ∈ {unit,integration,contract,e2e}`,
  `executable: bool`, `classification_confidence`, `skip_reason`.
- `ExecutionCrew` now splits runnable vs skipped by `executable`; `ExecutionSummary`
  gains `runnable_count`, `skipped_count`, `skipped_reasons`; pass_rate is
  computed against runnable denominator.
- Storage: new helper `storage.upload_report(run_id, html_bytes, docx_bytes)`.
- API: new endpoint `GET /pipeline/runs/{id}/report/verification`. Download
  endpoints `/export/html|docx` return **409** with `{error_type:"report_verification", components}`
  when verification fails; `?force=true` provides admin override.
- FE shared: `ReportVerificationResponse` / `MDSpecValidationErrorPayload` types,
  `useReportVerification` hook, `<ReportVerificationCard runId />` component.
- New fixtures: `backend/tests/fixtures/md_specs/{valid_login.md, invalid_missing_*}.md`.
- New tests: `test_md_api_spec_validator.py`, `test_test_level_tagger.py`,
  `test_executable_filter_execution_crew.py`, `test_report_verifier.py` — 30 cases pass.
- Contract doc: `docs/Flow/automation-testing-api-md-contract.md` (v1).

14/05/2026:
- Flow run many time in tester,
- agent execution -> exection test case -> re-gen test case -> agent execution (this is a cycle). 
When stop? 
- Pipeline must specific UI/API. Maybe unit test, it test ???

Problem
- Wrong input requirement

API requirement input:
UI requirement input:
Unit testing input:
