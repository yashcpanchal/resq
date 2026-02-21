"""
Layer 3 — Context Engine (Safety Intelligence via RAG)

Pipeline: GDACS + HDX → chunk → embed (OpenAI) → store (Actian VectorAI) → search.

Actian VectorAI DB integration uses the ``cortex`` gRPC Python client
(not SQL / pyodbc).  Docker: ``docker compose up -d`` in actian-beta/.
The DB runs on ``localhost:50051``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any
from xml.etree import ElementTree as ET

import httpx
import tiktoken
import reverse_geocoder as rg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GDACS_RSS_URL = "https://www.gdacs.org/xml/rss.xml"
HDX_CKAN_URL = "https://data.humdata.org/api/3/action/package_search"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
CHUNK_MAX_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50

# Actian VectorAI config
ACTIAN_SERVER = os.getenv("ACTIAN_SERVER", "localhost:50051")
COLLECTION_NAME = "safety_intelligence"

# ---------------------------------------------------------------------------
# Country lookup (Dynamic via reverse_geocoder)
# ---------------------------------------------------------------------------

_CC_TO_NAME = {
    "AF": "Afghanistan", "BD": "Bangladesh", "CD": "Democratic Republic of the Congo",
    "ET": "Ethiopia", "HT": "Haiti", "JO": "Jordan", "ML": "Mali", "MZ": "Mozambique",
    "MM": "Myanmar", "NG": "Nigeria", "PK": "Pakistan", "SO": "Somalia", "SD": "Sudan",
    "SY": "Syria", "UA": "Ukraine", "YE": "Yemen", "KE": "Kenya", "LB": "Lebanon",
    "IQ": "Iraq", "SS": "South Sudan", "LY": "Libya", "TD": "Chad", "NE": "Niger",
    "BF": "Burkina Faso", "CF": "Central African Republic", "VE": "Venezuela",
    "CO": "Colombia", "EG": "Egypt", "TR": "Turkey", "KZ": "Kazakhstan", "TJ": "Tajikistan",
    "TM": "Turkmenistan", "CN": "China", "IR": "Iran",
}


def _coords_to_country(lat: float, lng: float) -> str:
    """Dynamic reverse geocode using reverse_geocoder library."""
    try:
        results = rg.search((lat, lng))
        cc = results[0].get("cc", "")
        best_match = _CC_TO_NAME.get(cc, cc)
        
        # Fallback to full country name if CC not in our subset mapping
        # In a production app, we'd use a full ISO-3166-1 library
        logger.info("Reverse Geocode: (%s, %s) -> %s (%s)", lat, lng, best_match, cc)
        return best_match
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


async def fetch_gdacs_alerts(country: str) -> list[dict[str, Any]]:
    """Fetch current disaster alerts from GDACS RSS filtered by *country*."""
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

    country_lower = country.lower()
    alerts: list[dict[str, Any]] = []

    for item in root.findall(".//item"):
        gdacs_country = item.findtext("gdacs:country", default="", namespaces=GDACS_NS)
        if not gdacs_country or country_lower not in gdacs_country.lower():
            continue

        title = item.findtext("title", default="")
        description = item.findtext("description", default="")
        description_clean = re.sub(r"<[^>]+>", " ", description)
        description_clean = re.sub(r"\s+", " ", description_clean).strip()

        event_type_code = item.findtext("gdacs:eventtype", default="", namespaces=GDACS_NS)
        event_type = _EVENT_TYPE_LABELS.get(event_type_code, event_type_code)
        alert_level = item.findtext("gdacs:alertlevel", default="", namespaces=GDACS_NS)
        severity = item.findtext("gdacs:severity", default="", namespaces=GDACS_NS)
        pub_date = item.findtext("pubDate", default="")

        body = (
            f"GDACS Alert — {event_type} in {gdacs_country}. "
            f"Alert Level: {alert_level}. Severity: {severity}. "
            f"{title}. {description_clean}"
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

    logger.info("GDACS: found %d alerts for %s", len(alerts), country)
    return alerts


async def fetch_hdx_reports(country: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search HDX for recent humanitarian reports about *country*."""
    queries = [
        f"situation report {country}",
        f"security access {country}",
        f"humanitarian crisis {country}",
    ]

    all_reports: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    async with httpx.AsyncClient(timeout=15) as client:
        for q in queries:
            try:
                resp = await client.get(
                    HDX_CKAN_URL,
                    params={
                        "q": q,
                        "rows": limit,
                        "sort": "metadata_modified desc",
                    },
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

                if not notes_clean:
                    continue

                org = pkg.get("organization", {})
                source_name = org.get("title", "HDX") if org else "HDX"
                modified = pkg.get("metadata_modified", "")

                all_reports.append({
                    "title": title,
                    "body": f"HDX Report — {title}. {notes_clean}",
                    "source": source_name,
                    "date": modified,
                    "country": country,
                })

    logger.info("HDX: found %d reports for %s", len(all_reports), country)
    return all_reports


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
#  SECTION 3 — OPENAI EMBEDDINGS
# ═══════════════════════════════════════════════════════════════════════════

async def embed_text(text: str) -> list[float]:
    """Return the embedding vector for *text* using OpenAI text-embedding-3-small."""
    from openai import AsyncOpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set — returning zero vector")
        return [0.0] * EMBEDDING_DIM

    client = AsyncOpenAI(api_key=api_key)
    resp = await client.embeddings.create(input=[text], model=EMBEDDING_MODEL)
    return resp.data[0].embedding


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch embed multiple texts using OpenAI text-embedding-3-small."""
    from openai import AsyncOpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set — returning zero vectors")
        return [[0.0] * EMBEDDING_DIM for _ in texts]

    client = AsyncOpenAI(api_key=api_key)
    resp = await client.embeddings.create(input=texts, model=EMBEDDING_MODEL)
    return [d.embedding for d in resp.data]


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
        - dimension: 1536 (OpenAI text-embedding-3-small)
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

        # Generate embeddings via OpenAI
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
#  SECTION 5 — HIGH-LEVEL ORCHESTRATORS (API Integration)
# ═══════════════════════════════════════════════════════════════════════════

async def ingest_country(country: str, limit: int = 10) -> int:
    """End-to-end: fetch GDACS + HDX → chunk → ingest into Actian.

    Returns the total number of vectors stored.
    """
    gdacs_alerts = await fetch_gdacs_alerts(country)
    hdx_reports = await fetch_hdx_reports(country, limit=limit)

    combined = gdacs_alerts + hdx_reports
    if not combined:
        logger.warning("No data found for %s from GDACS or HDX", country)
        return 0

    logger.info(
        "Ingesting %d sources for %s (%d GDACS, %d HDX)",
        len(combined), country, len(gdacs_alerts), len(hdx_reports),
    )

    # Chunk all report bodies
    text_list: list[str] = []
    for rpt in combined:
        chunks = chunk_text(rpt["body"])
        text_list.extend(chunks)

    if not text_list:
        return 0

    stored = await ingest_intelligence(country, text_list)
    return stored


async def get_safety_report(lat: float, lng: float) -> str:
    """Return a safety/security briefing for the location at (*lat*, *lng*).

    Tries Actian RAG first; falls back to live-fetched data.
    """
    country = _coords_to_country(lat, lng)

    # Try Actian RAG first
    results, status = await get_safety_brief(
        country, f"What are the security risks and safety conditions in {country}?"
    )
    if results:
        sections = [f"[{i}] {text[:1500]}" for i, text in enumerate(results, 1)]
        return (
            f"## Safety & Security Briefing — {country}\n"
            f"Coordinates: ({lat}, {lng})\n"
            f"Source: {status}\n\n"
            + "\n\n---\n\n".join(sections)
        )

    # Fallback: fetch live data directly
    logger.info("RAG fallback (%s) — building live briefing for %s", status, country)
    gdacs_alerts = await fetch_gdacs_alerts(country)
    hdx_reports = await fetch_hdx_reports(country, limit=3)

    parts: list[str] = []

    if gdacs_alerts:
        parts.append("### Active Disaster Alerts (GDACS)\n")
        for a in gdacs_alerts[:5]:
            parts.append(
                f"- **{a['event_type']}** — Alert: {a['alert_level']} — "
                f"{a['title']}\n  {a['body'][:300]}\n"
            )

    if hdx_reports:
        parts.append("\n### Humanitarian Reports (HDX)\n")
        for r in hdx_reports[:5]:
            parts.append(f"- **{r['title']}** ({r['source']})\n  {r['body'][:300]}\n")

    if not parts:
        return (
            f"No safety intelligence currently available for {country} "
            f"({lat}, {lng}). {status}. "
            "Neither GDACS nor HDX returned results."
        )

    header = (
        f"## Safety & Security Briefing — {country}\n"
        f"Coordinates: ({lat}, {lng})\n"
        f"*Live data — {status}*\n\n"
    )
    return header + "\n".join(parts)


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

    # ── Step 1: Fetch ──────────────────────────────────────────
    print("[Step 1] Fetching intelligence from GDACS + HDX...")
    gdacs_alerts = await fetch_gdacs_alerts(country)
    hdx_reports = await fetch_hdx_reports(country, limit=5)
    combined = gdacs_alerts + hdx_reports
    print(f"  → GDACS: {len(gdacs_alerts)} alerts")
    print(f"  → HDX:   {len(hdx_reports)} reports")

    if not combined:
        print(f"\n  ⚠ No data found for {country}.")
        return

    # Chunk
    text_list: list[str] = []
    for rpt in combined:
        text_list.extend(chunk_text(rpt["body"]))
    print(f"  → Chunks: {len(text_list)} text chunks prepared\n")

    # ── Step 2: Ingest into Actian ─────────────────────────────
    print("[Step 2] Ingesting into Actian VectorAI...")
    stored = await ingest_intelligence(country, text_list)
    if stored > 0:
        print(f"  → ✅ Stored {stored} vectors in '{COLLECTION_NAME}'")
    else:
        print(f"  → ⚠ Actian unavailable — {len(text_list)} chunks ready but not stored")
        print(f"    Start Docker: cd actian-beta && docker compose up -d")

    # ── Step 3: Search ─────────────────────────────────────────
    test_query = "What are the security risks?"
    print(f"\n[Step 3] Running test search: '{test_query}'")
    results = await get_safety_brief(country, test_query)
    if results:
        print(f"  → ✅ Retrieved {len(results)} relevant chunks:\n")
        for i, text in enumerate(results, 1):
            print(f"  --- Result {i} ---")
            print(f"  {text[:300]}...")
            print()
    else:
        print("  → ⚠ No Actian results — showing raw data preview:\n")
        for rpt in combined[:3]:
            print(f"  [{rpt['source']}] {rpt['title']}")
            print(f"  {rpt['body'][:200]}...\n")

    print(f"{'='*60}")
    print(f"  Pipeline complete for {country}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    target_country = sys.argv[1] if len(sys.argv) > 1 else "Afghanistan"
    asyncio.run(_run_pipeline(target_country))
