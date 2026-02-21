"""
Layer 3 — Context Engine (Safety Intelligence via RAG)

Pipeline: GDACS + HDX → chunk → embed (OpenRouter) → store (Actian VectorAI) → search.

Actian VectorAI DB integration uses the ``cortex`` gRPC Python client
(not SQL / pyodbc).  Docker: ``docker compose up -d`` in actian-beta/.
The DB runs on ``localhost:50051``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import base64
import re
from typing import Any
from xml.etree import ElementTree as ET

import httpx
import tiktoken

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GDACS_RSS_URL = "https://www.gdacs.org/xml/rss.xml"
HDX_CKAN_URL = "https://data.humdata.org/api/3/action/package_search"
HDX_HAPI_URL = "https://hapi.humdata.org/api/v2"
STATE_DEPT_ADVISORIES_URL = "https://cadataapi.state.gov/api/TravelAdvisories"
STATE_DEPT_COUNTRY_URL = "https://cadataapi.state.gov/api/CountryTravelInformation"
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_EMBED_MODEL = os.getenv("OPENROUTER_EMBED_MODEL", "openai/text-embedding-3-large")
OPENROUTER_CHAT_MODEL = os.getenv("OPENROUTER_CHAT_MODEL", "arcee-ai/trinity-large-preview:free")
EMBEDDING_DIM = 3072
CHUNK_MAX_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50

# Actian VectorAI config
ACTIAN_SERVER = os.getenv("ACTIAN_SERVER", "localhost:50051")
COLLECTION_NAME = "safety_intelligence"

# ---------------------------------------------------------------------------
# Country lookup (async via Nominatim HTTP API — no extra dependency)
# ---------------------------------------------------------------------------

NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"


async def _country_to_coords(country: str) -> tuple[float, float] | None:
    """Forward-geocode country name to (lat, lng) via Nominatim. Returns None if not found."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                NOMINATIM_SEARCH,
                params={"q": country, "format": "json", "limit": 5},
                headers={"User-Agent": "ResQ-Capital/0.1"},
            )
            resp.raise_for_status()
            results = resp.json()
            for r in results:
                if r.get("type") == "country" or "country" in (r.get("type") or ""):
                    return (float(r["lat"]), float(r["lon"]))
            if results:
                return (float(results[0]["lat"]), float(results[0]["lon"]))
        return None
    except Exception as exc:
        logger.error("Forward geocoding failed for %s: %s", country, exc)
        return None


async def _coords_to_location(lat: float, lng: float) -> dict[str, str]:
    """Reverse-geocode (lat, lng) to country, city, and region via Nominatim.

    Returns {"country": ..., "city": ..., "region": ...}. Values default to "".
    """
    loc: dict[str, str] = {"country": "", "city": "", "region": ""}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                NOMINATIM_REVERSE,
                params={"lat": lat, "lon": lng, "format": "jsonv2", "accept-language": "en",
                        "zoom": 10},
                headers={"User-Agent": "ResQ-Capital/0.1"},
            )
            resp.raise_for_status()
            data = resp.json()
            addr = data.get("address", {})
            loc["country"] = addr.get("country", "")
            loc["city"] = (
                addr.get("city", "")
                or addr.get("town", "")
                or addr.get("village", "")
                or addr.get("municipality", "")
            )
            loc["region"] = addr.get("state", "") or addr.get("region", "")
            logger.info(
                "Reverse Geocode: (%s, %s) -> %s / %s / %s",
                lat, lng, loc["country"], loc["region"], loc["city"],
            )
    except Exception as exc:
        logger.error("Reverse geocoding failed: %s", exc)
    return loc


async def _coords_to_country(lat: float, lng: float) -> str:
    """Reverse-geocode (lat, lng) to a country name."""
    loc = await _coords_to_location(lat, lng)
    return loc["country"] or "Unknown"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 1 — DATA INGESTION (GDACS + HDX)
# ═══════════════════════════════════════════════════════════════════════════

GDACS_NS = {"gdacs": "http://www.gdacs.org"}

_EVENT_TYPE_LABELS = {
    "EQ": "Earthquake",
    "TC": "Tropical Cyclone",
    "FL": "Flood",
    "VO": "Volcano",
    "DR": "Drought",
    "WF": "Wild Fire",
    "TS": "Tsunami",
}


_ALERT_PRIORITY = {"Red": 3, "Orange": 2, "Green": 1}


async def fetch_gdacs_alerts(country: str, min_level: str = "Orange") -> list[dict[str, Any]]:
    """Fetch disaster alerts from GDACS RSS, filtered by country and severity.

    Only returns alerts at *min_level* or above (Orange/Red by default).
    """
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                GDACS_RSS_URL,
                headers={"User-Agent": "ResQ-Capital/0.1"},
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("GDACS RSS unavailable: %s", exc)
        return []

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        logger.error("Failed to parse GDACS RSS XML: %s", exc)
        return []

    min_pri = _ALERT_PRIORITY.get(min_level, 2)
    country_lower = country.lower()
    alerts: list[dict[str, Any]] = []

    for item in root.findall(".//item"):
        gdacs_country = item.findtext("gdacs:country", default="", namespaces=GDACS_NS)
        if not gdacs_country or country_lower not in gdacs_country.lower():
            continue

        alert_level = item.findtext("gdacs:alertlevel", default="", namespaces=GDACS_NS)
        if _ALERT_PRIORITY.get(alert_level, 0) < min_pri:
            continue

        title = item.findtext("title", default="")
        description = item.findtext("description", default="")
        description_clean = re.sub(r"<[^>]+>", " ", description)
        description_clean = re.sub(r"\s+", " ", description_clean).strip()

        event_type_code = item.findtext("gdacs:eventtype", default="", namespaces=GDACS_NS)
        event_type = _EVENT_TYPE_LABELS.get(event_type_code, event_type_code)
        severity = item.findtext("gdacs:severity", default="", namespaces=GDACS_NS)
        pub_date = item.findtext("pubDate", default="")

        body = (
            f"GDACS Disaster Alert [{alert_level.upper()}] — {event_type} in {gdacs_country}. "
            f"Severity: {severity}. {title}. {description_clean}"
        )

        alerts.append({
            "title": title,
            "body": body,
            "source": "GDACS",
            "date": pub_date,
            "country": country,
            "alert_level": alert_level,
            "event_type": event_type,
        })

    logger.info("GDACS: found %d alerts (>=%s) for %s", len(alerts), min_level, country)
    return alerts


