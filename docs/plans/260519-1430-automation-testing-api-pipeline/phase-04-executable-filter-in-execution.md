---
phase: 4
title: "Executable filter in Execution"
status: pending
priority: P1
effort: "0.5d"
dependencies: [3]
---

# Phase 4: Executable filter in Execution

## Overview

Sửa `ExecutionCrew` để chỉ chạy `test_cases` có `executable=true`. Các case `executable=false` được pass-through (giữ status `skipped`) để Reporting phân biệt rõ "không thực thi" vs "thực thi nhưng fail".

## Requirements

**Functional**
- `ExecutionCrew.run({test_cases, ...})` tách `test_cases` thành 2 nhánh:
  - `runnable = [tc for tc in test_cases if tc.get("executable")]`
  - `skipped = [tc for tc in test_cases if not tc.get("executable")]`
- Chỉ feed `runnable` vào `test_runner`.
- Output `ExecutionOutput.results` chứa cả 2 nhóm với `status="skipped"` cho non-executable, gắn `skip_reason="not_executable: <test_level>"`.
- Summary metric tách: `total_runnable`, `total_skipped`, `pass_rate` chỉ tính trên runnable.

**Non-functional**
- Không break mock mode (`_mock_run` cũng phải filter).
- Không yêu cầu schema migration thêm — dùng field đã thêm Phase 3.

## Architecture

`ExecutionOutput.results: list[TestExecutionResult]` đã tồn tại. Thêm enum value `SKIPPED` vào `ExecutionStatus` nếu chưa có, hoặc reuse value sẵn.

`ExecutionSummary` cần thêm `runnable_count`, `skipped_count`, `skipped_reasons: dict[str,int]`.

## Related Code Files

- Modify: `backend/app/crews/execution_crew.py` — filter logic trong `run()`, `_real_run()`, `_mock_run()`
- Modify: `backend/app/schemas/pipeline_io.py` — thêm `ExecutionStatus.SKIPPED` (nếu chưa có) + extend `ExecutionSummary`
- Modify: `backend/app/crews/reporting_crew.py` — phân biệt skipped vs failed trong root cause analysis
- Modify: `backend/app/templates/report.html.j2` — render section "Skipped tests"
- Modify: `backend/app/services/docx_builder.py` — thêm bảng skipped tests
- Read: `backend/app/crews/execution_crew.py` (hiểu mock & real run)

## Implementation Steps

1. Đọc `ExecutionStatus` enum hiện tại; thêm `SKIPPED = "skipped"` nếu chưa có.
2. Trong `ExecutionCrew.run()`:
   ```python
   runnable = [tc for tc in test_cases if tc.get("executable")]
   skipped = [tc for tc in test_cases if not tc.get("executable")]
   ```
   Log `_emit_log(f"Filtered {len(skipped)} non-executable case(s)")`.
3. Tạo `_build_skipped_results(skipped)` trả `list[TestExecutionResult]` với `status="skipped"`, `skip_reason="not_executable"`, `actual=null`.
4. Sau khi `_real_run`/`_mock_run` xong, concat skipped results vào `output.results`.
5. Update `ExecutionSummary` builder để tách runnable/skipped count.
6. Update HTML/DOCX template để hiển thị bảng "Skipped (non-executable)".
7. Update prompt `coverage_analyzer` + `root_cause_analyzer` để bỏ qua skipped khi tính pass-rate nhưng vẫn trong coverage denominator.

## Success Criteria

- [ ] Test e2e: 10 cases (5 unit không URL, 5 integration có URL) → execution runs 5, skips 5; `summary.runnable_count=5`, `summary.skipped_count=5`.
- [ ] Report HTML hiển thị bảng skipped riêng.
- [ ] `pass_rate` tính trên runnable, không phải trên total.
- [ ] Mock mode hành xử đồng nhất với real mode trên filter logic.

## Risk Assessment

- **Risk:** Reporting crew prompt cũ tính pass_rate sai sau khi có skipped. **Mitigation:** Update prompt + có unit test snapshot.
- **Risk:** Skipped không có URL → executor crash. **Mitigation:** Filter trước khi gọi `api_runner`.

## Next Steps

Phase 5 verifier cần đọc cả skipped count và unit test file count để check report completeness.
