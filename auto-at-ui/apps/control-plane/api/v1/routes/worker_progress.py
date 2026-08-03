"""Authenticated internal worker progress intake; it never accepts a verdict."""

from datetime import UTC, datetime
from hmac import compare_digest
from typing import Annotated
from uuid import UUID

from application.runs import GetRun, RunNotFoundError
from config import Settings, get_settings
from domain.activity import ActivityEvent
from fastapi import APIRouter, Depends, Header, HTTPException, status
from infrastructure.persistence.repositories import (
    SqlAlchemyActivityEventRepository,
    SqlAlchemyRunRepository,
)
from infrastructure.persistence.session import create_session_factory, transactional_session
from pydantic import BaseModel, Field

router = APIRouter(prefix="/internal/worker-progress", tags=["internal"])


class WorkerProgressRequest(BaseModel):
    contract_version: str = "v1"
    tenant_id: str = Field(min_length=1, max_length=200)
    run_id: UUID
    correlation_id: UUID
    stage: str = Field(min_length=1, max_length=100)
    status: str
    safe_summary: str = Field(min_length=1, max_length=1_000)
    metadata: dict[str, object] = Field(default_factory=dict)


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
def record_worker_progress(
    payload: WorkerProgressRequest,
    secret: Annotated[str | None, Header(alias="X-Worker-Progress-Secret")] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> None:
    expected = settings.worker_progress_callback_secret
    if not expected or secret is None or not compare_digest(secret, expected):
        raise HTTPException(status_code=404, detail="Not found.")
    if payload.contract_version != "v1":
        raise HTTPException(status_code=422, detail="Unsupported progress contract.")
    with transactional_session(create_session_factory(settings)) as session:
        try:
            run = GetRun(SqlAlchemyRunRepository(session)).execute(
                payload.tenant_id, payload.run_id
            )
        except RunNotFoundError as error:
            raise HTTPException(status_code=404, detail="Run not found.") from error
        if run.correlation_id != payload.correlation_id:
            raise HTTPException(status_code=409, detail="Progress does not match the run.")
        try:
            event = ActivityEvent.create(
                tenant_id=payload.tenant_id, run_id=payload.run_id,
                correlation_id=payload.correlation_id, source="worker", stage=payload.stage,
                status=payload.status, safe_summary=payload.safe_summary,
                metadata=payload.metadata, occurred_at=datetime.now(UTC),
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        SqlAlchemyActivityEventRepository(session).append(event)
