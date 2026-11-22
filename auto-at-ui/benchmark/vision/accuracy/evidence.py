"""Allowlisted evidence export. Never copy request bodies, DOM or form values."""

import hashlib
import json
import re
import unicodedata

from metrics import oracle_paths

ROLE = re.compile(r"^[a-z]{3,32}$")
ROLE_BY_TAG = {"a": "link", "button": "button"}  # other oracle tags have no unambiguous role
MIN_BOX_IOU = 0.8
LOCATOR_STATUSES = {"verified", "ambiguous", "not_found", "stale", "unsupported", "redacted"}
ID = re.compile(r"^[a-f0-9-]{36}$")
HASH = re.compile(r"^[a-f0-9]{64}$")
CODE = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
STATES = {"queued", "running", "completed", "unavailable", "cancelled"}
STATUSES = {"prepared", "executing", "completed", "failed", "rejected", "unknown"}
ACTIONS = {"navigate", "click", "type", "scroll", "wait", "back", "close_popup"}
STAGES = {"prepare_start", "prepare_end", "before_dispatch", "page_settle"}
PATH = re.compile(r"^html(?: > [a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]*\)){1,24}$")


def safe_id(value):
    return value if isinstance(value, str) and ID.fullmatch(value) else None


def safe_code(value):
    return value if isinstance(value, str) and CODE.fullmatch(value) else None


def frame_metadata(value):
    value = value or {}
    return {"id": safe_id(value.get("id")),
            "checksum": value.get("checksum") if HASH.fullmatch(value.get("checksum", ""))
            else None,
            "availability": value.get("availability")
            if value.get("availability") in {"retained", "deleted", "missing"} else "missing",
            "byte_count": value.get("byte_count") if type(value.get("byte_count")) is int else None}


def export_operation(row):
    if row.get("status") not in STATUSES or row.get("action_kind") not in ACTIONS:
        raise ValueError("unknown operation status/action")
    if row.get("purpose") not in {"setup", "explore", "restore", "replay"}:
        raise ValueError("unknown operation purpose")
    if not safe_id(row.get("id")) or type(row.get("sequence")) is not int:
        raise ValueError("invalid operation identity")
    return {
        "id": row["id"], "sequence": row["sequence"], "status": row["status"],
        "action_kind": row["action_kind"], "purpose": row["purpose"],
        "outcome_code": safe_code(row.get("outcome_code")),
        **{key: safe_id(row.get(key)) for key in (
            "state_id", "checkpoint_id", "locator_id", "proposal_id", "parent_operation_id",
            "before_page_id", "after_page_id",
        )},
        **{key: row.get(key) if row.get(key) in {"changed", "unchanged", "unavailable"}
           else "unavailable" for key in ("url_change", "visual_change")},
        "before": frame_metadata(row.get("before")), "after": frame_metadata(row.get("after")),
    }


def export_locator(row):
    descriptor = row.get("descriptor") or {}
    path = descriptor.get("value", "")
    return {"id": safe_id(row.get("id")), "operation_id": safe_id(row.get("operation_id")),
            "status": row.get("status") if row.get("status") in LOCATOR_STATUSES
            else "unsupported",
            "path": path if descriptor.get("strategy") == "dom_path"
            and len(path) <= 1024 and PATH.fullmatch(path) else None}


def _unit(value):
    return float(value) if type(value) in {int, float} and 0 <= value <= 1 else None


def _pixels(value):
    return value if type(value) is int and 0 < value <= 16384 else None


def _count(value):
    return value if type(value) is int and 0 <= value <= 10_000_000 else None


def click_context(click):
    """Scroll offset and page URL fingerprint of a click (ADR-040, `click-context-v1`), or None.

    Present only when the worker exported all three facts and they are valid; partial or invalid
    data is treated as absent, so it can only fall back to the context-free rule."""
    click = click or {}
    x, y = _count(click.get("scroll_x")), _count(click.get("scroll_y"))
    url = click.get("url_fingerprint")
    if x is None or y is None or not isinstance(url, str) or not HASH.fullmatch(url):
        return None
    return {"scroll": {"x": x, "y": y}, "url_fingerprint": url}


