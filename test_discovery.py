import asyncio
import os
from dotenv import load_dotenv
from modules.crisis_query import get_crises_for_country

load_dotenv()

async def test():
    print("Testing get_crises_for_country for Sudan...")
    try:
        data = await get_crises_for_country("Sudan")
        print(f"Country: {data.get('country')}")
        print(f"Sources: {data.get('sources_note')}")
        print(f"Common cities: {[c['name'] for c in data.get('cities', [])]}")
        for city in data.get('cities', [])[:2]:
            print(f" - {city['name']} ({city.get('lat')}, {city.get('lng')}) - {len(city.get('needs', []))} needs")
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
