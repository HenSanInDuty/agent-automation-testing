from fastapi import APIRouter

from api.v1.routes.activities import router as activities_router
from api.v1.routes.auth import admin_router
from api.v1.routes.auth import router as auth_router
from api.v1.routes.catalog import router as catalog_router
from api.v1.routes.demo import router as demo_router
from api.v1.routes.generation import router as generation_router
from api.v1.routes.operations import router as operations_router
from api.v1.routes.platform import router as platform_router
from api.v1.routes.proposals import router as proposals_router
from api.v1.routes.runs import router as runs_router
from api.v1.routes.worker_progress import router as worker_progress_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(activities_router)
router.include_router(catalog_router)
router.include_router(admin_router)
router.include_router(demo_router)
router.include_router(generation_router)
router.include_router(operations_router)
router.include_router(platform_router)
router.include_router(proposals_router)
router.include_router(runs_router)
router.include_router(worker_progress_router)