def export_contexts(operations):
    """Click contexts by operation id; callers omit the key when there is none."""
    return {row["id"]: context for row in operations if safe_id(row.get("id"))
            and (context := click_context(row.get("executed_click")))}


def export_grounding(operations, locators):
    """Facts of `role` locators that bind a click to an oracle target. Invalid facts stay None
    (never repaired), so they can only remove credit. Names are control labels, never values."""
    clicks = {row.get("id"): row.get("executed_click") or {} for row in operations}
    exported = {}
    for row in locators:
        descriptor = row.get("descriptor") or {}
        identifier = safe_id(row.get("id"))
        if not identifier or descriptor.get("strategy") != "role":
            continue
        click, box = clicks.get(row.get("operation_id"), {}), row.get("bounding_box") or {}
        name, role = descriptor.get("value"), descriptor.get("role")
        parts = {key: _unit(box.get(key)) for key in ("x", "y", "width", "height")}
        width, height = _pixels(click.get("viewport_width")), _pixels(click.get("viewport_height"))
        point = {key: _unit(click.get(key)) for key in ("x", "y")}
        exported[identifier] = {
            "operation_id": safe_id(row.get("operation_id")),
            "status": row.get("status") if row.get("status") in LOCATOR_STATUSES
            else "unsupported",
            "role": role if isinstance(role, str) and ROLE.fullmatch(role) else None,
            "name": name if isinstance(name, str) and len(name) <= 240 else None,
            "box": parts if None not in parts.values() and parts["width"] > 0
            and parts["height"] > 0 else None,
            "viewport": {"width": width, "height": height} if width and height else None,
            "click": point if None not in point.values() else None,
        }
    return exported


def normalize_label(value):
    """Case, accent and spacing insensitive label; nothing fuzzier than that."""
    folded = unicodedata.normalize("NFD", value.replace("đ", "d").replace("Đ", "D"))
    return " ".join("".join(c for c in folded if not unicodedata.combining(c)).casefold().split())


def box_iou(first, second):
    """Intersection over union of two (x, y, width, height) pixel boxes."""
    width = min(first[0] + first[2], second[0] + second[2]) - max(first[0], second[0])
    height = min(first[1] + first[3], second[1] + second[3]) - max(first[1], second[1])
    overlap = max(width, 0) * max(height, 0)
    union = first[2] * first[3] + second[2] * second[3] - overlap
    return overlap / union if union > 0 else 0


def source_fingerprint(oracle):
    """SHA-256 of the oracle page URL: the worker's `url_fingerprint` of that page."""
    url = oracle.get("source_url")
    return hashlib.sha256(url.encode()).hexdigest() if isinstance(url, str) and url else None


def _role_binding_error(oracle, target, grounded, operation, root_page_id, context=None):
    if not grounded or grounded["operation_id"] != operation["id"]:
        return "no_role_grounding"
    box, viewport, point = grounded["box"], grounded["viewport"], grounded["click"]
    if None in (box, viewport, point, grounded["role"], grounded["name"]):
        return "incomplete_grounding"
    if viewport != {key: (oracle.get("viewport") or {}).get(key) for key in ("width", "height")}:
        return "viewport"
    if root_page_id is None or operation.get("before_page_id") != root_page_id:
        return "off_root_page"  # popup/new tab; the worker blocks same-tab off-origin actions
    name = normalize_label(grounded["name"])
    if not name:
        return "empty_name"
    pixels = (box["x"] * viewport["width"], box["y"] * viewport["height"],
              box["width"] * viewport["width"], box["height"] * viewport["height"])
    # Oracle boxes are document coordinates, the locator box is viewport relative. Without click
    # context the offset is taken as 0 (ADR-039). With it, a fixed element matches at offset 0 and
    # an in-flow element at the click's scroll offset; the candidate must still be unique.
    offsets = [(0, 0)]
    if context and (context["scroll"]["x"], context["scroll"]["y"]) != (0, 0):
        offsets.append((context["scroll"]["x"], context["scroll"]["y"]))
    matched = {}
    for item in oracle["examples"]:
        if (ROLE_BY_TAG.get(item.get("tag")) != grounded["role"]
                or normalize_label(item.get("label") or "") != name):
            continue
        reference = tuple(item["reference_box"][k] for k in ("x", "y", "width", "height"))
        for dx, dy in offsets:
            if box_iou((pixels[0] + dx, pixels[1] + dy, pixels[2], pixels[3]),
                       reference) >= MIN_BOX_IOU:
                matched.setdefault(item["id"], []).append((dx, dy))
    if len(matched) != 1:
        return "ambiguous_oracle_match" if matched else "no_oracle_match"
    if target["id"] not in matched:
        return "target_mismatch"
    ref = target["reference_box"]
    for dx, dy in matched[target["id"]]:
        x, y = point["x"] * viewport["width"] + dx, point["y"] * viewport["height"] + dy
        if ref["x"] <= x <= ref["x"] + ref["width"] and ref["y"] <= y <= ref["y"] + ref["height"]:
            return None
    return "click_outside_target"


