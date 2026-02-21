"""
api.routes — Aggregates all domain-specific route modules into a single router.

app.py imports ``from api.routes import router`` which resolves here.
"""

from fastapi import APIRouter

from api.routes.pipeline import router as pipeline_router
from api.routes.vision import router as vision_router
from api.routes.context_engine import router as context_engine_router
from api.routes.synthesis import router as synthesis_router

router = APIRouter()

router.include_router(pipeline_router)
router.include_router(vision_router)
router.include_router(context_engine_router)
router.include_router(synthesis_router)
