from fastapi import APIRouter

from api.v1.routes.demo import router as demo_router
from api.v1.routes.platform import router as platform_router
from api.v1.routes.runs import router as runs_router

router = APIRouter()
router.include_router(demo_router)
router.include_router(platform_router)
router.include_router(runs_router)
