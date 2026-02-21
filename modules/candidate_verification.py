"""
Visionary — Visual Reasoning Orchestrator

End-to-end pipeline that:
  1. Queries OpenStreetMap for candidate staging grounds
  2. Fetches satellite imagery for each candidate
  3. Uses GPT-4o Vision to verify ground suitability
  4. Returns a ranked list of viable sites
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from modules.ground_verifier import fetch_satellite_image, verify_ground_viability
from modules.osm_finder import find_staging_candidates

logger = logging.getLogger(__name__)

# Maximum number of candidates to verify (limits API cost)
MAX_VERIFY = 10


async def _verify_single(candidate: dict[str, Any]) -> dict[str, Any]:
    """Fetch satellite image and run GPT-4o Vision for one candidate."""
    try:
        image_bytes = fetch_satellite_image(
            lat=candidate["lat"],
            lng=candidate["lng"],
        )
        verification = await verify_ground_viability(
            image_bytes=image_bytes,
            site_name=candidate["name"],
            category=candidate["category"],
        )
        return {**candidate, **verification}

    except Exception as exc:
        logger.warning(
            "Verification failed for %s: %s", candidate["name"], exc,
        )
        return {
            **candidate,
            "viable": False,
            "reason": f"Verification error: {exc}",
            "confidence": 0.0,
        }


async def evaluate_staging_grounds(
    lat: float,
    lng: float,
    radius_m: int = 2000,
) -> list[dict[str, Any]]:
    """Run the full visual-reasoning pipeline for a location.

    1. Finds candidate sites (schools, hospitals, open land) via OSM.
    2. For each candidate (up to ``MAX_VERIFY``), fetches a satellite
       image and asks GPT-4o Vision whether the site is viable.
    3. Returns all candidates sorted: viable first, then by confidence
       descending.

    Args:
        lat: Latitude of the crisis zone centre.
        lng: Longitude of the crisis zone centre.
        radius_m: Search radius in metres (default 2 000 m).

    Returns:
        List of dicts with keys:
        ``name, category, lat, lng, osm_id, viable, reason, confidence``.
    """
    # Step 1 — Find OSM candidates
    candidates = await find_staging_candidates(lat, lng, radius_m)
    if not candidates:
        logger.info("No OSM candidates found near (%.4f, %.4f)", lat, lng)
        return []

    # Cap the number of candidates to verify
    to_verify = candidates[:MAX_VERIFY]
    logger.info(
        "Verifying %d / %d candidates via GPT-4o Vision",
        len(to_verify), len(candidates),
    )

    # Step 2 — Verify each candidate concurrently
    tasks = [_verify_single(c) for c in to_verify]
    verified = await asyncio.gather(*tasks)

    # Add any un-verified candidates with default viability = unknown
    unverified = [
        {**c, "viable": False, "reason": "Not verified (limit reached)", "confidence": 0.0}
        for c in candidates[MAX_VERIFY:]
    ]
    all_results = list(verified) + unverified

    # Step 3 — Sort: viable first, then by confidence desc
    all_results.sort(
        key=lambda r: (r.get("viable", False), r.get("confidence", 0.0)),
        reverse=True,
    )

    viable_count = sum(1 for r in all_results if r.get("viable"))
    logger.info(
        "Pipeline complete: %d viable / %d total candidates",
        viable_count, len(all_results),
    )
    return all_results


async def get_best_staging_ground(
    lat: float,
    lng: float,
    radius_m: int = 2000,
) -> dict[str, Any] | None:
    """Convenience wrapper — return the single best viable staging ground.

    Returns ``None`` if no viable candidate is found.
    """
    results = await evaluate_staging_grounds(lat, lng, radius_m)
    for r in results:
        if r.get("viable"):
            return r
    return None