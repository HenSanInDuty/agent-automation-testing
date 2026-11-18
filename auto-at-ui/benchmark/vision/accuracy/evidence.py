"""Allowlisted evidence export. Never copy request bodies, DOM or form values."""

import re

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
            "status": row.get("status") if row.get("status") in {
                "verified", "ambiguous", "not_found", "stale", "unsupported", "redacted",
            } else "unsupported",
            "path": path if descriptor.get("strategy") == "dom_path"
            and len(path) <= 1024 and PATH.fullmatch(path) else None}


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
