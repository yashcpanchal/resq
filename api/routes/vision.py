"""
Vision Routes — Satellite / image-based endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas import ParkingRequest, ParkingResponse
from modules.vision import get_parking_capacity

router = APIRouter()


@router.post("/parking-capacity", response_model=ParkingResponse)
async def parking_capacity(req: ParkingRequest):
    """Estimate parking/staging capacity at given coordinates."""
    capacity = await get_parking_capacity(req.lat, req.lng)
    return ParkingResponse(lat=req.lat, lng=req.lng, capacity=capacity)
