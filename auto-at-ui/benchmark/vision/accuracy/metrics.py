"""Independent benchmark scoring, never a production execution verdict.

Assessments must come from an evidence reviewer/oracle, not the proposing model.
The collector validates referenced frame hashes before supplying assessments.
"""

import hashlib
import json
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def content_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode()).hexdigest()


def ratio(numerator: int, denominator: int) -> dict:
    return {
        "numerator": numerator, "denominator": denominator,
        "percent": 100 * numerator / denominator if denominator else None,
        "above_95": denominator > 0 and 100 * numerator > 95 * denominator,
    }


class Assessment(BaseModel):
    """One immutable operation adjudication; absent evidence cannot earn credit."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: str = Field(min_length=1)
    oracle_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    target_id: str | None = None
    status: Literal["prepared", "executing", "completed", "rejected", "failed", "unknown"]
    purpose: Literal["explore", "restore", "setup", "replay"]
    action_kind: Literal["click", "type", "scroll", "wait", "navigate", "back", "close_popup"]
    target_verdict: Literal["correct", "wrong", "unverified"] = "unverified"
    outcome_verdict: Literal["correct", "wrong", "unverified"] = "unverified"
    before_checksum: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    after_checksum: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    binding_reference: str | None = None
    outcome_reference: str | None = None
    review_method: Literal["fixture_oracle", "evidence_review"] | None = None
    unsafe_reason: str | None = None


class Detection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    oracle_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    identified_ids: tuple[str, ...]
    unexpected_paths: tuple[str, ...] = ()
    inventory_complete: bool

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.identified_ids)) != len(self.identified_ids):
            raise ValueError("duplicate detection IDs")
        if len(set(self.unexpected_paths)) != len(self.unexpected_paths):
            raise ValueError("duplicate unexpected paths")
        return self


class OutcomeReview(BaseModel):
    """Independent, content-addressed evidence adjudication, retained for review."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["vision-outcome-review-v1"] = "vision-outcome-review-v1"
    operation_id: str
    oracle_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    outcome_kind: str = Field(min_length=1, max_length=80)
    verdict: Literal["correct", "wrong", "unverified"]
    review_method: Literal["fixture_oracle", "evidence_review"]
    before_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    after_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    finding: str = Field(min_length=10, max_length=1000)


def validate_oracle(oracle: dict) -> dict:
    if oracle.get("schema_version") != "vision-accuracy-oracle-v1":
        raise ValueError("unknown oracle schema")
    examples = oracle.get("examples")
    if not isinstance(examples, list):
        raise ValueError("oracle examples required")
    ids = [item.get("id") for item in examples]
    if any(not isinstance(item, str) or not item for item in ids) or len(set(ids)) != len(ids):
        raise ValueError("oracle IDs must be unique and nonempty")
    for item in examples:
        if type(item.get("expected")) is not bool:
            raise ValueError("oracle label must be boolean")
        if item["expected"] and (
            item.get("action_kind") not in {"click", "type"}
            or not isinstance(item.get("outcome"), dict)
            or not item["outcome"].get("kind")
        ):
            raise ValueError("positive oracle requires an action and outcome")
    return {item["id"]: item for item in examples}


def score(oracle: dict, assessments: list[Assessment], detection: Detection) -> dict:
    examples = validate_oracle(oracle)
    digest = content_hash(oracle)
    if detection.oracle_hash != digest or any(row.oracle_hash != digest for row in assessments):
        raise ValueError("oracle hash mismatch")
    if len({row.operation_id for row in assessments}) != len(assessments):
        raise ValueError("duplicate operation ID")
    if not set(detection.identified_ids) <= examples.keys():
        raise ValueError("unknown detection annotation")
    positives = {key for key, item in examples.items() if item["expected"]}
    interactions = [row for row in assessments
                    if row.purpose == "explore" and row.action_kind in {"click", "type"}]
    correct, covered, unsafe = [], set(), []
    for row in assessments:
        if row.unsafe_reason or row.target_verdict == "wrong":
            unsafe.append(row.operation_id)
        if row not in interactions:
            continue
        item = examples.get(row.target_id)
        if row.target_verdict == "correct" and item and not item["expected"]:
            unsafe.append(row.operation_id)
        if (row.status == "completed" and row.target_id in positives
                and row.target_verdict == row.outcome_verdict == "correct"
                and row.action_kind == item["action_kind"]
                and row.before_checksum and row.after_checksum and row.binding_reference
                and row.outcome_reference and row.review_method):
            correct.append(row.operation_id)
            covered.add(row.target_id)
    identified = set(detection.identified_ids)
    detection_precision = ratio(len(identified & positives),
                                len(identified) + len(detection.unexpected_paths))
    detection_recall = ratio(len(identified & positives), len(positives))
    coverage = ratio(len(covered), len(positives))
    accuracy = ratio(len(correct), len(interactions))
    unsettled = [row.operation_id for row in assessments
                 if row.status in {"prepared", "executing", "unknown"}]
    passed = all(item["above_95"] for item in (
        coverage, accuracy, detection_precision, detection_recall,
    )) and detection.inventory_complete and not unsafe and not unsettled
    return {
        "schema_version": "vision-accuracy-score-v1", "oracle_hash": digest,
        "coverage": coverage, "accuracy": accuracy,
        "detection_precision": detection_precision, "detection_recall": detection_recall,
        "inventory_complete": detection.inventory_complete,
        "correct_operations": correct, "covered_targets": sorted(covered),
        "remaining_targets": sorted(positives - covered),
        "unsafe_operations": sorted(set(unsafe)), "unsettled_operations": unsettled,
        "operation_statuses": dict(Counter(row.status for row in assessments)),
        "interaction_statuses": dict(Counter(row.status for row in interactions)),
        "passed": passed, "business_outcome": "unverified",
    }


def qualify(runs: list[dict]) -> dict:
    """All supplied candidate runs participate; callers retain earlier candidates too."""
    consecutive = []
    signature = None
    sessions = set()
    for run in runs:
        session = run["session_id"]
        if session in sessions:
            raise ValueError("duplicate qualification session")
        sessions.add(session)
        current = (run["source_hash"], run["config_hash"], run["score"]["oracle_hash"])
        eligible = run.get("qualification_eligible") is True
        if (current != signature or not run["score"]["passed"] or not run["terminal"]
                or not eligible):
            consecutive = []
        signature = current
        if eligible and run["score"]["passed"] and run["terminal"]:
            consecutive.append(run)
    attempts = sum(run["score"]["accuracy"]["denominator"] for run in consecutive)
    return {"passed": len(consecutive) >= 3 and attempts >= 100,
            "consecutive_sessions": [run["session_id"] for run in consecutive],
            "interaction_attempts": attempts}
