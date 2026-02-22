"""
OSM Features — Overpass API query for tactical grid overlay.
Fetches building footprints, roads, landuse/open-space areas, amenities
(schools, hospitals, places of worship), and leisure areas from OSM via
the Overpass API.  Each feature is tagged with the 3×3 grid sector its
centroid falls in, plus a *category* that drives colour on the frontend:
    staging    — open spaces, fields, parks, pitches, meadows
    risk       — residential/commercial buildings
    access     — roads, paths, tracks
    operations — schools, hospitals, government, places of worship
"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

CELL_DEG = 0.001

GRID_OFFSETS: dict[str, tuple[int, int]] = {
    "NW": (+1, -1), "N": (+1, 0), "NE": (+1, +1),
    "W":  ( 0, -1), "C": ( 0, 0), "E":  ( 0, +1),
    "SW": (-1, -1), "S": (-1, 0), "SE": (-1, +1),
}

_OFFSET_TO_TAG = {v: k for k, v in GRID_OFFSETS.items()}

# ------------------------------------------------------------------ #
#  Category assignment — purely from OSM tags, not from VLM text      #
# ------------------------------------------------------------------ #

_AMENITY_OPS = {
    "school", "university", "college", "hospital", "clinic",
    "fire_station", "police", "community_centre", "townhall",
    "place_of_worship", "public_building", "social_facility",
}

_LANDUSE_STAGING = {
    "meadow", "grass", "recreation_ground", "farmland", "farmyard",
    "orchard", "vineyard", "allotments", "cemetery", "village_green",
    "greenfield", "brownfield", "vacant",
}

_LEISURE_STAGING = {
    "park", "pitch", "garden", "stadium", "playground",
    "sports_centre", "track", "nature_reserve", "common",
}


def _categorize(tags: dict[str, str]) -> tuple[str, str]:
    """Return (feature_type, category) from raw OSM tags.
    feature_type  — the OSM key that matched (building, highway, ...)
    category      — one of staging / risk / access / operations / unknown
    """
    # 1) Amenities that are usable for operations
    amenity = tags.get("amenity", "")
    if amenity in _AMENITY_OPS:
        return ("amenity", "operations")

    # 2) Landuse — most are open land → staging
    landuse = tags.get("landuse", "")
    if landuse:
        if landuse in ("residential", "commercial", "industrial", "retail"):
            return ("landuse", "risk")
        if landuse in _LANDUSE_STAGING or landuse not in ("residential",):
            return ("landuse", "staging")
        return ("landuse", "unknown")

    # 3) Leisure
    leisure = tags.get("leisure", "")
    if leisure:
        if leisure in _LEISURE_STAGING:
            return ("leisure", "staging")
        return ("leisure", "staging")

    # 4) Natural
    natural = tags.get("natural", "")
    if natural:
        return ("natural", "staging")

    # 5) Roads / paths
    if "highway" in tags:
        return ("highway", "access")

    # 6) Buildings — always risk (structures)
    if "building" in tags:
        return ("building", "risk")

    return ("unknown", "unknown")


def _readable_name(tags: dict[str, str], feature_type: str, category: str) -> str:
    """Build a human-readable label from OSM tags."""
    name = tags.get("name", "")
    if name:
        return name

    amenity = tags.get("amenity", "")
    if amenity:
        return amenity.replace("_", " ").title()

    landuse = tags.get("landuse", "")
    if landuse:
        return f"{landuse.replace('_', ' ').title()} area"

    leisure = tags.get("leisure", "")
    if leisure:
        return leisure.replace("_", " ").title()

    natural = tags.get("natural", "")
    if natural:
        return natural.replace("_", " ").title()

    hw = tags.get("highway", "")
    if hw:
        return f"{hw.replace('_', ' ').title()} road"

    if "building" in tags:
        bval = tags["building"]
        if bval and bval != "yes":
            return bval.replace("_", " ").title()
        return "Building"

    return feature_type


# ------------------------------------------------------------------ #
#  Geometry helpers                                                    #
# ------------------------------------------------------------------ #

def _point_to_sector(
    plat: float, plng: float,
    center_lat: float, center_lng: float,
) -> str:
    dlat = round((plat - center_lat) / CELL_DEG)
    dlng = round((plng - center_lng) / CELL_DEG)
    dlat = max(-1, min(1, dlat))
    dlng = max(-1, min(1, dlng))
    return _OFFSET_TO_TAG.get((dlat, dlng), "C")


def _centroid(coords: list[list[float]]) -> tuple[float, float]:
    n = len(coords)
    if n == 0:
        return (0.0, 0.0)
    avg_lng = sum(c[0] for c in coords) / n
    avg_lat = sum(c[1] for c in coords) / n
    return (avg_lat, avg_lng)


def _element_to_geojson(
    element: dict[str, Any],
    center_lat: float,
    center_lng: float,
) -> dict[str, Any] | None:
    """Convert an Overpass way/relation element to a GeoJSON Feature."""
    geom = element.get("geometry")
    if not geom or len(geom) < 2:
        return None

    coords = [[pt["lon"], pt["lat"]] for pt in geom]
    tags = element.get("tags", {})

    feature_type, category = _categorize(tags)
    name = _readable_name(tags, feature_type, category)

    is_closed = (
        len(coords) >= 4
        and coords[0][0] == coords[-1][0]
        and coords[0][1] == coords[-1][1]
    )

    if is_closed and feature_type != "highway":
        geom_type = "Polygon"
        geom_coords = [coords]
    else:
        geom_type = "LineString"
        geom_coords = coords

    clat, clng = _centroid(coords)
    sector = _point_to_sector(clat, clng, center_lat, center_lng)

    return {
        "type": "Feature",
        "geometry": {
            "type": geom_type,
            "coordinates": geom_coords,
        },
        "properties": {
            "osm_id": element.get("id", 0),
            "feature_type": feature_type,
            "sector": sector,
            "category": category,
            "name": name,
        },
    }


# ------------------------------------------------------------------ #
#  Main query                                                          #
# ------------------------------------------------------------------ #

def fetch_osm_features(
    lat: float,
    lng: float,
) -> dict[str, Any]:
    """Query Overpass for all tactically relevant features in the 3×3 grid.
    Returns a GeoJSON FeatureCollection.  Each Feature has properties:
    ``sector``, ``feature_type``, ``category``, ``name``.
    """
    pad = CELL_DEG * 1.6
    south = lat - pad
    north = lat + pad
    west = lng - pad
    east = lng + pad
    bbox = f"{south},{west},{north},{east}"

    query = f"""
