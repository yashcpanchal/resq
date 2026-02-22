"""
Vision Routes — Satellite / image-based endpoints.
"""

from __future__ import annotations

import re
import logging

from fastapi import APIRouter

from api.schemas import (
    AidSiteRequest,
    AidSiteResponse,
    TacticalAnalysisRequest,
    TacticalAnalysisResponse,
)
from modules.vision import get_parking_capacity
from modules.candidate_verification import find_aid_sites, analyze_location
from modules.osm_features import fetch_osm_features

logger = logging.getLogger(__name__)
router = APIRouter()

GRID_TAGS = ["NW", "N", "NE", "W", "C", "E", "SW", "S", "SE"]


def _parse_sectors(analysis_text: str) -> dict[str, str]:
    """Extract per-sector descriptions from VLM analysis text."""
    tag_re = re.compile(
        r"\[(" + "|".join(GRID_TAGS) + r")\]\s*([\s\S]*?)(?=\[(?:"
        + "|".join(GRID_TAGS)
        + r")\]|$)",
        re.IGNORECASE,
    )
    sectors: dict[str, str] = {}
    for m in tag_re.finditer(analysis_text):
        tag = m.group(1).upper()
        if tag not in sectors:
            sectors[tag] = m.group(2).strip().replace("\n", " ")
    return sectors


# ---- Tactical Analysis ---- #

@router.post("/tactical-analysis", response_model=TacticalAnalysisResponse)
async def tactical_analysis(req: TacticalAnalysisRequest):
    """Run VLM satellite analysis + fetch OSM features for a 3x3 grid.

    1. Fetches Esri satellite imagery for the location.
    2. Runs Ollama VLM analysis (full image + 9 cell crops).
    3. Queries Overpass for building/road/landuse features in the grid.
    4. Returns analysis text, per-sector descriptions, GeoJSON features,
       and an annotated satellite image.
    """
    logger.info("Tactical analysis for (%.5f, %.5f) '%s'", req.lat, req.lng, req.name)

    result = await analyze_location(
        lat=req.lat,
        lng=req.lng,
        name=req.name,
        model=req.model,
    )

    analysis_text = result.get("analysis", "")
    sectors = _parse_sectors(analysis_text)

    geojson = fetch_osm_features(req.lat, req.lng)

    # Enrich GeoJSON features with VLM sector classifications
    for feat in geojson.get("features", []):
        sector = feat["properties"].get("sector", "C")
        sector_desc = sectors.get(sector, "")
        if sector_desc:
            feat["properties"]["sector_description"] = sector_desc

    return TacticalAnalysisResponse(
        lat=req.lat,
        lng=req.lng,
        name=req.name,
        analysis=analysis_text,
        sectors=sectors,
        geojson=geojson,
        annotated_image=result.get("annotated_image", ""),
    )


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
