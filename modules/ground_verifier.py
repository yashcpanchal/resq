"""
Visionary — Ground Verifier

Provides two strategies for each step of the verification pipeline:

**Satellite Imagery:**
  - ``fetch_satellite_image``       — Google Maps Static API (requires GOOGLE_MAPS_API_KEY)
  - ``fetch_satellite_image_esri``  — Esri World Imagery tiles (FREE, no key needed)

**Visual Reasoning:**
  - ``verify_ground_viability``   — OpenAI GPT-4o Vision (requires OPENAI_API_KEY, paid)
  - ``analyze_site_ollama``       — Local Ollama VLM (FREE, runs locally, no API key)
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

# ── Prompts ──────────────────────────────────────────────────────── #

# Simple viability prompt (used by GPT-4o)
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

# Humanitarian aid analysis prompt (used by Ollama — plain text output)
AID_ANALYSIS_PROMPT = (
    "You are analyzing a satellite image of '{site_name}' ({category}). "
    "Only use information that is directly visible in the image. "
    "Do NOT give general humanitarian advice. Do NOT mention coordination, policy, or training.\n\n"

    "Step 1 — Describe Visible Features:\n"
    "- Describe terrain (flat, sloped, flooded, rubble, vegetation).\n"
    "- Identify roads or paths and where they enter/exit the area.\n"
    "- Identify open flat spaces large enough for trucks or helicopters.\n"
    "- Identify damaged or intact buildings.\n"
    "- Identify obstacles (debris, water, blocked roads).\n\n"

    "Step 2 — Plan Aid Delivery Using Only What You See:\n"
    "- Choose a specific entry point (north, south, east, west, or visible road).\n"
    "- Choose a specific staging area visible in the image and explain why it works.\n"
    "- Explain how trucks or helicopters would access that staging area.\n"
    "- Mention any visible risks and how to avoid them.\n\n"

    "Be concrete and reference visible landmarks. "
    "Do NOT give generic advice. Base every decision on visible features in the image."
)

# Short prompt for per-cell descriptions
CELL_PROMPT = (
    "Describe this satellite image crop in 3-8 words. "
    "Do NOT start with 'The image shows' or 'This is'. "
    "Just name what you see: terrain type, buildings, roads, damage, etc. "
    "Example: 'Damaged buildings with scattered rubble'"
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
    zoom: int = 17,
    grid: int = 1,
) -> bytes:
    """Download satellite imagery from Esri World Imagery — **completely free**.

    Fetches a *grid × grid* block of 256 px tiles centred on the
    coordinate, producing a ``(grid*256) × (grid*256)`` JPEG image
    (default 256×256 with grid=1 for speed).

    No API key or account is required.  The tiles come from Esri's
    public ArcGIS World Imagery service.

    Args:
        lat: Latitude of the target.
        lng: Longitude of the target.
        zoom: Tile zoom level (17 ≈ neighbourhood detail, 18 ≈ building).
        grid: Number of tiles per side (default 1 → 256 px, fast).

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
#  Image Preprocessing                                               #
# ================================================================== #

