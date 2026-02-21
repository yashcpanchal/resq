"""
Layer 3 — Context Engine (Safety Intelligence via RAG)

Pipeline: ReliefWeb → chunk → embed (OpenAI) → store (Actian VectorAI) → search.
Gracefully degrades when Actian or OpenAI credentials are missing.
"""

from __future__ import annotations

import logging
import os
import textwrap
from typing import Any

import httpx
import tiktoken

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RELIEFWEB_API = "https://api.reliefweb.int/v2/reports"
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
    # (country, lat_centre, lng_centre, radius_deg)
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
# 1.  ReliefWeb Ingest
# ---------------------------------------------------------------------------

# Sample data returned when the API is unavailable (demo/hackathon fallback)
_MOCK_REPORTS: dict[str, list[dict[str, Any]]] = {
    "Sudan": [
        {
            "title": "Sudan: Escalation of armed conflict — Flash Update #42",
            "body": (
                "Heavy fighting continues in Khartoum, El-Fasher, and surrounding areas. "
                "Displacement has surged past 10 million internally displaced persons. "
                "Access constraints remain severe in Darfur and Kordofan states. "
                "Humanitarian corridors are intermittently blocked by active combat. "
                "Road infrastructure is degraded, limiting truck-based aid delivery. "
                "Security risks include armed checkpoints, carjacking, and unexploded ordnance. "
                "Health facilities are non-functional in over 60 percent of conflict zones. "
                "Food insecurity is at crisis levels (IPC Phase 4) across five states. "
                "Water and sanitation infrastructure is severely damaged in urban centers."
            ),
            "source": "OCHA",
            "date": "2026-02-20T00:00:00+00:00",
            "country": "Sudan",
        },
        {
            "title": "Sudan: Humanitarian Access Snapshot — February 2026",
            "body": (
                "Humanitarian access remains severely constrained across Sudan. "
                "Armed groups continue to impose movement restrictions. "
                "Cross-line access from Port Sudan to Darfur is largely suspended. "
                "Aid warehouses in El Obeid and Nyala have been looted. "
                "Fuel shortages are impacting logistics operations. "
                "UN agencies report bureaucratic impediments including visa delays. "
                "Safe passage agreements are routinely violated. "
                "Parking and staging areas near El-Fasher airport are contested territory."
            ),
            "source": "OCHA",
            "date": "2026-02-18T00:00:00+00:00",
            "country": "Sudan",
        },
    ],
    "Yemen": [
        {
            "title": "Yemen: Humanitarian Update — Issue 2, February 2026",
            "body": (
                "Conflict escalation in Marib and Taiz governorates has displaced "
                "an additional 35,000 people. Port of Hodeidah operations disrupted "
                "by renewed airstrikes. Fuel imports down 40 percent month-on-month. "
                "Cholera cases rising in Aden and Lahj. Road access to northern "
                "governorates remains largely blocked. Staging areas near Sana'a "
                "airport are inaccessible due to military activity."
            ),
            "source": "OCHA",
            "date": "2026-02-19T00:00:00+00:00",
            "country": "Yemen",
        },
    ],
}


def _get_mock_reports(country: str) -> list[dict[str, Any]]:
    """Return mock sample reports when the live API is unavailable."""
    if country in _MOCK_REPORTS:
        return _MOCK_REPORTS[country]
    # Generic fallback
    return [
        {
            "title": f"{country}: Situation Overview (Mock Data)",
            "body": (
                f"This is placeholder safety intelligence for {country}. "
                "The ReliefWeb API requires a pre-approved appname (since Nov 2025). "
                "Set the RELIEFWEB_APPNAME environment variable with your approved "
                "appname to fetch live data. Security conditions should be verified "
                "through official OCHA channels before deploying aid resources."
            ),
            "source": "ResQ-Capital (Mock)",
            "date": "2026-02-21T00:00:00+00:00",
            "country": country,
        }
    ]


