"""Prepare a non-secret configuration backup for an older policy parser; no DB writes."""

import argparse
import copy
import json
from pathlib import Path


def rollback_override(override: dict, provider: str, model: str) -> dict:
    if provider not in {"huggingface", "gemini"} or not isinstance(model, str) or not model.strip():
        raise ValueError("supply the previously configured legacy provider and model")
    updated = copy.deepcopy(override)
    vision = updated.get("vision")
    if not isinstance(vision, dict):
        raise ValueError("expected an exported agent.runtime.v1 override with a vision object")
    vision.pop("codex", None)
    vision.pop("input_policy_fingerprint", None)
    vision.update(
        enabled=False, provider=provider, model=model,
        raw_screenshot_transfer_accepted=False, raw_screenshot_transfer_provider=None,
    )
    return updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--provider", required=True, choices=("huggingface", "gemini"))
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    updated = rollback_override(json.loads(args.input.read_text()), args.provider, args.model)
    with args.output.open("x", encoding="utf-8") as destination:
        json.dump(updated, destination, indent=2)
        destination.write("\n")
    print("Prepared disabled legacy policy; review before applying. No database was changed.")


if __name__ == "__main__":
    main()
