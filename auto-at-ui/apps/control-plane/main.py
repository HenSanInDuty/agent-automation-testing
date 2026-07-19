from api.v1.router import router as v1_router
from api.v1.routes.health import router as health_router
from config import get_settings
from fastapi import FastAPI

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="API boundary for multi-agent automation testing.",
)


app.include_router(health_router)
app.include_router(v1_router, prefix="/api/v1")
