from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["platform"])


class HealthResponse(BaseModel):
    status: str
    service: str


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok", service="control-plane")
