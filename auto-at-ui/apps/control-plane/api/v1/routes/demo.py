from typing import Annotated, Any

from agents.demo.weather import run_weather_demo
from config import Settings, get_settings
from fastapi import APIRouter, Depends, HTTPException, status
from httpx import ConnectError
from pydantic import BaseModel, Field

router = APIRouter(prefix="/demo", tags=["demo"])


class WeatherDemoRequest(BaseModel):
    """Public, non-sensitive input accepted by the local Ollama demonstration."""

    city: str = Field(min_length=1, max_length=100)


class WeatherDemoResponse(BaseModel):
    content_blocks: list[dict[str, Any]]


@router.post("/weather", response_model=WeatherDemoResponse)
def weather_demo(
    payload: WeatherDemoRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> WeatherDemoResponse:
    """Invoke the configured local Ollama model on demand.

    The endpoint has no persistence or mutation side effects. An unavailable model
    produces a service-unavailable response rather than a synthetic result.
    """
    try:
        content_blocks = run_weather_demo(
            payload.city,
            settings.ollama_model,
            settings.ollama_base_url,
        )
    except ConnectError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cannot connect to Ollama at {settings.ollama_base_url}.",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The configured Ollama model is unavailable.",
        ) from error

    return WeatherDemoResponse(content_blocks=content_blocks)
