"""Offline re-score of a stored dom_path (engine v4) iteration under another oracle version.

Reads only retained artifacts of `runs/<iteration>/` (evidence.json, inventory-evidence.json and
outcome findings keyed by operation sequence); never calls the API, a browser or a model. Writes
`runs/<iteration>/rescore-<oracle hash[:12]>/` with content-addressed reviews and score.json, so
the original manifest, reviews and score under the start oracle stay untouched.

    uv run python benchmark/vision/accuracy/rescore.py --iteration <id> \
        --oracle benchmark/vision/accuracy/oracle-mongchiton-1280-v2.json \
        --findings runs/<id>/manual-findings.json [--findings extra.json]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from evidence import binding_error, descriptor_key  # noqa: E402
from metrics import (  # noqa: E402
    Assessment,
    Detection,
    OutcomeReview,
    content_hash,
    oracle_paths,
    score,
    validate_oracle,
)

RUNS = Path(__file__).parent / "runs"


def read(path):
    return json.loads(Path(path).read_text("utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", "utf-8")


def detection_facts(oracle, pages):
    by_key = {descriptor_key(path, version): item["id"] for item in oracle["examples"]
              for path in oracle_paths(item) for version in ("v2", "v3")}
    keys = {key for page in pages for key in page["keys"]}
    return {
        "identified_ids": tuple(sorted({by_key[key] for key in keys if key in by_key})),
        "unexpected_paths": tuple(sorted("unmatched_key:" + key for key in keys
                                         if key not in by_key)),
        "inventory_complete": bool(pages) and any(not page["scrollable"] for page in pages)
        and not any(page["truncated"] or page["skipped_count"] for page in pages),
    }


def rescore(folder, oracle, findings):
    examples = validate_oracle(oracle)
    digest = content_hash(oracle)
    evidence = read(folder / "evidence.json")
    pages = read(folder / "inventory-evidence.json")
    locators = {locator["id"]: locator for locator in evidence["locators"]}
    out = folder / f"rescore-{digest[:12]}"
    out.mkdir(exist_ok=True)
    assessments, credited, bindings = [], {}, {}
    for operation in evidence["operations"]:
        locator = locators.get(operation["locator_id"]) or {}
        target = next((item for item in examples.values()
                       if locator.get("path") in oracle_paths(item)), None)
        bound = bool(target) and binding_error(
            oracle, target, locator, None, operation, None, locator.get("id")) is None
        if target:
            bindings[str(operation["sequence"])] = target["id"]
        finding = findings.get(str(operation["sequence"]))
        reference = None
        if finding:
            if not (bound and target["expected"] and operation["status"] == "completed"):
                raise ValueError(f"finding for unbound operation {operation['sequence']}")
            if target["id"] in credited:
                raise ValueError(f"{target['id']} already credited by {credited[target['id']]}")
            credited[target["id"]] = operation["sequence"]
            review = OutcomeReview(
                operation_id=operation["id"], oracle_hash=digest,
                outcome_kind=target["outcome"]["kind"], verdict="correct",
                review_method="evidence_review", before_checksum=operation["before"]["checksum"],
                after_checksum=operation["after"]["checksum"], finding=finding)
            body = review.model_dump(mode="json")
            reference = content_hash(body)
            write(out / f"review-{reference}.json", body)
        assessments.append(Assessment(
            operation_id=operation["id"], oracle_hash=digest,
            status=operation["status"], purpose=operation["purpose"],
            action_kind=operation["action_kind"],
            target_id=target["id"] if target else None,
            target_verdict="correct" if bound else "unverified",
            outcome_verdict="correct" if reference else "unverified",
            outcome_reference=reference, review_method="evidence_review" if reference else None,
            binding_reference=locator.get("id") if bound else None,
            before_checksum=operation["before"]["checksum"],
            after_checksum=operation["after"]["checksum"]))
    detection = Detection(oracle_hash=digest, **detection_facts(oracle, pages))
    result = score(oracle, assessments, detection)
    result |= {"iteration_id": folder.name, "session_id": evidence["session_id"],
               "start_oracle_hash": read(folder / "manifest.json")["oracle_hash"],
               "credited_sequences": dict(sorted(credited.items())),
               "bound_sequences": bindings,
               "unexpected_paths": list(detection.unexpected_paths),
               "note": "Offline re-score of retained evidence; not a new live run."}
    write(out / "score.json", result)
    return out, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iteration", required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--findings", type=Path, action="append", required=True)
    args = parser.parse_args()
    findings = {}
    for path in args.findings:
        for key, value in read(path).items():
            if not key.startswith("_"):
                if key in findings:
                    raise ValueError(f"duplicate finding for sequence {key}")
                findings[key] = value
    out, result = rescore(RUNS / args.iteration, read(args.oracle), findings)
    summary = {key: result[key] for key in ("coverage", "accuracy", "detection_precision",
                                            "detection_recall", "inventory_complete", "passed",
                                            "remaining_targets", "unsafe_operations")}
    print(out)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
