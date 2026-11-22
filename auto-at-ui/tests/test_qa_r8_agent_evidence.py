# ruff: noqa: E501  (long literal fixtures/assert messages in a QA file)
"""QA r8 (phase 04): independent behaviour checks of ADR-040 flags A1/A2/A3. Offline, no DB/docker/model.

Ids refer to plan/09112026103202-vision-accuracy-loop/qa/phase-04/r8-test-cases.md.
"""

import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from itertools import product
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from application.vision_agent_loop import worker_capabilities
from auto_at.contracts.vision import VisualExecutedClick
from auto_at.contracts.vision_worker import VisualWorkerOpen
from config import Settings
from infrastructure.vision_worker import HttpVisualWorker, VisualWorkerUnavailable

sys.path.insert(0, str(Path(__file__).parent))
import test_vision_accuracy_agent_evidence as agent  # noqa: E402
import test_vision_accuracy_binding as base  # noqa: E402

module, evidence_module = base.module, base.evidence_module
ROOT = Path(__file__).parents[1]
ACCURACY = ROOT / "benchmark/vision/accuracy"
R6 = "1c56623e-8f37-4705-946b-5f1a6752f81c"
ORACLE_HASH = "9242b33d5e4cdd155b6642262c32f166b365edeec7d7b9642c5b88df35147a4e"
OLD_CLICK_KEYS = {"x", "y", "viewport_width", "viewport_height", "before_frame_id", "confirmed_at"}
NOW = datetime.now(UTC)


# ---------------------------------------------------------------- QA-R8-01 r6 score regression

@pytest.fixture
def r6_loop(tmp_path, monkeypatch):
    source = ACCURACY / "runs" / R6
    if not (source / "rescore-role-binding.json").exists():
        pytest.skip("stored r6 run folder not available")
    shutil.copytree(source, tmp_path / "runs" / R6)
    monkeypatch.setattr(module.Loop, "frame", lambda self, iteration, metadata: b"")  # offline GET
    return module.Loop(None, tmp_path / "runs"), tmp_path / "runs" / R6


def stored(folder):
    return json.loads((folder / "rescore-role-binding.json").read_text("utf-8"))


@pytest.mark.parametrize("sources", ["none", None, "all", "click_context", "inventory"])
def test_r6_stored_session_still_scores_as_r7(r6_loop, sources):
    """The r6 trace has no click context and no inventory: every source selection must give r7's score."""
    loop, folder = r6_loop
    rescore = stored(folder)
    rows = [module.Assessment.model_validate(row) for row in rescore["assessments"]]
    detection = module.Detection.model_validate(json.loads((folder / "detection.json").read_text()))
    result = loop.evaluate(R6, rows, detection, sources=sources, label="qa")
    assert result["oracle_hash"] == ORACLE_HASH
    assert (result["coverage"]["numerator"], result["coverage"]["denominator"]) == (5, 47)
    assert (result["accuracy"]["numerator"], result["accuracy"]["denominator"]) == (5, 12)
    assert (result["detection_recall"]["numerator"], result["detection_recall"]["denominator"]) == (0, 47)
    assert result["detection_precision"]["percent"] is None
    assert result["inventory_complete"] is False and result["passed"] is False
    assert result["covered_targets"] == ["mct-01", "mct-02", "mct-04", "mct-05", "mct-06"]
    assert result == rescore["score"]
    assert result["unsafe_operations"] == [] and result["unsettled_operations"] == []


def test_r6_detect_without_inventory_is_the_old_empty_detection(r6_loop):
    loop, folder = r6_loop
    for sources in ("none", "all", "inventory"):
        got = loop.detect(R6, sources=sources, label="qa" + sources)
        assert got == {"oracle_hash": ORACLE_HASH, "identified_ids": [], "unexpected_paths": [],
                       "inventory_complete": False}
    assert not (folder / "inventory.json").exists()


