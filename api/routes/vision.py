"""
Vision Routes — Satellite / image-based endpoints.
"""

from __future__ import annotations

import os
import re
import json
import time
import hashlib
import logging
from typing import Any

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

# ---------------------------------------------------------------------------
# Persistent file-based cache (data/tactical_cache/)
# ---------------------------------------------------------------------------
_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "tactical_cache"
)
os.makedirs(_CACHE_DIR, exist_ok=True)
_CACHE_TTL = 3600  # 1 hour
_COORD_PRECISION = 4  # ~11m precision for cache keys

def _get_tactical_cache_path(lat: float, lng: float, model: str) -> str:
    """Create a unique hash for the location + model."""
    key = f"{round(lat, _COORD_PRECISION)},{round(lng, _COORD_PRECISION)},{model}"
    h = hashlib.md5(key.encode()).hexdigest()
    return os.path.join(_CACHE_DIR, f"{h}.json")

def _load_tactical_cache(lat: float, lng: float, model: str) -> dict[str, Any] | None:
    path = _get_tactical_cache_path(lat, lng, model)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            entry = json.load(f)
            if time.time() - entry.get("ts", 0) < _CACHE_TTL:
                return entry.get("data")
    except Exception:
        pass
    return None

def _save_tactical_cache(lat: float, lng: float, model: str, data: dict[str, Any]):
    path = _get_tactical_cache_path(lat, lng, model)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"data": data, "ts": time.time()}, f)
    except Exception as e:
        logger.warning("Failed to save tactical cache: %s", e)

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

    Results are cached for 1 hour based on coordinates (rounded to 4 decimals).
    """
    cached = _load_tactical_cache(req.lat, req.lng, req.model)
    if cached:
        logger.info("Tactical cache hit for %s", req.name)
        return TacticalAnalysisResponse(**cached)

    logger.info("Tactical analysis for (%.5f, %.5f) '%s'", req.lat, req.lng, req.name)

    try:
        result = await analyze_location(
            lat=req.lat,
            lng=req.lng,
            name=req.name,
            model=req.model,
        )
    except Exception as exc:
        logger.warning("VLM analysis failed for %s: %s", req.name, exc)
        result = {"analysis": f"VLM analysis unavailable: {exc}", "annotated_image": ""}

    analysis_text = result.get("analysis", "")
    sectors = _parse_sectors(analysis_text)

    geojson = fetch_osm_features(req.lat, req.lng)

    # Enrich GeoJSON features with VLM sector classifications
    for feat in geojson.get("features", []):
        sector = feat["properties"].get("sector", "C")
        sector_desc = sectors.get(sector, "")
        if sector_desc:
            feat["properties"]["sector_description"] = sector_desc

    resp_data = {
        "lat": req.lat,
        "lng": req.lng,
        "name": req.name,
        "analysis": analysis_text,
        "sectors": sectors,
        "geojson": geojson,
        "annotated_image": result.get("annotated_image", ""),
    }

    # Store in cache persistently
    _save_tactical_cache(req.lat, req.lng, req.model, resp_data)

    return TacticalAnalysisResponse(**resp_data)


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