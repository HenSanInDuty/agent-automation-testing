"""ADR-040 harness side: click context (A1), dom_path bindings (A2) and inventory detection (A3).

Offline: a fake API serves a stored trace; every optional source may be absent, partial or
corrupt, and each source combination re-scores from the same stored data.
"""

import hashlib
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import test_vision_accuracy_binding as base  # noqa: E402

module, evidence_module = base.module, base.evidence_module
VIEW = base.VIEW
SOURCE = "https://site.test/"
SOURCE_FP = hashlib.sha256(SOURCE.encode()).hexdigest()
OTHER_FP = hashlib.sha256(b"https://site.test/other").hexdigest()


def item(identifier, label, box, *, tag="a", expected=True, path=None):
    row = base.example(identifier, label, box, tag=tag, expected=expected)
    row["reference_path"] = path or (
        f"html > body:nth-of-type(1) > {tag}:nth-of-type({identifier[1:]})")
    return row


ORACLE = {"schema_version": "vision-accuracy-oracle-v1", "viewport": VIEW, "source_url": SOURCE,
          "examples": [
              item("h1", "TRANG CHỦ", (332, 10, 145, 37)),                    # fixed header
              item("f1", "Đăng ký", (100, 877, 80, 40), tag="button"),          # in flow
              item("f2", "Đăng ký", (100, 1477, 80, 40), tag="button"),         # same label, lower
              item("g1", "Go", (100, 277, 80, 40), tag="button"),
              item("g2", "Go", (100, 877, 80, 40), tag="button"),
              item("u1", "", (585, 2375, 8, 8), tag="button",
                   path="html > body:nth-of-type(1) > div:nth-of-type(2) > button:nth-of-type(1)"),
              item("n1", "Thoát", (900, 300, 80, 40), expected=False),
          ]}
CHECKSUM = base.CHECKSUM


class AgentTrace(base.Trace):
    """The base trace plus the optional evidence: click context and `/result` pages."""

    def __init__(self, pages=None):
        super().__init__()
        self.pages = pages or []

    def click_with(self, name, context=None, **kwargs):
        identifier = self.click(name, **kwargs)
        if context:
            self.items[-1]["executed_click"].update(context)
        return identifier

    def __call__(self, request):
        if request.url.path.endswith("/result"):
            return httpx.Response(200, json={
                "schema_version": "v1", "session_id": self.session,
                "exploration_state": "unavailable", "completion_reason": "agent_stopped",
                "exploration_report": {"conclusion": {}}, "pages": self.pages})
        return super().__call__(request)


def collected(tmp_path, build, pages=None, oracle=ORACLE):
    trace = AgentTrace(pages)
    build(trace)
    client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(trace),
                          headers={"Authorization": "Bearer private-secret"})
    loop = module.Loop(client, tmp_path / "runs")
    iteration = loop.start(trace.session, oracle, base.POLICY, candidate_hash="x", existing=True)
    return loop, iteration, loop.collect(iteration), trace


def ctx(scroll_y=0, scroll_x=0, url=SOURCE_FP):
    return {"scroll_x": scroll_x, "scroll_y": scroll_y, "url_fingerprint": url}


def box_at(doc_box, scroll_y=0):
    x, y, w, h = doc_box
    return (x, y - scroll_y, w, h)


def grade(loop, iteration, evidence, credited, **options):
    detection = module.Detection(oracle_hash=module.content_hash(ORACLE), identified_ids=(),
                                 inventory_complete=False)
    rows = base.assess(loop, iteration, evidence, ORACLE, credited)
    return loop.evaluate(iteration, rows, detection, **options)


def in_flow(build_context, *, scroll=600, target="f1", name="Đăng ký", doc=(100, 877, 80, 40)):
    ids = {}

    def build(trace):
        ids["op"] = trace.click_with(name, build_context, role="button",
                                     box=box_at(doc, scroll))

    loop, iteration, evidence, _ = collected_pair(build)
    return loop, iteration, evidence, {ids["op"]: target}


