"""
P2: Actian RAG Logic — Vector Module

Performs retrieval-augmented generation against Actian VectorDB
to produce safety context reports for a given location.
"""

from __future__ import annotations


async def get_safety_report(lat: float, lng: float) -> str:
    """Return a textual safety summary for the given coordinates.

    Args:
        lat: Latitude of the crisis zone.
        lng: Longitude of the crisis zone.

    Returns:
        A text summary describing safety conditions.
    """
    from modules.context_engine import get_safety_report as _engine_report

    return await _engine_report(lat, lng)
