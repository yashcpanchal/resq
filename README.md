# ResQ-Capital

The "Arbitrage" Platform for Humanitarian Aid Allocation. ResQ-Capital identifies underfunded global crises using Databricks and validates logistical/safety feasibility using computer vision and vector RAG.

## Getting Started

### 1. Create & activate the virtual environment

```bash
py -3.13 -m venv .venv
.venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Start the backend server

```bash
uvicorn app:app --reload
```

The server will start at **http://localhost:8000**. Interactive API docs are available at **http://localhost:8000/docs**.

## Testing with Postman

Once the server is running, import or manually create the following requests:

| Method | URL | Body |
|--------|-----|------|
| `GET` | `http://localhost:8000/api/v1/health` | — |
| `GET` | `http://localhost:8000/api/v1/neglect-scores` | — |
| `POST` | `http://localhost:8000/api/v1/parking-capacity` | `{"lat": 0.0, "lng": 0.0}` |
| `POST` | `http://localhost:8000/api/v1/safety-report` | `{"lat": 0.0, "lng": 0.0}` |
| `POST` | `http://localhost:8000/api/v1/generate-memo` | `{"crisis_id": "test-001", "country": "Test", "coordinates": {"lat": 0.0, "lng": 0.0}, "neglect_score": 0.5, "severity": 3, "funding_gap_usd": 100000, "parking_capacity": 10, "safety_report": "Stable"}` |

For all `POST` requests, set the **Content-Type** header to `application/json`.