_DIRECTORY = []


def collected_pair(build, pages=None):
    import tempfile
    directory = Path(tempfile.mkdtemp(prefix="agent-evidence-", dir=_DIRECTORY[0]))
    return collected(directory, build, pages)


@pytest.fixture(autouse=True)
def scratch(tmp_path):
    _DIRECTORY[:] = [tmp_path]


# ------------------------------------------------------------------------------ A1 click context

def test_without_click_context_the_in_flow_target_is_unbindable_as_before():
    loop, iteration, evidence, credited = in_flow(None)
    with pytest.raises(ValueError, match=r"binding does not match oracle \(no_oracle_match\)"):
        grade(loop, iteration, evidence, credited)


def test_scroll_context_binds_an_in_flow_target_and_old_sources_are_selectable():
    loop, iteration, evidence, credited = in_flow(ctx(600))
    score = grade(loop, iteration, evidence, credited)
    assert score["covered_targets"] == ["f1"]
    grounding = json.loads((loop.directory / iteration / "grounding.json").read_text("utf-8"))
    assert list(grounding["contexts"].values()) == [
        {"scroll": {"x": 0, "y": 600}, "url_fingerprint": SOURCE_FP}]
    for sources in ("none", "inventory"):  # click_context not selected: scored as without A1
        with pytest.raises(ValueError, match="no_oracle_match"):
            grade(loop, iteration, evidence, credited, sources=sources)


def test_a_fixed_header_binds_at_any_scroll_and_a_wrong_offset_never_helps():
    ids = {}

    def build(trace):
        ids["op"] = trace.click_with("TRANG CHỦ", ctx(900), box=(332, 10, 145, 37))

    loop, iteration, evidence, _ = collected_pair(build)
    assert grade(loop, iteration, evidence, {ids["op"]: "h1"})["covered_targets"] == ["h1"]
    loop, iteration, evidence, credited = in_flow(ctx(300))  # box is 877-600, scrolled by 300
    with pytest.raises(ValueError, match="no_oracle_match"):
        grade(loop, iteration, evidence, credited)


def test_the_scroll_offset_picks_between_controls_with_the_same_label():
    loop, iteration, evidence, credited = in_flow(
        ctx(1200), scroll=1200, target="f2", doc=(100, 1477, 80, 40))
    assert grade(loop, iteration, evidence, credited)["covered_targets"] == ["f2"]
    loop, iteration, evidence, _ = in_flow(
        ctx(1200), scroll=1200, target="f2", doc=(100, 1477, 80, 40))
    operation = next(row["id"] for row in evidence["operations"] if row["action_kind"] == "click")
    with pytest.raises(ValueError, match="target_mismatch"):
        grade(loop, iteration, evidence, {operation: "f1"})


def test_a_control_matching_at_two_offsets_is_ambiguous_not_credited():
    """Fixed g1 (offset 0) and in-flow g2 (offset 600) both fit the same viewport box."""
    ids = {}

    def build(trace):
        ids["op"] = trace.click_with("Go", ctx(600), role="button", box=(100, 277, 80, 40))

    loop, iteration, evidence, _ = collected_pair(build)
    with pytest.raises(ValueError, match="ambiguous_oracle_match"):
        grade(loop, iteration, evidence, {ids["op"]: "g2"})


@pytest.mark.parametrize("rule", ["role", "path"])
def test_a_click_on_another_page_earns_nothing_for_both_binding_rules(rule):
    ids = {}

    def build(trace):
        if rule == "role":
            ids["op"] = trace.click_with("TRANG CHỦ", ctx(0, url=OTHER_FP), box=(332, 10, 145, 37))
        else:
            ids["op"] = trace.click_with(
                ORACLE["examples"][5]["reference_path"], ctx(0, url=OTHER_FP),
                strategy="dom_path", role="button", box=(585, 2375, 8, 8))

    loop, iteration, evidence, _ = collected_pair(build)
    target = "h1" if rule == "role" else "u1"
    with pytest.raises(ValueError, match="off_page_url"):
        grade(loop, iteration, evidence, {ids["op"]: target})
    # Without the click-context source the old rules apply unchanged.
    score = grade(loop, iteration, evidence, {ids["op"]: target}, sources="none")
    assert score["covered_targets"] == [target]