def test_r6_grounding_has_no_contexts_and_default_artifacts_untouched(r6_loop):
    loop, folder = r6_loop
    grounding = json.loads((folder / "grounding.json").read_text("utf-8"))
    assert "contexts" not in grounding
    before = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
    rows = [module.Assessment.model_validate(r) for r in stored(folder)["assessments"]]
    detection = module.Detection.model_validate(json.loads((folder / "detection.json").read_text()))
    loop.evaluate(R6, rows, detection, sources="none", label="x")
    after = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
    assert {k: v for k, v in after.items() if k in before} == before
    assert set(after) - set(before) == {"assessments.x.json", "detection.x.json", "score.x.json"}


# ---------------------------------------------------------------- QA-R8-07 oracle / metrics integrity

def test_oracle_content_hash_and_frozen_files_unchanged():
    oracle = json.loads((ACCURACY / "oracle-mongchiton-1280-v1.json").read_text("utf-8"))
    assert module.content_hash(oracle) == ORACLE_HASH
    changed = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", "benchmark/vision/accuracy/metrics.py",
         "benchmark/vision/accuracy/oracle-mongchiton-1280-v1.json"], cwd=ROOT, timeout=60)
    assert changed.returncode == 0


# ---------------------------------------------------------------- QA-R8-02 flags off: shapes unchanged

def test_flags_off_capabilities_and_click_shape_are_the_old_ones():
    settings = Settings(_env_file=None)
    assert worker_capabilities(settings, 30) == ("dom-observation-v1", "step-timeout-v1")
    click = VisualExecutedClick(x=0.1, y=0.2, viewport_width=1280, viewport_height=720,
                                before_frame_id=uuid4(), confirmed_at=NOW)
    assert set(click.model_dump(mode="json")) == OLD_CLICK_KEYS
    assert set(click.model_dump()) == OLD_CLICK_KEYS
    # exclude_none/json round trip, the form used for stored payloads and the trace revision hash
    assert json.loads(click.model_dump_json()).keys() == OLD_CLICK_KEYS


def test_flags_off_grounding_and_collect_keep_old_artifacts(tmp_path):
    ids = {}

    def build(trace):
        ids["op"] = trace.click("TRANG CHỦ", box=(332, 10, 145, 37))

    loop, iteration, evidence, _ = agent.collected(tmp_path, build)
    folder = loop.directory / iteration
    grounding = json.loads((folder / "grounding.json").read_text("utf-8"))
    assert set(grounding) == {"schema_version", "session_id", "trace_revision", "locators"}
    assert not (folder / "inventory.json").exists()
    assert "executed_click" not in json.dumps(evidence)


# ---------------------------------------------------------------- QA-R8-03 flag combinations

@pytest.mark.parametrize("a1,a2,a3", list(product([False, True], repeat=3)))
def test_each_flag_only_adds_its_own_capability(a1, a2, a3):
    settings = Settings(_env_file=None, vision_agent_click_context_enabled=a1,
                        vision_agent_dom_path_enabled=a2, vision_agent_inventory_enabled=a3)
    got = worker_capabilities(settings, 30)
    assert got[:2] == ("dom-observation-v1", "step-timeout-v1")
    assert set(got[2:]) == ({"click-context-v1"} if a1 else set()) | (
        {"agent-dom-path-v1"} if a2 else set())
    assert len(got) == len(set(got))  # no duplicate capability
    VisualWorkerOpen(tenant_id="t", project_id=uuid4(), session_id=uuid4(), fencing_token=1,
                     target_url="https://app.test/", allowed_origins=(),
                     deadline=NOW + timedelta(seconds=60), max_session_seconds=60, max_states=5,
                     max_hops=1, max_screenshot_bytes=1024, required_capabilities=got)


