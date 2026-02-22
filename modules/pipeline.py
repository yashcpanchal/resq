"""
P1: ACAPS/FTS Data Engineering — Pipeline Module

Ingests humanitarian crisis data and calculates neglect scores.
Output target: data/neglect_scores.json
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
import csv
import os
from collections import defaultdict
from typing import Any

# Path to the FTS funding CSV relative to the project root.
_CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "funding",
    "fts_requirements_funding_globalcluster_global.csv",
)


def calculate_funding_scores() -> dict[str, float]:
    """Calculate a funding score for each country.

    Score = total funding received / total funding required.
    Uses the columns ``funding`` (received) and ``requirements`` (needed)
    from the FTS global-cluster CSV.

    Returns:
        A dict mapping ISO-3 country code to its funding score,
        e.g. ``{"AFG": 0.4231, "BDI": 0.5012, ...}``.
    """
    totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {"funding": 0.0, "requirements": 0.0}
    )

    with open(_CSV_PATH, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            # Skip the HXL tag row (values start with '#')
            country_code = row.get("countryCode", "")
            if not country_code or country_code.startswith("#"):
                continue

            funding_str = row.get("funding", "").strip()
            requirements_str = row.get("requirements", "").strip()

            funding = float(funding_str) if funding_str else 0.0
            requirements = float(requirements_str) if requirements_str else 0.0

            totals[country_code]["funding"] += funding
            totals[country_code]["requirements"] += requirements

    scores: dict[str, float] = {}
    for country_code, vals in totals.items():
        if vals["requirements"] > 0:
            scores[country_code] = round(
                vals["funding"] / vals["requirements"], 4
            )
        else:
            scores[country_code] = 0.0

    return scores


async def get_neglect_scores() -> list[dict[str, Any]]:
    """Fetch and compute neglect scores for global crises.

    Returns a list of dicts matching the data contract:
        {
            "crisis_id": str,
            "country": str,
            "coordinates": {"lat": float, "lng": float},
            "neglect_score": float,
            "severity": int,
            "funding_gap_usd": int,
        }
    """
    # TODO: Implement Databricks / PySpark ingestion
    return []