def _resize_for_vlm(image_bytes: bytes, max_dim: int = 384) -> bytes:
    """Shrink an image so its longest side is at most *max_dim* pixels.

    VLMs do not benefit from high-res input — 384 px is more than
    enough for spatial reasoning while keeping payloads small and
    inference fast.

    Returns JPEG bytes (always, regardless of input format).
    """
    from PIL import Image  # lazy import

    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _add_grid_labels(image_bytes: bytes) -> bytes:
    """Draw bold, visible grid cell labels on the image (used for debug only now)."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    font_size = max(16, w // 20)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except (OSError, IOError):
            font = ImageFont.load_default()
    for i in range(1, 3):
        draw.line([(i * w // 3, 0), (i * w // 3, h)], fill=(255, 255, 255), width=2)
        draw.line([(0, i * h // 3), (w, i * h // 3)], fill=(255, 255, 255), width=2)
    labels = {
        "NW": (0, 0), "N": (1, 0), "NE": (2, 0),
        "W": (0, 1), "C": (1, 1), "E": (2, 1),
        "SW": (0, 2), "S": (1, 2), "SE": (2, 2),
    }
    cw, ch = w // 3, h // 3
    for label, (gx, gy) in labels.items():
        cx, cy = gx * cw + cw // 2, gy * ch + ch // 2
        bbox = font.getbbox(label)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.rectangle([cx - tw//2 - 4, cy - th//2 - 4, cx + tw//2 + 4, cy + th//2 + 4],
                       fill=(0, 0, 0), outline=(255, 255, 255))
        draw.text((cx, cy), label, fill=(255, 255, 255), font=font, anchor="mm")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _crop_grid_cells(image_bytes: bytes) -> dict[str, bytes]:
    """Crop a satellite image into 9 grid cells.

    Returns a dict mapping grid tag ('NW', 'N', etc.) to JPEG bytes.
    """
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    cw, ch = w // 3, h // 3

    grid = {
        "NW": (0, 0), "N": (1, 0), "NE": (2, 0),
        "W": (0, 1),  "C": (1, 1), "E": (2, 1),
        "SW": (0, 2), "S": (1, 2), "SE": (2, 2),
    }

    cells: dict[str, bytes] = {}
    for tag, (gx, gy) in grid.items():
        box = (gx * cw, gy * ch, (gx + 1) * cw, (gy + 1) * ch)
        cell = img.crop(box)
        buf = io.BytesIO()
        cell.save(buf, format="JPEG", quality=80)
        cells[tag] = buf.getvalue()

    return cells


def _describe_cell_sync(
    cell_bytes: bytes,
    tag: str,
    model: str,
    host: str,
) -> tuple[str, str]:
    """Send a single cropped cell to Ollama and get a short description.

    Returns (tag, description).
    """
    b64 = base64.b64encode(cell_bytes).decode("utf-8")

    payload = {
        "model": model,
        "prompt": CELL_PROMPT,
        "images": [b64],
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 64,
        },
    }

    try:
        resp = requests.post(f"{host}/api/generate", json=payload, timeout=30)
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        # Clean up — take first sentence, strip preamble
        text = text.split(".")[0].strip().rstrip(".")
        # Remove common LLM preambles
        for prefix in ["The image shows ", "This is ", "This shows ",
                       "This image shows ", "The image is ", "I see "]:
            if text.lower().startswith(prefix.lower()):
                text = text[len(prefix):]
                break
        # Capitalize first letter
        if text:
            text = text[0].upper() + text[1:]
        if not text:
            text = "No distinct features visible"
        return (tag, text)
    except Exception as exc:
        logger.warning("Cell %s description failed: %s", tag, exc)
        return (tag, "Could not analyze this cell")



# ================================================================== #
#  JSON Parsing Helpers                                              #
# ================================================================== #

def _parse_vision_json(raw_text: str) -> dict[str, Any]:
    """Parse a simple viability JSON response (viable/reason/confidence)."""
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


def _parse_action_plan_json(raw_text: str) -> dict[str, Any]:
    """Parse a full humanitarian action-plan JSON from the VLM.

    Handles common VLM quirks:
    - Leading/trailing whitespace or text
    - Markdown ```json fences
    - Fields returned as arrays instead of strings
    """
    import re

    json_text = raw_text.strip()

    # Remove markdown fences
    if json_text.startswith("```"):
        json_text = "\n".join(json_text.split("\n")[1:])
    if json_text.endswith("```"):
        json_text = json_text[: json_text.rfind("```")]

    # Try to extract the first JSON object from the text
    match = re.search(r"\{[\s\S]*\}", json_text)
    if match:
        json_text = match.group(0)

    try:
        result = json.loads(json_text)
    except json.JSONDecodeError:
        # Model returned plain text — use it as the terrain assessment
        text = raw_text.strip()[:500]
        if text:
            logger.info("VLM returned plain text, using as terrain assessment")
            return {
                "viable": True,
                "confidence": 0.5,
                "terrain_assessment": text,
                "access_routes": "See terrain assessment",
                "staging_capacity": "Unknown — manual review needed",
                "recommended_actions": [],
                "risks": "Unknown — manual review needed",
                "priority": "medium",
                "reason": text[:200],
            }
        logger.warning("VLM returned empty response")
        return {
            "viable": False,
            "confidence": 0.0,
            "terrain_assessment": "No response from model",
            "access_routes": "Unknown",
            "staging_capacity": "Unknown",
            "recommended_actions": [],
            "risks": "Unknown",
            "priority": "unknown",
            "reason": "Model returned empty response",
        }

    def _to_str(val: Any, default: str = "Unknown") -> str:
        """Coerce a value to string — join lists with ', '."""
        if val is None:
            return default
        if isinstance(val, list):
            return ", ".join(str(v) for v in val) if val else default
        return str(val)

    return {
        "viable": bool(result.get("viable", False)),
        "confidence": float(result.get("confidence", 0.0)),
        "terrain_assessment": _to_str(result.get("terrain_assessment"), "Not assessed"),
        "access_routes": _to_str(result.get("access_routes")),
        "staging_capacity": _to_str(result.get("staging_capacity")),
        "recommended_actions": list(result.get("recommended_actions", [])),
        "risks": _to_str(result.get("risks")),
        "priority": str(result.get("priority", "unknown")).lower(),
        "reason": _to_str(result.get("reason"), "No summary provided"),
    }


