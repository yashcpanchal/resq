# ResQ-Capital

The "Arbitrage" Platform for Humanitarian Aid Allocation. ResQ-Capital identifies underfunded global crises and validates logistical/safety feasibility using vector RAG and operational intelligence.

## Layer 3 — Context Engine (Safety Intelligence)

The backend provides **operational field briefings** for humanitarian workers deploying to a specific location. Data sources:

- **GDACS** — Natural disaster alerts (earthquakes, floods, cyclones) + proximity-based nearby alerts
- **HDX (Humanitarian Data Exchange)** — Country-tagged humanitarian datasets (CKAN + HAPI)
- **US State Department** — Travel advisories and country safety/health/transport info
- **HDX HAPI** — ACLED conflict events, IPC food security by region
- **Google News RSS** — Breaking news (last 7 days), always fetched live; **city-specific** + country-level

Briefings are synthesized by **OpenRouter LLM** (default: Arcee AI Trinity Large Preview) into: *What Changed This Week* → *Operating Environment* → *Key Risks* → *Local Situation* → *Operational Recommendations*. Aimed at aid workers who are deploying regardless; focus is on how to operate safely, not whether to go.

## Layer 2 — Candidate Verification (Vision/Logistics)

The pipeline identifies viable aid drop-zones/staging areas using local machine vision:
1. **OSM Scouting** (`osm_finder.py`) — Queries OpenStreetMap for nearby schools, hospitals, open land, etc.
2. **Satellite Intelligence** (`ground_verifier.py`) — Fetches high-resolution satellite imagery (Esri) for each coordinate.
3. **VLM Validation** (`candidate_verification.py` / `Ollama`) — Feeds images into a local Vision-Language Model (`llava`) to assess ground operability (e.g., road access, rubble blockages).
4. **Visual Annotation** (`image_annotator.py`) — Draws bounding boxes and labels VLM insights on the raw image using Pillow.

## Getting Started

### 1. Python environment

```bash
py -3.13 -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
pip install actian-beta/actiancortex-0.1.0b1-py3-none-any.whl
```

### 2. Actian VectorAI and Ollama (Local AI)

For full RAG (ingest + search), run Actian in Docker:

```bash
cd actian-beta
docker compose up -d
```

Default: `localhost:50051`. Override with `ACTIAN_SERVER` if needed. If Actian is not running, the API still works using live-fetched data only.

For Layer 2 image verification, ensure **[Ollama](https://ollama.com/)** is running locally with the `llava` model:
```bash
ollama run llava
```


### 3. Environment variables

Create a `.env` file in the project root (or set in the shell):

```
OPENROUTER_API_KEY=your_openrouter_api_key
```

Get a key at [OpenRouter Keys](https://openrouter.ai/keys). Used for embeddings and briefing synthesis. Optional overrides: `OPENROUTER_EMBED_MODEL` (default `openai/text-embedding-3-large`), `OPENROUTER_CHAT_MODEL` (default `arcee-ai/trinity-large-preview:free`).

### 4. Start the server

Use the **venv** so Actian (cortex) is available:

```bash
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux
uvicorn app:app --reload
```

Or without activating: `./.venv/Scripts/python -m uvicorn app:app --reload` (Windows). Server runs at **http://localhost:8000** (or the port you specify).

## Test UI and API

- **Test UI (Layer 3):** [http://localhost:8000/test](http://localhost:8000/test) — Enter a country, click **Ingest** to load intelligence into the vector DB, then **Get safety report** for an operational field briefing.
- **Simple docs:** [http://localhost:8000/docs-simple](http://localhost:8000/docs-simple) — Lightweight API reference (no external CDN).
- **OpenAPI:** [http://localhost:8000/docs](http://localhost:8000/docs) or [http://localhost:8000/redoc](http://localhost:8000/redoc).

### Key endpoints

| Method | Endpoint | Body | Description |
|--------|----------|------|-------------|
| `GET` | `/api/v1/health` | — | Health check |
| `POST` | `/api/v1/ingest-reports` | `{"country": "Sudan"}` | Ingest GDACS, HDX, State Dept, HAPI, news for country into vector DB |
| `POST` | `/api/v1/ingest-reports-all` | `{}` | Ingest all 202 countries in background |
| `GET` | `/api/v1/countries` | — | List all supported country names |
| `POST` | `/api/v1/safety-report-by-country` | `{"country": "Sudan"}` | Operational field briefing by country name |
| `POST` | `/api/v1/safety-report` | `{"lat": 15.5, "lng": 32.5}` | Location-specific briefing (city + country data) |
| `GET` | `/api/v1/neglect-scores` | — | Neglect scores (pipeline) |
| `POST` | `/api/v1/parking-capacity` | `{"lat": 0, "lng": 0}` | Staging capacity (stub) |
| `POST` | `/api/v1/generate-memo` | Memo payload | Deployment memo (stub) |

## Project structure

```
resq/
├── app.py              # FastAPI app, routes /, /test, /docs-simple
├── api/
│   ├── routes.py       # API route handlers
│   └── schemas.py      # Pydantic request/response models
├── modules/
│   ├── candidate_verification.py # Layer 2: OSM finder + Ollama VLM verification
│   ├── context_engine.py  # Layer 3: data fetch, chunk, embed, Actian, synthesis
│   ├── country_codes.py   # ISO3 / State Dept code maps for all countries
│   ├── crisis_query.py    # Layer 3: City-level LLM queries (OpenRouter)
│   ├── ground_verifier.py # Layer 2: Ollama vision logic and Esri tiles
│   ├── image_annotator.py # Layer 2: Pillow bounding box drawing
│   ├── osm_finder.py      # Layer 2: OSM staging area finder (OSMnx/Nominatim)
│   ├── osm_features.py    # Layer 2: Extends OSM mapping logic
│   ├── pipeline.py    # Neglect scores (stub)
│   ├── vision.py      # Parking capacity (stub)
│   ├── vector.py      # Delegates to context_engine for safety report
│   └── synthesis.py   # Memo generation (stub)
├── static/
│   └── test.html      # Layer 3 test UI (country search, ingest, report)
├── actian-beta/       # Actian VectorAI Docker setup + cortex wheel
├── context.txt        # Project spec (architecture, data flow, guardrails)
├── requirements.txt
└── README.md
```

## Dependencies

- **FastAPI / Uvicorn** — API server
- **httpx** / **requests** — Async/Sync HTTP (GDACS, HDX, State Dept, Google News, OpenRouter, Esri, Ollama)
- **tiktoken** — Chunking for embeddings
- **python-dotenv** — Load `.env`
- **Pillow** — Image annotation for UI payloads
- **Actian Cortex** — Install from `actian-beta/actiancortex-*.whl` when using the vector DB

See `requirements.txt`. ReliefWeb is not used (requires pre-approved app name).
