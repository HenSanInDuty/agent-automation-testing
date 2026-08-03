"""Authorized read-only timeline for a run or correlation."""

import asyncio
from datetime import datetime
from typing import Annotated
from uuid import UUID

from application.runs import GetRun, RunNotFoundError
from config import Settings, get_settings
from domain.authorization import (
    AuthorizationError,
    Permission,
    Principal,
    actor_for_tenant,
    require,
)
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from infrastructure.persistence.repositories import (
    SqlAlchemyActivityEventRepository,
    SqlAlchemyRunRepository,
)
from infrastructure.persistence.session import create_session_factory
from pydantic import BaseModel

from api.v1.dependencies.authorization import current_principal, current_tenant

router = APIRouter(prefix="/activities", tags=["activities"])


class ActivityResponse(BaseModel):
    id: UUID
    run_id: UUID | None
    correlation_id: UUID
    source: str
    stage: str
    status: str
    safe_summary: str
    metadata: dict[str, object]
    occurred_at: datetime


@router.get("", response_model=list[ActivityResponse])
def list_activities(
    run_id: UUID | None = None,
    correlation_id: UUID | None = None,
    after: datetime | None = None,
    tenant_id: Annotated[str, Depends(current_tenant)] = "",
    principal: Annotated[Principal, Depends(current_principal)] = None,  # type: ignore[assignment]
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> list[ActivityResponse]:
    if (run_id is None) == (correlation_id is None):
        raise HTTPException(
            status_code=422, detail="Provide exactly one of run_id or correlation_id."
        )
    with create_session_factory(settings)() as session:
        if run_id is not None:
            try:
                run = GetRun(SqlAlchemyRunRepository(session)).execute(tenant_id, run_id)
                require(actor_for_tenant(principal, tenant_id, run.project_id), Permission.READ)
            except (RunNotFoundError, AuthorizationError) as error:
                raise HTTPException(status_code=404, detail="Run not found.") from error
        else:
            # A correlation may span resources; only return events belonging to projects
            # the principal can read. Current activities include run IDs for this reason.
            events = SqlAlchemyActivityEventRepository(session).list(
                tenant_id, correlation_id=correlation_id, after=after
            )
            visible = []
            runs = SqlAlchemyRunRepository(session)
            for event in events:
                if event.run_id is None:
                    continue
                run = runs.get(tenant_id, event.run_id)
                if run is None:
                    continue
                try:
                    require(actor_for_tenant(principal, tenant_id, run.project_id), Permission.READ)
                    visible.append(event)
                except AuthorizationError:
                    continue
            return [
                ActivityResponse.model_validate(event, from_attributes=True) for event in visible
            ]
        events = SqlAlchemyActivityEventRepository(session).list(
            tenant_id, run_id=run_id, after=after
        )
    return [ActivityResponse.model_validate(event, from_attributes=True) for event in events]


@router.get("/stream")
async def stream_activities(
    run_id: UUID | None = None,
    correlation_id: UUID | None = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    tenant_id: Annotated[str, Depends(current_tenant)] = "",
    principal: Annotated[Principal, Depends(current_principal)] = None,  # type: ignore[assignment]
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> StreamingResponse:
    """Stream the authorized history, then append new events with keepalives."""
    initial = list_activities(run_id, correlation_id, None, tenant_id, principal, settings)
    seen = {str(event.id) for event in initial}
    if last_event_id:
        try:
            resume_at = next(
                index for index, event in enumerate(initial) if str(event.id) == last_event_id
            )
            initial = initial[resume_at + 1 :]
        except StopIteration:
            pass

    async def events():
        for event in initial:
            yield _sse_event(event)
        while True:
            await asyncio.sleep(5)
            current = list_activities(run_id, correlation_id, None, tenant_id, principal, settings)
            fresh = [event for event in current if str(event.id) not in seen]
            for event in fresh:
                seen.add(str(event.id))
                yield _sse_event(event)
            yield ": keepalive\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


def _sse_event(event: ActivityResponse) -> str:
    return f"id: {event.id}\nevent: activity\ndata: {event.model_dump_json()}\n\n"
