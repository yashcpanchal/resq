# ResQ-Capital

The "Arbitrage" Platform for Humanitarian Aid Allocation. ResQ-Capital identifies underfunded global crises and validates logistical/safety feasibility using vector RAG and operational intelligence.

## Layer 3 — Context Engine (Safety Intelligence)

The backend provides **operational field briefings** for humanitarian workers deploying to a country. Data sources:

- **GDACS** — Natural disaster alerts (earthquakes, floods, cyclones)
- **HDX (Humanitarian Data Exchange)** — Country-tagged humanitarian datasets (CKAN + HAPI)
- **US State Department** — Travel advisories and country safety/health/transport info
- **HDX HAPI** — ACLED conflict events, IPC food security by region
- **Google News RSS** — Breaking news (last 7 days), always fetched live

Briefings are synthesized by **Gemini** into: *What Changed This Week* → *Operating Environment* → *Key Risks* → *Operational Recommendations*. Aimed at aid workers who are deploying regardless; focus is on how to operate safely, not whether to go.

## Getting Started

### 1. Python environment

```bash
py -3.13 -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

### 2. Actian VectorAI (optional but recommended for RAG)

For full RAG (ingest + search), run Actian in Docker:

```bash
cd actian-beta
docker compose up -d
```

Default: `localhost:50051`. Override with `ACTIAN_SERVER` if needed. If Actian is not running, the API still works using live-fetched data only.

### 3. Environment variables

Create a `.env` file in the project root (or set in the shell):

```
GEMINI_API_KEY=your_google_ai_api_key
```

Used for embeddings (Gemini) and briefing synthesis. Get a key at [Google AI Studio](https://aistudio.google.com/apikey).

### 4. Start the server

```bash
uvicorn app:app --reload
```

Server runs at **http://localhost:8000** (or the port you specify, e.g. `--port 8010`).

## Test UI and API

- **Test UI (Layer 3):** [http://localhost:8000/test](http://localhost:8000/test) — Enter a country, click **Ingest** to load intelligence into the vector DB, then **Get safety report** for an operational field briefing.
- **Simple docs:** [http://localhost:8000/docs-simple](http://localhost:8000/docs-simple) — Lightweight API reference (no external CDN).
- **OpenAPI:** [http://localhost:8000/docs](http://localhost:8000/docs) or [http://localhost:8000/redoc](http://localhost:8000/redoc).

### Key endpoints

| Method | Endpoint | Body | Description |
|--------|----------|------|-------------|
| `GET` | `/api/v1/health` | — | Health check |
| `POST` | `/api/v1/ingest-reports` | `{"country": "Sudan"}` | Ingest GDACS, HDX, State Dept, HAPI, news for country into vector DB |
| `POST` | `/api/v1/safety-report-by-country` | `{"country": "Sudan"}` | Operational field briefing by country name |
| `POST` | `/api/v1/safety-report` | `{"lat": 15.5, "lng": 32.5}` | Same briefing by coordinates |
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
│   ├── context_engine.py  # Layer 3: data fetch, chunk, embed, Actian, Gemini synthesis
│   ├── pipeline.py    # Neglect scores (stub)
│   ├── vision.py      # Parking capacity (stub)
│   ├── vector.py      # Delegates to context_engine for safety report
│   └── synthesis.py   # Memo generation (stub)
├── static/
│   └── test.html      # Layer 3 test UI (country search, ingest, report)
├── context.txt        # Project spec (architecture, data flow, guardrails)
├── requirements.txt
└── README.md
```

## Dependencies

- **FastAPI / Uvicorn** — API server
- **httpx** — Async HTTP (GDACS, HDX, State Dept, Google News, Gemini REST)
- **tiktoken** — Chunking for embeddings
- **python-dotenv** — Load `.env`
- **Actian Cortex** — Install from `actian-beta/actiancortex-*.whl` when using the vector DB

See `requirements.txt`. ReliefWeb is not used (requires pre-approved app name).
