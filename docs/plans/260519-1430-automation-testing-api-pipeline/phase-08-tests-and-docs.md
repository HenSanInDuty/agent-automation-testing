---
phase: 8
title: "Tests and docs"
status: pending
priority: P2
effort: "1d"
dependencies: [7]
---

# Phase 8: Tests and docs

## Overview

Tests (unit + integration + e2e) + cập nhật docs (`docs/architecture.md`, `docs/pipeline-execution.md`, `docs/changelog.md`, `docs/development-roadmap.md`). Không skip test fail; mọi thay đổi phải xanh trước khi đóng plan.

## Requirements

**Functional**
- Unit tests:
  - `test_md_api_spec_validator.py` — 1 valid + 3 invalid fixtures.
  - `test_test_level_tagger.py` — rule classification + fallback boundary.
  - `test_executable_filter_execution_crew.py` — runnable/skipped split.
  - `test_report_verifier.py` — 3 component check, missing scenarios.
- Integration tests:
  - `test_automation_testing_api_pipeline.py` — chạy full DAG mock_mode với fixture, assert `status=completed`, `verified=true`.
  - `test_md_spec_validation_error_propagation.py` — invalid MD → run failed, error JSON đúng.
- E2E:
  - Playwright (FE) hoặc cypress: login → chọn template → upload MD valid → đợi completed → download HTML success.

**Non-functional**
- Coverage incremental ≥ 80% cho code mới (`md_api_spec_validator`, `test_level_tagger`, `report_verifier`, executable filter logic).
- CI xanh, không skip.

## Architecture

Test layout theo project hiện tại (`backend/tests/`). FE test (nếu có infrastructure) trong `apps/admin-app/tests/`.

## Related Code Files

- Create: `backend/tests/test_md_api_spec_validator.py`
- Create: `backend/tests/test_test_level_tagger.py`
- Create: `backend/tests/test_executable_filter_execution_crew.py`
- Create: `backend/tests/test_report_verifier.py`
- Create: `backend/tests/test_automation_testing_api_pipeline.py`
- Modify: `docs/architecture.md` — thêm 3 box mới (md_api_spec_verifier, export_html_docx, report_verifier) vào diagram
- Modify: `docs/pipeline-execution.md` — thêm flowchart riêng cho template `automation-testing-api`
- Modify: `docs/changelog.md` — entry release notes
- Modify: `docs/development-roadmap.md` — đánh dấu phase hoàn thành
- Create: `docs/Flow/automation-testing-api-md-contract.md` (đã có từ Phase 1)
- Modify: `docs/api-flow.md` — endpoint mới (verification + download guard)

## Implementation Steps

1. Viết unit tests theo từng module mới — chạy `pytest -q` đảm bảo xanh.
2. Viết integration test full pipeline với mock_mode để không cần LLM/HTTP thật.
3. Cập nhật `docs/architecture.md` thêm nodes & flow mới.
4. Bổ sung section "Automation Testing API Pipeline" trong `docs/pipeline-execution.md` với mermaid flowchart riêng.
5. Cập nhật `docs/api-flow.md` các endpoint:
   - `GET /pipeline/runs/{id}/report/verification`
   - `GET /pipeline/runs/{id}/report/{html|docx}` (409 behavior)
6. Ghi `docs/changelog.md` (entry mới): tóm tắt 3 tool mới + template mới.
7. Update `docs/development-roadmap.md` status.
8. Tag PR, đảm bảo `gitnexus_detect_changes()` cho thấy phạm vi đúng (md_api_spec_validator, test_level_tagger, report_verifier, execution_crew, seed, FE shared components).

## Success Criteria

- [ ] `pytest backend/tests/` xanh (cả test cũ + mới).
- [ ] FE test smoke pass.
- [ ] `docs/architecture.md` + `docs/pipeline-execution.md` + `docs/changelog.md` đã cập nhật.
- [ ] PR description list rõ 7 file mới, 6 file modified.
- [ ] No lint error, `mypy` (nếu enable) không warn.

## Risk Assessment

- **Risk:** Mock_mode không phản ánh đúng real LLM behavior. **Mitigation:** Có 1 smoke test optional (`@pytest.mark.real_llm`) chạy manual.
- **Risk:** Coverage drop do refactor lớn. **Mitigation:** Track coverage delta trong CI.

## Next Steps

Sau khi merge, chạy `/ck:plan archive` để archive plan + ghi journal entry.
