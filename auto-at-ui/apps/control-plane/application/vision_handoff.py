"""Build immutable root-to-leaf evidence paths from the committed operation ledger."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from auto_at.contracts.vision import VisualHandoffBranch, VisualHandoffStep, VisualLocatorHandoff


def build_vision_handoff(scope, snapshot):
    operations = {o.id: o for o in snapshot["operations"] if o.purpose in {"setup", "explore"}}
    locators = {item.id: item for item in snapshot["locators"]}
    parents = {o.parent_operation_id for o in operations.values()}
    leaves = [o for o in operations.values() if o.id not in parents and o.purpose == "explore"]
    branches = []
    for leaf in leaves:
        path, seen, node = [], set(), leaf
        while node is not None:
            if node.id in seen:
                raise ValueError("invalid_branch_ancestry")
            seen.add(node.id)
            path.append(node)
            if node.parent_operation_id is None:
                break
            node = operations.get(node.parent_operation_id)
            if node is None:
                raise ValueError("incomplete_branch_ancestry")
        path.reverse()
        reason, steps = None, []
        for operation in path:
            locator = locators.get(operation.locator_id)
            if operation.status != "completed":
                reason = (
                    "action_outcome_unknown" if operation.status == "unknown" else "action_failed"
                )
            elif operation.action_kind in {"click", "type"} and (
                locator is None or locator.status != "verified"
            ):
                reason = "locator_unavailable"
            elif not operation.actual_after_frame_id:
                reason = "capture_unavailable"
            codes = ("visible", "enabled") if locator and locator.status == "verified" else ()
            steps.append(
                VisualHandoffStep(
                    operation_id=operation.id,
                    locator_id=operation.locator_id,
                    input_reference=uuid4() if operation.action_kind == "type" else None,
                    observation_codes=codes,
                )
            )
        if path[0].action_kind != "navigate" or path[0].purpose != "setup":
            reason = "setup_unavailable"
        if any(step.input_reference for step in steps):
            reason = "input_binding_required"
        branches.append(
            VisualHandoffBranch(
                id=uuid4(),
                steps=tuple(steps),
                status="blocked" if reason else "ready",
                reason_code=reason,
            )
        )
    # Refuse an oversized package as a whole, never silently select the first N paths.
    if len(branches) > 50:
        raise ValueError("handoff_branch_limit")
    values = dict(
        schema_version="v1",
        id=str(uuid4()),
        tenant_id=scope.tenant_id,
        project_id=str(scope.project_id),
        session_id=str(scope.session_id),
        version=1,
        branches=[b.model_dump(mode="json") for b in branches],
        unresolved_count=sum(item.status != "verified" for item in locators.values()),
        created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    values["content_hash"] = hashlib.sha256(
        json.dumps(
            values,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    return VisualLocatorHandoff.model_validate(values)