def test_source_selection_does_not_leak_between_sources(tmp_path):
    """A1 only helps in-flow binding; A3 only produces detection; neither implies the other."""
    ids = {}

    def build(trace):
        ids["flow"] = trace.click_with("Đăng ký", agent.ctx(600), role="button",
                                       box=agent.box_at((100, 877, 80, 40), 600))

    pages = [agent.page(agent.SOURCE_FP, [agent.control("a" * 64, "link", "TRANG CHỦ")])]
    loop, iteration, evidence, _ = agent.collected(tmp_path, build, pages)
    folder = loop.directory / iteration
    assert (folder / "inventory.json").exists()
    assert json.loads((folder / "grounding.json").read_text("utf-8"))["contexts"]
    credited = {ids["flow"]: "f1"}

    inventory_only = loop.detect(iteration, sources="inventory", label="inv")
    context_only = loop.detect(iteration, sources="click_context", label="ctx")
    none = loop.detect(iteration, sources="none", label="none")
    assert inventory_only["identified_ids"] == ["h1"]
    assert context_only == none and context_only["identified_ids"] == []

    # click credited only when A1 is selected
    assert agent.grade(loop, iteration, evidence, credited, sources="click_context",
                       label="a1")["coverage"]["numerator"] == 1
    for sources in ("inventory", "none"):
        with pytest.raises(ValueError, match="binding does not match oracle"):
            agent.grade(loop, iteration, evidence, credited, sources=sources, label="x" + sources[:2])
    # all three artifacts sets exist side by side; default artifacts untouched
    assert not (folder / "score.json").exists()


# ---------------------------------------------------------------- QA-R8-04 worker without capability

def worker_with(capabilities, request):
    def handler(http):
        return httpx.Response(200, json={
            "session_id": str(request.session_id), "contract_version": "v4",
            "operation_budget": 1 + request.max_states * (2 * request.max_hops + 3),
            "state_fingerprint": "a" * 64, "capabilities": capabilities})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HttpVisualWorker(client, "http://worker.test", "secret"), client


def open_request(capabilities):
    return VisualWorkerOpen(
        tenant_id="t", project_id=uuid4(), session_id=uuid4(), fencing_token=1,
        target_url="https://app.test/", allowed_origins=(), deadline=NOW + timedelta(seconds=60),
        max_session_seconds=60, max_states=5, max_hops=1, max_screenshot_bytes=1024,
        required_capabilities=capabilities)


@pytest.mark.parametrize("missing", ["click-context-v1", "agent-dom-path-v1"])
def test_old_worker_without_the_new_capability_fails_closed_with_a_typed_error(missing):
    wanted = ("dom-observation-v1", "step-timeout-v1", "click-context-v1", "agent-dom-path-v1")
    request = open_request(wanted)
    offered = [c for c in wanted if c != missing]

    async def run():
        worker, client = worker_with(offered, request)
        try:
            return await worker.open(request)
        finally:
            await client.aclose()

    with pytest.raises(VisualWorkerUnavailable):
        asyncio.run(run())


def test_flags_off_request_is_satisfied_by_a_pre_r8_worker():
    request = open_request(worker_capabilities(Settings(_env_file=None), 30))
    assert "click-context-v1" not in request.required_capabilities

    async def run():
        worker, client = worker_with(["dom-observation-v1", "step-timeout-v1"], request)
        try:
            return await worker.open(request)
        finally:
            await client.aclose()

    assert asyncio.run(run()) == "a" * 64


# ---------------------------------------------------------------- QA-R8-05 corrupt / missing data

HASH_A, HASH_B = "a" * 64, "b" * 64


