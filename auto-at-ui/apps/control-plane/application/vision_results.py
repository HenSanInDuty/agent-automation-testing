"""Authorized deterministic trace/result views; reads never invoke an agent or runner."""

import hashlib
import json
import re
from uuid import uuid4

from auto_at.contracts.vision import VisualLocatorEvidence
from domain.authorization import Permission
from domain.runs import AuditEvent
from domain.vision import VisualSessionScope

from application.vision_replay import (
    VisionReplay,
    VisionReplayDeletionError,
    VisionReplayNotFoundError,
)


class VisionRevisionChanged(ValueError):
    pass


class VisionResults:
    def __init__(self, sessions, trace, store=None, audits=None):
        self.sessions, self.trace, self.store, self.audits = sessions, trace, store, audits

    def _load(self, tenant_id, principal, session_id, permission=Permission.READ):
        record = VisionReplay(self.sessions, self.store, self.audits)._session(
            tenant_id, principal, session_id, permission
        )
        scope = VisualSessionScope(tenant_id, record.project_id, session_id)
        snapshot = self.trace.snapshot(scope)
        return record, scope, snapshot

    @staticmethod
    def _revision(record, snapshot):
        data = dict(
            state=record.state,
            operations=[item.model_dump(mode="json") for item in snapshot["operations"]],
            frames=[item.metadata.model_dump(mode="json") for item in snapshot["frames"]],
            locators=[item.model_dump(mode="json") for item in snapshot["locators"]],
            handoffs=[item.content_hash for item in snapshot["handoffs"]],
        )
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def _frame(frame_id, frames, reason):
        frame = frames.get(frame_id)
        if frame is None:
            return dict(
                id=str(frame_id) if frame_id else None,
                availability="missing",
                reason_code=reason or "frame_metadata_unavailable",
            )
        metadata = frame.metadata
        return metadata.model_dump(mode="json") | dict(
            availability="deleted" if metadata.deleted_at else "retained",
            reason_code="evidence_deleted" if metadata.deleted_at else None,
        )

    def read_trace(
        self, *, tenant_id, principal, session_id, after_sequence=0, limit=100, revision=None
    ):
        if not 1 <= limit <= 100 or after_sequence < 0:
            raise ValueError("invalid trace page")
        record, _, snapshot = self._load(tenant_id, principal, session_id)
        current = self._revision(record, snapshot)
        if revision is not None and revision != current:
            raise VisionRevisionChanged
        all_items = [o for o in snapshot["operations"] if o.sequence > after_sequence]
        page = all_items[:limit]
        frames = {item.metadata.id: item for item in snapshot["frames"]}
        locator_ids = {o.locator_id for o in page}
        state_ids = {o.state_id for o in page}
        return dict(
            schema_version="v1",
            session_id=str(session_id),
            revision=current,
            trace_version=getattr(record, "trace_version", "legacy"),
            items=[
                o.model_dump(mode="json")
                | {
                    "before": self._frame(
                        o.actual_before_frame_id, frames, o.before_unavailable_reason
                    ),
                    "after": self._frame(
                        o.actual_after_frame_id, frames, o.after_unavailable_reason
                    ),
                }
                for o in page
            ],
            locators=[
                VisualLocatorEvidence.model_validate(item.model_dump()).model_dump(mode="json")
                for item in snapshot["locators"]
                if item.id in locator_ids
            ],
            next_sequence=page[-1].sequence if page else after_sequence,
            has_more=len(all_items) > limit,
            states=[
                dict(
                    id=str(item.id),
                    parent_id=str(item.parent_id) if item.parent_id else None,
                    hop=item.hop,
                )
                for item in self.sessions.list_states(tenant_id, session_id)
                if item.id in state_ids
            ],
        )

    def locators(self, *, tenant_id, principal, session_id, status=None, after_id=None, limit=100):
        if not 1 <= limit <= 100 or status not in {
            None,
            "verified",
            "ambiguous",
            "not_found",
            "stale",
            "unsupported",
            "redacted",
        }:
            raise ValueError("invalid locator page")
        record, _, snapshot = self._load(tenant_id, principal, session_id)
        items = sorted(
            (
                item
                for item in snapshot["locators"]
                if (status is None or item.status == status)
                and (after_id is None or item.id.int > after_id.int)
            ),
            key=lambda x: x.id.int,
        )
        page = items[:limit]
        return dict(
            schema_version="v1",
            revision=self._revision(record, snapshot),
            items=[
                VisualLocatorEvidence.model_validate(item.model_dump()).model_dump(mode="json")
                for item in page
            ],
            has_more=len(items) > limit,
            next_id=str(page[-1].id) if page else None,
        )

    def result(self, *, tenant_id, principal, session_id):
        record, scope, snapshot = self._load(tenant_id, principal, session_id)
        operations, locators = snapshot["operations"], snapshot["locators"]
        edges = self.sessions.list_trajectory_edges(tenant_id, session_id)
        links = self.trace.result_links(
            scope, legacy=getattr(record, "trace_version", "legacy") != "v4"
        )
        retained = sum(not item.metadata.deleted_at for item in snapshot["frames"])
        deleted = len(snapshot["frames"]) - retained
        legacy = getattr(record, "trace_version", "legacy") != "v4"
        terminal = record.state in {"completed", "cancelled", "unavailable"}
        missing = sum(
            not getattr(o, f"actual_{role}_frame_id")
            for o in operations
            for role in ("before", "after")
        )
        payload = dict(
            schema_version="v1",
            session_id=str(session_id),
            project_id=str(record.project_id),
            exploration_state=record.state,
            completion_reason=(
                record.safe_failure_reason
                if record.safe_failure_reason
                and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", record.safe_failure_reason)
                else "exploration_unavailable"
                if record.safe_failure_reason
                else None
            )
            or ("exploration_finished" if terminal else None),
            evidence_status="legacy_evidence_only"
            if legacy
            else ("partial" if missing or deleted else "available" if retained else "not_started"),
            counts=dict(
                proposed=len(self.sessions.list_actions(tenant_id, session_id)),
                operations=len(operations),
                completed=sum(o.status == "completed" for o in operations),
                failed=sum(o.status in {"failed", "rejected"} for o in operations),
                unknown=sum(o.status == "unknown" for o in operations),
                executing=sum(o.status == "executing" for o in operations),
                verified_locators=sum(item.status == "verified" for item in locators),
                unresolved_locators=sum(item.status != "verified" for item in locators),
                frames_retained=retained,
                frames_deleted=deleted,
                frames_missing=missing,
                branches_explored=sum(
                    e.status in {"observed", "no_meaningful_change"} for e in edges
                ),
                branches_failed=sum(e.status == "failed" for e in edges),
                branches_skipped=sum(e.status == "terminal" for e in edges),
            ),
            branches=[
                dict(
                    id=str(e.id),
                    status=e.status,
                    reason_code=e.outcome_code,
                    parent_state_id=str(e.parent_state_id),
                    child_state_id=str(e.child_state_id) if e.child_state_id else None,
                )
                for e in edges
            ],
            handoffs=[item.model_dump(mode="json") for item in snapshot["handoffs"]],
            links=links,
            limitations=[
                "Recorded observations do not establish business success.",
                "Typed inputs require binding before their branches can execute.",
            ],
        )
        payload["revision"] = hashlib.sha256(
            json.dumps(
                payload | {"trace_revision": self._revision(record, snapshot)},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        return payload

    def read_frame(self, *, tenant_id, principal, session_id, frame_id):
        record, _, snapshot = self._load(tenant_id, principal, session_id)
        frame = next((f for f in snapshot["frames"] if f.metadata.id == frame_id), None)
        if frame is None or frame.metadata.deleted_at:
            raise VisionReplayNotFoundError
        try:
            content = self.store.read_operation_frame(frame)
            if (
                len(content) != frame.metadata.byte_count
                or hashlib.sha256(content).hexdigest() != frame.metadata.checksum
            ):
                raise ValueError("frame integrity mismatch")
        except Exception:
            raise VisionReplayNotFoundError from None
        self._audit(record, principal, "vision.operation_frame_read", frame_id)
        return content, frame.metadata.content_type

    def _audit(self, record, principal, action, frame_id):
        self.audits.append(
            AuditEvent(
                id=uuid4(),
                tenant_id=record.tenant_id,
                actor=principal.subject,
                action=action,
                entity_type="visual_operation_frame",
                entity_id=frame_id,
                correlation_id=record.correlation_id,
            )
        )

    def delete_frames(self, *, tenant_id, principal, session_id, frame_id=None):
        record, scope, snapshot = self._load(
            tenant_id, principal, session_id, Permission.MANAGE_TENANT
        )
        frames = [
            f
            for f in snapshot["frames"]
            if not f.metadata.deleted_at and (frame_id is None or f.metadata.id == frame_id)
        ]
        for frame in frames:
            self._audit(
                record, principal, "vision.operation_frame_delete_requested", frame.metadata.id
            )
            try:
                self.store.delete_operation_frame(frame)
            except Exception:
                self._audit(
                    record, principal, "vision.operation_frame_delete_failed", frame.metadata.id
                )
                raise VisionReplayDeletionError from None
            self.trace.tombstone_frame(scope, frame.metadata.id)
            self._audit(
                record, principal, "vision.operation_frame_delete_completed", frame.metadata.id
            )
        return len(frames)