def binding_error(oracle, target, binding, grounded, operation, root_page_id, reference,
                  context=None):
    """None when a credited operation is bound to its oracle target, else a reason code.

    A locator with a DOM path keeps the exact historical rule (path equals reference_path).
    Only a path-less locator may use the stricter role rule: the unique oracle candidate must
    match role, normalized name, box (IoU), viewport and click point, on the session's root tab.
    `context` (click scroll offset and page URL fingerprint, when the session exported it) adds one
    gate to both rules, the click must be on the oracle page, and lets role binding use the scroll.
    """
    if not target:
        return "unknown_target"
    if not binding or binding["status"] != "verified":
        return "locator_not_verified"
    if reference != binding["id"]:
        return "binding_reference"
    expected_page = source_fingerprint(oracle)
    if context and expected_page and context["url_fingerprint"] != expected_page:
        return "off_page_url"
    if binding["path"] is not None:
        return None if binding["path"] in oracle_paths(target) else "path_mismatch"
    return _role_binding_error(oracle, target, grounded, operation, root_page_id, context)


def export_inventory(pages):
    """Allowlisted per-state page inventory of a session (`/result` `pages`, ADR-040 A3).

    Controls keep their descriptor key and the public role/name label, nothing else."""
    exported = []
    for page in pages or ():
        if not isinstance(page, dict):
            continue
        controls = [{"key": control["key"], "role": control["role"],
                     "name": control["name"] if isinstance(control.get("name"), str)
                     and len(control["name"]) <= 120 else None}
                    for control in page.get("controls") or ()
                    if isinstance(control, dict)
                    and isinstance(control.get("key"), str) and HASH.fullmatch(control["key"])
                    and isinstance(control.get("role"), str) and ROLE.fullmatch(control["role"])]
        url, state = page.get("url_fingerprint"), safe_id(page.get("state_id"))
        if not state or not isinstance(url, str) or not HASH.fullmatch(url):
            continue
        exported.append({
            "state_id": state, "url_fingerprint": url, "controls": controls,
            "truncated": page.get("truncated") is True,
            "scrollable": page.get("scrollable") is True,
            "skipped_count": _count(page.get("skipped_count")) or 0})
    return exported


