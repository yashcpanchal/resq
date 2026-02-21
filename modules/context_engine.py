"""
Layer 3 — Context Engine (Safety Intelligence via RAG)

Pipeline: GDACS + HDX → chunk → embed (OpenAI) → store (Actian VectorAI) → search.
Gracefully degrades when Actian or OpenAI credentials are missing.

CLI usage:
    python -m modules.context_engine          # full pipeline test
    python -m modules.context_engine Sudan    # target a specific country
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import textwrap
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
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
CHUNK_MAX_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50

# Actian VectorAI table — matches the hackathon sponsor requirement
TABLE_NAME = "safety_intelligence"

# ---------------------------------------------------------------------------
# Country lookup (simple lat/lng → country for the hackathon)
# ---------------------------------------------------------------------------

_COUNTRY_COORDS: list[tuple[str, float, float, float]] = [
    ("Sudan", 15.5, 32.5, 8),
    ("Yemen", 15.5, 48.0, 5),
    ("Syria", 35.0, 38.0, 4),
    ("Somalia", 5.0, 46.0, 6),
    ("Afghanistan", 33.9, 67.7, 6),
    ("Ethiopia", 9.0, 38.7, 6),
    ("Democratic Republic of the Congo", -4.0, 21.7, 8),
    ("Myanmar", 19.7, 96.2, 6),
    ("Nigeria", 9.0, 8.0, 5),
    ("Ukraine", 48.3, 31.1, 7),
    ("Haiti", 19.0, -72.0, 3),
    ("Mozambique", -18.6, 35.5, 7),
    ("Pakistan", 30.3, 69.3, 7),
    ("Bangladesh", 23.6, 90.3, 4),
    ("Mali", 17.5, -4.0, 6),
]


def _coords_to_country(lat: float, lng: float) -> str:
    """Best-effort reverse geocode using a simple distance heuristic."""
    best, best_dist = "Unknown", float("inf")
    for name, clat, clng, radius in _COUNTRY_COORDS:
        dist = ((lat - clat) ** 2 + (lng - clng) ** 2) ** 0.5
        if dist < radius and dist < best_dist:
            best, best_dist = name, dist
    return best


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 1 — DATA INGESTION (GDACS + HDX)
# ═══════════════════════════════════════════════════════════════════════════

# ---------------------------------------------------------------------------
# 1a. GDACS RSS Feed — Live Disaster Alerts
# ---------------------------------------------------------------------------

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
    """Fetch current disaster alerts from GDACS RSS filtered by *country*.

    Returns list of dicts with keys: title, body, source, date, country,
    alert_level, event_type.
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


# ---------------------------------------------------------------------------
# 1b. HDX CKAN API — Humanitarian Reports & Datasets
# ---------------------------------------------------------------------------

