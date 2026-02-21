# ResQ-Capital

The "Arbitrage" Platform for Humanitarian Aid Allocation. ResQ-Capital identifies underfunded global crises and validates logistical/safety feasibility using vector RAG and operational intelligence.

## Layer 3 — Context Engine (Safety Intelligence)

The backend provides **operational field briefings** for humanitarian workers deploying to a specific location. Data sources:

- **GDACS** — Natural disaster alerts (earthquakes, floods, cyclones) + proximity-based nearby alerts; **proximity-based** (within 500 km) for lat/lng reports
- **HDX (Humanitarian Data Exchange)** — Country-tagged humanitarian datasets (CKAN + HAPI), filtered by ISO3
- **US State Department** — Travel advisories and country safety/health/transport info
- **HDX HAPI** — ACLED conflict events, IPC food security by region
- **Google News RSS** — Breaking news (last 7 days), always fetched live; **city-specific** + country-level

Briefings are synthesized by **OpenRouter LLM** (default: Arcee AI Trinity Large Preview) into: *What Changed This Week* → *Operating Environment* → *Key Risks* → *Local Situation* → *Operational Recommendations*. Aimed at aid workers who are deploying regardless; focus is on how to operate safely, not whether to go.

**Layer 3 ingest flow:** Ingest loads GDACS, HDX, State Dept, HAPI, and News for a country into the Actian vector DB. Get report uses RAG (stored chunks) plus live city-level news and nearby GDACS, then synthesizes with the LLM. If the vector DB is empty, the report uses live-fetched data only. The app **auto-recovers** from Actian collection corruption (recreates the collection and retries ingest).

## Prerequisites

- **Python 3.13+**
- **Node.js 18+** and **npm**
- **Docker** (optional, for Actian VectorAI)

## Quickstart

### 1. Clone and set up environment variables

```bash
git clone <repo-url> && cd resq
cp .env.example .env
```

Edit `.env` and add your [OpenRouter API key](https://openrouter.ai/keys):

```
OPENROUTER_API_KEY=your_key_here
```

Optional overrides: `OPENROUTER_EMBED_MODEL` (default `openai/text-embedding-3-large`), `OPENROUTER_CHAT_MODEL` (default `arcee-ai/trinity-large-preview:free`), `ACTIAN_SERVER` (default `localhost:50051`).

### 2. Backend (Python / FastAPI)

```bash
# Create and activate virtual environment
py -3.13 -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# (Optional) Install Actian VectorAI for full RAG support
pip install actian-beta/actiancortex-0.1.0b1-py3-none-any.whl

# Start the API server
uvicorn app:app --reload
```

The API runs at **http://localhost:8000**. Without activating the venv you can also run: `.venv\Scripts\python -m uvicorn app:app --reload`, or use `.\run_server.ps1` (Windows) / `./run_server.sh` (macOS/Linux).

### 3. Frontend (Next.js)

```bash
cd resq-frontend
npm install
npm run dev
```

The frontend dev server runs at **http://localhost:3000**.

### 4. Actian VectorAI (optional)

For full RAG (ingest + vector search), run Actian in Docker:

```bash
cd actian-beta
docker compose up -d
```

If Actian is not running, the API still works using live-fetched data only. The app **auto-recovers** from Actian collection corruption (recreates the collection and retries ingest).

## API Reference

- **Test UI (Layer 3):** [http://localhost:8000/test](http://localhost:8000/test) — Enter a country, ingest data, get an operational briefing.
- **OpenAPI docs:** [http://localhost:8000/docs](http://localhost:8000/docs) · [ReDoc](http://localhost:8000/redoc) · [Simple docs](http://localhost:8000/docs-simple)

### Key endpoints

| Method | Endpoint | Body | Description |
|--------|----------|------|-------------|
| `GET` | `/api/v1/health` | — | Health check |
| `POST` | `/api/v1/ingest-reports` | `{"country": "Sudan"}` | Ingest GDACS, HDX, State Dept, HAPI, news into vector DB |
| `POST` | `/api/v1/ingest-reports-all` | `{}` | Ingest all 202 countries (background) |
| `GET` | `/api/v1/countries` | — | List all supported country names |
| `POST` | `/api/v1/safety-report-by-country` | `{"country": "Sudan"}` | Operational field briefing by country |
| `POST` | `/api/v1/safety-report` | `{"lat": 15.5, "lng": 32.5}` | Location-specific briefing (city + country + nearby disasters) |
| `GET` | `/api/v1/neglect-scores` | — | Neglect scores (pipeline) |
| `POST` | `/api/v1/parking-capacity` | `{"lat": 0, "lng": 0}` | Staging capacity (stub) |
| `POST` | `/api/v1/generate-memo` | Memo payload | Deployment memo (stub) |

## Project structure

```
resq/
├── app.py                    # FastAPI app entry point
├── api/
│   ├── routes/
│   │   ├── __init__.py       # Aggregates all sub-routers
│   │   ├── context_engine.py # Ingest & safety-report routes
│   │   ├── pipeline.py       # Neglect-score routes
│   │   ├── synthesis.py      # Memo generation routes
│   │   └── vision.py         # Parking capacity routes
│   └── schemas.py            # Pydantic request/response models
├── modules/
│   ├── context_engine.py     # Data fetch, chunk, embed, Actian, OpenRouter synthesis
│   ├── country_codes.py      # ISO3 / State Dept code maps (202 countries)
│   ├── pipeline.py          # Neglect scores
│   ├── vision.py             # Parking capacity
│   ├── vector.py             # Delegates to context_engine for safety report
│   └── synthesis.py          # Memo generation
├── resq-frontend/            # Next.js frontend
│   ├── app/                  # App router pages
│   ├── components/         # React components
│   ├── lib/                  # Utilities
│   └── package.json
├── static/                   # Backend test UI
├── actian-beta/             # Actian VectorAI Docker setup + cortex wheel
├── data/                     # Data files
├── run_server.ps1            # Start backend with venv (Windows)
├── run_server.sh             # Start backend with venv (macOS/Linux)
├── requirements.txt         # Python dependencies (pinned)
└── .env.example             # Environment variable template
```

## Dependencies

**Backend** — see `requirements.txt`:
- **FastAPI / Uvicorn** — API server
- **httpx** — Async HTTP (GDACS, HDX, State Dept, Google News, OpenRouter)
- **tiktoken** — Chunking for embeddings
- **python-dotenv** — Environment config
- **Actian Cortex** *(optional)* — Vector DB, install from `actian-beta/actiancortex-*.whl`

**Layer 3** uses **OpenRouter only** for embeddings and briefing synthesis (no Gemini). Set `OPENROUTER_API_KEY` in `.env`.

**Frontend** — see `resq-frontend/package.json`:
- **Next.js / React** — UI framework
- **Framer Motion** — Animations
- **React Globe GL** — 3D globe visualization
- **TanStack React Query** — Data fetching
- **Radix UI / shadcn** — Component library
- **Tailwind CSS** — Styling
