"""
P1: ACAPS/FTS Data Engineering — Pipeline Module

Ingests humanitarian crisis data and calculates neglect scores.
Output target: data/neglect_scores.json
"""

from __future__ import annotations

from typing import Any


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