def test_partial_or_corrupt_context_is_ignored_and_never_crashes():
    for bad in ({"scroll_y": 600}, {"scroll_x": 0, "scroll_y": -4, "url_fingerprint": SOURCE_FP},
                {"scroll_x": 0, "scroll_y": "600", "url_fingerprint": SOURCE_FP},
                {"scroll_x": 0, "scroll_y": 600, "url_fingerprint": "nope"},
                {"scroll_x": 0, "scroll_y": True, "url_fingerprint": SOURCE_FP}):
        loop, iteration, evidence, credited = in_flow(bad)
        grounding = json.loads((loop.directory / iteration / "grounding.json").read_text("utf-8"))
        assert "contexts" not in grounding
        with pytest.raises(ValueError, match="no_oracle_match"):
            grade(loop, iteration, evidence, credited)


def test_click_context_unit_contract():
    assert evidence_module.click_context(None) is None
    assert evidence_module.click_context({}) is None
    assert evidence_module.click_context(ctx(5, 2)) == {
        "scroll": {"x": 2, "y": 5}, "url_fingerprint": SOURCE_FP}
    assert evidence_module.source_fingerprint({"source_url": SOURCE}) == SOURCE_FP
    assert evidence_module.source_fingerprint({}) is None


def test_grounding_without_any_context_keeps_exactly_its_old_shape(tmp_path):
    ids = {}

    def build(trace):
        ids["op"] = trace.click_with("TRANG CHỦ", None, box=(332, 10, 145, 37))

    loop, iteration, evidence, _ = collected(tmp_path, build)
    grounding = json.loads((loop.directory / iteration / "grounding.json").read_text("utf-8"))
    assert set(grounding) == {"schema_version", "session_id", "trace_revision", "locators"}
    assert not (loop.directory / iteration / "inventory.json").exists()
    assert grade(loop, iteration, evidence, {ids["op"]: "h1"})["covered_targets"] == ["h1"]


def test_stored_grounding_cannot_claim_context_for_an_unknown_operation(tmp_path):
    loop, iteration, evidence, _ = collected_pair(
        lambda trace: trace.click_with("TRANG CHỦ", ctx(0), box=(332, 10, 145, 37)))
    path = loop.directory / iteration / "grounding.json"
    document = json.loads(path.read_text("utf-8"))
    document["contexts"]["00000000-0000-0000-0000-000000000000"] = document["contexts"].popitem()[1]
    with pytest.raises(ValueError, match="grounding does not match evidence"):
        module.check_grounding(document, evidence)


def test_ground_adds_contexts_and_inventory_to_stored_evidence_and_reports_counts():
    pages = [page(SOURCE_FP, [control("a" * 64, "link", "Trang chu")])]
    loop, iteration, _, _ = collected_pair(
        lambda trace: trace.click_with("TRANG CHỦ", ctx(0), box=(332, 10, 145, 37)), pages)
    document = loop.ground(iteration)
    assert len(document["contexts"]) == 1
    assert json.loads((loop.directory / iteration / "inventory.json").read_text("utf-8"))["pages"]


# ------------------------------------------------------------------------------ A2 path bindings

def test_a_dom_path_locator_of_an_unnamed_control_binds_by_the_historical_rule():
    ids = {}
    path = ORACLE["examples"][5]["reference_path"]

    def build(trace):
        ids["op"] = trace.click_with(path, ctx(1800), strategy="dom_path", role="button",
                                     box=(585, 575, 8, 8))

    loop, iteration, evidence, _ = collected_pair(build)
    assert [row["path"] for row in evidence["locators"]] == [path]
    assert grade(loop, iteration, evidence, {ids["op"]: "u1"})["covered_targets"] == ["u1"]
    with pytest.raises(ValueError, match="path_mismatch"):
        grade(loop, iteration, evidence, {ids["op"]: "h1"})


