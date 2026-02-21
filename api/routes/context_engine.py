"""
Context Engine Routes — Ingest, safety reports, and country lookups.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from api.schemas import (
    IngestRequest,
    IngestResponse,
    SafetyByCountryRequest,
    SafetyByCountryResponse,
    SafetyRequest,
    SafetyResponse,
)
from modules.vector import get_safety_report
from modules.context_engine import (
    ingest_country,
    ingest_all_countries,
    get_safety_report_by_country,
)
from modules.country_codes import list_all_countries

router = APIRouter()


# ---- Vector / RAG ---- #

@router.post("/safety-report", response_model=SafetyResponse)
async def safety_report(req: SafetyRequest):
    """Generate a safety report for given coordinates via RAG."""
    report = await get_safety_report(req.lat, req.lng)
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
