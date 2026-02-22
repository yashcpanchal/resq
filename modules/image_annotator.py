"""
Image Annotator — clean, map-style visual overlays on satellite images.

Parses explicit grid-tagged annotations from LLM output (e.g.
``[NW] Rubble and debris``) and places marker pins at the correct
positions on the satellite image.

Colour coding:
    🟢 Green  — staging areas / open spaces
    🔵 Blue   — access routes / roads
    🔴 Red    — risk zones / debris / obstacles
    🟡 Amber  — structures / buildings
"""

from __future__ import annotations

import io
import re
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# ------------------------------------------------------------------ #
#  Grid positions — map tag → fractional image coordinate            #
# ------------------------------------------------------------------ #

GRID_POSITIONS: dict[str, tuple[float, float]] = {
    "NW": (0.17, 0.17),
    "N":  (0.50, 0.17),
    "NE": (0.83, 0.17),
    "W":  (0.17, 0.50),
    "C":  (0.50, 0.50),
    "E":  (0.83, 0.50),
    "SW": (0.17, 0.83),
    "S":  (0.50, 0.83),
    "SE": (0.83, 0.83),
}

# ------------------------------------------------------------------ #
#  Category classification                                           #
# ------------------------------------------------------------------ #

_CAT_KEYWORDS: dict[str, list[str]] = {
    "staging": [
        "staging", "open", "flat", "courtyard", "field", "parking",
        "landing", "helicopter", "clearing", "camp", "suitable",
    ],
    "access": [
        "road", "path", "entry", "access", "route", "highway",
        "street", "vehicle", "driveway", "entrance", "gate",
    ],
    "risk": [
        "rubble", "debris", "damage", "hazard", "obstacle", "flood",
        "collapse", "destroy", "ruin", "block", "crater", "risk",
        "unsafe", "unstable", "narrow",
    ],
    "structure": [
        "building", "school", "hospital", "structure", "house",
        "wall", "roof", "intact", "facility", "mosque", "church",
    ],
}

CAT_COLORS: dict[str, tuple[int, int, int]] = {
    "staging":   (46, 204, 113),
    "access":    (52, 152, 219),
    "risk":      (231, 76, 60),
    "structure": (241, 196, 15),
}

CAT_LABELS: dict[str, str] = {
    "staging": "Staging",
    "access":  "Access",
    "risk":    "Risk",
    "structure": "Structure",
}


def _classify(description: str) -> str:
    """Classify a description into a category by keyword matching."""
    desc_lower = description.lower()
    scores: dict[str, int] = {cat: 0 for cat in _CAT_KEYWORDS}
    for cat, keywords in _CAT_KEYWORDS.items():
        for kw in keywords:
            if kw in desc_lower:
                scores[cat] += 1
    best = max(scores, key=lambda c: scores[c])
    return best if scores[best] > 0 else "structure"


# ------------------------------------------------------------------ #
#  Parse grid-tagged annotations from LLM output                    #
# ------------------------------------------------------------------ #

def _parse_grid_annotations(text: str) -> list[dict]:
    """Extract ``[TAG] description`` lines from the LLM output.

    Returns a list of findings with position, label, category, and color.
    """
    # Match lines like: [NW] Rubble and debris
    pattern = re.compile(
        r'\[(' + '|'.join(GRID_POSITIONS.keys()) + r')\]\s*(.+)',
        re.IGNORECASE,
    )

    findings: list[dict] = []
    seen_tags: set[str] = set()

    for match in pattern.finditer(text):
        tag = match.group(1).upper()
        description = match.group(2).strip().rstrip('.')

        if tag in seen_tags:
            continue
        seen_tags.add(tag)

        # Trim description for label
        label = description
        if len(label) > 32:
            label = label[:30] + "…"

        cat = _classify(description)
        x, y = GRID_POSITIONS[tag]

        findings.append({
            "tag": tag,
            "label": label,
            "category": cat,
            "color": CAT_COLORS[cat],
            "x": x,
            "y": y,
        })

    return findings


# ------------------------------------------------------------------ #
#  Font loader                                                       #
# ------------------------------------------------------------------ #

def _load_fonts() -> tuple:
    """Load system fonts with fallback."""
    paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in paths:
        try:
            return (
                ImageFont.truetype(path, 11),
                ImageFont.truetype(path, 13),
                ImageFont.truetype(path, 15),
            )
        except (OSError, IOError):
            continue
    default = ImageFont.load_default()
    return default, default, default


# ------------------------------------------------------------------ #
#  Drawing primitives                                                #
# ------------------------------------------------------------------ #

