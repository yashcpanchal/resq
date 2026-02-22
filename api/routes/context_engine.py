import json
import time
import hashlib
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse

from api.schemas import (
    IngestRequest,
    IngestResponse,
    SafetyByCountryRequest,
    SafetyByCountryResponse,
    SafetyRequest,
    SafetyResponse,
    CountryCrisesRequest,
    CountryCrisesResponse,
)
from modules.vector import get_safety_report
from modules.context_engine import (
    ingest_country,
    ingest_all_countries,
    get_safety_report_by_country,
)
from modules.crisis_query import get_crises_for_country
from modules.country_codes import list_all_countries

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Persistent file-based cache for Safety Reports
# ---------------------------------------------------------------------------
# Anchor to the project root (where app.py lives) — reliable regardless of
# how uvicorn resolves __file__ during --reload.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CACHE_DIR = _PROJECT_ROOT / "data" / "safety_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
logger.info("Safety cache directory: %s (exists=%s)", _CACHE_DIR, _CACHE_DIR.exists())

_CACHE_TTL = 3600  # 1 hour
_COORD_PRECISION = 4  # ~11m precision for cache keys

def _get_safety_cache_path(lat: float, lng: float) -> Path:
    """Create a unique hash for the location."""
    key = f"{round(lat, _COORD_PRECISION)},{round(lng, _COORD_PRECISION)}"
    h = hashlib.md5(key.encode()).hexdigest()
    return _CACHE_DIR / f"{h}.json"

def _load_safety_cache(lat: float, lng: float) -> str | None:
    path = _get_safety_cache_path(lat, lng)
    if not path.exists():
        return None
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - entry.get("ts", 0) < _CACHE_TTL:
            return entry.get("report")
    except Exception:
        pass
    return None

def _save_safety_cache(lat: float, lng: float, report: str):
    path = _get_safety_cache_path(lat, lng)
    print(f"[CACHE-DEBUG] save called for ({lat}, {lng}) -> {path}")
    try:
        data = json.dumps({"report": report, "ts": time.time()}, ensure_ascii=False)
        print(f"[CACHE-DEBUG] json.dumps OK, {len(data)} chars")
        path.write_text(data, encoding="utf-8")
        print(f"[CACHE-DEBUG] write_text OK, file exists={path.exists()}, size={path.stat().st_size}")
        logger.info("Saved safety cache → %s (%d bytes)", path.name, path.stat().st_size)
    except Exception as e:
        import traceback
        print(f"[CACHE-DEBUG] EXCEPTION: {e}")
        traceback.print_exc()
        logger.warning("Failed to save safety cache: %s", e)


# ---- Layer 1.5 (City-level Discovery) ---- #

@router.post("/crises-by-country")
async def crises_by_country(req: CountryCrisesRequest):
    """Identify cities with humanitarian needs for a given country."""
    try:
        data = await get_crises_for_country(req.country)
        logger.info("crises-by-country: %s → %d cities", req.country, len(data.get("cities", [])))
        return JSONResponse(content=data)
    except Exception as exc:
        logger.exception("crises-by-country failed for %s", req.country)
        return JSONResponse(
            content={"country": req.country, "cities": [], "sources_note": f"Error: {exc}"},
            status_code=200,
        )


# ---- Vector / RAG ---- #

@router.post("/safety-report", response_model=SafetyResponse)
async def safety_report(req: SafetyRequest):
    """Generate a safety report for given coordinates via RAG. Cached for 1hr."""
    print(f"[CACHE-DEBUG] safety_report called ({req.lat}, {req.lng})")
    cached = _load_safety_cache(req.lat, req.lng)
    if cached:
        print(f"[CACHE-DEBUG] HIT - returning cached ({len(cached)} chars)")
        logger.info("Safety cache hit for (%.4f, %.4f)", req.lat, req.lng)
        return SafetyResponse(lat=req.lat, lng=req.lng, report=cached)

    print(f"[CACHE-DEBUG] MISS - generating report...")
    report = await get_safety_report(req.lat, req.lng)
    print(f"[CACHE-DEBUG] Report generated: {len(report)} chars. Saving...")
    _save_safety_cache(req.lat, req.lng, report)
    return SafetyResponse(lat=req.lat, lng=req.lng, report=report)


# ---- Context Engine (L3) ---- #

@router.post("/ingest-reports", response_model=IngestResponse)
async def ingest_reports(req: IngestRequest):
    """Ingest GDACS, HDX, US State Dept, HAPI and news for a country into Actian VectorAI."""
    count = await ingest_country(req.country)
    return IngestResponse(country=req.country, chunks_ingested=count)


@router.get("/countries")
async def countries_list():
    """Return all country names supported for ingest and safety reports."""
    return {"countries": list_all_countries()}


@router.post("/ingest-reports-all", status_code=202)
async def ingest_reports_all(background_tasks: BackgroundTasks):
    """Start ingesting all countries in the background (delay 6s between each). Check server logs for progress."""
    n = len(list_all_countries())
    background_tasks.add_task(ingest_all_countries, 6.0, None)
    return {"message": f"Started ingesting {n} countries in background. Check server logs for progress."}


@router.post("/safety-report-by-country", response_model=SafetyByCountryResponse)
async def safety_report_by_country(req: SafetyByCountryRequest):
    """Get safety report by country name (forward-geocodes to coordinates, then RAG/live)."""
    report, lat, lng = await get_safety_report_by_country(req.country)
    return SafetyByCountryResponse(country=req.country, lat=lat, lng=lng, report=report)
