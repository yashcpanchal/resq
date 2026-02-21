"""
Pydantic models — Data Contracts for the ResQ-Capital API.

These schemas enforce the structure defined in context.md and serve
as the single source of truth for request/response shapes.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------- Pipeline (P1) ---------- #

class Coordinates(BaseModel):
    lat: float
    lng: float


class NeglectScore(BaseModel):
    crisis_id: str
    country: str
    coordinates: Coordinates
    neglect_score: float = Field(..., ge=0)
    severity: int = Field(..., ge=0)
    funding_gap_usd: int = Field(..., ge=0)


# ---------- Vision (P2) ---------- #

class ParkingRequest(BaseModel):
    lat: float
    lng: float


class ParkingResponse(BaseModel):
    lat: float
    lng: float
    capacity: int


# ---------- Vector (P2) ---------- #

class SafetyRequest(BaseModel):
    lat: float
    lng: float


class SafetyResponse(BaseModel):
    lat: float
    lng: float
    report: str


# ---------- Synthesis (P3) ---------- #

class MemoRequest(BaseModel):
    crisis_id: str
    country: str
    coordinates: Coordinates
    neglect_score: float
    severity: int
    funding_gap_usd: int
    parking_capacity: int
    safety_report: str


class MemoResponse(BaseModel):
    crisis_id: str
    memo: str


# ---------- Visionary (Humanitarian Aid Sites) ---------- #

class AidSiteRequest(BaseModel):
    lat: float
    lng: float
    radius_m: int = Field(default=5000, ge=100, le=20000)
    max_sites: int = Field(default=10, ge=1, le=50)
    model: str = Field(default="moondream", description="Ollama vision model name")


class AidSiteCandidate(BaseModel):
    name: str
    category: str
    lat: float
    lng: float
    osm_id: str
    analysis: str = ""


class AidSiteResponse(BaseModel):
    lat: float
    lng: float
    radius_m: int
    total_candidates: int
    analyzed_candidates: int
    sites: list[AidSiteCandidate]

