"""
ResQ-Capital — FastAPI Entry Point

Start with:  uvicorn app:app --reload
"""

import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from api.routes import router

_STATIC = Path(__file__).parent / "static"

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(name)s — %(message)s")

app = FastAPI(
    title="ResQ-Capital API",
    description="Humanitarian Aid Allocation — Arbitrage Platform",
    version="0.1.0",
)

<<<<<<< HEAD
app.include_router(router, prefix="")
=======

@app.get("/")
def root(request: Request):
    """Quick check that the server is up. Links use the same host/port you used to connect."""
    base = str(request.base_url).rstrip("/")
    return {
        "message": "ResQ-Capital API is running",
        "test_ui": f"{base}/test",
        "docs_simple": f"{base}/docs-simple",
        "health": f"{base}/api/v1/health",
    }


@app.get("/docs-simple", response_class=HTMLResponse)
def docs_simple():
    """Lightweight API docs — no external CDN, works when /docs is stuck."""
    return """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>ResQ-Capital API</title>
  <style>
    body { font-family: system-ui; max-width: 640px; margin: 2rem auto; padding: 0 1rem; }
    h1 { color: #333; }
    a { color: #0066cc; }
    pre { background: #f5f5f5; padding: 1rem; overflow: auto; }
    .endpoint { margin: 1.5rem 0; padding: 1rem; border: 1px solid #eee; border-radius: 8px; }
    .method { font-weight: bold; color: #0a0; }
    code { background: #f0f0f0; padding: 2px 6px; }
  </style>
</head>
<body>
  <h1>ResQ-Capital API</h1>
  <p>Use this page if <a href="/docs">/docs</a> or <a href="/redoc">/redoc</a> are stuck loading (they use external CDNs).</p>

  <div class="endpoint">
    <span class="method">GET</span> <code>/api/v1/health</code>
    <p>Check server is up.</p>
    <p><a href="/api/v1/health" target="_blank">Open /api/v1/health</a></p>
  </div>

  <div class="endpoint">
    <span class="method">GET</span> <code>/api/v1/neglect-scores</code>
    <p>List neglect scores (pipeline).</p>
    <p><a href="/api/v1/neglect-scores" target="_blank">Open /api/v1/neglect-scores</a></p>
  </div>

  <div class="endpoint">
    <span class="method">POST</span> <code>/api/v1/ingest-reports</code>
    <p>Body: <code>{"country": "Sudan"}</code></p>
    <p>Ingest GDACS + HDX reports for a country into the vector DB.</p>
  </div>

  <div class="endpoint">
    <span class="method">POST</span> <code>/api/v1/safety-report</code>
    <p>Body: <code>{"lat": 15.5, "lng": 32.5}</code></p>
    <p>Operational field briefing for coordinates (reverse geocode + RAG or live).</p>
  </div>

  <div class="endpoint">
    <span class="method">POST</span> <code>/api/v1/safety-report-by-country</code>
    <p>Body: <code>{"country": "Sudan"}</code></p>
    <p>Operational field briefing by country name (forward geocode then same pipeline).</p>
  </div>

  <div class="endpoint">
    <span class="method">POST</span> <code>/api/v1/parking-capacity</code>
    <p>Body: <code>{"lat": 0.0, "lng": 0.0}</code></p>
  </div>

  <div class="endpoint">
    <span class="method">POST</span> <code>/api/v1/generate-memo</code>
    <p>Body: full memo payload (see OpenAPI schema).</p>
  </div>

  <p>Raw OpenAPI schema: <a href="/openapi.json" target="_blank">/openapi.json</a></p>
</body>
</html>
"""


@app.get("/test", response_class=HTMLResponse)
def test_ui():
    """Layer 3 test UI: search by country, ingest or get safety report."""
    return (_STATIC / "test.html").read_text(encoding="utf-8")


app.include_router(router, prefix="/api/v1")
>>>>>>> 592d5f732bddbd7462b0310394798fcbe260abbf
