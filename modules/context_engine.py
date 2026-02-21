"""
Layer 3 — Context Engine (Safety Intelligence via RAG)

Pipeline: GDACS + HDX → chunk → embed (Gemini) → store (Actian VectorAI) → search.

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
EMBEDDING_MODEL = "models/gemini-embedding-001"
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


async def _coords_to_country(lat: float, lng: float) -> str:
    """Reverse-geocode (lat, lng) to a country name via Nominatim HTTP API."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                NOMINATIM_REVERSE,
                params={"lat": lat, "lon": lng, "format": "jsonv2", "accept-language": "en"},
                headers={"User-Agent": "ResQ-Capital/0.1"},
            )
            resp.raise_for_status()
            data = resp.json()
            country = data.get("address", {}).get("country", "")
            if country:
                logger.info("Reverse Geocode: (%s, %s) -> %s", lat, lng, country)
                return country
        logger.warning("Nominatim returned no country for (%s, %s)", lat, lng)
        return "Unknown"
    except Exception as exc:
        logger.error("Reverse geocoding failed: %s", exc)
        return "Unknown"


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
# Country-code mappings (ISO3 for HDX, 2-letter for State Dept, ISO3 upper for HAPI)
# ---------------------------------------------------------------------------

_COUNTRY_TO_ISO3: dict[str, str] = {
    "afghanistan": "afg", "bangladesh": "bgd", "burkina faso": "bfa",
    "central african republic": "caf", "chad": "tcd", "colombia": "col",
    "democratic republic of the congo": "cod", "drc": "cod",
    "egypt": "egy", "ethiopia": "eth", "haiti": "hti", "india": "ind",
    "iraq": "irq", "iran": "irn", "jordan": "jor", "kenya": "ken",
    "lebanon": "lbn", "libya": "lby", "mali": "mli", "mozambique": "moz",
    "myanmar": "mmr", "niger": "ner", "nigeria": "nga", "pakistan": "pak",
    "palestine": "pse", "somalia": "som", "south sudan": "ssd",
    "sudan": "sdn", "syria": "syr", "turkey": "tur", "turkiye": "tur",
    "ukraine": "ukr", "venezuela": "ven", "yemen": "yem",
    "china": "chn", "nepal": "npl", "philippines": "phl",
    "indonesia": "idn", "japan": "jpn", "mexico": "mex", "brazil": "bra",
}

_COUNTRY_TO_STATE_DEPT: dict[str, str] = {
    "afghanistan": "AF", "bangladesh": "BG", "burkina faso": "UV",
    "central african republic": "CT", "chad": "CD", "colombia": "CO",
    "democratic republic of the congo": "CG", "drc": "CG",
    "egypt": "EG", "ethiopia": "ET", "haiti": "HA", "india": "IN",
    "iraq": "IZ", "iran": "IR", "jordan": "JO", "kenya": "KE",
    "lebanon": "LE", "libya": "LY", "mali": "ML", "mozambique": "MZ",
    "myanmar": "BM", "niger": "NG", "nigeria": "NI", "pakistan": "PK",
    "palestine": "GZ", "somalia": "SO", "south sudan": "OD",
    "sudan": "SU", "syria": "SY", "turkey": "TU", "turkiye": "TU",
    "ukraine": "UP", "venezuela": "VE", "yemen": "YM",
    "china": "CH", "nepal": "NP", "philippines": "RP",
    "indonesia": "ID", "japan": "JA", "mexico": "MX", "brazil": "BR",
}

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
#  SECTION 3 — GEMINI EMBEDDINGS (via REST API — no SDK dependency)
# ═══════════════════════════════════════════════════════════════════════════

GEMINI_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/{model}:embedContent"
)
GEMINI_BATCH_URL = (
    "https://generativelanguage.googleapis.com/v1beta/{model}:batchEmbedContents"
)


def _gemini_api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


async def embed_text(text: str) -> list[float]:
    """Return the embedding vector for *text* using Gemini gemini-embedding-001."""
    api_key = _gemini_api_key()
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — returning zero vector")
        return [0.0] * EMBEDDING_DIM

    url = GEMINI_EMBED_URL.format(model=EMBEDDING_MODEL)
    body = {"model": EMBEDDING_MODEL, "content": {"parts": [{"text": text}]}}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, params={"key": api_key}, json=body)
        resp.raise_for_status()
        return resp.json()["embedding"]["values"]


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch embed multiple texts using Gemini gemini-embedding-001."""
    api_key = _gemini_api_key()
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — returning zero vectors")
        return [[0.0] * EMBEDDING_DIM for _ in texts]

    url = GEMINI_BATCH_URL.format(model=EMBEDDING_MODEL)
    requests = [
        {"model": EMBEDDING_MODEL, "content": {"parts": [{"text": t}]}}
        for t in texts
    ]

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            url, params={"key": api_key}, json={"requests": requests},
        )
        resp.raise_for_status()
        return [e["values"] for e in resp.json()["embeddings"]]


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
        - dimension: 3072 (Gemini gemini-embedding-001)
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

        # Generate embeddings via Gemini
        embeddings = await embed_texts(text_list)

        # Prepare batch data
        ids = list(range(_next_id, _next_id + len(text_list)))
        vectors = [emb for emb in embeddings]
        payloads = [
            {"country": country, "content": text}
            for text in text_list
        ]

        # Batch upsert into Actian VectorAI
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
        # Embed the query
        query_emb = await embed_text(query)

        # Broad search — fetch many results, then filter by country client-side
        # (Actian beta's server-side Filter DSL does not filter payloads yet)
        total = client.count(COLLECTION_NAME)
        search_k = min(total, 200)  # cap at 200 to stay performant

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
#  SECTION 5 — GEMINI GENERATION (synthesize intelligence from chunks)
# ═══════════════════════════════════════════════════════════════════════════

GEMINI_GENERATE_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent"
)

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

## Operational Recommendations
Practical, specific advice: communication protocols, supply chain \
considerations, evacuation routes, coordination contacts, medical prep. \
NOT generic "stay alert" — things like "Maintain HF radio capability as \
mobile networks are down in Darfur" or "Coordinate movements through OCHA \
access working group."

RULES:
- Discard information about other countries.
- Be SPECIFIC: name regions, cities, roads, dates, groups.
- If data is sparse for a section, say so briefly and move on.
- Cite sources inline (Google News / US State Dept / HDX / GDACS).
- Keep under 700 words. Use markdown.\
"""


