"""Strict role-locator binding for agent_loop evidence. Offline: no Docker, provider or browser."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

DIRECTORY = Path(__file__).parents[1] / "benchmark/vision/accuracy"
sys.path.insert(0, str(DIRECTORY))
spec = importlib.util.spec_from_file_location("accuracy_run_binding", DIRECTORY / "run.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
evidence_module = sys.modules["evidence"]
sys.path.remove(str(DIRECTORY))

POLICY = {"expected_provider": "claude_cli", "expected_model": "m",
          "expected_input_policy_fingerprint": "a" * 64}
VIEW = {"width": 1280, "height": 720}
ROOT_PAGE, POPUP_PAGE = str(uuid4()), str(uuid4())
FRAME = b"synthetic-frame-content"
CHECKSUM = hashlib.sha256(FRAME).hexdigest()
REAL_ORACLE = json.loads((DIRECTORY / "oracle-mongchiton-1280-v1.json").read_text("utf-8"))


def example(identifier, label, box, *, tag="a", expected=True):
    item = {"id": identifier, "expected": expected, "tag": tag, "label": label,
            "reference_box": dict(zip(("x", "y", "width", "height"), box, strict=True)),
            "reference_path": f"html > body:nth-of-type(1) > {tag}:nth-of-type(1)"}
    if expected:
        item |= {"action_kind": "click", "outcome": {"kind": "navigation_destination"}}
    return item


MINI = {"schema_version": "vision-accuracy-oracle-v1", "viewport": VIEW, "examples": [
    example("m1", "SỰ KIỆN", (488, 11, 145, 37)),
    example("m2", "Đăng ký", (100, 300, 80, 40), tag="button"),
    example("m3", "Thoát", (900, 300, 80, 40), expected=False),
    example("m4", "Xem", (300, 500, 100, 40)),
    example("m5", "Xem", (305, 502, 100, 40)),
    example("m6", "Xem thêm", (300, 600, 100, 40)),
    example("m7", "Xem thêm", (700, 600, 100, 40)),
    example("m8", "", (50, 50, 40, 40)),
]}


def px_box(box, viewport=VIEW):
    x, y, w, h = box
    return {"x": x / viewport["width"], "y": y / viewport["height"],
            "width": w / viewport["width"], "height": h / viewport["height"]}


def centre(box, viewport=VIEW):
    x, y, w, h = box
    return {"x": (x + w / 2) / viewport["width"], "y": (y + h / 2) / viewport["height"]}


class Trace:
    """Stands in for GET /result, /trace and frame bytes of one agent_loop session."""

    def __init__(self):
        self.session = str(uuid4())
        self.items, self.locators = [], []
        self.revision = "b" * 64
        self.add("setup", "navigate", page=ROOT_PAGE)

    def frame(self):
        return {"id": str(uuid4()), "checksum": CHECKSUM, "byte_count": len(FRAME),
                "availability": "retained"}

    def add(self, purpose, action, *, status="completed", locator=None, click=None,
            page=ROOT_PAGE, after=ROOT_PAGE, code="observed", identifier=None):
        operation = {"id": identifier or str(uuid4()), "sequence": len(self.items) + 1,
                     "status": status, "purpose": purpose, "action_kind": action,
                     "outcome_code": code,
                     "locator_id": locator, "before_page_id": page, "after_page_id": after,
                     "url_change": "changed", "visual_change": "changed",
                     "before": self.frame(), "after": self.frame(), "executed_click": click}
        self.items.append(operation)
        return operation["id"]

    def click(self, name, *, role="link", box=None, norm=None, point=None, viewport=VIEW,
              page=ROOT_PAGE, status="verified", strategy="role", after=ROOT_PAGE):
        locator, operation = str(uuid4()), str(uuid4())
        norm = norm or px_box(box, viewport)
        point = point or centre(box, viewport)
        descriptor = {"schema_version": "v1", "strategy": strategy, "value": name, "exact": True,
                      "scope": [], "role": role if strategy == "role" else None}
        self.locators.append({"id": locator, "operation_id": operation, "status": status,
                              "descriptor": descriptor, "bounding_box": norm,
                              "matched_count": 1})
        click = {**point, "viewport_width": viewport["width"],
                 "viewport_height": viewport["height"], "before_frame_id": str(uuid4())}
        return self.add("explore", "click", locator=locator, click=click, page=page,
                        after=after, identifier=operation)

    def __call__(self, request):
        path = request.url.path
        if path.endswith("/result"):
            return httpx.Response(200, json={
                "schema_version": "v1", "session_id": self.session,
                "exploration_state": "unavailable", "completion_reason": "agent_stopped",
                "exploration_report": {"conclusion": {}}, "pages": []})
        if path.endswith("/trace"):
            return httpx.Response(200, json={
                "schema_version": "v1", "session_id": self.session, "revision": self.revision,
                "next_sequence": len(self.items), "has_more": False, "items": self.items,
                "locators": self.locators})
        if "/operation-frames/" in path:
            return httpx.Response(200, content=FRAME)
        if path.endswith("/explorations"):
            return httpx.Response(200, json={"items": []})
        return httpx.Response(200, json={"id": self.session, "state": "unavailable"})


def collected(tmp_path, oracle, build):
    trace = Trace()
    build(trace)
    client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(trace),
                          headers={"Authorization": "Bearer private-secret"})
    loop = module.Loop(client, tmp_path / "runs")
    iteration = loop.start(trace.session, oracle, POLICY, candidate_hash="x", existing=True)
    return loop, iteration, loop.collect(iteration), trace


def assess(loop, iteration, evidence, oracle, credited):
    digest = module.content_hash(oracle)
    targets = {item["id"]: item for item in oracle["examples"]}
    rows = []
    for operation in evidence["operations"]:
        base = {"operation_id": operation["id"], "oracle_hash": digest,
                "status": operation["status"], "purpose": operation["purpose"],
                "action_kind": operation["action_kind"],
                "before_checksum": operation["before"]["checksum"],
                "after_checksum": operation["after"]["checksum"]}
        target = credited.get(operation["id"])
        if not target:
            rows.append(module.Assessment(**base))
            continue
        kind = targets[target].get("outcome", {}).get("kind", "navigation_destination")
        reference = loop.record_review(iteration, module.OutcomeReview(
            operation_id=operation["id"], oracle_hash=digest, outcome_kind=kind,
            verdict="correct", review_method="evidence_review",
            before_checksum=operation["before"]["checksum"],
            after_checksum=operation["after"]["checksum"],
            finding="Synthetic reviewed destination matches the declared outcome.",
        ))
        rows.append(module.Assessment(
            **base, target_id=target, target_verdict="correct", outcome_verdict="correct",
            binding_reference=operation["locator_id"], review_method="evidence_review",
            outcome_reference=reference))
    return rows


def evaluate(loop, iteration, evidence, oracle, credited):
    detection = module.Detection(oracle_hash=module.content_hash(oracle), identified_ids=(),
                                 inventory_complete=False)
    return loop.evaluate(iteration, assess(loop, iteration, evidence, oracle, credited),
                         detection)


def credit_one(tmp_path, name, *, target="m1", oracle=MINI, **kwargs):
    ids = {}

    def build(trace):
        ids["op"] = trace.click(name, **kwargs)

    loop, iteration, evidence, _ = collected(tmp_path, oracle, build)
    return evaluate(loop, iteration, evidence, oracle, {ids["op"]: target})


R6 = [  # (name, role, normalized box, click point, oracle id) copied from agent_loop r6 locators
    ("SỰ KIỆN", "link", (0.3809733152389526, 0.015379051367441813, 0.11297199726104737,
                         0.050708915127648246), (0.438577015200474, 0.042169679686820886),
     "mct-02"),
    ("ĐIỀU KHOẢN", "link", (0.623583984375, 0.015379051367441813, 0.11297202110290527,
                            0.050708915127648246), (0.6813760597879203, 0.042169679686820886),
     "mct-04"),
    ("CỘNG ĐỒNG", "link", (0.7448893547058105, 0.015379051367441813, 0.11297197341918945,
                           0.050708915127648246), (0.8027834321857896, 0.042169679686820886),
     "mct-05"),
    ("HỖ TRỢ", "link", (0.8661947250366211, 0.015379051367441813, 0.11297197341918945,
                        0.050708915127648246), (0.9241829783400117, 0.042169679686820886),
     "mct-06"),
    ("TRANG CHỦ", "link", (0.25966796875, 0.015379051367441813, 0.11297202110290527,
                           0.050708915127648246), (0.3171774929067509, 0.042169679686820886),
     "mct-01"),
]
R6_TABS = [  # completed clicks on /su-kien, /tin-tuc, /cam-nang: same labels, other role and place
    ("Tin Tức", (0.31171875, 0.7077401902940538, 0.12135419845581055, 0.05536744859483507),
     (0.3726817855059495, 0.7364394993045897)),
    ("Sự Kiện", (0.44140625, 0.7077401902940538, 0.12135419845581055, 0.05536744859483507),
     (0.502470659221682, 0.7364394993045897)),
    ("Cẩm Nang", (0.57109375, 0.7077401902940538, 0.12135419845581055, 0.05536744859483507),
     (0.6322595567979135, 0.7364394993045897)),
]


def unit(norm):
    return dict(zip(("x", "y", "width", "height"), norm, strict=True))


def build_r6(trace):
    """Operation order of r6: clicks, popup recoveries, then four rejected state_mismatch clicks."""
    credited = {}

    def header(index, **extra):
        name, role, norm, point, target = R6[index]
        operation = trace.click(name, role=role, norm=unit(norm),
                                point=dict(zip(("x", "y"), point, strict=True)), **extra)
        credited[operation] = target
        if extra:
            trace.add("explore", "close_popup", page=POPUP_PAGE)

    header(0)
    for name, norm, point in R6_TABS:
        trace.click(name, role="button", norm=unit(norm),
                    point=dict(zip(("x", "y"), point, strict=True)))
    for index in (1, 2, 3):
        header(index, after=POPUP_PAGE)
    header(4)
    for _ in range(4):
        trace.add("explore", "click", status="rejected", page=None, after=None,
                  code="state_mismatch")
    trace.credited = credited


def test_r6_shape_five_header_clicks_bind_to_oracle_and_score_matches_manual_review(tmp_path):
    """Red before the change: every credited click raised 'assessment binding does not match'."""
    loop, iteration, evidence, trace = collected(tmp_path, REAL_ORACLE, build_r6)
    assert all(row["path"] is None for row in evidence["locators"])
    score = evaluate(loop, iteration, evidence, REAL_ORACLE, trace.credited)
    assert (score["coverage"]["numerator"], score["coverage"]["denominator"]) == (5, 47)
    assert (score["accuracy"]["numerator"], score["accuracy"]["denominator"]) == (5, 12)
    assert score["covered_targets"] == ["mct-01", "mct-02", "mct-04", "mct-05", "mct-06"]
    assert score["detection_recall"]["numerator"] == 0 and not score["inventory_complete"]
    assert not score["passed"] and not score["unsafe_operations"]


def test_name_is_normalised_but_must_still_equal_and_boxes_pick_between_duplicates(tmp_path):
    box = MINI["examples"][0]["reference_box"]
    ref = tuple(box.values())
    assert credit_one(tmp_path / "a", "su kien", box=ref)["covered_targets"] == ["m1"]
    far = MINI["examples"][6]["reference_box"]
    result = credit_one(tmp_path / "b", "XEM THEM", target="m7", box=tuple(far.values()))
    assert result["covered_targets"] == ["m7"]


def test_normalize_label_and_iou_contract():
    assert evidence_module.normalize_label("  ĐIỀU   Khoản ") == "dieu khoan"
    assert evidence_module.normalize_label("Đăng ký") == "dang ky"
    assert evidence_module.box_iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1
    assert evidence_module.box_iou((0, 0, 10, 10), (20, 0, 10, 10)) == 0


M1 = tuple(MINI["examples"][0]["reference_box"].values())
M2 = tuple(MINI["examples"][1]["reference_box"].values())
M4 = tuple(MINI["examples"][3]["reference_box"].values())
SHIFT = (M1[0], M1[1] + 20, M1[2], M1[3])


@pytest.mark.parametrize("name,kwargs,target,reason", [
    ("SỰ KIỆN nhanh", {"box": M1}, "m1", "no_oracle_match"),           # label differs
    ("SỰ KIỆN", {"box": SHIFT}, "m1", "no_oracle_match"),               # box off by 20 px
    ("SỰ KIỆN", {"box": M1, "role": "button"}, "m1", "no_oracle_match"),  # link vs button
    ("Đăng ký", {"box": M2}, "m2", "no_oracle_match"),                  # role link, oracle button
    ("SỰ KIỆN", {"box": M1, "page": POPUP_PAGE}, "m1", "off_root_page"),
    ("SỰ KIỆN", {"box": M1, "viewport": {"width": 1024, "height": 768}}, "m1", "viewport"),
    ("SỰ KIỆN", {"box": M1, "point": {"x": 0.9, "y": 0.9}}, "m1", "click_outside_target"),
    ("Khuyến mãi", {"box": M2, "role": "button"}, "m2", "no_oracle_match"),  # outside the oracle
    ("Xem", {"box": M4}, "m4", "ambiguous_oracle_match"),               # two candidates
    ("", {"box": (50, 50, 40, 40)}, "m8", "empty_name"),
    ("Thoát", {"box": (900, 300, 80, 40)}, "m1", "target_mismatch"),    # reviewer names m1
    ("SỰ KIỆN", {"box": M1, "status": "ambiguous"}, "m1", "locator_not_verified"),
    ("SỰ KIỆN", {"box": M1, "strategy": "css"}, "m1", "no_role_grounding"),
])
def test_ambiguous_or_mismatched_role_locators_earn_no_credit(tmp_path, name, kwargs, target,
                                                              reason):
    with pytest.raises(ValueError, match=f"does not match oracle.*{reason}"):
        credit_one(tmp_path, name, target=target, **kwargs)


def test_same_target_cannot_be_credited_twice(tmp_path):
    ids = []

    def build(trace):
        ids.extend(trace.click("SỰ KIỆN", box=M1) for _ in range(2))

    loop, iteration, evidence, _ = collected(tmp_path, MINI, build)
    with pytest.raises(ValueError, match="already credited"):
        evaluate(loop, iteration, evidence, MINI, dict.fromkeys(ids, "m1"))
    one = {ids[0]: "m1"}
    score = evaluate(loop, iteration, evidence, MINI, one)
    assert score["covered_targets"] == ["m1"] and score["accuracy"]["numerator"] == 1
    assert score["accuracy"]["denominator"] == 2


def test_uncredited_unverified_attempts_still_count_against_accuracy(tmp_path):
    ids = []

    def build(trace):
        ids.append(trace.click("Khuyến mãi", box=M2, role="button"))

    loop, iteration, evidence, _ = collected(tmp_path, MINI, build)
    score = evaluate(loop, iteration, evidence, MINI, {})
    assert score["accuracy"]["numerator"] == 0 and score["accuracy"]["denominator"] == 1


def test_legacy_evidence_needs_explicit_grounding_and_tampering_is_rejected(tmp_path):
    loop, iteration, evidence, trace = collected(
        tmp_path, MINI, lambda trace: trace.click("SỰ KIỆN", box=M1))
    folder = loop.directory / iteration
    credited = {trace.items[1]["id"]: "m1"}
    (folder / "grounding.json").unlink()  # evidence collected before grounding existed
    with pytest.raises(ValueError, match="no_role_grounding"):
        evaluate(loop, iteration, evidence, MINI, credited)
    grounding = loop.ground(iteration)
    assert evaluate(loop, iteration, evidence, MINI, credited)["covered_targets"] == ["m1"]
    assert loop.ground(iteration) == grounding  # idempotent, immutable
    module.write_json(folder / "grounding.json", {**grounding, "trace_revision": "c" * 64},
                      replace=True)
    with pytest.raises(ValueError, match="grounding does not match evidence"):
        evaluate(loop, iteration, evidence, MINI, credited)
    module.write_json(folder / "grounding.json", grounding, replace=True)
    (folder / "grounding.json").unlink()
    trace.revision = "c" * 64  # the stored trace changed after collection
    with pytest.raises(ValueError, match="grounding does not match evidence"):
        loop.ground(iteration)


def test_grounding_export_is_allowlisted():
    raw = {"id": str(uuid4()), "operation_id": str(uuid4()), "status": "verified",
           "descriptor": {"strategy": "role", "role": "link", "value": "SỰ KIỆN",
                          "private": "private-secret"},
           "bounding_box": {"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1, "q": 1}}
    operation = {"id": raw["operation_id"], "executed_click": {
        "x": 0.1, "y": 0.1, "viewport_width": 1280, "viewport_height": 720,
        "before_frame_id": "private-secret"}}
    exported = evidence_module.export_grounding([operation], [raw])
    assert "private-secret" not in json.dumps(exported)
    bad = {**raw, "bounding_box": {"x": 2, "y": 0, "width": 1, "height": 1}}
    assert evidence_module.export_grounding([operation], [bad])[raw["id"]]["box"] is None


def test_old_runs_keep_their_credited_bindings_and_stored_scores():
    """dom_path runs: every credited assessment passes the unchanged path rule and re-scores."""
    runs = sorted((DIRECTORY / "runs").glob("*/assessments.json"))
    assert runs
    checked = credited = 0
    for assessments_path in runs:
        folder = assessments_path.parent
        if not (folder / "score.json").exists() or (folder / "grounding.json").exists():
            continue
        oracle = json.loads((folder / "oracle.json").read_text("utf-8"))
        evidence = json.loads((folder / "evidence.json").read_text("utf-8"))
        rows = [module.Assessment.model_validate(row) for row in json.loads(
            assessments_path.read_text("utf-8"))]
        detection = module.Detection.model_validate(json.loads(
            (folder / "detection.json").read_text("utf-8")))
        stored = json.loads((folder / "score.json").read_text("utf-8"))
        if stored.get("oracle_hash") != module.content_hash(oracle):
            continue
        operations = {row["id"]: row for row in evidence["operations"]}
        locators = {row["id"]: row for row in evidence["locators"]}
        for row in rows:
            if row.target_verdict == row.outcome_verdict == "correct":
                target = next(e for e in oracle["examples"] if e["id"] == row.target_id)
                binding = locators[operations[row.operation_id]["locator_id"]]
                assert evidence_module.binding_error(
                    oracle, target, binding, None, operations[row.operation_id], None,
                    row.binding_reference) is None
                credited += 1
        assert module.score(oracle, rows, detection) == stored, folder.name
        checked += 1
    assert checked and credited