async def fetch_reliefweb_reports(
    country: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Fetch the latest situation reports from ReliefWeb for *country*.

    Returns a list of dicts: ``{title, body, source, date}``.
    Falls back to mock data when the API is unavailable.
    """
    appname = os.getenv("RELIEFWEB_APPNAME", "resq-capital")

    payload = {
        "preset": "latest",
        "limit": limit,
        "filter": {
            "field": "country.name",
            "value": [country],
        },
        "fields": {
            "include": [
                "title",
                "body",
                "source.name",
                "date.created",
                "country.name",
            ],
        },
    }

    headers = {
        "User-Agent": "ResQ-Capital/0.1 (humanitarian-hackathon)",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                RELIEFWEB_API,
                params={"appname": appname},
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "ReliefWeb API returned %s — falling back to mock data. "
            "Set RELIEFWEB_APPNAME env var with a pre-approved appname.",
            exc.response.status_code,
        )
        return _get_mock_reports(country)[:limit]
    except httpx.HTTPError as exc:
        logger.warning("ReliefWeb API unreachable (%s) — using mock data", exc)
        return _get_mock_reports(country)[:limit]

    reports: list[dict[str, Any]] = []
    for item in data.get("data", []):
        fields = item.get("fields", {})
        body = fields.get("body", "")
        if not body:
            continue
        # Strip HTML tags (lightweight)
        import re
        body_clean = re.sub(r"<[^>]+>", " ", body)
        body_clean = re.sub(r"\s+", " ", body_clean).strip()

        reports.append({
            "title": fields.get("title", ""),
            "body": body_clean,
            "source": (fields.get("source", [{}]) or [{}])[0].get("name", ""),
            "date": fields.get("date", {}).get("created", ""),
            "country": (fields.get("country", [{}]) or [{}])[0].get("name", country),
        })

    if not reports:
        logger.info("No live reports found for %s — using mock data", country)
        return _get_mock_reports(country)[:limit]

    logger.info("Fetched %d reports for %s from ReliefWeb", len(reports), country)
    return reports


# ---------------------------------------------------------------------------
# 2.  Text Chunking
# ---------------------------------------------------------------------------

_enc: tiktoken.Encoding | None = None


def _get_encoder() -> tiktoken.Encoding:
    global _enc
    if _enc is None:
        _enc = tiktoken.encoding_for_model("gpt-4o-mini")
    return _enc


def chunk_text(text: str, max_tokens: int = CHUNK_MAX_TOKENS, overlap: int = CHUNK_OVERLAP_TOKENS) -> list[str]:
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
# 3.  OpenAI Embeddings
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
# 4.  Actian VectorAI (pyodbc)
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
        conn = pyodbc.connect(f"DSN={dsn};UID={user};PWD={password}", autocommit=True)
        return conn
    except Exception as exc:
        logger.error("Failed to connect to Actian VectorAI: %s", exc)
        return None


def init_table(conn) -> None:
    """Create the vector store table if it does not already exist."""
    ddl = textwrap.dedent(f"""\
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id         INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            country    VARCHAR(120)  NOT NULL,
            title      VARCHAR(500),
            chunk_text VARCHAR(8000) NOT NULL,
            source     VARCHAR(300),
            report_date VARCHAR(60),
            embedding  VECTOR({EMBEDDING_DIM}) NOT NULL
        )
    """)
    cursor = conn.cursor()
    cursor.execute(ddl)
    cursor.close()


def store_chunks(
    conn,
    chunks: list[dict[str, Any]],
) -> int:
    """Insert pre-embedded chunks into Actian VectorAI.

    Each item in *chunks* must have keys:
        country, title, chunk_text, source, report_date, embedding (list[float])

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
    """Find the *top_k* most similar chunks to *query_embedding*.

    Optionally filter by *country*.
    Returns list of dicts with keys: title, chunk_text, source, report_date, country.
    """
    emb_str = ",".join(str(v) for v in query_embedding)
    where = f"WHERE country = ?" if country else ""
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
# 5.  High-level Orchestrators
# ---------------------------------------------------------------------------

async def ingest_country(country: str, limit: int = 10) -> int:
    """End-to-end: fetch ReliefWeb reports → chunk → embed → store in Actian.

    Returns the total number of chunks stored.
    """
    reports = await fetch_reliefweb_reports(country, limit=limit)
    if not reports:
        logger.warning("No reports found for %s", country)
        return 0

    # Chunk all reports
    all_chunks: list[dict[str, Any]] = []
    for rpt in reports:
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
        logger.warning("Actian unavailable — skipping storage for %s (%d chunks)", country, len(all_chunks))
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
    placeholder message when the database is unavailable.
    """
    country = _coords_to_country(lat, lng)

    conn = _get_actian_connection()
    if conn is None:
        return (
            f"[Fallback] Safety intelligence for {country} ({lat}, {lng}) is currently "
            "unavailable. Actian VectorAI connection not configured. "
            "Please ingest reports and configure ACTIAN_DSN to enable RAG search."
        )

    try:
        query = f"What are the current security risks and safety conditions in {country}?"
        query_emb = await embed_text(query)
        results = search_similar(conn, query_emb, country=country, top_k=5)
    finally:
        conn.close()

    if not results:
        return (
            f"No safety intelligence available for {country}. "
            "Run the /api/v1/ingest-reports endpoint to load ReliefWeb data first."
        )

    # Assemble briefing from retrieved chunks
    sections: list[str] = []
    for i, r in enumerate(results, 1):
        sections.append(
            f"[{i}] {r['title']} (Source: {r['source']}, Date: {r['report_date']})\n"
            f"{r['chunk_text'][:1500]}"
        )

    briefing = (
        f"## Safety & Security Briefing — {country}\n"
        f"Coordinates: ({lat}, {lng})\n\n"
        + "\n\n---\n\n".join(sections)
    )
    return briefing