# ---------------------------------------------------------------------------
# Country-code mappings (from modules.country_codes)
# ---------------------------------------------------------------------------

from modules.country_codes import build_country_maps, list_all_countries

_COUNTRY_TO_ISO3, _COUNTRY_TO_STATE_DEPT = build_country_maps()

_HAPI_APP_ID = base64.b64encode(b"ResQ-Capital:resq@resqcapital.org").decode()


def _country_to_iso3(country: str) -> str | None:
    return _COUNTRY_TO_ISO3.get(country.lower().strip())


def _country_to_state_dept_code(country: str) -> str | None:
    return _COUNTRY_TO_STATE_DEPT.get(country.lower().strip())


async def fetch_hdx_reports(country: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search HDX for humanitarian reports strictly filtered to *country*.

    Uses the HDX CKAN ``fq=groups:{iso3}`` facet to guarantee results
    are tagged for the correct country, not just keyword matches.
    """
    iso3 = _country_to_iso3(country)
    if not iso3:
        logger.warning("No ISO3 code for '%s' — HDX results may be inaccurate", country)

    queries = [
        "conflict security",
        "humanitarian situation",
        "displacement protection",
        "food insecurity",
    ]

    all_reports: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    async with httpx.AsyncClient(timeout=15) as client:
        for q in queries:
            params: dict[str, Any] = {
                "q": q,
                "rows": limit,
                "sort": "metadata_modified desc",
            }
            if iso3:
                params["fq"] = f"groups:{iso3}"

            try:
                resp = await client.get(
                    HDX_CKAN_URL, params=params,
                    headers={"User-Agent": "ResQ-Capital/0.1"},
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as exc:
                logger.warning("HDX query '%s' failed: %s", q, exc)
                continue

            for pkg in data.get("result", {}).get("results", []):
                pkg_id = pkg.get("id", "")
                if pkg_id in seen_ids:
                    continue
                seen_ids.add(pkg_id)

                title = pkg.get("title", "")
                notes = pkg.get("notes", "")
                notes_clean = re.sub(r"<[^>]+>", " ", notes)
                notes_clean = re.sub(r"\s+", " ", notes_clean).strip()

                if not notes_clean or len(notes_clean) < 50:
                    continue

                org = pkg.get("organization", {})
                source_name = org.get("title", "HDX") if org else "HDX"
                modified = pkg.get("metadata_modified", "")

                all_reports.append({
                    "title": title,
                    "body": f"[{country}] {title} (Source: {source_name}). {notes_clean}",
                    "source": source_name,
                    "date": modified,
                    "country": country,
                })

    logger.info("HDX: found %d reports for %s (iso3=%s)", len(all_reports), country, iso3)
    return all_reports


# ---------------------------------------------------------------------------
# 1c. US State Dept Travel Advisories + Country Info
# ---------------------------------------------------------------------------

async def fetch_travel_advisory(country: str) -> list[dict[str, Any]]:
    """Fetch US State Department travel advisory and country safety info."""
    code = _country_to_state_dept_code(country)
    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=15) as client:
        # Travel advisory (level + summary)
        try:
            resp = await client.get(
                STATE_DEPT_ADVISORIES_URL,
                headers={"User-Agent": "ResQ-Capital/0.1"},
            )
            resp.raise_for_status()
            for adv in resp.json():
                cats = adv.get("Category", [])
                if code and code in cats:
                    title = adv.get("Title", "")
                    summary = re.sub(r"<[^>]+>", " ", adv.get("Summary", ""))
                    summary = re.sub(r"\s+", " ", summary).strip()
                    body = f"US State Department Travel Advisory: {title}. {summary}"
                    results.append({
                        "title": title,
                        "body": body,
                        "source": "US State Dept",
                        "date": adv.get("DatePublished", ""),
                        "country": country,
                    })
                    break
        except httpx.HTTPError as exc:
            logger.warning("State Dept advisories failed: %s", exc)

        # Detailed country travel info (safety, health, transportation)
        if code:
            try:
                resp = await client.get(
                    f"{STATE_DEPT_COUNTRY_URL}/{code}",
                    headers={"User-Agent": "ResQ-Capital/0.1"},
                )
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list) and data:
                    data = data[0]
                if isinstance(data, dict):
                    for field in [
                        "safety_and_security", "local_laws_and_special_circumstances",
                        "health", "travel_and_transportation",
                    ]:
                        val = data.get(field, "")
                        if not val:
                            continue
                        clean = re.sub(r"<[^>]+>", " ", str(val))
                        clean = re.sub(r"\s+", " ", clean).strip()
                        if len(clean) < 50:
                            continue
                        label = field.replace("_", " ").title()
                        results.append({
                            "title": f"{country} — {label}",
                            "body": f"[{country}] US State Dept — {label}: {clean}",
                            "source": "US State Dept",
                            "date": "",
                            "country": country,
                        })
            except httpx.HTTPError as exc:
                logger.warning("State Dept country info for %s failed: %s", code, exc)

    logger.info("State Dept: found %d items for %s (code=%s)", len(results), country, code)
    return results


# ---------------------------------------------------------------------------
# 1d. HDX HAPI — Structured humanitarian data (conflict events, food security)
# ---------------------------------------------------------------------------

async def fetch_hapi_data(country: str) -> list[dict[str, Any]]:
    """Fetch structured conflict events and food security data from HDX HAPI."""
    iso3 = _country_to_iso3(country)
    if not iso3:
        return []

    iso3_upper = iso3.upper()
    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=20) as client:
        # Conflict events (recent, aggregated by admin1)
        try:
            resp = await client.get(
                f"{HDX_HAPI_URL}/coordination-context/conflict-events",
                params={
                    "app_identifier": _HAPI_APP_ID,
                    "location_code": iso3_upper,
                    "admin_level": "1",
                    "limit": "100",
                },
                headers={"User-Agent": "ResQ-Capital/0.1"},
            )
            resp.raise_for_status()
            rows = resp.json().get("data", [])

            region_stats: dict[str, dict[str, int]] = {}
            for r in rows:
                region = r.get("admin1_name") or "National"
                etype = r.get("event_type", "unknown")
                events = r.get("events", 0) or 0
                fatalities = r.get("fatalities", 0) or 0
                if events == 0 and fatalities == 0:
                    continue
                key = region
                if key not in region_stats:
                    region_stats[key] = {"events": 0, "fatalities": 0}
                region_stats[key]["events"] += events
                region_stats[key]["fatalities"] += fatalities

            if region_stats:
                top = sorted(region_stats.items(), key=lambda x: x[1]["fatalities"], reverse=True)[:10]
                lines = [f"  - {reg}: {s['events']} conflict events, {s['fatalities']} fatalities"
                         for reg, s in top]
                body = (
                    f"[{country}] HDX HAPI Conflict Events Summary (ACLED data).\n"
                    f"Regions with highest conflict activity:\n" + "\n".join(lines)
                )
                results.append({
                    "title": f"{country} — Conflict Events (ACLED via HAPI)",
                    "body": body,
                    "source": "HDX HAPI / ACLED",
                    "date": "",
                    "country": country,
                })
        except httpx.HTTPError as exc:
            logger.warning("HAPI conflict-events for %s failed: %s", iso3_upper, exc)

        # Food security (IPC phases)
        try:
            resp = await client.get(
                f"{HDX_HAPI_URL}/food-security-nutrition-poverty/food-security",
                params={
                    "app_identifier": _HAPI_APP_ID,
                    "location_code": iso3_upper,
                    "admin_level": "1",
                    "limit": "200",
                },
                headers={"User-Agent": "ResQ-Capital/0.1"},
            )
            resp.raise_for_status()
            rows = resp.json().get("data", [])

            crisis_regions: list[str] = []
            for r in rows:
                phase_raw = str(r.get("ipc_phase", ""))
                pop = r.get("population_in_phase", 0) or 0
                region = r.get("admin1_name") or "National"
                phase_num = int(re.sub(r"[^0-9]", "", phase_raw) or "0")
                if phase_num >= 3 and pop > 0:
                    crisis_regions.append(
                        f"  - {region}: IPC Phase {phase_raw}, {pop:,} people affected"
                    )

            if crisis_regions:
                seen = set()
                unique = []
                for line in crisis_regions:
                    if line not in seen:
                        seen.add(line)
                        unique.append(line)
                body = (
                    f"[{country}] HDX HAPI Food Security (IPC Classification).\n"
                    f"Regions at Crisis level or worse (IPC Phase 3+):\n"
                    + "\n".join(unique[:15])
                )
                results.append({
                    "title": f"{country} — Food Insecurity (IPC via HAPI)",
                    "body": body,
                    "source": "HDX HAPI / IPC",
                    "date": "",
                    "country": country,
                })
        except httpx.HTTPError as exc:
            logger.warning("HAPI food-security for %s failed: %s", iso3_upper, exc)

    logger.info("HAPI: found %d items for %s", len(results), country)
    return results


# ---------------------------------------------------------------------------
# 1e. Google News RSS — Breaking news and current events
# ---------------------------------------------------------------------------

async def fetch_news(country: str, max_articles: int = 10) -> list[dict[str, Any]]:
    """Fetch recent news headlines relevant to safety/security via Google News RSS.

    Uses multiple targeted queries to get diverse coverage (conflict, disaster,
    health emergency, political unrest).
    """
    queries = [
        f'"{country}" conflict OR violence OR attack OR security when:7d',
        f'"{country}" crisis OR emergency OR disaster OR humanitarian when:7d',
        f'"{country}" protest OR unrest OR coup OR political when:7d',
    ]

    articles: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    async with httpx.AsyncClient(timeout=15) as client:
        for q in queries:
            try:
                resp = await client.get(
                    GOOGLE_NEWS_RSS_URL,
                    params={"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"},
                    headers={"User-Agent": "ResQ-Capital/0.1"},
                )
                resp.raise_for_status()

                root = ET.fromstring(resp.text)
                for item in root.findall(".//item"):
                    title = item.findtext("title", "").strip()
                    if not title or title in seen_titles:
                        continue

                    country_lower = country.lower()
                    if country_lower not in title.lower():
                        desc = item.findtext("description", "").lower()
                        if country_lower not in desc:
                            continue

                    seen_titles.add(title)
                    pub_date = item.findtext("pubDate", "")
                    source = item.findtext("source", "")
                    link = item.findtext("link", "")
                    desc_raw = item.findtext("description", "")
                    desc_clean = re.sub(r"<[^>]+>", " ", desc_raw)
                    desc_clean = re.sub(r"\s+", " ", desc_clean).strip()

                    body = (
                        f"[BREAKING NEWS — {country}] {title} "
                        f"(Source: {source}, {pub_date}). "
                        f"{desc_clean}"
                    )

                    articles.append({
                        "title": title,
                        "body": body,
                        "source": source or "Google News",
                        "date": pub_date,
                        "country": country,
                    })

                    if len(articles) >= max_articles:
                        break
            except (httpx.HTTPError, ET.ParseError) as exc:
                logger.warning("Google News query failed: %s", exc)
                continue

            if len(articles) >= max_articles:
                break

    logger.info("Google News: found %d articles for %s", len(articles), country)
    return articles


async def fetch_city_news(city: str, country: str, max_articles: int = 5) -> list[dict[str, Any]]:
    """Fetch news specifically about a city/region within a country."""
    if not city:
        return []
    queries = [
        f'"{city}" "{country}" conflict OR violence OR attack OR security when:7d',
        f'"{city}" "{country}" crisis OR emergency OR disaster when:7d',
    ]

    articles: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    async with httpx.AsyncClient(timeout=15) as client:
        for q in queries:
            try:
                resp = await client.get(
                    GOOGLE_NEWS_RSS_URL,
                    params={"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"},
                    headers={"User-Agent": "ResQ-Capital/0.1"},
                )
                resp.raise_for_status()
                root = ET.fromstring(resp.text)
                for item in root.findall(".//item"):
                    title = (item.findtext("title", "") or "").strip()
                    if not title or title in seen_titles:
                        continue
                    seen_titles.add(title)
                    pub_date = item.findtext("pubDate", "")
                    source = item.findtext("source", "")
                    desc_raw = item.findtext("description", "")
                    desc_clean = re.sub(r"<[^>]+>", " ", desc_raw)
                    desc_clean = re.sub(r"\s+", " ", desc_clean).strip()

                    articles.append({
                        "title": title,
                        "body": (
                            f"[LOCAL NEWS — {city}, {country}] {title} "
                            f"(Source: {source}, {pub_date}). {desc_clean}"
                        ),
                        "source": source or "Google News",
                        "date": pub_date,
                        "country": country,
                    })
                    if len(articles) >= max_articles:
                        break
            except (httpx.HTTPError, ET.ParseError) as exc:
                logger.warning("City news query failed for %s: %s", city, exc)
            if len(articles) >= max_articles:
                break

    logger.info("City News: found %d articles for %s, %s", len(articles), city, country)
    return articles


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance in km between two coordinates."""
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def fetch_gdacs_nearby(lat: float, lng: float, radius_km: float = 500) -> list[dict[str, Any]]:
    """Fetch GDACS alerts near (lat, lng) regardless of country — proximity-based."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(GDACS_RSS_URL, headers={"User-Agent": "ResQ-Capital/0.1"})
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("GDACS RSS unavailable: %s", exc)
        return []

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return []

    nearby: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        try:
            geo_lat = float(item.findtext("{http://www.w3.org/2003/01/geo/wgs84_pos#}lat", "0"))
            geo_lng = float(item.findtext("{http://www.w3.org/2003/01/geo/wgs84_pos#}long", "0"))
        except (ValueError, TypeError):
            continue
        if geo_lat == 0.0 and geo_lng == 0.0:
            continue
        dist = _haversine_km(lat, lng, geo_lat, geo_lng)
        if dist > radius_km:
            continue

        alert_level = item.findtext("gdacs:alertlevel", default="", namespaces=GDACS_NS)
        title = item.findtext("title", default="")
        description = re.sub(r"<[^>]+>", " ", item.findtext("description", ""))
        description = re.sub(r"\s+", " ", description).strip()
        event_type_code = item.findtext("gdacs:eventtype", default="", namespaces=GDACS_NS)
        event_type = _EVENT_TYPE_LABELS.get(event_type_code, event_type_code)
        severity = item.findtext("gdacs:severity", default="", namespaces=GDACS_NS)

        nearby.append({
            "title": title,
            "body": (
                f"[NEARBY DISASTER — {int(dist)}km away] GDACS [{alert_level.upper()}] "
                f"{event_type}. Severity: {severity}. {title}. {description}"
            ),
            "source": "GDACS",
            "date": item.findtext("pubDate", ""),
            "distance_km": dist,
        })

    nearby.sort(key=lambda x: x.get("distance_km", 9999))
    logger.info("GDACS nearby: %d alerts within %dkm of (%s, %s)", len(nearby), radius_km, lat, lng)
    return nearby[:5]


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 2 — TEXT CHUNKING
# ═══════════════════════════════════════════════════════════════════════════

_enc: tiktoken.Encoding | None = None


def _get_encoder() -> tiktoken.Encoding:
    global _enc
    if _enc is None:
        _enc = tiktoken.encoding_for_model("gpt-4o-mini")
    return _enc


def chunk_text(
    text: str,
    max_tokens: int = CHUNK_MAX_TOKENS,
    overlap: int = CHUNK_OVERLAP_TOKENS,
) -> list[str]:
    """Split *text* into chunks of roughly *max_tokens* tokens with overlap."""
    enc = _get_encoder()
    tokens = enc.encode(text)
    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = start + max_tokens
        chunk_tokens = tokens[start:end]
        chunks.append(enc.decode(chunk_tokens))
        start += max_tokens - overlap
    return chunks


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 3 — EMBEDDINGS (OpenRouter)
# ═══════════════════════════════════════════════════════════════════════════


def _openrouter_api_key() -> str | None:
    return os.getenv("OPENROUTER_API_KEY") or None


async def embed_text(text: str) -> list[float]:
    """Return the embedding vector for *text* via OpenRouter."""
    key = _openrouter_api_key()
    if not key:
        logger.warning("OPENROUTER_API_KEY not set — returning zero vector")
        return [0.0] * EMBEDDING_DIM
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{OPENROUTER_API_BASE}/embeddings",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": OPENROUTER_EMBED_MODEL, "input": text},
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch embed multiple texts via OpenRouter. Retries on 429."""
    key = _openrouter_api_key()
    if not key:
        logger.warning("OPENROUTER_API_KEY not set — returning zero vectors")
        return [[0.0] * EMBEDDING_DIM for _ in texts]
    delays = [30, 60, 90]
    async with httpx.AsyncClient(timeout=120) as client:
        for attempt, delay in enumerate(delays):
            try:
                resp = await client.post(
                    f"{OPENROUTER_API_BASE}/embeddings",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": OPENROUTER_EMBED_MODEL, "input": texts},
                )
                resp.raise_for_status()
                return [item["embedding"] for item in resp.json()["data"]]
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429 and attempt < len(delays) - 1:
                    logger.warning(
                        "OpenRouter embedding 429 — waiting %ds then retry (attempt %d)",
                        delay, attempt + 1,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise
    return [[0.0] * EMBEDDING_DIM for _ in texts]


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 4 — ACTIAN VectorAI DB (gRPC via cortex client)
# ═══════════════════════════════════════════════════════════════════════════

def _get_cortex_client():
    """Return a sync CortexClient connected to Actian VectorAI, or None.

    IMPORTANT: The caller must close via ``client.__exit__(None, None, None)``
    or use it as a context manager.
    """
    try:
        from cortex import CortexClient
        client = CortexClient(ACTIAN_SERVER)
        client.__enter__()  # required to initialize the gRPC channel
        client.health_check()
        return client
    except Exception as exc:
        logger.warning("Actian VectorAI unavailable at %s: %s", ACTIAN_SERVER, exc)
        return None


async def _get_async_cortex_client():
    """Return an AsyncCortexClient connected to Actian VectorAI, or None."""
    try:
        from cortex import AsyncCortexClient
        client = AsyncCortexClient(ACTIAN_SERVER)
        await client.__aenter__()
        await client.health_check()
        return client
    except Exception as exc:
        logger.warning("Actian VectorAI unavailable at %s: %s", ACTIAN_SERVER, exc)
        return None


# ---------------------------------------------------------------------------
# 4a. init_db() — Create the safety_intelligence collection
# ---------------------------------------------------------------------------

def init_db(client=None) -> bool:
    """Create the ``safety_intelligence`` collection if it doesn't exist.

    Collection schema:
        - dimension: 3072 (openai/text-embedding-3-large via OpenRouter)
        - distance_metric: COSINE
        - payload fields: country (str), content (str)

    Returns True on success, False if unavailable.
    """
    close_after = False
    if client is None:
        client = _get_cortex_client()
        close_after = True
    if client is None:
        return False

    try:
        from cortex import DistanceMetric

        if not client.has_collection(COLLECTION_NAME):
            client.create_collection(
                name=COLLECTION_NAME,
                dimension=EMBEDDING_DIM,
                distance_metric=DistanceMetric.COSINE,
            )
            logger.info("Created collection '%s' (dim=%d, COSINE)", COLLECTION_NAME, EMBEDDING_DIM)
        else:
            logger.info("Collection '%s' already exists", COLLECTION_NAME)
        return True
    except Exception as exc:
        logger.error("init_db failed: %s", exc)
        return False
    finally:
        if close_after:
            client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# 4b. ingest_intelligence() — Embed + Store in Actian VectorAI
# ---------------------------------------------------------------------------

_next_id = 0


def _recreate_collection(client) -> None:
    """Delete and recreate the safety_intelligence collection (recovery from Actian beta corruption)."""
    from cortex import DistanceMetric
    try:
        if client.has_collection(COLLECTION_NAME):
            client.delete_collection(COLLECTION_NAME)
        client.create_collection(
            name=COLLECTION_NAME,
            dimension=EMBEDDING_DIM,
            distance_metric=DistanceMetric.COSINE,
        )
        logger.info("Recreated collection '%s' after corruption", COLLECTION_NAME)
    except Exception as exc:
        logger.error("Failed to recreate collection: %s", exc)
        raise


async def ingest_intelligence(
    country: str,
    text_list: list[str],
) -> int:
    """Generate embeddings and insert into Actian VectorAI.

    Uses ``batch_upsert`` with payloads storing country + content.

    Returns the number of vectors inserted, or 0 if the DB is unavailable.
    """
    global _next_id

    if not text_list:
        return 0

    client = _get_cortex_client()
    if client is None:
        logger.warning("Actian unavailable — cannot ingest %d texts", len(text_list))
        return 0

    try:
        # Ensure collection exists
        init_db(client)

        # Get current count to generate unique IDs
        try:
            _next_id = client.count(COLLECTION_NAME)
        except Exception:
            _next_id = 0

        # Generate embeddings via OpenRouter
        embeddings = await embed_texts(text_list)

        # Prepare batch data
        ids = list(range(_next_id, _next_id + len(text_list)))
        vectors = [emb for emb in embeddings]
        payloads = [
            {"country": country, "content": text}
            for text in text_list
        ]

        # Batch upsert into Actian VectorAI (with auto-recovery on corruption)
        try:
            client.batch_upsert(
                COLLECTION_NAME,
                ids=ids,
                vectors=vectors,
                payloads=payloads,
            )
        except Exception as upsert_exc:
            logger.warning(
                "batch_upsert failed (%s) — recreating collection and retrying",
                upsert_exc,
            )
            _recreate_collection(client)
            _next_id = 0
            ids = list(range(0, len(text_list)))
            client.batch_upsert(
                COLLECTION_NAME,
                ids=ids,
                vectors=vectors,
                payloads=payloads,
            )

        _next_id += len(text_list)
        logger.info(
            "Ingested %d vectors for %s into '%s'",
            len(text_list), country, COLLECTION_NAME,
        )
        return len(text_list)

    except Exception as exc:
        logger.error("ingest_intelligence failed: %s", exc)
        return 0
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# 4c. get_safety_brief() — Vector Search + Client-Side Country Filtering
# ---------------------------------------------------------------------------

async def get_safety_brief(
    country: str,
    query: str,
    top_k: int = 3,
) -> tuple[list[str], str]:
    """Embed the *query* and retrieve the top-k most relevant chunks.

    Uses broad vector search + client-side country filtering because the
    Actian beta's server-side payload filter is not yet functional.

    Returns a tuple of (content_list, status_message).
    """
    client = _get_cortex_client()
    if client is None:
        return [], "Actian VectorAI offline"

    try:
        total = client.count(COLLECTION_NAME)
        if total == 0:
            return [], "No data in DB"

        query_emb = await embed_text(query)
        search_k = min(total, 200)

        results = client.search(
            COLLECTION_NAME,
            query=query_emb,
            top_k=search_k,
            with_payload=True,
        )

        # Client-side country filter
        contents: list[str] = []
        for r in results:
            if r.payload and r.payload.get("country") == country:
                content = r.payload.get("content", "")
                if content:
                    contents.append(content)
                if len(contents) >= top_k:
                    break

        if not contents:
            return [], f"No safety context found in DB for {country}"

        logger.info(
            "get_safety_brief: %d results for '%s' in %s",
            len(contents), query[:50], country,
        )
        return contents, "Actian VectorAI RAG"

    except Exception as exc:
        logger.error("get_safety_brief failed: %s", exc)
        return [], f"Actian error: {str(exc)}"
    finally:
        if client:
            client.__exit__(None, None, None)


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 5 — GENERATION (OpenRouter)
# ═══════════════════════════════════════════════════════════════════════════

_BRIEFING_SYSTEM_PROMPT = """\
You are an operational intelligence analyst writing field briefings for \
humanitarian workers who are DEPLOYING to this country. They already know \
it is dangerous — do NOT waste space saying "don't go" or repeating generic \
warnings. They need to know what has CHANGED, what to WATCH FOR, and how \
to OPERATE.

AUDIENCE: Aid workers, NGO staff, medical teams entering or already in-country.

STRUCTURE (use these exact headings):

## What Changed This Week
Summarize ONLY breaking news items (tagged [BREAKING NEWS]). Focus on \
developments that change the operational picture: new offensives, ceasefires, \
territorial shifts, attacks on aid workers, infrastructure damage, border \
closures, disease outbreaks. Include dates and source names.

## Operating Environment
Synthesize from all sources into a practical picture:
- **Access & movement**: Which regions are hardest to reach? Known road \
  blockages, checkpoint patterns, airport/border status if mentioned.
- **Who controls what**: Faction/group territorial control if data supports it.
- **Threats to aid operations**: Specific risks to humanitarian staff — \
  carjacking, diversion, bureaucratic obstruction, targeting patterns.
- **Health & disease**: Outbreaks, hospital capacity, medical evacuation needs.
- **Food & displacement**: IPC/food crisis data, IDP movements, camp conditions.

## Key Risks to Be Aware Of
Bullet-point the TOP 5 concrete, specific risks — not generic "crime exists" \
but things like "RSF drone strikes on Kordofan aid convoys (20 Feb)" or \
"Cholera outbreak in Kassala state" or "Checkpoint extortion on Khartoum-Port \
Sudan highway." Each risk should name a PLACE and a THREAT.

## Local Situation (if city/region specified)
If a specific city or region is given, include a focused subsection:
- What is happening in and around that specific location right now?
- Local threats, recent incidents, infrastructure status.
- Nearby natural disasters (items tagged [NEARBY DISASTER]).
- If no local data is available, say so briefly.

## Operational Recommendations
Practical, specific advice: communication protocols, supply chain \
considerations, evacuation routes, coordination contacts, medical prep. \
NOT generic "stay alert" — things like "Maintain HF radio capability as \
mobile networks are down in Darfur" or "Coordinate movements through OCHA \
access working group." If a specific city is given, tailor recommendations \
to that location.

RULES:
- Discard information about other countries.
- Be SPECIFIC: name regions, cities, roads, dates, groups.
- If data is sparse for a section, say so briefly and move on.
- Cite sources inline (Google News / US State Dept / HDX / GDACS).
- Keep under 700 words. Use markdown.\
"""


async def _openrouter_generate(prompt: str, *, max_tokens: int = 1200) -> str | None:
    """Call OpenRouter chat completions with retry on 429."""
    key = _openrouter_api_key()
    if not key:
        return None
    body = {
        "model": OPENROUTER_CHAT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    delays = [5, 15, 30]
    async with httpx.AsyncClient(timeout=60) as client:
        for attempt, delay in enumerate(delays):
            try:
                resp = await client.post(
                    f"{OPENROUTER_API_BASE}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as exc:
                try:
                    err_body = exc.response.text[:500] if exc.response else ""
                    logger.error(
                        "OpenRouter generation HTTP %s: %s",
                        exc.response.status_code if exc.response else "?",
                        err_body,
                    )
                except Exception:
                    logger.error("OpenRouter generation failed: %s", exc)
                if exc.response.status_code == 429 and attempt < len(delays) - 1:
                    await asyncio.sleep(delay)
                    continue
                return None
            except Exception as exc:
                logger.error("OpenRouter generation failed: %s", exc)
                return None
    return None


async def _llm_generate(prompt: str, *, max_tokens: int = 1200) -> str | None:
    """Generate text via OpenRouter."""
    return await _openrouter_generate(prompt, max_tokens=max_tokens)


async def synthesize_briefing(
    country: str,
    chunks: list[str],
    lat: float | None = None,
    lng: float | None = None,
    city: str = "",
    region: str = "",
) -> str:
    """Use LLM (OpenRouter) to synthesize retrieved chunks into an actionable briefing.

    Falls back to formatted raw chunks if LLM is unavailable.
    """
    context = "\n\n---\n\n".join(c[:2000] for c in chunks[:15])

    coord_str = f"Coordinates: ({lat}, {lng})\n" if lat is not None else ""
    location_parts = [p for p in [city, region, country] if p]
    location_label = ", ".join(location_parts) if location_parts else country

    location_note = ""
    if city or region:
        location_note = (
            f"\nSPECIFIC LOCATION: {location_label}\n"
            f"Prioritize intel about {city or region} and its immediate surroundings. "
            f"Items tagged [LOCAL NEWS] or [NEARBY DISASTER] are specific to this "
            f"location — give them extra weight. Also include country-level context "
            f"that affects this area.\n"
        )

    prompt = (
        f"{_BRIEFING_SYSTEM_PROMPT}\n\n"
        f"TARGET COUNTRY: {country}\n{coord_str}{location_note}\n"
        f"RETRIEVED INTELLIGENCE ({len(chunks)} chunks):\n\n{context}\n\n"
        f"Write the operational field briefing now. Remember: the reader is "
        f"deploying to {location_label} regardless — help them operate safely, "
        f"not decide whether to go."
    )

    generated = await _llm_generate(prompt)

    if generated:
        header = (
            f"## Operational Field Briefing — {location_label}\n"
            f"{coord_str}"
            f"*Intel from GDACS, HDX, US State Dept, HAPI & live news — synthesized via LLM*\n\n"
        )
        return header + generated

    sections = [f"[{i}] {text[:1500]}" for i, text in enumerate(chunks, 1)]
    return (
        f"## Safety & Security Briefing — {location_label}\n"
        f"{coord_str}"
        f"Source: Raw retrieved data (LLM unavailable)\n\n"
        + "\n\n---\n\n".join(sections)
    )


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 6 — HIGH-LEVEL ORCHESTRATORS (API Integration)
# ═══════════════════════════════════════════════════════════════════════════

async def ingest_country(country: str, limit: int = 10) -> int:
    """End-to-end: fetch all sources -> chunk -> ingest into Actian.

    Sources: GDACS, HDX CKAN, US State Dept, HDX HAPI, Google News.
    Returns the total number of vectors stored.
    """
    results = await asyncio.gather(
        fetch_gdacs_alerts(country, min_level="Green"),
        fetch_hdx_reports(country, limit=limit),
        fetch_travel_advisory(country),
        fetch_hapi_data(country),
        fetch_news(country),
    )
    gdacs_alerts, hdx_reports, state_reports, hapi_reports, news_articles = results

    combined = gdacs_alerts + hdx_reports + state_reports + hapi_reports + news_articles
    if not combined:
        logger.warning("No data found for %s from any source", country)
        return 0

    logger.info(
        "Ingesting %d sources for %s (%d GDACS, %d HDX, %d StateDept, %d HAPI, %d News)",
        len(combined), country, len(gdacs_alerts), len(hdx_reports),
        len(state_reports), len(hapi_reports), len(news_articles),
    )

    text_list: list[str] = []
    for rpt in combined:
        chunks = chunk_text(rpt["body"])
        text_list.extend(chunks)

    if not text_list:
        return 0

    stored = await ingest_intelligence(country, text_list)
    return stored


async def ingest_all_countries(
    delay_seconds: float = 6.0,
    countries: list[str] | None = None,
) -> dict[str, Any]:
    """Ingest every country in the codebook. Optional delay between countries to reduce rate limits.

    Returns a summary: {"ingested": n, "total_chunks": sum, "by_country": {country: chunks}}.
    """
    if countries is None:
        countries = list_all_countries()
    total_chunks = 0
    by_country: dict[str, int] = {}
    for i, country in enumerate(countries, 1):
        try:
            n = await ingest_country(country)
            by_country[country] = n
            total_chunks += n
            logger.info("Ingest-all %d/%d: %s -> %d chunks", i, len(countries), country, n)
        except Exception as exc:
            logger.exception("Ingest-all failed for %s: %s", country, exc)
            by_country[country] = 0
        if i < len(countries):
            await asyncio.sleep(delay_seconds)
    return {"ingested": len(countries), "total_chunks": total_chunks, "by_country": by_country}


async def get_safety_report(lat: float, lng: float) -> str:
    """Return a safety/security briefing for (*lat*, *lng*).

    1. Reverse-geocode to country + city/region.
    2. Fetch city-specific news + nearby GDACS alerts (always live).
    3. Fetch country-level news (always live).
    4. Try Actian RAG for deeper country context.
    5. Merge city-level + country-level chunks -> LLM synthesis.
    6. Fallback: live all-source fetch + city data -> LLM synthesis.
    """
    loc = await _coords_to_location(lat, lng)
    country = loc["country"] or "Unknown"
    city = loc["city"]
    region = loc["region"]
    location_label = ", ".join(filter(None, [city, region, country]))

    # Kick off city-specific + country-level fetches in parallel
    city_news_task = fetch_city_news(city, country, max_articles=5)
    nearby_gdacs_task = fetch_gdacs_nearby(lat, lng, radius_km=500)
    country_news_task = fetch_news(country, max_articles=5)

    rag_results, status = await get_safety_brief(
        country, f"security risks safety humanitarian situation in {country}",
        top_k=5,
    )

    city_news, nearby_gdacs, country_news = await asyncio.gather(
        city_news_task, nearby_gdacs_task, country_news_task,
    )

    # City-level chunks go first (highest priority)
    city_chunks: list[str] = []
    for a in city_news[:5]:
        city_chunks.append(a["body"])
    for a in nearby_gdacs[:3]:
        city_chunks.append(a["body"])

    country_news_chunks = [a["body"] for a in country_news[:5]]

    if rag_results:
        combined = city_chunks + country_news_chunks + rag_results
        return await synthesize_briefing(
            country, combined, lat, lng,
            city=city, region=region,
        )

    logger.info("RAG fallback (%s) — live fetch for %s", status, country)
    live_results = await asyncio.gather(
        fetch_gdacs_alerts(country, min_level="Green"),
        fetch_hdx_reports(country, limit=5),
        fetch_travel_advisory(country),
        fetch_hapi_data(country),
    )
    gdacs_alerts, hdx_reports, state_reports, hapi_reports = live_results

    chunks: list[str] = city_chunks[:]
    for item in country_news[:5]:
        chunks.append(item["body"])
    for item in state_reports[:5]:
        chunks.append(item["body"])
    for a in gdacs_alerts[:5]:
        chunks.append(a["body"])
    for r in hdx_reports[:5]:
        chunks.append(r["body"])
    for h in hapi_reports[:3]:
        chunks.append(h["body"])

    if not chunks:
        return (
            f"No safety intelligence currently available for {location_label} "
            f"({lat}, {lng}). {status}. "
            "No sources returned results for this location."
        )

    return await synthesize_briefing(
        country, chunks, lat, lng,
        city=city, region=region,
    )


async def get_safety_report_by_country(country: str) -> tuple[str, float | None, float | None]:
    """Get safety report for a country by name.

    Forward-geocodes to (lat, lng) then runs the full RAG pipeline.
    Returns (report_text, lat, lng). lat/lng are None if geocoding failed.
    """
    coords = await _country_to_coords(country)
    if coords is None:
        return (
            f"Could not find coordinates for \"{country}\". "
            "Try a different spelling or use the safety-report endpoint with lat/lng.",
            None,
            None,
        )
    lat, lng = coords
    report = await get_safety_report(lat, lng)
    return report, lat, lng


# ═══════════════════════════════════════════════════════════════════════════
#  __main__ — Full Pipeline Test
# ═══════════════════════════════════════════════════════════════════════════

async def _run_pipeline(country: str) -> None:
    """Execute the complete Layer 3 pipeline for demonstration."""
    print(f"\n{'='*60}")
    print(f"  ResQ-Capital — Layer 3 Context Engine")
    print(f"  Target Country: {country}")
    print(f"  Actian Server:  {ACTIAN_SERVER}")
    print(f"{'='*60}\n")

    print("[Step 1] Fetching intelligence from GDACS + HDX...")
    gdacs_alerts = await fetch_gdacs_alerts(country, min_level="Green")
    hdx_reports = await fetch_hdx_reports(country, limit=5)
    combined = gdacs_alerts + hdx_reports
    print(f"  GDACS: {len(gdacs_alerts)} alerts")
    print(f"  HDX:   {len(hdx_reports)} reports")

    if not combined:
        print(f"\n  No data found for {country}.")
        return

    text_list: list[str] = []
    for rpt in combined:
        text_list.extend(chunk_text(rpt["body"]))
    print(f"  Chunks: {len(text_list)} text chunks prepared\n")

    print("[Step 2] Ingesting into Actian VectorAI...")
    stored = await ingest_intelligence(country, text_list)
    if stored > 0:
        print(f"  Stored {stored} vectors in '{COLLECTION_NAME}'")
    else:
        print(f"  Actian unavailable — {len(text_list)} chunks ready but not stored")
        print(f"  Start Docker: cd actian-beta && docker compose up -d")

    print(f"\n[Step 3] Generating safety briefing (LLM synthesis)...")
    report = await get_safety_report_by_country(country)
    print(report[0])

    print(f"\n{'='*60}")
    print(f"  Pipeline complete for {country}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    target_country = sys.argv[1] if len(sys.argv) > 1 else "Afghanistan"
    asyncio.run(_run_pipeline(target_country))
