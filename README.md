# ResQ-Capital

The "Arbitrage" Platform for Humanitarian Aid Allocation. ResQ-Capital identifies underfunded global crises and validates logistical/safety feasibility using computer vision and vector RAG.

## Features

- **Backend (FastAPI):** Pipeline (funding/neglect scores), vision (parking capacity, satellite imagery), tactical analysis (Ollama VLM + OSM overlay), aid-site search, safety RAG, memo synthesis.
- **Frontend (Next.js):** 3D globe with country click, side panel with country info and “Run VLM Analysis,” tactical grid page with satellite map and OSM features (staging/access/operations/risk).

## Getting Started

### Backend (Python)

1. **Create and activate a virtual environment**

   ```bash
   py -3.13 -m venv .venv
   .venv\Scripts\activate
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Start the API server**

   ```bash
   uvicorn app:app --host 127.0.0.1 --port 8000
   ```

   The API will be at **http://localhost:8000**. Interactive docs: **http://localhost:8000/docs**.

### Frontend (Next.js)

1. **Install and run**

   ```bash
   cd resq-frontend
   npm install
   npm run dev
   ```

   The app will be at **http://localhost:3000**. The dev server rewrites `/api/*` to the backend (port 8000).

### Optional: Tactical analysis (VLM + OSM)

- **Ollama:** Install [Ollama](https://ollama.ai) and pull a vision model, e.g. `ollama pull llava` (used by tactical analysis).
- **Funding data:** To show funding scores on the globe, add `data/funding/fts_requirements_funding_globalcluster_global.csv`. If missing, the API returns an empty map and the app still runs.

## API overview

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Liveness |
| `GET` | `/api/v1/funding-scores` | Per-country funding score (empty if CSV missing) |
| `GET` | `/api/v1/neglect-scores` | Neglect scores list |
| `POST` | `/api/v1/tactical-analysis` | VLM + OSM tactical grid (lat, lng, name?, model?) — can take 1–2 min |
| `POST` | `/api/v1/aid-sites` | Aid site candidates + VLM analysis (lat, lng, radius_m?, max_sites?, model?) |
| `POST` | `/api/v1/parking-capacity` | `{"lat": 0.0, "lng": 0.0}` |
| `POST` | `/api/v1/safety-report` | `{"lat": 0.0, "lng": 0.0}` |
| `POST` | `/api/v1/generate-memo` | Memo request body |

For all `POST` requests, set **Content-Type** to `application/json`.

## Testing with Postman

Use base URL `http://localhost:8000` (or `http://localhost:3000` for proxied `/api`). Examples:

- `GET` `http://localhost:8000/api/v1/health`
- `GET` `http://localhost:8000/api/v1/funding-scores`
- `POST` `http://localhost:8000/api/v1/tactical-analysis` with body: `{"lat": 15.5, "lng": 32.56, "name": "Khartoum"}`
