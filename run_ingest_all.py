"""
Ingest all countries into Actian VectorAI (Layer 3).

Run from project root with the venv activated:
  .venv\\Scripts\\python.exe run_ingest_all.py

Uses a 25-second delay between countries to stay under Gemini free-tier rate limits.
On 429, embedding retries after 30s/60s/90s. Logs progress to stdout.
Run with:  .venv\\Scripts\\python.exe run_ingest_all.py
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from modules.context_engine import ingest_all_countries
from modules.country_codes import list_all_countries

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# Delay between countries (seconds). ~25s keeps embed calls under Gemini free-tier RPM.
DELAY_BETWEEN_COUNTRIES = 25.0


async def main():
    countries = list_all_countries()
    print(f"Ingesting {len(countries)} countries ({DELAY_BETWEEN_COUNTRIES}s delay between each).")
    print("On 429, embedding will retry after 30s/60s/90s. Ctrl+C to stop.")
    result = await ingest_all_countries(delay_seconds=DELAY_BETWEEN_COUNTRIES, countries=countries)
    print(f"Done. Ingested {result['ingested']} countries, {result['total_chunks']} total chunks.")
    return result


if __name__ == "__main__":
    asyncio.run(main())
