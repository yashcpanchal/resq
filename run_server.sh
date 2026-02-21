#!/usr/bin/env bash
# Run the API server using the project venv (so Actian/cortex is available).
cd "$(dirname "$0")"
.venv/bin/python -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