@pytest.mark.parametrize("pages", [
    [], [{}], [None], "junk", [{"state_id": "x"}],
    [{"state_id": str(uuid4()), "url_fingerprint": None, "controls": []}],
    [{"state_id": str(uuid4()), "url_fingerprint": agent.SOURCE_FP, "controls": None}],
    [{"state_id": str(uuid4()), "url_fingerprint": agent.SOURCE_FP, "controls": [{}]}],
])
def test_corrupt_or_missing_inventory_never_crashes_and_never_credits(pages):
    exported = evidence_module.export_inventory(pages if isinstance(pages, list) else None)
    facts = evidence_module.derive_detection(agent.ORACLE, exported)
    assert facts["identified_ids"] == [] and facts["unexpected_paths"] == []
    # Observation (not a credit): flags alone decide completeness, so a valid oracle-page state whose
    # control rows are all junk reports complete with 0 identified; recall then stays 0, so no score.
    assert facts["inventory_complete"] is (bool(exported) and exported[0]["url_fingerprint"] == agent.SOURCE_FP)


def test_empty_controls_page_is_not_complete_credit_free():
    pages = [agent.page(agent.SOURCE_FP, [])]
    facts = evidence_module.derive_detection(
        agent.ORACLE, evidence_module.export_inventory(pages))
    assert facts["identified_ids"] == [] and facts["pages_on_oracle_url"] == 1


def test_duplicate_dom_path_and_duplicate_names_count_each_target_once():
    key = agent.U1_KEY
    pages = [agent.page(agent.SOURCE_FP, [
        agent.control(key, "button", ""), agent.control(key, "button", ""),
        agent.control(HASH_A, "link", "Trang chu"), agent.control(HASH_B, "link", "TRANG CHỦ"),
        agent.control(HASH_A, "link", "Khác"), agent.control("c" * 64, "link", "Lạ"),
        agent.control("c" * 64, "link", "Lạ")])]
    facts = evidence_module.derive_detection(agent.ORACLE, evidence_module.export_inventory(pages))
    assert facts["identified_ids"] == ["h1", "u1"]
    assert facts["unexpected_paths"] == sorted({"unmatched_key:" + HASH_A, "unmatched_key:" + "c" * 64})
    # metrics: the same id twice would be rejected or double counted; it must not be
    detection = module.Detection(oracle_hash=module.content_hash(agent.ORACLE),
                                 identified_ids=tuple(facts["identified_ids"]),
                                 unexpected_paths=tuple(facts["unexpected_paths"]),
                                 inventory_complete=False)
    result = module.score(agent.ORACLE, [], detection)
    assert result["detection_recall"]["numerator"] == 2


def test_non_expected_oracle_control_in_inventory_earns_no_recall():
    pages = [agent.page(agent.SOURCE_FP, [agent.control(HASH_A, "link", "Thoát")])]
    facts = evidence_module.derive_detection(agent.ORACLE, evidence_module.export_inventory(pages))
    detection = module.Detection(oracle_hash=module.content_hash(agent.ORACLE),
                                 identified_ids=tuple(facts["identified_ids"]),
                                 unexpected_paths=tuple(facts["unexpected_paths"]),
                                 inventory_complete=False)
    result = module.score(agent.ORACLE, [], detection)
    assert result["detection_recall"]["numerator"] == 0
    assert result["detection_precision"]["numerator"] == 0


@pytest.mark.parametrize("click", [
    {}, {"scroll_x": 0}, {"scroll_y": 5}, {"scroll_x": 0, "scroll_y": 5},
    {"scroll_x": 0, "scroll_y": 5, "url_fingerprint": "short"},
    {"scroll_x": 0, "scroll_y": -1, "url_fingerprint": agent.SOURCE_FP},
    {"scroll_x": True, "scroll_y": 0, "url_fingerprint": agent.SOURCE_FP},
    {"scroll_x": 0.5, "scroll_y": 0, "url_fingerprint": agent.SOURCE_FP},
    {"scroll_x": "1", "scroll_y": 0, "url_fingerprint": agent.SOURCE_FP},
    {"scroll_x": None, "scroll_y": None, "url_fingerprint": None},
])
def test_missing_or_corrupt_click_context_is_absent_never_partial(click):
    assert evidence_module.click_context(click) is None
    assert evidence_module.click_context(None) is None


