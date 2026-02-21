# ResQ-Capital

The "Arbitrage" Platform for Humanitarian Aid Allocation. ResQ-Capital identifies underfunded global crises and validates logistical/safety feasibility using vector RAG and operational intelligence.

## Layer 3 — Context Engine (Safety Intelligence)

The backend provides **operational field briefings** for humanitarian workers deploying to a specific location. Data sources:

- **GDACS** — Natural disaster alerts (earthquakes, floods, cyclones); country-filtered for ingest, **proximity-based** (within 500 km) for lat/lng reports
- **HDX (Humanitarian Data Exchange)** — Country-tagged humanitarian datasets (CKAN + HAPI), filtered by ISO3
- **US State Department** — Travel advisories and country safety/health/transport info
- **HDX HAPI** — ACLED conflict events, IPC food security by region
- **Google News RSS** — Breaking news (last 7 days), always fetched live; **city-specific** + country-level for coordinates

Briefings are synthesized by **OpenRouter** (default: Arcee AI Trinity Large Preview) into: *What Changed This Week* → *Operating Environment* → *Key Risks* → *Local Situation* → *Operational Recommendations*. Aimed at aid workers who are deploying regardless; focus is on how to operate safely, not whether to go.

**Ingest flow:** Ingest loads GDACS, HDX, State Dept, HAPI, and News for a country into the Actian vector DB. Get report uses RAG (stored chunks) plus live city-level news and nearby GDACS, then synthesizes with the LLM. If the vector DB is empty, the report uses live-fetched data only.

---

## Getting Started

### 1. Python environment

```bash
py -3.13 -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
pip install actian-beta/actiancortex-0.1.0b1-py3-none-any.whl
```

Use the **venv** when running the server so the Actian Cortex client is available.

### 2. Actian VectorAI (optional but recommended for RAG)

For full RAG (ingest + search), run Actian in Docker:

```bash
cd actian-beta
docker compose up -d
```

Default: `localhost:50051`. Override with `ACTIAN_SERVER` in `.env` if needed. If Actian is not running, the API still works using live-fetched data only. The app **auto-recovers** from Actian collection corruption (recreates the collection and retries ingest).

### 3. Environment variables

Create a `.env` file in the project root:

```
OPENROUTER_API_KEY=your_openrouter_api_key
```

Get a key at [OpenRouter Keys](https://openrouter.ai/keys). Used for embeddings and briefing synthesis. Optional: `OPENROUTER_EMBED_MODEL` (default `openai/text-embedding-3-large`), `OPENROUTER_CHAT_MODEL` (default `arcee-ai/trinity-large-preview:free`).

### 4. Start the server

```bash
.venv\Scripts\activate
uvicorn app:app --reload
```

Or without activating: `.\run_server.ps1` (Windows) or `./run_server.sh` (macOS/Linux). Server runs at **http://localhost:8000**.

---

## Test UI and API

- **Test UI (Layer 3):** [http://localhost:8000/test](http://localhost:8000/test) — Enter a country (e.g. Nigeria, Sudan), click **Ingest** to load intelligence into the vector DB, then **Get safety report** for an operational briefing.
- **Simple docs:** [http://localhost:8000/docs-simple](http://localhost:8000/docs-simple)
- **OpenAPI:** [http://localhost:8000/docs](http://localhost:8000/docs) or [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Key endpoints

| Method | Endpoint | Body | Description |
|--------|----------|------|-------------|
| `GET` | `/api/v1/health` | — | Health check |
| `POST` | `/api/v1/ingest-reports` | `{"country": "Sudan"}` | Ingest GDACS, HDX, State Dept, HAPI, news for country into vector DB |
| `POST` | `/api/v1/ingest-reports-all` | `{}` | Ingest all 202 countries in background |
| `GET` | `/api/v1/countries` | — | List all supported country names |
| `POST` | `/api/v1/safety-report-by-country` | `{"country": "Sudan"}` | Operational field briefing by country name |
| `POST` | `/api/v1/safety-report` | `{"lat": 15.5, "lng": 32.5}` | Location-specific briefing (city + country + nearby disasters) |
| `GET` | `/api/v1/neglect-scores` | — | Neglect scores (pipeline) |
| `POST` | `/api/v1/parking-capacity` | `{"lat": 0, "lng": 0}` | Staging capacity (stub) |
| `POST` | `/api/v1/generate-memo` | Memo payload | Deployment memo (stub) |

---

## Project structure

```
resq/
├── app.py                 # FastAPI app; routes /, /test, /docs-simple
├── api/
│   ├── routes.py          # API route handlers
│   └── schemas.py         # Pydantic request/response models
├── modules/
│   ├── context_engine.py  # Layer 3: fetch, chunk, embed (OpenRouter), Actian, synthesis
│   ├── country_codes.py   # ISO3 / State Dept code maps (202 countries)
│   ├── pipeline.py        # Neglect scores (stub)
│   ├── vision.py          # Parking capacity (stub)
│   ├── vector.py          # Delegates safety report to context_engine
│   └── synthesis.py       # Memo generation (stub)
├── static/
│   └── test.html          # Layer 3 test UI
├── actian-beta/           # Actian VectorAI Docker + cortex wheel
├── context.txt            # Project spec (architecture, data flow, guardrails)
├── requirements.txt
├── run_server.ps1         # Start server with venv (Windows)
├── run_server.sh          # Start server with venv (macOS/Linux)
└── README.md
```

---

## Dependencies

- **fastapi**, **uvicorn** — API server
- **httpx** — Async HTTP (GDACS, HDX, State Dept, Google News, OpenRouter)
- **tiktoken** — Chunking for embeddings
- **python-dotenv** — Load `.env`
- **pydantic** — Request/response schemas
- **Actian Cortex** — Install from `actian-beta/actiancortex-0.1.0b1-py3-none-any.whl` when using the vector DB

ReliefWeb is not used (requires pre-approved app name).
