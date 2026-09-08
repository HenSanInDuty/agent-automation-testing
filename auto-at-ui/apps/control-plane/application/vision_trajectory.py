"""Authorized, redacted graph snapshots for advisory Vision exploration."""

from uuid import UUID

from domain.authorization import (
    AuthorizationError,
    Permission,
    Principal,
    actor_for_tenant,
    require,
)


class VisionTrajectoryNotFoundError(LookupError):
    """Avoid distinguishing an inaccessible exploration from a missing one."""


class VisionTrajectory:
    def __init__(self, sessions) -> None:
        self._sessions = sessions

    def read(self, *, tenant_id: str, principal: Principal, session_id: UUID) -> dict[str, object]:
        session = self._sessions.get(tenant_id, session_id)
        try:
            if session is None or principal.is_service:
                raise AuthorizationError("missing")
            require(actor_for_tenant(principal, tenant_id, session.project_id), Permission.READ)
        except AuthorizationError as error:
            raise VisionTrajectoryNotFoundError from error

        replay_frames = self._sessions.list_replay_frames(tenant_id, session_id)
        frames = {frame.state_id: frame for frame in replay_frames}
        actions = self._sessions.list_actions(tenant_id, session_id)
        proposals = {proposal.id: proposal for proposal in actions}
        edges = self._sessions.list_trajectory_edges(tenant_id, session_id)
        states = self._sessions.list_states(tenant_id, session_id)
        return {
            "session": {
                "id": session.id,
                "state": session.state,
                "safe_failure_reason": session.safe_failure_reason,
            },
            "trajectory_available": bool(edges),
            "legacy_label": (
                None
                if edges
                else "Legacy exploration evidence gallery; branch outcomes were not recorded."
            ),
            "states": [
                {
                    "id": state.id,
                    "parent_id": state.parent_id,
                    "hop": state.hop,
                    "sequence": frames[state.id].sequence if state.id in frames else None,
                    "captured_at": state.created_at,
                    "frame_id": frames[state.id].id if state.id in frames else None,
                }
                for state in states
            ],
            "proposals": [
                {
                    "id": proposal.id,
                    "state_id": proposal.originating_state_id,
                    "sequence": proposal.sequence,
                    "action": proposal.action,
                    "confidence": proposal.action.get("confidence"),
                }
                for proposal in proposals.values()
            ],
            "edges": [
                {
                    "id": edge.id,
                    "parent_state_id": edge.parent_state_id,
                    "proposal_id": edge.proposal_id,
                    "attempt": edge.attempt,
                    "action": edge.action,
                    "confidence": edge.confidence,
                    "status": edge.status,
                    "outcome_code": edge.outcome_code,
                    "child_state_id": edge.child_state_id,
                    "observed_at": edge.observed_at,
                    "duration_ms": edge.duration_ms,
                    "url_change": edge.url_change,
                }
                for edge in edges
            ],
        }
