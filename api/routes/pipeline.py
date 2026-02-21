"""
Pipeline Routes — Data engineering endpoints (neglect scores, funding scores).
"""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas import NeglectScore
from modules.pipeline import calculate_funding_scores, get_neglect_scores

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


@router.get("/funding-scores")
async def funding_scores():
    """Return funding score (received / required) per country."""
    return calculate_funding_scores()