def test_corrupt_context_cannot_credit_an_in_flow_click(tmp_path):
    ids = {}

    def build(trace):
        ids["op"] = trace.click_with("Đăng ký", {"scroll_x": 0, "scroll_y": 600},  # no fingerprint
                                     role="button", box=agent.box_at((100, 877, 80, 40), 600))

    loop, iteration, evidence, _ = agent.collected(tmp_path, build)
    with pytest.raises(ValueError, match="binding does not match oracle"):
        agent.grade(loop, iteration, evidence, {ids["op"]: "f1"})


def test_a_repeated_click_on_one_target_is_credited_once(tmp_path):
    ids = []

    def build(trace):
        for _ in range(2):
            ids.append(trace.click_with("TRANG CHỦ", agent.ctx(0), box=(332, 10, 145, 37)))

    loop, iteration, evidence, _ = agent.collected(tmp_path, build)
    with pytest.raises(ValueError, match="already credited"):
        agent.grade(loop, iteration, evidence, {ids[0]: "h1", ids[1]: "h1"})
    assert agent.grade(loop, iteration, evidence, {ids[0]: "h1"})["coverage"]["numerator"] == 1


def test_inventory_of_another_page_or_url_missing_fingerprint_is_ignored():
    pages = [agent.page(agent.OTHER_FP, [agent.control(agent.U1_KEY, "button", "")])]
    facts = evidence_module.derive_detection(agent.ORACLE, evidence_module.export_inventory(pages))
    assert facts["identified_ids"] == [] and facts["pages_on_oracle_url"] == 0
    assert facts["inventory_complete"] is False


# ---------------------------------------------------------------- QA-R8-06 no sensitive text

SECRET = "hunter2-SECRET-typed-value"


def test_no_form_value_or_url_reaches_inventory_or_context_artifacts(tmp_path):
    ids = {}

    def build(trace):
        ids["op"] = trace.click_with("TRANG CHỦ", {**agent.ctx(0), "typed": SECRET, "page_url":
                                                    "https://x/?token=" + SECRET},
                                     box=(332, 10, 145, 37))

    page = agent.page(agent.SOURCE_FP, [{**agent.control(HASH_A, "textbox", "Email"),
                                         "value": SECRET, "text": SECRET}])
    page["page_url"] = "https://site.test/?token=" + SECRET
    page["checkpoint_id"] = page["state_id"]
    loop, iteration, _, _ = agent.collected(tmp_path, build, [page])
    folder = loop.directory / iteration
    for name in ("grounding.json", "inventory.json", "evidence.json"):
        assert SECRET not in (folder / name).read_text("utf-8"), name
    inventory = json.loads((folder / "inventory.json").read_text("utf-8"))
    assert set(inventory["pages"][0]) == {"state_id", "url_fingerprint", "controls", "truncated",
                                          "scrollable", "skipped_count"}
    contexts = json.loads((folder / "grounding.json").read_text("utf-8"))["contexts"]
    assert set(next(iter(contexts.values()))) == {"scroll", "url_fingerprint"}


def test_worker_dom_skips_private_inputs_and_redacts_sensitive_names():
    """Static guard (the browser spec is the behaviour proof): password/hidden are skipped before
    any name is read and the sensitive-name regex still ships in the observation."""
    source = (ROOT / "workers/playwright/src/vision-dom.ts").read_text("utf-8")
    assert 'type === "password" || type === "hidden"' in source and "private_input" in source
    assert "password|passwd|secret|token" in source
    assert "[redacted]" in source.replace(chr(92), "")


def test_executed_click_contract_rejects_free_text_fields():
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError, extra=forbid
        VisualExecutedClick(x=0.1, y=0.1, viewport_width=1280, viewport_height=720,
                            before_frame_id=uuid4(), confirmed_at=NOW, typed_text=SECRET)
    assert hashlib.sha256(b"x").hexdigest()  # keep hashlib import honest