async def _gemini_generate(prompt: str, *, max_tokens: int = 1200) -> str | None:
    """Call Gemini to generate text with retry on rate-limit (429)."""
    api_key = _gemini_api_key()
    if not api_key:
        return None

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": max_tokens,
        },
    }

    delays = [5, 15, 30]
    async with httpx.AsyncClient(timeout=60) as client:
        for attempt, delay in enumerate(delays):
            try:
                resp = await client.post(
                    GEMINI_GENERATE_URL,
                    params={"key": api_key},
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429 and attempt < len(delays) - 1:
                    logger.warning("Gemini 429 — retrying in %ds (attempt %d)", delay, attempt + 1)
                    await asyncio.sleep(delay)
                    continue
                logger.error("Gemini generation failed: %s", exc)
                return None
            except Exception as exc:
                logger.error("Gemini generation failed: %s", exc)
                return None
    return None


async def synthesize_briefing(
    country: str,
    chunks: list[str],
    lat: float | None = None,
    lng: float | None = None,
) -> str:
    """Use Gemini to synthesize retrieved chunks into an actionable briefing.

    Falls back to formatted raw chunks if Gemini is unavailable.
    """
    context = "\n\n---\n\n".join(c[:2000] for c in chunks[:10])

    coord_str = f"Coordinates: ({lat}, {lng})\n" if lat is not None else ""
    prompt = (
        f"{_BRIEFING_SYSTEM_PROMPT}\n\n"
        f"TARGET COUNTRY: {country}\n{coord_str}\n"
        f"RETRIEVED INTELLIGENCE ({len(chunks)} chunks):\n\n{context}\n\n"
        f"Write the operational field briefing now. Remember: the reader is "
        f"deploying to {country} regardless — help them operate safely, "
        f"not decide whether to go."
    )

    generated = await _gemini_generate(prompt)

    if generated:
        header = (
            f"## Operational Field Briefing — {country}\n"
            f"{coord_str}"
            f"*Intel from GDACS, HDX, US State Dept, HAPI & live news — synthesized via Gemini*\n\n"
        )
        return header + generated

    sections = [f"[{i}] {text[:1500]}" for i, text in enumerate(chunks, 1)]
    return (
        f"## Safety & Security Briefing — {country}\n"
        f"{coord_str}"
        f"Source: Raw retrieved data (Gemini unavailable)\n\n"
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


async def get_safety_report(lat: float, lng: float) -> str:
    """Return a safety/security briefing for (*lat*, *lng*).

    1. Reverse-geocode to country name.
    2. Fetch breaking news (always live — never stale).
    3. Try Actian RAG for deeper context -> Gemini synthesis.
    4. Fallback: live all-source fetch -> Gemini synthesis.
    """
    country = await _coords_to_country(lat, lng)

    news_task = fetch_news(country, max_articles=5)

    results, status = await get_safety_brief(
        country, f"security risks safety humanitarian situation in {country}",
        top_k=5,
    )

    news_articles = await news_task
    news_chunks = [a["body"] for a in news_articles[:5]]

    if results:
        combined_chunks = news_chunks + results
        return await synthesize_briefing(country, combined_chunks, lat, lng)

    logger.info("RAG fallback (%s) — live fetch for %s", status, country)
    results = await asyncio.gather(
        fetch_gdacs_alerts(country, min_level="Green"),
        fetch_hdx_reports(country, limit=5),
        fetch_travel_advisory(country),
        fetch_hapi_data(country),
        fetch_news(country, max_articles=5),
    )
    gdacs_alerts, hdx_reports, state_reports, hapi_reports, news_articles = results

    chunks: list[str] = []
    for item in news_articles[:5]:
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
            f"No safety intelligence currently available for {country} "
            f"({lat}, {lng}). {status}. "
            "No sources returned results for this country."
        )

    return await synthesize_briefing(country, chunks, lat, lng)


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

    print(f"\n[Step 3] Generating safety briefing (Gemini synthesis)...")
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
