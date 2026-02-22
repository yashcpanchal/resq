"""
Crisis query — identify cities that need humanitarian relief.

Uses the Layer 3 LLM (OpenRouter) with a focused prompt to produce
structured city-level crisis data from its training knowledge of
UN OCHA, ReliefWeb, WHO, UNHCR, WFP, IPC, and FEWS NET reports.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _current_date_str() -> str:
    return os.getenv("CRISIS_QUERY_DATE") or datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Prompt — direct, substance-focused, forces specificity
# ---------------------------------------------------------------------------

SYSTEM = (
    "You are a senior humanitarian analyst writing a relief assessment. "
    "Draw on UN OCHA situation reports, ReliefWeb, UNHCR, WHO, UNICEF, WFP, "
    "IPC/FEWS NET food security data, and ICRC/IOM displacement data. "
    "Be SPECIFIC: include numbers, dates, and concrete details from real reports. "
    "Every description must be actionable — an operations team should be able to "
    "read it and know what relief to deploy, where, and why."
)

PROMPT_TEMPLATE = """Today is {date}. Produce a humanitarian relief assessment for **{country}**.

For each major city or area with significant needs, provide:

1. **name** — the city or town name (if referencing a region/state/oblast, use its main city)
2. **needs** — a list of specific humanitarian needs, each with:
   - **sector**: Protection, Health, WASH, Food Security, Nutrition, Education, Shelter, Displacement, Conflict, Infrastructure, or Other
   - **severity**: "critical", "high", or "moderate"
   - **description**: 2-3 sentences with REAL DETAILS — how many people displaced, what diseases are spreading, what infrastructure is destroyed, what the IPC classification is, etc. NO vague filler like "the situation is dire" or "conditions are deteriorating." Every sentence must contain a fact.
   - **affected_population**: a number or estimate (e.g. "450,000 displaced", "~1.2M in IPC Phase 3+"), or null if unknown
   - **funding_gap**: underfunding data if known (e.g. "HRP 34% funded", "WASH cluster received $12M of $89M needed"), or null

REQUIREMENTS:
- 10-15+ cities/locations covering the FULL humanitarian picture
- Front-line cities, displacement hubs, disease hotspots, food crisis zones, infrastructure damage areas
- Population-level issues ONLY — no individual stories, no single-person anecdotes
- Use real statistics: IPC phases, displacement figures, attack counts, disease case numbers, funding percentages
- If you know the HRP funding status, include it in sources_note

Return ONLY valid JSON, no markdown fences:
{{"country": "{country}", "cities": [{{"name": "...", "needs": [{{"sector": "...", "severity": "...", "description": "...", "affected_population": "..." or null, "funding_gap": "..." or null}}]}}], "sources_note": "Key sources and overall stats"}}"""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_REGION_TO_CITY = {
    "donetska": "Donetsk", "donetsk oblast": "Donetsk",
    "khersonska": "Kherson", "kherson oblast": "Kherson",
    "kharkivska": "Kharkiv", "kharkiv oblast": "Kharkiv",
    "sumska": "Sumy", "sumy oblast": "Sumy",
    "zaporizka": "Zaporizhzhia", "zaporizhzhia oblast": "Zaporizhzhia",
    "luhanska": "Luhansk", "luhansk oblast": "Luhansk",
    "mykolaivska": "Mykolaiv", "mykolaiv oblast": "Mykolaiv",
    "dnipropetrovska": "Dnipro", "dnipropetrovsk oblast": "Dnipro",
    "south darfur": "Nyala", "north darfur": "El Fasher",
    "west darfur": "El Geneina", "al jazirah": "Wad Madani",
    "central darfur": "Zalingei", "east darfur": "Ed Daein",
    "blue nile": "Ed Damazin", "north kordofan": "El Obeid",
    "south kordofan": "Kadugli", "white nile": "Rabak",
}


def _clean_name(name: str) -> str:
    if not name:
        return ""
    n = name.strip()
    key = n.lower().replace(" oblast", "").strip()
    return _REGION_TO_CITY.get(key, _REGION_TO_CITY.get(n.lower(), n))


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s.lower() not in ("null", "none", "n/a", "") else None


def _parse_response(country: str, raw: str) -> dict[str, Any]:
    out: dict[str, Any] = {"country": country, "cities": [], "sources_note": ""}
    if not raw or not raw.strip():
        return out

    text = raw.strip()
    if "```" in text:
        text = re.sub(r"^.*?```(?:json)?\s*", "", text, flags=re.DOTALL)
        text = re.sub(r"\s*```.*$", "", text, flags=re.DOTALL).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("JSON parse failed on %d chars", len(text))
        out["cities"] = [{"name": "Parse error", "needs": [
            {"sector": "Other", "severity": "high", "description": raw[:800],
             "affected_population": None, "funding_gap": None}
        ]}]
        return out

    out["country"] = data.get("country", country)
    out["sources_note"] = data.get("sources_note", "")

    merged: dict[str, list[dict]] = {}
    for city in data.get("cities", []):
        if not isinstance(city, dict):
            continue
        name = _clean_name(city.get("name", ""))
        if not name:
            continue

        needs_raw = city.get("needs") or city.get("crises") or []
        needs_out = []
        for n in needs_raw:
            if not isinstance(n, dict):
                continue
            sector = (n.get("sector") or n.get("cluster") or "Other").strip()
            severity = (n.get("severity") or "high").strip().lower()
            if severity not in ("critical", "high", "moderate"):
                severity = "high"
            desc = (n.get("description") or n.get("explanation") or "").strip()
            if not desc:
                continue
            needs_out.append({
                "sector": sector,
                "severity": severity,
                "description": desc,
                "affected_population": _str_or_none(n.get("affected_population")),
                "funding_gap": _str_or_none(n.get("funding_gap")),
            })

        if needs_out:
            merged.setdefault(name, []).extend(needs_out)

    out["cities"] = [{"name": n, "needs": needs} for n, needs in merged.items()]

    for city in out["cities"]:
        city["crises"] = [
            {
                "type": nd["sector"],
                "type_label": nd["sector"],
                "cluster": nd["sector"],
                "explanation": nd["description"],
                "people_in_need": nd["affected_population"],
                "funding_coverage_note": nd["funding_gap"],
            }
            for nd in city["needs"]
        ]
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_crises_for_country(country: str) -> dict[str, Any]:
    """Return city-level humanitarian needs for a country.

    Uses the Layer 3 LLM with a substantive prompt to produce
    structured relief assessment data.
    """
    if not (country or "").strip():
        return {"country": "", "cities": [], "sources_note": ""}

    from modules.context_engine import generate_with_openrouter

    country = country.strip()
    date = _current_date_str()
    prompt = SYSTEM + "\n\n" + PROMPT_TEMPLATE.format(country=country, date=date)

    raw = await generate_with_openrouter(prompt, max_tokens=4000)
    return _parse_response(country, raw or "")
