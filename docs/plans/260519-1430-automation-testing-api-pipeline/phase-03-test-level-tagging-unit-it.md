---
phase: 3
title: "Test-level tagging (Unit/IT)"
status: pending
priority: P1
effort: "1d"
dependencies: [2]
---

# Phase 3: Test-level tagging (Unit/IT)

## Overview

Mở rộng `TestCase` schema để mỗi case có `test_level ∈ {unit, integration, contract, e2e}` và `executable: bool`. Thêm node mới `test_level_classifier` (sau `test_case_generator`) áp rule-first + LLM-fallback. Đây là chìa khóa cho yêu cầu "case có thể bao phủ nhiều nhất" + Phase 4 filter.

## Requirements

**Functional**
- `TestCase.test_level: Literal["unit","integration","contract","e2e"]`.
- `TestCase.executable: bool` — `true` khi có đủ URL/method/expected_status để chạy qua `api_runner`; ngược lại `false`.
- Classifier ưu tiên rule (cheap, deterministic):
  - URL absolute + method + status_code → `integration`.
  - Validation rule đơn (field-level, không hit network) → `unit`.
  - Có schema validation cross-field → `contract`.
  - Sequence nhiều bước (login → call) → `e2e`.
- LLM fallback chỉ gọi khi không đủ tín hiệu (≤ 20% cases dự kiến).
- `TestCaseGenerator` prompt update: yêu cầu sinh **đa loại** (unit + integration + contract) cho mỗi rule để tối đa coverage.

**Non-functional**
- Tăng token cost ≤ 15% so với pipeline hiện tại.
- Backward compatible: schema cũ không có `test_level` vẫn parse được (default `unit`, `executable=false`).

## Architecture

```
test_case_generator → test_level_classifier → automation_agent
                          (NEW node)
```

`test_level_classifier`:
- `node_type=agent` (CrewAI) nhưng đa số xử lý qua tool `test_level_rule_tagger` chạy trong agent task.
- Agent chỉ gọi LLM khi tool trả `confidence < 0.7`.

Schema update `app/schemas/pipeline_io.py`:

```python
class TestLevel(str, Enum):
    UNIT = "unit"
    INTEGRATION = "integration"
    CONTRACT = "contract"
    E2E = "e2e"

class TestCase(BaseModel):
    ...
    test_level: TestLevel = TestLevel.UNIT
    executable: bool = False
```

Tool mới `app/tools/test_level_tagger.py`:

```python
def classify(test_case: dict, endpoint_hint: dict | None) -> tuple[TestLevel, bool, float]:
    # returns (level, executable, confidence)
```

## Related Code Files

- Modify: `backend/app/schemas/pipeline_io.py` — thêm `TestLevel`, field `test_level`, `executable`
- Modify: `backend/app/crews/testcase_crew.py` — prompt update for `test_case_generator`
- Create: `backend/app/tools/test_level_tagger.py`
- Create: `backend/app/tasks/test_level_tasks.py` (CrewAI task definition)
- Modify: `backend/app/db/seed.py` — thêm agent_config `test_level_classifier` (stage=`testcase`)
- Modify: `backend/app/tools/registry.py` — register tool

## Implementation Steps

1. Cập nhật `TestCase` schema + `TestCaseOutput` (đảm bảo `model_validate` cũ vẫn pass — dùng `Field(default=...)`).
2. Implement `test_level_tagger.classify()`:
   - Rule 1: `url and method and expected_status` → `integration`, `executable=true`, conf=0.95.
   - Rule 2: field-level validation step không hit network → `unit`, `executable=true` (chạy được trong artifact_crew sinh code), conf=0.9.
   - Rule 3: nhiều bước trong `steps` + nhiều endpoint → `e2e`, `executable=false` (chưa support multi-step runner) conf=0.85.
   - Rule 4: chỉ có schema check → `contract`, `executable=false`, conf=0.8.
   - Default `unit`, `executable=false`, conf=0.5.
3. Cập nhật prompt `test_case_generator` ép đa cấp test cho mỗi requirement: tối thiểu 1 unit + 1 integration nếu endpoint khả dụng.
4. Tạo agent_config `test_level_classifier`:
   - role: "Test Level Classifier"
   - goal: "Gắn nhãn test_level và executable cho từng test case dựa vào endpoint hint và nội dung."
   - tool_names: `["test_level_tagger"]`
5. Thêm node `test-level-classifier` vào template (Phase 6).
6. Truyền `parsed.endpoint` từ output của `md_api_spec_verifier` → input của classifier qua DAG merged_input.

## Success Criteria

- [ ] `TestCase` schema có `test_level` + `executable`, các unit test cũ vẫn pass.
- [ ] Run end-to-end với fixture `valid_login.md`: ≥ 70% cases có `test_level` đúng (so với expected snapshot).
- [ ] Token cost incremental đo qua Kafka `llm_call` events ≤ 15% so với baseline.
- [ ] Field `executable=true` xuất hiện cho cases có URL + method + status.

## Risk Assessment

- **Risk:** Schema migration breaking old runs. **Mitigation:** Default value + Pydantic `Optional[...]` để backward-compat khi đọc kết quả cũ.
- **Risk:** Classifier sai → executor chạy nhầm case. **Mitigation:** Confidence threshold + log mismatch.

## Next Steps

Phase 4 dùng `executable=true` để filter trong `ExecutionCrew`.
