"""Oracle v2 alternate paths: one logical target with several DOM copies. Offline only."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(1, str(Path(__file__).parents[1] / "benchmark/vision/accuracy"))
import test_vision_accuracy_binding as base  # noqa: E402

DIRECTORY = base.DIRECTORY
evidence = base.evidence_module
metrics = sys.modules["metrics"]
V1 = json.loads((DIRECTORY / "oracle-mongchiton-1280-v1.json").read_text("utf-8"))
V2 = json.loads((DIRECTORY / "oracle-mongchiton-1280-v2.json").read_text("utf-8"))
MCT47 = next(item for item in V2["examples"] if item["id"] == "mct-47")


def test_v2_only_adds_mct47_alternates_to_v1():
    stripped = copy.deepcopy(V2)
    for key in ("schema_version", "reviewed_on", "annotation_method", "derived_from_sha256"):
        stripped.pop(key)
    for item in stripped["examples"]:
        item.pop("alternate_paths", None)
        item.pop("alternate_evidence", None)
    original = {key: value for key, value in V1.items()
                if key not in ("schema_version", "reviewed_on", "annotation_method")}
    assert stripped == original
    assert [item["id"] for item in V2["examples"] if "alternate_paths" in item] == ["mct-47"]
    assert sum(item["expected"] for item in V2["examples"]) == 47
    assert metrics.validate_oracle(V1) and metrics.validate_oracle(V2)
    assert (DIRECTORY / MCT47["alternate_evidence"]).is_file()


@pytest.mark.parametrize("mutate", [
    lambda o: o.update(schema_version="vision-accuracy-oracle-v1"),   # v1 cannot carry alternates
    lambda o: o["examples"][0].update(alternate_paths=[o["examples"][1]["reference_path"]],
                                      alternate_evidence="x"),        # path owned by another id
    lambda o: next(i for i in o["examples"] if i["id"] == "mct-47").pop("alternate_evidence"),
    lambda o: next(i for i in o["examples"] if i["id"] == "mct-47").update(alternate_paths=[]),
    lambda o: next(i for i in o["examples"] if i["id"] == "mct-47").update(alternate_paths=[""]),
    lambda o: o.update(schema_version="vision-accuracy-oracle-v3"),
])
def test_invalid_alternates_fail_closed(mutate):
    oracle = copy.deepcopy(V2)
    mutate(oracle)
    with pytest.raises(ValueError):
        metrics.validate_oracle(oracle)


def binding(path):
    return {"id": "b1", "status": "verified", "path": path}


@pytest.mark.parametrize("path", [MCT47["reference_path"], *MCT47["alternate_paths"]])
def test_every_copy_binds_to_mct47_under_v2(path):
    assert evidence.binding_error(V2, MCT47, binding(path), None, {}, None, "b1") is None


def test_alternate_copy_does_not_bind_under_v1_or_to_another_target():
    v1_target = next(item for item in V1["examples"] if item["id"] == "mct-47")
    other = next(item for item in V2["examples"] if item["id"] == "mct-46")
    alternate = MCT47["alternate_paths"][0]
    assert evidence.binding_error(V1, v1_target, binding(alternate), None, {}, None,
                                  "b1") == "path_mismatch"
    assert evidence.binding_error(V2, other, binding(alternate), None, {}, None,
                                  "b1") == "path_mismatch"


def test_detection_maps_all_copies_to_one_target():
    source = evidence.source_fingerprint(V2)
    keys = [evidence.descriptor_key(path, "v3")
            for path in (MCT47["reference_path"], *MCT47["alternate_paths"])]
    page = {"state_id": "s", "url_fingerprint": source, "truncated": False, "scrollable": False,
            "skipped_count": 0, "controls": [{"key": key, "role": None, "name": None}
                                             for key in keys]}
    assert evidence.derive_detection(V2, [page])["identified_ids"] == ["mct-47"]
    assert evidence.derive_detection(V2, [page])["unexpected_paths"] == []
    v1_facts = evidence.derive_detection(V1, [page])
    assert v1_facts["identified_ids"] == ["mct-47"] and len(v1_facts["unexpected_paths"]) == 3


def test_round21_unmatched_keys_are_the_mct47_copies():
    """The three keys that failed round 21 precision are exactly the v2 alternates."""
    unmatched = {"50f0e9d3cd67d0f398c4443fd52a1d4d63a95d396f31ce08e0b0821b47ceca7f",
                 "52249891675260f9ec80645ce2ccaae8f98349157b155621dbf3d90a80564ed0",
                 "eefb08807cc41c046e5c15d272917e4a1459efe5fda624e39b22c5a2ff020b39"}
    assert {evidence.descriptor_key(path, "v3") for path in MCT47["alternate_paths"]} == unmatched


ROUND21 = DIRECTORY / "runs/39de5dc7-c68e-49e1-b1b5-9cdc3b3a6391"


@pytest.mark.skipif(not ROUND21.is_dir(), reason="round 21 evidence not present")
@pytest.mark.parametrize("oracle,extra,expected", [
    (V1, False, ((45, 47), (45, 47), (47, 50), False)),   # reproduces the original round 21 score
    (V2, True, ((46, 47), (46, 47), (47, 47), True)),
])
def test_rescore_round21_from_retained_evidence(tmp_path, oracle, extra, expected):
    import shutil
    rescore = sys.modules.get("rescore") or __import__("rescore")
    folder = tmp_path / ROUND21.name
    folder.mkdir()
    for name in ("evidence.json", "inventory-evidence.json", "manifest.json"):
        shutil.copy(ROUND21 / name, folder / name)
    findings = {k: v for k, v in rescore.read(ROUND21 / "manual-findings.json").items()
                if not k.startswith("_")}
    if extra:
        findings |= {k: v for k, v in rescore.read(
            ROUND21 / "oracle-v2-findings-20261122.json").items() if not k.startswith("_")}
    _, result = rescore.rescore(folder, oracle, findings)
    got = tuple((result[k]["numerator"], result[k]["denominator"])
                for k in ("coverage", "accuracy", "detection_precision"))
    assert (*got, result["passed"]) == expected
    assert result["unsafe_operations"] == [] and result["remaining_targets"][-1] == "mct-57"


def batch_run(index, *, passed=True, unsafe=(), attempts=47, source="s", eligible=True):
    return {"session_id": f"session-{index}", "source_hash": source, "config_hash": "c",
            "terminal": True, "qualification_eligible": eligible,
            "score": {"oracle_hash": "o", "passed": passed, "unsafe_operations": list(unsafe),
                      "unsettled_operations": [], "accuracy": {"denominator": attempts}}}


@pytest.mark.parametrize("runs,expected", [
    ([batch_run(i) for i in range(5)], True),
    ([batch_run(i, passed=i != 2) for i in range(5)], True),                 # 4/5
    ([batch_run(i, passed=i > 1) for i in range(5)], False),                 # 3/5
    ([batch_run(i, passed=i != 2, unsafe=["x"] if i == 2 else []) for i in range(5)], False),
    ([batch_run(i, source="s" if i else "t") for i in range(5)], False),     # mixed candidate
    ([batch_run(i, eligible=i != 4) for i in range(5)], False),
    ([batch_run(i, attempts=19) for i in range(5)], False),                  # 95 < 100 attempts
])
def test_sprint_batch_rule_four_of_five(runs, expected):
    assert metrics.qualify_batch(runs)["passed"] is expected


def test_sprint_batch_must_be_exactly_five_distinct_sessions():
    with pytest.raises(ValueError):
        metrics.qualify_batch([batch_run(i) for i in range(4)])
    with pytest.raises(ValueError):
        metrics.qualify_batch([batch_run(0)] * 5)
