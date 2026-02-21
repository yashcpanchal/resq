"""
ResQ-Capital — FastAPI Entry Point

Start with:  uvicorn app:app --reload
"""

from dotenv import load_dotenv
from fastapi import FastAPI

from api.routes import router

load_dotenv()

app = FastAPI(
    title="ResQ-Capital API",
    description="Humanitarian Aid Allocation — Arbitrage Platform",
    version="0.1.0",
)

app.include_router(router, prefix="")
