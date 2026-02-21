"""
Layer 3 — Context Engine (Safety Intelligence via RAG)

Pipeline: GDACS + HDX → chunk → embed (OpenAI) → store (Actian VectorAI) → search.
Gracefully degrades when Actian or OpenAI credentials are missing.
"""

from __future__ import annotations

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

# Actian table name for our vector store
TABLE_NAME = "resq_safety_chunks"

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

    Returns list of dicts: ``{title, body, source, date, country, alert_level, event_type}``.
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

    Returns list of dicts: ``{title, body, source, date, country}``.
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


# ---------------------------------------------------------------------------
# 2. Text Chunking
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 3. OpenAI Embeddings
# ---------------------------------------------------------------------------

async def embed_text(text: str) -> list[float]:
    """Return the embedding vector for *text* using OpenAI."""
    from openai import AsyncOpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set — returning zero vector")
        return [0.0] * EMBEDDING_DIM

    client = AsyncOpenAI(api_key=api_key)
    resp = await client.embeddings.create(input=[text], model=EMBEDDING_MODEL)
    return resp.data[0].embedding


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch embed multiple texts."""
    from openai import AsyncOpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set — returning zero vectors")
        return [[0.0] * EMBEDDING_DIM for _ in texts]

    client = AsyncOpenAI(api_key=api_key)
    resp = await client.embeddings.create(input=texts, model=EMBEDDING_MODEL)
    return [d.embedding for d in resp.data]


# ---------------------------------------------------------------------------
# 4. Actian VectorAI (pyodbc)
# ---------------------------------------------------------------------------

def _get_actian_connection():
    """Return a pyodbc connection to Actian VectorAI, or None."""
    dsn = os.getenv("ACTIAN_DSN")
    if not dsn:
        logger.warning("ACTIAN_DSN not set — Actian VectorAI unavailable")
        return None

    try:
        import pyodbc
        user = os.getenv("ACTIAN_USER", "")
        password = os.getenv("ACTIAN_PASSWORD", "")
        conn = pyodbc.connect(
            f"DSN={dsn};UID={user};PWD={password}", autocommit=True,
        )
        return conn
    except Exception as exc:
        logger.error("Failed to connect to Actian VectorAI: %s", exc)
        return None


def init_table(conn) -> None:
    """Create the vector store table if it does not already exist."""
    ddl = textwrap.dedent(f"""\
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            country     VARCHAR(120)  NOT NULL,
            title       VARCHAR(500),
            chunk_text  VARCHAR(8000) NOT NULL,
            source      VARCHAR(300),
            report_date VARCHAR(60),
            embedding   VECTOR({EMBEDDING_DIM}) NOT NULL
        )
    """)
    cursor = conn.cursor()
    cursor.execute(ddl)
    cursor.close()


def store_chunks(conn, chunks: list[dict[str, Any]]) -> int:
    """Insert pre-embedded chunks into Actian VectorAI.

    Returns the number of rows inserted.
    """
    sql = textwrap.dedent(f"""\
        INSERT INTO {TABLE_NAME}
            (country, title, chunk_text, source, report_date, embedding)
        VALUES
            (?, ?, ?, ?, ?, TO_VECTOR(?))
    """)
    cursor = conn.cursor()
    count = 0
    for c in chunks:
        emb_str = ",".join(str(v) for v in c["embedding"])
        cursor.execute(sql, (
            c["country"],
            c["title"][:500],
            c["chunk_text"][:8000],
            c["source"][:300],
            c["report_date"],
            emb_str,
        ))
        count += 1
    cursor.close()
    return count


def search_similar(
    conn,
    query_embedding: list[float],
    country: str | None = None,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Find the *top_k* most similar chunks to *query_embedding*."""
    emb_str = ",".join(str(v) for v in query_embedding)
    where = "WHERE country = ?" if country else ""
    sql = textwrap.dedent(f"""\
        SELECT title, chunk_text, source, report_date, country
        FROM   {TABLE_NAME}
        {where}
        ORDER BY VECTOR_DISTANCE(embedding, TO_VECTOR(?))
        FETCH FIRST ? ROWS ONLY
    """)

    cursor = conn.cursor()
    if country:
        cursor.execute(sql, (country, emb_str, top_k))
    else:
        cursor.execute(sql, (emb_str, top_k))

    rows = cursor.fetchall()
    columns = ["title", "chunk_text", "source", "report_date", "country"]
    results = [dict(zip(columns, row)) for row in rows]
    cursor.close()
    return results


# ---------------------------------------------------------------------------
# 5. High-level Orchestrators
# ---------------------------------------------------------------------------

async def ingest_country(country: str, limit: int = 10) -> int:
    """End-to-end: fetch GDACS + HDX → chunk → embed → store in Actian.

    Returns the total number of chunks stored.
    """
    # Fetch from both sources concurrently
    gdacs_alerts = await fetch_gdacs_alerts(country)
    hdx_reports = await fetch_hdx_reports(country, limit=limit)

    combined = gdacs_alerts + hdx_reports
    if not combined:
        logger.warning("No data found for %s from GDACS or HDX", country)
        return 0

    logger.info(
        "Ingesting %d sources for %s (%d GDACS alerts, %d HDX reports)",
        len(combined), country, len(gdacs_alerts), len(hdx_reports),
    )

    # Chunk all reports
    all_chunks: list[dict[str, Any]] = []
    for rpt in combined:
        text_chunks = chunk_text(rpt["body"])
        for tc in text_chunks:
            all_chunks.append({
                "country": rpt["country"],
                "title": rpt["title"],
                "chunk_text": tc,
                "source": rpt["source"],
                "report_date": rpt["date"],
            })

    if not all_chunks:
        return 0

    # Batch embed
    texts = [c["chunk_text"] for c in all_chunks]
    embeddings = await embed_texts(texts)
    for c, emb in zip(all_chunks, embeddings):
        c["embedding"] = emb

    # Store in Actian
    conn = _get_actian_connection()
    if conn is None:
        logger.warning(
            "Actian unavailable — skipping storage for %s (%d chunks prepared)",
            country, len(all_chunks),
        )
        return 0

    try:
        init_table(conn)
        stored = store_chunks(conn, all_chunks)
        logger.info("Stored %d chunks for %s in Actian VectorAI", stored, country)
        return stored
    finally:
        conn.close()


async def get_safety_report(lat: float, lng: float) -> str:
    """Return a safety/security briefing for the location at (*lat*, *lng*).

    Performs RAG search against Actian VectorAI. Falls back to a
    live-fetched briefing when the database is unavailable.
    """
    country = _coords_to_country(lat, lng)

    # Try Actian RAG first
    conn = _get_actian_connection()
    if conn is not None:
        try:
            query = f"What are the current security risks and safety conditions in {country}?"
            query_emb = await embed_text(query)
            results = search_similar(conn, query_emb, country=country, top_k=5)
        finally:
            conn.close()

        if results:
            sections: list[str] = []
            for i, r in enumerate(results, 1):
                sections.append(
                    f"[{i}] {r['title']} (Source: {r['source']}, "
                    f"Date: {r['report_date']})\n{r['chunk_text'][:1500]}"
                )
            return (
                f"## Safety & Security Briefing — {country}\n"
                f"Coordinates: ({lat}, {lng})\n\n"
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
