"""
Vision Routes — Satellite / image-based endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas import AidSiteRequest, AidSiteResponse
from modules.vision import get_parking_capacity
from modules.candidate_verification import find_aid_sites

router = APIRouter()

# ---- Humanitarian Aid Sites ---- #

@router.post("/aid-sites", response_model=AidSiteResponse)
async def aid_sites(req: AidSiteRequest):
    """Find nearby humanitarian aid sites and generate action plans.

    Takes a lat/lng coordinate and searches for schools, hospitals,
    parks, and open land within the given radius. For each site,
    fetches satellite imagery and uses a local Ollama VLM to generate
    a humanitarian aid action plan.
    """
    sites = await find_aid_sites(
        lat=req.lat,
        lng=req.lng,
        radius_m=req.radius_m,
        max_sites=req.max_sites,
        model=req.model,
    )
    analyzed_sites = [s for s in sites if "Not analyzed" not in s.get("analysis", "")]
    return AidSiteResponse(
        lat=req.lat,
        lng=req.lng,
        radius_m=req.radius_m,
        total_candidates=len(sites),
        analyzed_candidates=len(analyzed_sites),
        sites=analyzed_sites,
    )