async def fetch_hdx_reports(country: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search HDX for recent humanitarian reports about *country*.

    Returns list of dicts with keys: title, body, source, date, country.
    """
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
#  SECTION 4 — ACTIAN VectorAI (pyodbc)
# ═══════════════════════════════════════════════════════════════════════════

def _get_actian_connection():
    """Return a pyodbc connection to Actian VectorAI, or None.

    Supports two connection modes:
      - DSN-based:    set ACTIAN_DSN
      - Direct:       set ACTIAN_HOST (defaults to localhost)

    Docker: docker pull williamimoh/actian-vectorai-db:1.0b
    """
    try:
        import pyodbc
    except ImportError:
        logger.warning("pyodbc not installed — Actian VectorAI unavailable")
        return None

    dsn = os.getenv("ACTIAN_DSN")
    host = os.getenv("ACTIAN_HOST", "")
    user = os.getenv("ACTIAN_USER", "")
    password = os.getenv("ACTIAN_PASSWORD", "")
    database = os.getenv("ACTIAN_DATABASE", "iidbdb")
    port = os.getenv("ACTIAN_PORT", "VW")

    if not dsn and not host:
        logger.warning(
            "Neither ACTIAN_DSN nor ACTIAN_HOST is set — "
            "Actian VectorAI unavailable"
        )
        return None

    try:
        if dsn:
            conn_str = f"DSN={dsn};UID={user};PWD={password}"
        else:
            conn_str = (
                f"driver=Ingres;servertype=ingres;"
                f"server=@{host},tcp_ip,{port};"
                f"uid={user};pwd={password};database={database}"
            )
        conn = pyodbc.connect(conn_str, autocommit=True)
        logger.info("Connected to Actian VectorAI")
        return conn
    except Exception as exc:
        logger.error("Failed to connect to Actian VectorAI: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 4a. init_db() — Create the safety_intelligence table
# ---------------------------------------------------------------------------

def init_db(conn=None) -> bool:
    """Create the ``safety_intelligence`` table if it doesn't exist.

    Schema:
        id        INT  (auto-increment)
        country   VARCHAR(200)
        content   VARCHAR(8000)
        embedding VECTOR(1536)

    Returns True on success, False if the connection is unavailable.
    """
    close_after = False
    if conn is None:
        conn = _get_actian_connection()
        close_after = True
    if conn is None:
        return False

    ddl = textwrap.dedent(f"""\
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id        INT          NOT NULL GENERATED ALWAYS AS IDENTITY,
            country   VARCHAR(200) NOT NULL,
            content   VARCHAR(8000) NOT NULL,
            embedding VECTOR({EMBEDDING_DIM}) NOT NULL
        )
    """)
    try:
        cursor = conn.cursor()
        cursor.execute(ddl)
        cursor.close()
        logger.info("Table '%s' is ready", TABLE_NAME)
        return True
    except Exception as exc:
        logger.error("init_db failed: %s", exc)
        return False
    finally:
        if close_after:
            conn.close()


# ---------------------------------------------------------------------------
# 4b. ingest_intelligence() — Embed + Store
# ---------------------------------------------------------------------------

async def ingest_intelligence(
    country: str,
    text_list: list[str],
    conn=None,
) -> int:
    """Generate embeddings for each text and insert into Actian VectorAI.

    Args:
        country:   Country name (e.g. "Sudan").
        text_list: List of text strings to embed and store.
        conn:      Optional existing pyodbc connection.

    Returns the number of rows inserted, or 0 if the DB is unavailable.
    """
    if not text_list:
        return 0

    close_after = False
    if conn is None:
        conn = _get_actian_connection()
        close_after = True
    if conn is None:
        logger.warning("Actian unavailable — cannot ingest %d texts", len(text_list))
        return 0

    try:
        init_db(conn)

        # Generate embeddings
        embeddings = await embed_texts(text_list)

        # Critical Actian SQL syntax — TO_VECTOR(?)
        sql = (
            f"INSERT INTO {TABLE_NAME} (country, content, embedding) "
            f"VALUES (?, ?, TO_VECTOR(?))"
        )

        cursor = conn.cursor()
        count = 0
        for text, emb in zip(text_list, embeddings):
            emb_str = ",".join(str(v) for v in emb)
            cursor.execute(sql, (country, text[:8000], emb_str))
            count += 1
        cursor.close()

        logger.info("Ingested %d rows for %s into '%s'", count, country, TABLE_NAME)
        return count

    except Exception as exc:
        logger.error("ingest_intelligence failed: %s", exc)
        return 0
    finally:
        if close_after:
            conn.close()


# ---------------------------------------------------------------------------
# 4c. get_safety_brief() — Hybrid Search (filter + vector distance)
# ---------------------------------------------------------------------------

async def get_safety_brief(
    country: str,
    query: str,
    top_k: int = 3,
    conn=None,
) -> list[str]:
    """Embed the *query* and retrieve the top-k most relevant chunks.

    Uses Actian's hybrid search: filter by country, sort by VECTOR_DISTANCE.

    Returns a list of content strings, or an empty list if unavailable.
    """
    close_after = False
    if conn is None:
        conn = _get_actian_connection()
        close_after = True
    if conn is None:
        return []

    try:
        query_emb = await embed_text(query)
        emb_str = ",".join(str(v) for v in query_emb)

        # Critical Actian SQL syntax — VECTOR_DISTANCE + TO_VECTOR
        sql = (
            f"SELECT content FROM {TABLE_NAME} "
            f"WHERE country = ? "
            f"ORDER BY VECTOR_DISTANCE(embedding, TO_VECTOR(?)) ASC "
            f"LIMIT 3"
        )

        cursor = conn.cursor()
        cursor.execute(sql, (country, emb_str))
        rows = cursor.fetchall()
        cursor.close()

        results = [row[0] for row in rows]
        logger.info("get_safety_brief: %d results for '%s' in %s", len(results), query[:50], country)
        return results

    except Exception as exc:
        logger.error("get_safety_brief failed: %s", exc)
        return []
    finally:
        if close_after:
            conn.close()


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 5 — HIGH-LEVEL ORCHESTRATORS (API Integration)
# ═══════════════════════════════════════════════════════════════════════════

async def ingest_country(country: str, limit: int = 10) -> int:
    """End-to-end: fetch GDACS + HDX → chunk → ingest into Actian.

    Returns the total number of rows stored.
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

    # Chunk all report bodies into smaller pieces
    text_list: list[str] = []
    for rpt in combined:
        chunks = chunk_text(rpt["body"])
        text_list.extend(chunks)

    if not text_list:
        return 0

    # Ingest into Actian VectorAI
    stored = await ingest_intelligence(country, text_list)
    return stored


