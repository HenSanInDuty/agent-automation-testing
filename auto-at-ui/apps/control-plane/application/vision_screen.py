"""Read-only, authorized viewport preview; never starts or resumes browser actions."""

from auto_at.contracts.vision_worker import VisualWorkerIdentity
from domain.authorization import Permission

from application.vision_replay import VisionReplay


class VisionScreenUnavailable(RuntimeError):
    pass


class VisionScreen:
    def __init__(self, sessions, worker):
        self.sessions, self.worker = sessions, worker

    async def read(self, *, tenant_id, principal, session_id):
        record = VisionReplay(self.sessions, None, None)._session(
            tenant_id, principal, session_id, Permission.READ
        )
        if record.state != "running" or record.trace_version != "v4" or record.fencing_token < 1:
            return None
        identity = VisualWorkerIdentity(
            tenant_id=tenant_id, project_id=record.project_id,
            session_id=session_id, fencing_token=record.fencing_token,
        )
        try:
            return await self.worker.screen(identity)
        except Exception:
            raise VisionScreenUnavailable from None