# ================================================================== #
#  Visual Reasoning — OpenAI GPT-4o Vision (paid)                    #
# ================================================================== #

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
            "Add it to your .env, or use analyze_site_ollama() instead."
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
#  Visual Reasoning — Ollama Local VLM (FREE, runs locally)          #
# ================================================================== #

async def analyze_site_ollama(
    image_bytes: bytes,
    site_name: str,
    category: str,
    model: str = "llava",
    ollama_host: str | None = None,
) -> dict[str, Any]:
    """Use a **local Ollama VLM** to analyze a site for humanitarian aid.

    Sends the satellite image with a natural language prompt and returns
    the model's plain-text analysis.  Runs entirely on your machine —
    no API key, no cost, no data leaves your network.

    Prerequisites:
        1. Install Ollama: https://ollama.com
        2. Pull a vision model:  ``ollama pull llava``
        3. Ollama server must be running (it auto-starts on install)

    Args:
        image_bytes: Raw satellite image (JPEG/PNG).
        site_name: Human-readable name of the site.
        category: OSM category tag (e.g. ``"amenity=school"``).
        model: Ollama model name (default ``"llava"``).
        ollama_host: Ollama API base URL (default ``http://localhost:11434``).

    Returns:
        A dict::

            {
                "analysis": str,   # Plain-text humanitarian aid analysis
            }
    """
    host = ollama_host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
    url = f"{host}/api/generate"

    # ── Pass 1: Full-image analysis (Steps 1-2) ─────────────────
    resized = _resize_for_vlm(image_bytes, max_dim=512)
    b64_image = base64.b64encode(resized).decode("utf-8")
    prompt = AID_ANALYSIS_PROMPT.format(site_name=site_name, category=category)

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [b64_image],
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 1024,
        },
    }

    try:
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
    except requests.ConnectionError:
        raise RuntimeError(
            f"Cannot connect to Ollama at {host}. "
            "Make sure Ollama is installed and running: https://ollama.com"
        )
    except requests.HTTPError as exc:
        if resp.status_code == 404:
            raise RuntimeError(
                f"Model '{model}' not found in Ollama. "
                f"Pull it first:  ollama pull {model}"
            )
        raise RuntimeError(f"Ollama request failed: {exc}")

    data = resp.json()
    analysis_text = data.get("response", "").strip()
    logger.info(
        "Ollama (%s) analyzed '%s' — %d chars response",
        model, site_name, len(analysis_text),
    )

    # ── Pass 2: Per-cell crop descriptions (concurrent) ────────
    cells = _crop_grid_cells(resized)

    import concurrent.futures
    cell_descriptions: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(_describe_cell_sync, cell_bytes, tag, model, host): tag
            for tag, cell_bytes in cells.items()
        }
        for future in concurrent.futures.as_completed(futures):
            tag, desc = future.result()
            cell_descriptions[tag] = desc

    # Append grid annotations to the analysis text
    grid_section = "\n\nGrid Annotations:"
    tag_order = ["NW", "N", "NE", "W", "C", "E", "SW", "S", "SE"]
    for tag in tag_order:
        if tag in cell_descriptions:
            grid_section += f"\n[{tag}] {cell_descriptions[tag]}"

    full_analysis = (analysis_text or "No analysis generated") + grid_section
    logger.info("Per-cell descriptions complete for '%s'", site_name)

    return {"analysis": full_analysis}