def descriptor_key(path, version):
    """Key of a `dom_path` locator descriptor, as the control plane hashes it for inventories."""
    document = {"exact": True, "role": None, "schema_version": version, "scope": [],
                "strategy": "dom_path", "value": path}
    return hashlib.sha256(json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def derive_detection(oracle, pages):
    """Detection facts of the oracle page from a retained inventory (never from clicks).

    A control is identified by its `dom_path` key, else by role and normalized name when exactly one
    oracle example has them (several: ambiguous, left out of both sides). Other controls on the
    oracle page are unexpected. Completeness needs an unscrollable, untruncated, nothing-skipped
    observation of that page."""
    by_key = {descriptor_key(path, version): item
              for item in oracle["examples"] for path in oracle_paths(item)
              for version in ("v2", "v3")}
    page_url = source_fingerprint(oracle)
    on_page = [page for page in pages if page["url_fingerprint"] == page_url]
    identified, unexpected, ambiguous = set(), set(), 0
    for page in on_page:
        for control in page["controls"]:
            item = by_key.get(control["key"])
            if item is None and control["name"]:
                label = normalize_label(control["name"])
                named = [e for e in oracle["examples"]
                         if ROLE_BY_TAG.get(e.get("tag")) == control["role"]
                         and normalize_label(e.get("label") or "") == label]
                if len(named) > 1:
                    ambiguous += 1
                    continue
                item = named[0] if named else None
            if item is None:
                unexpected.add("unmatched_key:" + control["key"])
            else:
                identified.add(item["id"])
    complete = bool(on_page) and any(not page["scrollable"] for page in on_page) and not any(
        page["truncated"] or page["skipped_count"] for page in on_page)
    return {"identified_ids": sorted(identified), "unexpected_paths": sorted(unexpected),
            "inventory_complete": complete, "ambiguous_controls": ambiguous,
            "pages_on_oracle_url": len(on_page)}


def export_diagnostic(row, session_id):
    if row.get("session_id") != session_id:
        return None
    flags = ("url_changed", "interaction_changed", "visual_semantics_changed",
             "form_presence_changed", "form_values_changed", "scroll_changed")
    return {"session_id": session_id, "operation_id": safe_id(row.get("operation_id")),
            "failure_stage": row.get("failure_stage") if row.get("failure_stage") in STAGES
            else None, "code": safe_code(row.get("code")),
            **{key: row[key] for key in flags if type(row.get(key)) is bool}}


def export_download_destination(row, session_id):
    """Facts for independent review, never an outcome adjudication."""
    hashes = row.get("destination_hashes")
    chain = row.get("navigation_chain", [])
    if (row.get("event") != "vision.download.destinations"
            or row.get("session_id") != session_id or not safe_id(session_id)
            or not safe_id(row.get("operation_id"))
            or row.get("status") not in STATUSES
            or type(row.get("truncated")) is not bool
            or not isinstance(hashes, list) or not 1 <= len(hashes) <= 8
            or any(not isinstance(value, str) or not HASH.fullmatch(value) for value in hashes)
            or len(set(hashes)) != len(hashes)):
        return None
    if not isinstance(chain, list) or len(chain) > 32:
        return None
    safe_chain = []
    for item in chain:
        if not isinstance(item, dict):
            return None
        url, parent = item.get("url_sha256"), item.get("redirected_from_sha256")
        if (not isinstance(url, str) or not HASH.fullmatch(url)
                or (parent is not None and (
                    not isinstance(parent, str) or not HASH.fullmatch(parent)
                ))):
            return None
        safe_chain.append({"url_sha256": url, "redirected_from_sha256": parent})
    return {"session_id": session_id, "operation_id": row["operation_id"],
            "destination_hashes": list(hashes), "truncated": row["truncated"],
            "status": row["status"], "navigation_chain": safe_chain}


def diagnose(reason, operations, diagnostics=()):
    categories = []
    for row in operations:
        if row["status"] not in {"failed", "rejected", "unknown"}:
            continue
        code = row.get("outcome_code") or "unspecified"
        diagnostic = next((d for d in diagnostics if d.get("operation_id") == row["id"]), {})
        stage = diagnostic.get("failure_stage")
        if row["status"] == "unknown":
            category = "unknown_action_outcome"
        elif code == "state_mismatch":
            category = stage if stage in STAGES else "state_drift_stage_unavailable"
        elif "locator" in code or "target" in code:
            category = "target_binding"
        elif "capture" in code or "settle" in code:
            category = "capture_or_readiness"
        else:
            category = "operation_failure"
        categories.append({"operation_id": row["id"], "category": category,
                           "code": code, "purpose": row["purpose"]})
    if reason in {"unsafe_replay", "state_restore_failed"}:
        categories.append({"category": "restoration", "code": reason})
    elif reason and any(part in reason for part in ("limit", "budget", "quota")):
        categories.append({"category": "budget_or_quota", "code": safe_code(reason)})
    elif reason and any(part in reason for part in ("bridge", "provider", "model")):
        categories.append({"category": "model_or_provider", "code": safe_code(reason)})
    missing = [row["id"] for row in operations
               if any(row[role]["availability"] != "retained" for role in ("before", "after"))]
    return {"categories": categories, "missing_evidence_operations": missing,
            "reason": safe_code(reason), "physical_retry_authorized": False}
