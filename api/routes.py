"""
FastAPI Routes — The API plumbing layer.

Each route delegates to the corresponding module in modules/.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas import (
    MemoRequest,
    MemoResponse,
    NeglectScore,
    ParkingRequest,
    ParkingResponse,
    SafetyRequest,
    SafetyResponse,
)
from modules.pipeline import get_neglect_scores
from modules.vision import get_parking_capacity
from modules.vector import get_safety_report
from modules.synthesis import generate_memo

router = APIRouter()


# ---- Health ---- #

@router.get("/health")
async def health():
    return {"status": "ok"}


# ---- Pipeline ---- #

@router.get("/neglect-scores", response_model=list[NeglectScore])
async def neglect_scores():
    """Return computed neglect scores for all tracked crises."""
    data = await get_neglect_scores()
    return data


# ---- Vision ---- #

@router.post("/parking-capacity", response_model=ParkingResponse)
async def parking_capacity(req: ParkingRequest):
    """Estimate parking/staging capacity at given coordinates."""
    capacity = await get_parking_capacity(req.lat, req.lng)
    return ParkingResponse(lat=req.lat, lng=req.lng, capacity=capacity)


# ---- Vector ---- #

@router.post("/safety-report", response_model=SafetyResponse)
async def safety_report(req: SafetyRequest):
    """Generate a safety report for given coordinates via RAG."""
    report = await get_safety_report(req.lat, req.lng)
    return SafetyResponse(lat=req.lat, lng=req.lng, report=report)


# ---- Synthesis ---- #

@router.post("/generate-memo", response_model=MemoResponse)
async def memo(req: MemoRequest):
    """Generate a deployment plan memo from aggregated data."""
    text = await generate_memo(req.model_dump())
    return MemoResponse(crisis_id=req.crisis_id, memo=text)
