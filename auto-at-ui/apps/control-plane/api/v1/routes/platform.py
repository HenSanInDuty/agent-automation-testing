from fastapi import APIRouter

router = APIRouter(tags=["platform"])


@router.get("/platform")
async def platform_info() -> dict[str, object]:
    return {
        "supported_targets": ["web_ui", "api", "game"],
        "execution_mode": "deterministic-with-agent-assistance",
    }