# ------------------------------------------------------------------------------ combinations

def test_each_source_combination_scores_from_the_same_stored_data_without_collisions():
    ids = {}

    def build(trace):
        ids["fixed"] = trace.click_with("TRANG CHỦ", ctx(0), box=(332, 10, 145, 37))
        ids["flow"] = trace.click_with("Đăng ký", ctx(600), role="button",
                                       box=box_at((100, 877, 80, 40), 600))

    loop, iteration, evidence, _ = collected_pair(build)
    both = grade(loop, iteration, evidence, {ids["fixed"]: "h1", ids["flow"]: "f1"},
                 label="click-context")
    old = grade(loop, iteration, evidence, {ids["fixed"]: "h1"}, sources="none", label="old")
    folder = loop.directory / iteration
    assert both["coverage"]["numerator"] == 2 and old["coverage"]["numerator"] == 1
    assert (folder / "score.click-context.json").exists() and (folder / "score.old.json").exists()
    assert not (folder / "score.json").exists()  # the retained default artifact is not touched
    assert module.parse_sources(None) == {"click_context", "inventory"}
    assert module.parse_sources("none") == set()
    assert module.parse_sources("inventory") == {"inventory"}
    for bad in ("bogus", "click_context,x"):
        with pytest.raises(ValueError, match="unknown evidence source"):
            module.parse_sources(bad)
    for label in ("../x", "a b", "a.b"):
        with pytest.raises(ValueError, match="invalid label"):
            module.artifact(folder, "score", label)


# ------------------------------------------------------------------------------ A3 inventory

def control(key, role, name):
    return {"key": key, "role": role, "name": name, "status": "pending"}


def page(url, controls, *, scrollable=False, truncated=False, skipped=0):
    return {"state_id": base.ROOT_PAGE, "checkpoint_id": base.ROOT_PAGE, "url_fingerprint": url,
            "controls": controls, "scrollable": scrollable, "truncated": truncated,
            "skipped_count": skipped, "interaction_scope": "all", "page_url": "https://x/"}


U1_KEY = evidence_module.descriptor_key(ORACLE["examples"][5]["reference_path"], "v2")
PAGES = [
    page(SOURCE_FP, [control(U1_KEY, "button", ""),                      # dom_path key -> u1
                     control("a" * 64, "link", "Trang chu"),             # unique name -> h1
                     control("b" * 64, "button", "Đăng ký"),              # two oracle matches
                     control("c" * 64, "link", "Không có")]),            # not in the oracle
    page(OTHER_FP, [control("d" * 64, "link", "Trang chu")]),            # other page: ignored
]


def test_descriptor_key_is_the_control_plane_content_hash():
    from auto_at.contracts.codex_bridge import content_hash
    from auto_at.contracts.vision import VisualLocatorDescriptor
    button = "html > body:nth-of-type(1) > div:nth-of-type(2) > button:nth-of-type(1)"
    other = "html > body:nth-of-type(1) > div:nth-of-type(2) > a:nth-of-type(1)"
    for path, version in ((button, "v2"), (other, "v3"), (button, "v3")):
        descriptor = VisualLocatorDescriptor(
            schema_version=version, strategy="dom_path", value=path)
        assert evidence_module.descriptor_key(path, version) == content_hash(descriptor)


