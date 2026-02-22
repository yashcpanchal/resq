"""Quick check: crisis query for Ukraine."""
import asyncio
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

try:
    from dotenv import load_dotenv
    for path in (Path(__file__).resolve().parent / ".env", Path(__file__).resolve().parent / "resq" / ".env"):
        if path.exists():
            load_dotenv(path)
            break
    else:
        load_dotenv()
except ImportError:
    pass

from modules.crisis_query import get_crises_for_country


async def main():
    print(f"OPENROUTER_API_KEY: {'set' if os.getenv('OPENROUTER_API_KEY') else 'MISSING'}")
    print()
    print("=" * 70)
    print("  UKRAINE -- Humanitarian Crisis Assessment")
    print("=" * 70)

    data = await get_crises_for_country("Ukraine")

    print(f"\nSources: {data.get('sources_note', '(none)')}")
    print(f"Cities/areas identified: {len(data['cities'])}")

    for city in data["cities"]:
        print(f"\n{'-' * 60}")
        print(f"  >> {city['name']}")
        print(f"{'-' * 60}")
        for need in city.get("needs", []):
            sev = need.get("severity", "?").upper()
            print(f"\n  [{sev}] {need['sector']}")
            print(f"  {need['description']}")
            if need.get("affected_population"):
                print(f"  Affected: {need['affected_population']}")
            if need.get("funding_gap"):
                print(f"  Funding: {need['funding_gap']}")


if __name__ == "__main__":
    asyncio.run(main())
