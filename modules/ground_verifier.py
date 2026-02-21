"""
Visionary — Ground Verifier

Provides two strategies for each step of the verification pipeline:

**Satellite Imagery:**
  - ``fetch_satellite_image``       — Google Maps Static API (requires GOOGLE_MAPS_API_KEY)
  - ``fetch_satellite_image_esri``  — Esri World Imagery tiles (FREE, no key needed)

**Visual Reasoning:**
  - ``verify_ground_viability``         — OpenAI GPT-4o Vision (requires OPENAI_API_KEY, paid)
  - ``verify_ground_viability_gemini``  — Google Gemini 2.0 Flash (FREE tier, requires GEMINI_API_KEY)
"""

from __future__ import annotations

import base64
import io
import json
import logging
import math
import os
from typing import Any

import requests
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

SATELLITE_PROMPT = (
    "Analyze this satellite image of a location identified as '{site_name}' "
    "(category: {category}). "
    "Determine whether there is a large, flat, open area — such as a "
    "courtyard, parking lot, sports field, or paved yard — that would be "
    "suitable for landing a helicopter or staging 5+ relief trucks.\n\n"
    "Reply ONLY with valid JSON in this exact schema:\n"
    '{{"viable": true/false, '
    '"reason": "<one-sentence explanation>", '
    '"confidence": <0.0-1.0>}}'
)


# ================================================================== #
#  Satellite Imagery — Google Maps (paid)                            #
# ================================================================== #

def fetch_satellite_image(
    lat: float,
    lng: float,
    zoom: int = 18,
    size: str = "600x600",
) -> bytes:
    """Download a satellite image from Google Maps Static API.

    Requires ``GOOGLE_MAPS_API_KEY`` in env / .env.

    Returns:
        Raw PNG image bytes.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_MAPS_API_KEY is not set. "
            "Add it to your .env file, or use fetch_satellite_image_esri() instead."
        )

    url = "https://maps.googleapis.com/maps/api/staticmap"
    params = {
        "center": f"{lat},{lng}",
        "zoom": zoom,
        "size": size,
        "maptype": "satellite",
        "key": api_key,
    }

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()

    if resp.headers.get("Content-Type", "").startswith("image/"):
        logger.info("Fetched satellite image (Google) for (%.4f, %.4f)", lat, lng)
        return resp.content

    raise RuntimeError(
        f"Google Maps API returned unexpected content: "
        f"{resp.headers.get('Content-Type')}"
    )


# ================================================================== #
#  Satellite Imagery — Esri World Imagery (FREE, no key needed)      #
# ================================================================== #

def _latlon_to_tile(lat: float, lng: float, zoom: int) -> tuple[int, int]:
    """Convert lat/lng to slippy-map tile coordinates at *zoom*."""
    n = 2 ** zoom
    x = int((lng + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def fetch_satellite_image_esri(
    lat: float,
    lng: float,
    zoom: int = 18,
    grid: int = 3,
) -> bytes:
    """Download satellite imagery from Esri World Imagery — **completely free**.

    Stitches a *grid × grid* block of 256 px tiles centred on the
    coordinate, producing a ``(grid*256) × (grid*256)`` JPEG image
    (default 768×768).

    No API key or account is required.  The tiles come from Esri's
    public ArcGIS World Imagery service.

    Args:
        lat: Latitude of the target.
        lng: Longitude of the target.
        zoom: Tile zoom level (18 ≈ building-level detail).
        grid: Number of tiles per side to stitch (default 3 → 768 px).

    Returns:
        Raw JPEG image bytes.
    """
    from PIL import Image  # lazy import — only needed here

    cx, cy = _latlon_to_tile(lat, lng, zoom)
    half = grid // 2

    tiles: list[tuple[int, int, Image.Image]] = []
    for dy in range(-half, half + 1):
        for dx in range(-half, half + 1):
            tx, ty = cx + dx, cy + dy
            url = (
                f"https://server.arcgisonline.com/ArcGIS/rest/services/"
                f"World_Imagery/MapServer/tile/{zoom}/{ty}/{tx}"
            )
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            tile_img = Image.open(io.BytesIO(resp.content))
            tiles.append((dx + half, dy + half, tile_img))

    tile_size = 256
    canvas = Image.new("RGB", (grid * tile_size, grid * tile_size))
    for gx, gy, tile_img in tiles:
        canvas.paste(tile_img, (gx * tile_size, gy * tile_size))

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=90)
    logger.info("Fetched satellite image (Esri) for (%.4f, %.4f)", lat, lng)
    return buf.getvalue()


# ================================================================== #
#  Visual Reasoning — OpenAI GPT-4o Vision (paid)                    #
# ================================================================== #

def _parse_vision_json(raw_text: str) -> dict[str, Any]:
    """Parse a JSON response from a vision model, handling markdown fences."""
    json_text = raw_text.strip()
    if json_text.startswith("```"):
        json_text = "\n".join(json_text.split("\n")[1:-1])

    try:
        result = json.loads(json_text)
    except json.JSONDecodeError:
        logger.warning("Vision model returned non-JSON: %s", raw_text)
        result = {
            "viable": False,
            "reason": f"Could not parse model response: {raw_text[:200]}",
            "confidence": 0.0,
        }

    return {
        "viable": bool(result.get("viable", False)),
        "reason": str(result.get("reason", "No reason provided")),
        "confidence": float(result.get("confidence", 0.0)),
    }


async def verify_ground_viability(
    image_bytes: bytes,
    site_name: str,
    category: str,
) -> dict[str, Any]:
    """Use **OpenAI GPT-4o Vision** to assess staging-ground suitability.

    Requires ``OPENAI_API_KEY`` in env / .env.  This is a **paid** API.

    Returns:
        ``{"viable": bool, "reason": str, "confidence": float}``
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. "
            "Add it to your .env, or use verify_ground_viability_gemini() instead."
        )

    client = AsyncOpenAI(api_key=api_key)
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    prompt = SATELLITE_PROMPT.format(site_name=site_name, category=category)

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64_image}",
                            "detail": "high",
                        },
                    },
                ],
            }
        ],
        max_tokens=300,
        temperature=0.1,
    )

    return _parse_vision_json(response.choices[0].message.content)


# ================================================================== #
#  Visual Reasoning — Google Gemini Flash (FREE tier)                 #
# ================================================================== #

async def verify_ground_viability_gemini(
    image_bytes: bytes,
    site_name: str,
    category: str,
) -> dict[str, Any]:
    """Use **Google Gemini 2.0 Flash** to assess staging-ground suitability.

    Requires ``GEMINI_API_KEY`` in env / .env.
    Gemini Flash is **free** on the Google AI Studio free tier
    (up to 15 RPM / 1 500 RPD as of 2025).

    Get a key at https://aistudio.google.com/apikey

    Returns:
        ``{"viable": bool, "reason": str, "confidence": float}``
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. "
            "Get a free key at https://aistudio.google.com/apikey "
            "and add it to your .env file."
        )

    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    prompt = SATELLITE_PROMPT.format(site_name=site_name, category=category)

    # Use the Gemini REST API directly (avoids extra SDK dependency)
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": b64_image,
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 300,
        },
    }

    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    raw_text = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )

    return _parse_vision_json(raw_text)
