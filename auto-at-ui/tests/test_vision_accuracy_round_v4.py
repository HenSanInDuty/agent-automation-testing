"""Machine outcome rules of the sprint runner never credit what independent review did not."""

import json
import shutil
import sys
from pathlib import Path

import pytest

DIRECTORY = Path(__file__).parents[1] / "benchmark/vision/accuracy"
sys.path.insert(0, str(DIRECTORY))
import round_v4  # noqa: E402

ROUND21 = DIRECTORY / "runs/39de5dc7-c68e-49e1-b1b5-9cdc3b3a6391"
V2 = json.loads((DIRECTORY / "oracle-mongchiton-1280-v2.json").read_text("utf-8"))
TARGETS = {item["id"]: item for item in V2["examples"]}


def test_plain_url_drops_query_fragment_and_trailing_slash():
    assert round_v4.plain("https://pay.tpl.vn/?a=1#x") == "https://pay.tpl.vn"
    assert round_v4.plain(None) is None


def test_redirect_destination_is_accepted_but_another_page_is_not():
    accepted = round_v4.destinations(TARGETS["mct-33"])
    assert "https://pay.tpl.vn" in accepted and "https://pay.tepaylink.vn" in accepted
    state = {"page_url": "https://id.tpl.vn/register"}
    assert round_v4.machine_finding(TARGETS["mct-33"], {"id": "x"}, state, []) is None


def test_visual_outcomes_never_get_a_machine_finding():
    state = {"page_url": "https://mongchiton.vn/", "url_fingerprint": round_v4.MCT47_PLAYER}
    for target in ("mct-30", "mct-51", "mct-57", "mct-43", "mct-21", "mct-44"):
        assert round_v4.machine_finding(TARGETS[target], {"id": "x"}, state, []) is None


def test_download_rule_needs_the_same_operation_and_declared_start():
    target = TARGETS["mct-38"]
    record = {"operation_id": "op", "status": "completed",
              "navigation_chain": [{"url_sha256": target["outcome"]["url_sha256"]}]}
    assert round_v4.machine_finding(target, {"id": "op"}, {}, [record])
    assert round_v4.machine_finding(target, {"id": "other"}, {}, [record]) is None
    assert round_v4.machine_finding(target, {"id": "op"}, {}, [
        {**record, "status": "failed"}]) is None


@pytest.mark.skipif(not ROUND21.is_dir(), reason="round 21 evidence not present")
def test_round21_machine_findings_are_a_subset_of_independent_review(tmp_path, monkeypatch):
    folder = tmp_path / ROUND21.name
    shutil.copytree(ROUND21, folder, ignore=shutil.ignore_patterns("rescore-*", "review-*"))
    (folder / "oracle.json").write_text(json.dumps(V2), "utf-8")
    monkeypatch.setattr(round_v4, "RUNS", tmp_path)
    round_v4.auto(ROUND21.name)
    machine = json.loads((folder / "auto-findings.json").read_text("utf-8"))
    manual = {k for k in json.loads((ROUND21 / "manual-findings.json").read_text("utf-8"))
              if not k.startswith("_")} | {"109"}
    review = json.loads((folder / "needs-review.json").read_text("utf-8"))
    assert set(machine) <= manual and len(machine) == 28
    assert {row["kind"] for row in review} <= {"carousel_selection", "carousel_step", "scroll_top",
                                               "selected_tab", "empty_search",
                                               "selected_character"}
