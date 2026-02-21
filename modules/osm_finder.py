"""
Visionary — OSM Candidate Finder

Queries OpenStreetMap for potential staging-ground sites
(schools, hospitals, flat/open land) within a radius of a
given coordinate using the `osmnx` library.
"""

from __future__ import annotations

import logging
from typing import Any

import osmnx as ox

logger = logging.getLogger(__name__)

# Tags that indicate potential staging grounds
STAGING_TAGS: dict[str, list[str]] = {
    "amenity": ["school", "hospital"],
    "landuse": ["meadow", "grass", "recreation_ground"],
    "leisure": ["park", "pitch", "stadium"],
}


def _build_tags_dict() -> dict[str, list[str]]:
    """Flatten STAGING_TAGS into the format osmnx expects."""
    return {k: v for k, v in STAGING_TAGS.items()}


def _extract_candidates(gdf, category: str) -> list[dict[str, Any]]:
    """Extract candidate dicts from a GeoDataFrame returned by osmnx."""
    candidates: list[dict[str, Any]] = []
    if gdf is None or gdf.empty:
        return candidates

    for idx, row in gdf.iterrows():
        # Get the centroid for polygon geometries, or direct coords for points
        geom = row.geometry
        if geom is None:
            continue
        centroid = geom.centroid

        name = row.get("name", None)
        if name is None or (isinstance(name, float)):
            name = f"Unnamed {category}"

        osm_id = str(idx) if not isinstance(idx, tuple) else str(idx[1])

        candidates.append(
            {
                "name": str(name),
                "category": category,
                "lat": round(centroid.y, 6),
                "lng": round(centroid.x, 6),
                "osm_id": osm_id,
            }
        )
    return candidates


async def find_staging_candidates(
    lat: float,
    lng: float,
    radius_m: int = 2000,
) -> list[dict[str, Any]]:
    """Find potential staging-ground sites near [lat, lng] via OpenStreetMap.

    Searches for schools, hospitals, parks, fields, and other open land
    within *radius_m* metres of the target coordinate.

    Args:
        lat: Latitude of the target location (crisis zone centre).
        lng: Longitude of the target location.
        radius_m: Search radius in metres (default 2 000 m).

    Returns:
        A list of candidate dicts, each containing:
        ``{"name", "category", "lat", "lng", "osm_id"}``.
    """
    all_candidates: list[dict[str, Any]] = []
    point = (lat, lng)

    for key, values in STAGING_TAGS.items():
        for value in values:
            tags = {key: value}
            try:
                gdf = ox.features_from_point(point, tags=tags, dist=radius_m)
                category = f"{key}={value}"
                extracted = _extract_candidates(gdf, category)
                all_candidates.extend(extracted)
                logger.info(
                    "OSM query %s near (%.4f, %.4f): %d results",
                    category, lat, lng, len(extracted),
                )
            except Exception as exc:
                # Some queries may return empty or fail — that's OK
                logger.warning(
                    "OSM query %s=%s failed: %s", key, value, exc,
                )

    logger.info(
        "Total staging candidates near (%.4f, %.4f): %d",
        lat, lng, len(all_candidates),
    )
    return all_candidates