[out:json][timeout:15];
(
  way["building"]({bbox});
  way["highway"]({bbox});
  way["landuse"]({bbox});
  way["leisure"]({bbox});
  way["natural"]({bbox});
  way["amenity"~"school|university|college|hospital|clinic|fire_station|police|community_centre|townhall|place_of_worship|public_building|social_facility"]({bbox});
  relation["landuse"]({bbox});
  relation["leisure"]({bbox});
  relation["natural"]({bbox});
  relation["amenity"~"school|university|college|hospital|clinic"]({bbox});
);
out geom;
"""

    features: list[dict[str, Any]] = []

    try:
        import time
        resp = None
        for attempt in range(3):
            resp = requests.post(
                OVERPASS_URL,
                data={"data": query},
                timeout=25,
            )
            if resp.status_code in (429, 502, 503, 504):
                wait = 2 ** attempt
                logger.info(
                    "Overpass %s — retrying in %ds (attempt %d/3)",
                    resp.status_code, wait, attempt + 1,
                )
                time.sleep(wait)
                continue
            break

        if resp is None or resp.status_code in (429, 502, 503, 504):
            logger.warning("Overpass unavailable after retries (status=%s)", getattr(resp, "status_code", None))
            return {"type": "FeatureCollection", "features": features}
        resp.raise_for_status()
        data = resp.json()

        for element in data.get("elements", []):
            etype = element.get("type")
            if etype == "way":
                feat = _element_to_geojson(element, lat, lng)
                if feat:
                    features.append(feat)
            elif etype == "relation":
                # Relations have members; extract outer ways
                for member in element.get("members", []):
                    if member.get("type") == "way" and member.get("role") in ("outer", ""):
                        geom = member.get("geometry")
                        if geom:
                            fake_way = {
                                "id": element.get("id", 0),
                                "tags": element.get("tags", {}),
                                "geometry": geom,
                            }
                            feat = _element_to_geojson(fake_way, lat, lng)
                            if feat:
                                features.append(feat)

        logger.info(
            "Overpass returned %d features near (%.5f, %.5f)",
            len(features), lat, lng,
        )

    except Exception as exc:
        logger.warning("Overpass query failed: %s", exc)

    return {
        "type": "FeatureCollection",
        "features": features,
    }