def _draw_marker(
    draw: ImageDraw.ImageDraw,
    x: int, y: int,
    color: tuple[int, int, int],
    size: int = 7,
):
    """Clean map-pin marker."""
    # Drop shadow
    draw.ellipse(
        [x - size, y - size + 2, x + size, y + size + 2],
        fill=(0, 0, 0, 60),
    )
    # Outer ring
    draw.ellipse(
        [x - size, y - size, x + size, y + size],
        fill=color, outline=(255, 255, 255), width=2,
    )
    # Inner dot
    dot = max(1, size // 3)
    draw.ellipse(
        [x - dot, y - dot, x + dot, y + dot],
        fill=(255, 255, 255, 200),
    )


def _draw_label(
    draw: ImageDraw.ImageDraw,
    pin_x: int, pin_y: int,
    tag: str, label: str,
    color: tuple[int, int, int],
    font,
    img_w: int, img_h: int,
    occupied: list,
):
    """Draw a label badge connected to its marker, avoiding overlaps."""
    display = f"{tag}: {label}"
    bbox = font.getbbox(display)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    px, py = 6, 3
    box_w = tw + px * 2
    box_h = th + py * 2 + 2

    # Try many offsets to find one that doesn't overlap
    offsets = [
        (16, -22), (16, 16), (-16 - box_w, -22), (-16 - box_w, 16),
        (16, -40), (16, 34), (-16 - box_w, -40), (-16 - box_w, 34),
        (30, -10), (-30 - box_w, -10), (30, 4), (-30 - box_w, 4),
    ]

    best_lx, best_ly = pin_x + offsets[0][0], pin_y + offsets[0][1]
    for ox, oy in offsets:
        lx = max(4, min(img_w - box_w - 4, pin_x + ox))
        ly = max(30, min(img_h - box_h - 24, pin_y + oy))

        # Check for overlap with already placed labels
        candidate = (lx, ly, lx + box_w, ly + box_h)
        overlap = False
        for placed in occupied:
            if (candidate[0] < placed[2] + 4 and candidate[2] > placed[0] - 4 and
                    candidate[1] < placed[3] + 2 and candidate[3] > placed[1] - 2):
                overlap = True
                break
        if not overlap and 30 < ly < img_h - box_h - 24:
            best_lx, best_ly = lx, ly
            break
        if not overlap:
            best_lx, best_ly = lx, ly

    x0, y0 = best_lx, best_ly
    x1, y1 = x0 + box_w, y0 + box_h
    occupied.append((x0, y0, x1, y1))

    # Connector line
    # Connect to nearest edge of label box
    mid_y = (y0 + y1) // 2
    line_x = x0 if x0 > pin_x else x1
    draw.line(
        [(pin_x, pin_y), (line_x, mid_y)],
        fill=(255, 255, 255, 120), width=1,
    )

    # Background
    draw.rectangle([x0, y0, x1, y1], fill=(10, 10, 15, 215))
    # Top accent
    draw.rectangle([x0, y0, x1, y0 + 2], fill=color)
    # Text
    draw.text((x0 + px, y0 + py + 2), display,
              fill=(255, 255, 255), font=font)


# ------------------------------------------------------------------ #
#  Main annotator                                                    #
# ------------------------------------------------------------------ #

def annotate_image(
    image_bytes: bytes,
    analysis_text: str,
    site_name: str,
) -> bytes:
    """Draw clean, map-style annotations on a satellite image.

    Parses explicit ``[TAG] description`` lines from the LLM output
    for deterministic, correctly-positioned annotations.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = img.size
    font_sm, font_md, font_lg = _load_fonts()

    # Parse grid-tagged annotations
    findings = _parse_grid_annotations(analysis_text)

    # Vignette
    vig = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    vig_draw = ImageDraw.Draw(vig)
    border = min(w, h) // 5
    for i in range(border):
        alpha = int(45 * (1 - i / border) ** 2.5)
        if alpha < 1:
            break
        vig_draw.rectangle([i, i, w - 1 - i, h - 1 - i],
                           outline=(0, 0, 0, alpha))
    img = Image.alpha_composite(img, vig)

    # Overlay
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # ── Title bar ────────────────────────────────────────────────
    title_h = 28
    for y in range(title_h):
        alpha = int(220 * (1 - y / title_h) ** 1.8)
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
    title = site_name[:52]
    draw.text((w // 2 + 1, title_h // 2 + 1), title,
              fill=(0, 0, 0), font=font_lg, anchor="mm")
    draw.text((w // 2, title_h // 2), title,
              fill=(255, 255, 255), font=font_lg, anchor="mm")

    # ── Compass (top-right) ──────────────────────────────────────
    cx_c, cy_c = w - 20, title_h + 16
    draw.ellipse([cx_c - 11, cy_c - 11, cx_c + 11, cy_c + 11],
                 fill=(0, 0, 0, 180), outline=(255, 255, 255, 80))
    draw.text((cx_c, cy_c), "N", fill=(231, 76, 60),
              font=font_sm, anchor="mm")
    draw.polygon(
        [(cx_c, cy_c - 11), (cx_c - 3, cy_c - 7), (cx_c + 3, cy_c - 7)],
        fill=(231, 76, 60),
    )

    # ── Markers + labels ─────────────────────────────────────────
    occupied: list[tuple[int, int, int, int]] = []  # track placed label rects
    for finding in findings:
        px = int(finding["x"] * w)
        py = int(finding["y"] * h)
        # Clamp within drawable area
        px = max(14, min(w - 14, px))
        py = max(title_h + 14, min(h - 36, py))

        _draw_marker(draw, px, py, finding["color"])
        _draw_label(draw, px, py, finding["tag"], finding["label"],
                    finding["color"], font_sm, w, h, occupied)

    # ── Legend bar ───────────────────────────────────────────────
    active_cats = {f["category"] for f in findings}
    if active_cats:
        legend_h = 22
        for y in range(legend_h):
            yy = h - legend_h + y
            alpha = int(210 * (y / legend_h) ** 1.3)
            draw.line([(0, yy), (w, yy)], fill=(0, 0, 0, alpha))

        x_pos = 8
        for cat_name in ["staging", "access", "risk", "structure"]:
            if cat_name not in active_cats:
                continue
            r, g, b = CAT_COLORS[cat_name]
            yc = h - legend_h // 2
            draw.ellipse([x_pos, yc - 3, x_pos + 6, yc + 3],
                         fill=(r, g, b))
            draw.text((x_pos + 10, yc), CAT_LABELS[cat_name],
                      fill=(r, g, b), font=font_sm, anchor="lm")
            x_pos += 10 + len(CAT_LABELS[cat_name]) * 7 + 14

    # ── Composite + output ───────────────────────────────────────
    img = Image.alpha_composite(img, overlay)
    img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=93)
    return buf.getvalue()
