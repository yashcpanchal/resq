"""
Pipeline Routes — Data engineering endpoints (neglect scores, funding scores).
"""

from __future__ import annotations

from fastapi import APIRouter

from modules.pipeline import calculate_funding_scores, get_crisis_scores

router = APIRouter()


# ---- Health ---- #

@router.get("/health")
async def health():
    return {"status": "ok"}


# ---- Pipeline ---- #

@router.get("/crisis-scores")
async def crisis_scores():
    """Return crisis final_score per country."""
    return await get_crisis_scores()


@router.get("/funding-scores")
async def funding_scores():
    """Return funding score (received / required) per country."""
    return calculate_funding_scores()
