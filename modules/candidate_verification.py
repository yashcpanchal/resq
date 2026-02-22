"""
Visionary — Humanitarian Aid Pipeline

Single unified pipeline that:
  1. Queries OpenStreetMap for nearby aid-receivable locations (schools,
     hospitals, parks, open land)
  2. Fetches satellite imagery for each via Esri (free, no API key)
  3. Analyzes each site with a local Ollama VLM to produce a
     humanitarian aid action plan
  4. Returns a ranked list of sites with full action plans

Usage:
    import asyncio
    from modules.candidate_verification import find_aid_sites

    results = asyncio.run(find_aid_sites(31.5017, 34.4668, radius_m=5000))
    for site in results:
        print(site["name"], site["priority"], site["recommended_actions"])
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from modules.ground_verifier import (
    analyze_site_ollama,
    fetch_satellite_image_esri,
)
from modules.image_annotator import annotate_image
from modules.osm_finder import find_staging_candidates

logger = logging.getLogger(__name__)

# Maximum number of candidates to run through the VLM
MAX_VERIFY = 10


async def _analyze_single(
    candidate: dict[str, Any],
    model: str = "llava",
    ollama_host: str | None = None,
) -> dict[str, Any]:
    """Fetch satellite image + run Ollama VLM for one candidate site.

    Returns the original candidate dict with 'analysis' text and
    'annotated_image' (base64 JPEG) fields.
    On failure, returns a safe fallback so the pipeline never crashes.
    """
    try:
        # Step A — Satellite image (Esri — free, no key)
        image_bytes = fetch_satellite_image_esri(
            lat=candidate["lat"],
            lng=candidate["lng"],
            grid=3,  # 3×3 tiles = 768×768 for sharp annotated images
        )

        # Step B — VLM analysis (Ollama — local, free)
        result = await analyze_site_ollama(
            image_bytes=image_bytes,
            site_name=candidate["name"],
            category=candidate["category"],
            model=model,
            ollama_host=ollama_host,
        )

        # Step C — Annotate image with visual overlays
        analysis_text = result.get("analysis", "")
        annotated_bytes = annotate_image(
            image_bytes=image_bytes,
            analysis_text=analysis_text,
            site_name=candidate["name"],
        )
        annotated_b64 = base64.b64encode(annotated_bytes).decode("utf-8")

        return {**candidate, **result, "annotated_image": annotated_b64}

    except Exception as exc:
        logger.warning(
            "Analysis failed for %s: %s", candidate["name"], exc,
        )
        return {
            **candidate,
            "analysis": f"Analysis failed: {exc}",
            "annotated_image": "",
        }


async def analyze_location(
    lat: float,
    lng: float,
    name: str = "Location",
    model: str = "llava",
    ollama_host: str | None = None,
) -> dict[str, Any]:
    """One-call entry point: satellite image → VLM analysis → annotated image.

    Takes a lat/lng, fetches satellite imagery, runs VLM (Ollama) analysis,
    and produces an annotated image with map-style labels.

    Args:
        lat: Latitude of the target location.
        lng: Longitude of the target location.
        name: Human-readable name for the location (used in title bar).
        model: Ollama model name (default ``"llava"``).
        ollama_host: Optional Ollama API URL override.

    Returns:
        A dict with::

            {
                "lat": float,
                "lng": float,
                "name": str,
                "analysis": str,           # Full VLM analysis text
                "annotated_image": str,     # Base64-encoded annotated JPEG
                "raw_image": str,           # Base64-encoded original satellite JPEG
            }

    Example::

        import asyncio
        from modules.candidate_verification import analyze_location

        result = asyncio.run(analyze_location(31.5017, 34.4668, name="Gaza School"))
        print(result["analysis"])

        # Save annotated image
        import base64
        with open("annotated.jpg", "wb") as f:
            f.write(base64.b64decode(result["annotated_image"]))
    """
    # Step 1 — Fetch satellite image
    image_bytes = fetch_satellite_image_esri(lat=lat, lng=lng, grid=3)
    raw_b64 = base64.b64encode(image_bytes).decode("utf-8")

    # Step 2 — VLM analysis (full image + per-cell crops)
    result = await analyze_site_ollama(
        image_bytes=image_bytes,
        site_name=name,
        category="location",
        model=model,
        ollama_host=ollama_host,
    )
    analysis_text = result.get("analysis", "")

    # Step 3 — Annotate image
    annotated_bytes = annotate_image(
        image_bytes=image_bytes,
        analysis_text=analysis_text,
        site_name=name,
    )
    annotated_b64 = base64.b64encode(annotated_bytes).decode("utf-8")

    return {
        "lat": lat,
        "lng": lng,
        "name": name,
        "analysis": analysis_text,
        "annotated_image": annotated_b64,
        "raw_image": raw_b64,
    }


async def find_aid_sites(
    lat: float,
    lng: float,
    radius_m: int = 5000,
    max_sites: int = MAX_VERIFY,
    model: str = "llava",
    ollama_host: str | None = None,
) -> list[dict[str, Any]]:
    """Find nearby locations that can receive humanitarian aid and generate
    a plain-text analysis for each based on satellite imagery.

    This is the main entry point — one function that does everything:
      1. Searches OpenStreetMap for schools, hospitals, parks, and open
         land within ``radius_m`` of the given coordinates.
      2. Downloads a satellite image of each site (Esri — free).
      3. Sends each image to a local Ollama VLM to produce a
         plain-text humanitarian aid analysis.
      4. Returns all sites with their analyses.

    Args:
        lat: Latitude of the crisis zone centre.
        lng: Longitude of the crisis zone centre.
        radius_m: Search radius in metres (default 5 000 m).
        max_sites: Maximum sites to analyze with the VLM (default 10).
        model: Ollama vision model name (default ``"llava"``).
        ollama_host: Optional Ollama URL (default ``http://localhost:11434``).

    Returns:
        List of dicts, each containing::

            {
                "name": str,       # e.g. "Al-Quds Hospital"
                "category": str,   # e.g. "amenity=hospital"
                "lat": float,
                "lng": float,
                "osm_id": str,
                "analysis": str,   # plain-text humanitarian aid analysis
            }
    """
    # ── Step 1: Find candidate locations via OpenStreetMap ────────
    logger.info(
        "Searching for aid sites near (%.4f, %.4f), radius=%dm",
        lat, lng, radius_m,
    )
    candidates = await find_staging_candidates(lat, lng, radius_m)

    if not candidates:
        logger.info("No candidate locations found near (%.4f, %.4f)", lat, lng)
        return []

    logger.info("Found %d candidate locations from OSM", len(candidates))

    # ── Step 2 + 3: Fetch imagery + VLM analysis (sequential) ──────
    # Ollama processes one inference at a time, so sequential is
    # actually faster than concurrent (avoids request queueing).
    to_analyze = candidates[:max_sites]
    logger.info(
        "Analyzing %d / %d candidates via Ollama (%s)",
        len(to_analyze), len(candidates), model,
    )

    analyzed = []
    for i, c in enumerate(to_analyze):
        logger.info(
            "[%d/%d] Analyzing %s ...", i + 1, len(to_analyze), c["name"],
        )
        result = await _analyze_single(c, model=model, ollama_host=ollama_host)
        analyzed.append(result)

    # Tag any remaining candidates as not-yet-analyzed
    remaining = [
        {
            **c,
            "analysis": "Not analyzed — increase max_sites to include",
            "annotated_image": "",
        }
        for c in candidates[max_sites:]
    ]

    all_results = analyzed + remaining

    logger.info(
        "Pipeline complete: %d analyzed / %d total sites",
        len(analyzed), len(all_results),
    )
    return all_results


async def get_best_aid_site(
    lat: float,
    lng: float,
    radius_m: int = 5000,
    model: str = "llava",
    ollama_host: str | None = None,
) -> dict[str, Any] | None:
    """Convenience wrapper — return the single highest-priority viable site.

    Returns the first analyzed site, or ``None`` if no candidates found.
    """
    results = await find_aid_sites(
        lat, lng, radius_m,
        model=model, ollama_host=ollama_host,
    )
    if results:
        return results[0]
    return None


# ── CLI entry point for quick testing ────────────────────────────── #

if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        description="Find humanitarian aid sites near a location",
    )
    parser.add_argument("lat", type=float, help="Latitude")
    parser.add_argument("lng", type=float, help="Longitude")
    parser.add_argument("--radius", type=int, default=5000, help="Search radius in metres")
    parser.add_argument("--max-sites", type=int, default=10, help="Max sites to analyze")
    parser.add_argument("--model", default="llava", help="Ollama model name")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    results = asyncio.run(
        find_aid_sites(
            args.lat, args.lng,
            radius_m=args.radius,
            max_sites=args.max_sites,
            model=args.model,
        )
    )

    if args.json:
        print(json.dumps(results, indent=2))
        sys.exit(0)

    if not results:
        print(f"No aid sites found near ({args.lat}, {args.lng})")
        sys.exit(0)

    # Pretty print
    analyzed = [r for r in results if "Not analyzed" not in r.get("analysis", "")]
    print(f"\n🔍 Found {len(results)} locations, analyzed {len(analyzed)} near ({args.lat}, {args.lng})\n")

    for i, site in enumerate(results, 1):
        analysis = site.get("analysis", "N/A")
        is_analyzed = "Not analyzed" not in analysis

        print(f"{'─' * 60}")
        print(f"  {i}. {site['name']}")
        print(f"     Category:  {site['category']}")
        print(f"     Coords:    ({site['lat']}, {site['lng']})")
        if is_analyzed:
            print(f"     📋 Analysis:")
            # Word-wrap the analysis to 55 chars per line
            words = analysis.split()
            line = "        "
            for word in words:
                if len(line) + len(word) + 1 > 65:
                    print(line)
                    line = "        " + word
                else:
                    line += " " + word if line.strip() else "        " + word
            if line.strip():
                print(line)
        else:
            print(f"     ⏭️  {analysis}")
        print()

    print(f"{'─' * 60}")
    print(f"  📊 {len(analyzed)} analyzed  |  {len(results) - len(analyzed)} pending")
    print()