async def get_safety_report(lat: float, lng: float) -> str:
    """Return a safety/security briefing for the location at (*lat*, *lng*).

    Tries Actian RAG first; falls back to live-fetched data.
    """
    country = _coords_to_country(lat, lng)

    # Try Actian RAG search first
    results = await get_safety_brief(
        country, f"What are the security risks and safety conditions in {country}?"
    )
    if results:
        sections = [f"[{i}] {text[:1500]}" for i, text in enumerate(results, 1)]
        return (
            f"## Safety & Security Briefing — {country}\n"
            f"Coordinates: ({lat}, {lng})\n"
            f"Source: Actian VectorAI RAG\n\n"
            + "\n\n---\n\n".join(sections)
        )

    # Fallback: fetch live data directly and return as briefing
    logger.info("Actian unavailable — building live briefing for %s", country)
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
            f"({lat}, {lng}). Neither GDACS nor HDX returned results."
        )

    header = (
        f"## Safety & Security Briefing — {country}\n"
        f"Coordinates: ({lat}, {lng})\n"
        f"*Live data — Actian VectorAI not configured*\n\n"
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
    print(f"{'='*60}\n")

    # Step 1: Fetch data from GDACS + HDX
    print("[Step 1] Fetching intelligence from GDACS + HDX...")
    gdacs_alerts = await fetch_gdacs_alerts(country)
    hdx_reports = await fetch_hdx_reports(country, limit=5)
    print(f"  → GDACS: {len(gdacs_alerts)} alerts")
    print(f"  → HDX:   {len(hdx_reports)} reports")

    combined = gdacs_alerts + hdx_reports
    if not combined:
        print(f"\n  ⚠ No data found for {country}. Try a different country.")
        return

    # Chunk the text
    text_list: list[str] = []
    for rpt in combined:
        chunks = chunk_text(rpt["body"])
        text_list.extend(chunks)
    print(f"  → Chunks: {len(text_list)} text chunks prepared")

    # Step 2: Ingest into Actian VectorAI
    print("\n[Step 2] Ingesting into Actian VectorAI...")
    stored = await ingest_intelligence(country, text_list)
    if stored > 0:
        print(f"  → ✅ Stored {stored} rows in '{TABLE_NAME}'")
    else:
        print(f"  → ⚠ Actian unavailable — {len(text_list)} chunks ready but not stored")
        print("    Set ACTIAN_DSN or ACTIAN_HOST env vars to enable storage")

    # Step 3: Search
    print(f"\n[Step 3] Running test search: 'What are the security risks?'")
    results = await get_safety_brief(country, "What are the security risks?")
    if results:
        print(f"  → ✅ Retrieved {len(results)} relevant chunks:\n")
        for i, text in enumerate(results, 1):
            print(f"  --- Result {i} ---")
            print(f"  {text[:300]}...")
            print()
    else:
        print("  → ⚠ No Actian results (DB not connected)")
        print("    Falling back to live data preview:\n")
        for rpt in combined[:3]:
            print(f"  [{rpt['source']}] {rpt['title']}")
            print(f"  {rpt['body'][:200]}...\n")

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
