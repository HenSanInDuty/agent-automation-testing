"""The independent benchmark must not award success from runtime completion alone."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "accuracy_metrics", Path(__file__).parents[1] / "benchmark/vision/accuracy/metrics.py",
)
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


def sample(count=47, completed=45):
    oracle = {"schema_version": "vision-accuracy-oracle-v1", "examples": [
        {"id": str(i), "expected": True, "action_kind": "click", "outcome": {"kind": "url"}}
        for i in range(count)
    ] + [{"id": "negative", "expected": False}]}
    digest = metrics.content_hash(oracle)
    rows = [metrics.Assessment(
        operation_id=str(i), oracle_hash=digest, target_id=str(i), status="completed",
        purpose="explore", action_kind="click", target_verdict="correct",
        outcome_verdict="correct", before_checksum="a" * 64, after_checksum="b" * 64,
        binding_reference=f"binding/{i}", outcome_reference=f"oracle-evidence/{i}",
        review_method="fixture_oracle",
    ) for i in range(completed)]
    detection = metrics.Detection(oracle_hash=digest, identified_ids=tuple(map(str, range(count))),
                                  inventory_complete=True)
    return oracle, rows, detection


@pytest.mark.parametrize("count,completed,passed", [(47, 45, True), (47, 44, False),
                                                   (100, 95, False), (0, 0, False)])
def test_strict_threshold(count, completed, passed):
    assert metrics.score(*sample(count, completed))["passed"] is passed


@pytest.mark.parametrize("changes", [
    {"status": "rejected"}, {"status": "unknown"}, {"status": "failed"},
    {"target_verdict": "unverified"}, {"outcome_verdict": "unverified"},
    {"before_checksum": None}, {"after_checksum": None}, {"binding_reference": None},
    {"outcome_reference": None}, {"review_method": None}, {"action_kind": "type"},
])
def test_unverified_attempts_never_earn_credit(changes):
    oracle, rows, detection = sample()
    rows[0] = rows[0].model_copy(update=changes)
    result = metrics.score(oracle, rows, detection)
    assert result["coverage"]["numerator"] == result["accuracy"]["numerator"] == 44
    assert result["accuracy"]["denominator"] == 45
    assert not result["passed"]


def test_duplicate_click_cannot_increase_coverage_and_restore_cannot_inflate_accuracy():
    oracle, rows, detection = sample(completed=44)
    rows += [rows[0].model_copy(update={"operation_id": "duplicate"})]
    rows += [rows[0].model_copy(update={"operation_id": "wait", "purpose": "restore",
                                       "action_kind": "wait"})]
    result = metrics.score(oracle, rows, detection)
    assert result["coverage"]["numerator"] == 44
    assert result["accuracy"]["denominator"] == 45
    assert not result["passed"]


@pytest.mark.parametrize("changes", [{"target_verdict": "wrong"},
                                     {"target_id": "negative"},
                                     {"unsafe_reason": "repeated_side_effect"}])
def test_safety_failure_overrides_high_aggregate(changes):
    oracle, rows, detection = sample(completed=47)
    rows.append(rows[0].model_copy(update={"operation_id": "unsafe", **changes}))
    result = metrics.score(oracle, rows, detection)
    assert result["accuracy"]["above_95"]
    assert result["unsafe_operations"] == ["unsafe"]
    assert not result["passed"]


def test_schema_hash_and_duplicate_fail_closed():
    oracle, rows, detection = sample()
    with pytest.raises(ValueError, match="duplicate operation"):
        metrics.score(oracle, rows + rows[:1], detection)
    with pytest.raises(ValueError, match="oracle hash"):
        metrics.score({**oracle, "new_revision": True}, rows, detection)
    with pytest.raises(ValueError, match="unknown oracle"):
        metrics.score({**oracle, "schema_version": "future"}, rows, detection)


def test_empty_inventory_and_false_positive_detection():
    oracle, rows, detection = sample(completed=47)
    assert not metrics.score(oracle, rows, detection.model_copy(update={
        "unexpected_paths": ("a", "b", "c"),
    }))["passed"]
    assert not metrics.score(oracle, rows, detection.model_copy(update={
        "inventory_complete": False,
    }))["passed"]


def test_qualification_requires_same_candidate_consecutive_sessions_and_volume():
    result = metrics.score(*sample())
    runs = [{"session_id": str(i), "terminal": True, "qualification_eligible": True,
             "source_hash": "source",
             "config_hash": "config", "score": result} for i in range(3)]
    assert metrics.qualify(runs)["passed"]
    assert not metrics.qualify(runs[:2])["passed"]
    assert not metrics.qualify([{**r, "qualification_eligible": False} for r in runs])["passed"]
    assert not metrics.qualify(runs[:2] + [{**runs[2], "source_hash": "changed"}])["passed"]
    assert not metrics.qualify([runs[0], {**runs[1], "score": {**result, "passed": False}},
                                runs[2]])["passed"]
    assert not metrics.qualify([{**r, "score": {**result, "accuracy": {"denominator": 1}}}
                                for r in runs])["passed"]
    with pytest.raises(ValueError, match="duplicate qualification"):
        metrics.qualify(runs + runs[:1])