def test_inventory_export_is_an_allowlist_and_survives_junk():
    exported = evidence_module.export_inventory([
        {**PAGES[0], "secret": "x", "controls": [
            {**control(U1_KEY, "button", ""), "value": "typed text", "operation_id": "z"},
            {"key": "short", "role": "link", "name": "x"}, {"key": U1_KEY, "role": "BAD!"},
            "junk", None, {**control("e" * 64, "link", "n" * 500)}]},
        {"state_id": "not-an-id", "url_fingerprint": SOURCE_FP}, {"url_fingerprint": 5}, None,
    ])
    assert len(exported) == 1
    assert set(exported[0]) == {"state_id", "url_fingerprint", "controls", "truncated",
                                "scrollable", "skipped_count"}
    assert exported[0]["controls"] == [{"key": U1_KEY, "role": "button", "name": ""},
                                       {"key": "e" * 64, "role": "link", "name": None}]
    assert evidence_module.export_inventory(None) == []
    assert "typed text" not in json.dumps(exported)


def test_detection_comes_from_the_inventory_of_the_oracle_page_only(tmp_path):
    loop, iteration, _, _ = collected(tmp_path, lambda trace: None, PAGES)
    detection = loop.detect(iteration)
    assert detection["identified_ids"] == ["h1", "u1"]
    assert len(detection["unexpected_paths"]) == 1
    assert detection["unexpected_paths"][0].startswith("unmatched_key:" + "c" * 64)
    assert detection["inventory_complete"] is True
    facts = json.loads((loop.directory / iteration / "detection.facts.json").read_text("utf-8"))
    assert facts == {"ambiguous_controls": 1, "pages_on_oracle_url": 1}
    assert module.Detection.model_validate(detection)  # usable as `evaluate --detection`


@pytest.mark.parametrize("change", [{"scrollable": True}, {"truncated": True}, {"skipped": 2}])
def test_inventory_is_incomplete_when_scrollable_truncated_or_skipped(tmp_path, change):
    pages = [page(SOURCE_FP, [control(U1_KEY, "button", "")], **change)]
    loop, iteration, _, _ = collected(tmp_path, lambda trace: None, pages)
    assert loop.detect(iteration)["inventory_complete"] is False


def test_without_inventory_or_with_it_deselected_detection_is_the_old_empty_one(tmp_path):
    loop, iteration, _, _ = collected(tmp_path / "a", lambda trace: None)
    assert not (loop.directory / iteration / "inventory.json").exists()
    old = {"oracle_hash": module.content_hash(ORACLE), "identified_ids": [],
           "unexpected_paths": [], "inventory_complete": False}
    assert loop.detect(iteration) == old
    loop, iteration, _, _ = collected(tmp_path / "b", lambda trace: None, PAGES)
    assert loop.detect(iteration, sources="click_context", label="no-inventory") == old
    assert loop.detect(iteration, sources="none", label="none") == old
    derived = loop.detect(iteration, sources="inventory", label="inv")
    assert derived["identified_ids"] == ["h1", "u1"]


def test_inventory_of_another_session_or_a_changed_oracle_is_refused(tmp_path):
    loop, iteration, _, _ = collected(tmp_path, lambda trace: None, PAGES)
    path = loop.directory / iteration / "inventory.json"
    document = json.loads(path.read_text("utf-8"))
    document["session_id"] = base.ROOT_PAGE
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="inventory does not match session"):
        loop.detect(iteration)
    (loop.directory / iteration / "oracle.json").write_text(
        json.dumps({**ORACLE, "examples": ORACLE["examples"][:2]}), encoding="utf-8")
    with pytest.raises(ValueError, match="oracle changed after start"):
        loop.detect(iteration)


def test_a_derived_detection_scores_with_the_unchanged_metrics(tmp_path):
    loop, iteration, evidence, _ = collected(tmp_path, lambda trace: None, PAGES)
    detection = module.Detection.model_validate(loop.detect(iteration))
    rows = base.assess(loop, iteration, evidence, ORACLE, {})
    score = loop.evaluate(iteration, rows, detection)
    assert score["detection_recall"]["numerator"] == 2  # h1 and u1 of 6 positives
    assert score["detection_precision"]["denominator"] == 3  # 2 identified + 1 unexpected
    assert score["inventory_complete"] is True and score["passed"] is False
