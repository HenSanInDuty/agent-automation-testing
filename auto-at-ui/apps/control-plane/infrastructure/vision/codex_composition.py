"""Opt-in local composition; disabled deployments never open a spool directory."""

from pathlib import Path

from application.codex_candidates import CodexCandidateService

from infrastructure.codex_bridge.doctor import FileReadiness
from infrastructure.codex_bridge.spool import FileSpool
from infrastructure.persistence.codex_bridge_repository import SqlAlchemyCodexJobGateway
from infrastructure.vision.codex_batch import CodexModelBatch


def codex_candidate_factory(settings, factory):
    if not settings.codex_bridge_enabled:
        return None

    def create(lease):
        if lease.scope.tenant_id != settings.codex_bridge_allowed_tenant:
            raise ValueError("bridge tenant mismatch")
        return CodexCandidateService(
            CodexModelBatch(
                bridge_id=settings.codex_bridge_id,
                spool=FileSpool(
                    Path(settings.codex_bridge_container_spool),
                    settings.codex_bridge_id,
                    settings.codex_bridge_allowed_tenant,
                    settings.codex_bridge_max_pending,
                ),
                readiness=FileReadiness(settings),
                gateway=SqlAlchemyCodexJobGateway(factory, lease),
            )
        )

    return create
