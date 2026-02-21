"""
Synthesis Routes — Memo generation endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas import MemoRequest, MemoResponse
from modules.synthesis import generate_memo

router = APIRouter()


@router.post("/generate-memo", response_model=MemoResponse)
async def memo(req: MemoRequest):
    """Generate a deployment plan memo from aggregated data."""
    text = await generate_memo(req.model_dump())
    return MemoResponse(crisis_id=req.crisis_id, memo=text)
