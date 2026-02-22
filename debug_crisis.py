"""Debug script: capture raw LLM output for crisis query."""
import asyncio
import json
from dotenv import load_dotenv
load_dotenv()

from modules.context_engine import generate_with_openrouter
from modules.crisis_query import SYSTEM, PROMPT_TEMPLATE, _parse_response, _current_date_str

async def main():
    country = "Sudan"
    date = _current_date_str()
    prompt = SYSTEM + "\n\n" + PROMPT_TEMPLATE.format(country=country, date=date)
    
    print(f"=== Prompt length: {len(prompt)} chars ===")
    print(f"=== Calling generate_with_openrouter... ===")
    
    raw = await generate_with_openrouter(prompt, max_tokens=4000)
    
    print(f"\n=== Raw response type: {type(raw)} ===")
    print(f"=== Raw response length: {len(raw) if raw else 0} ===")
    
    if raw:
        print(f"\n=== First 500 chars of raw response ===")
        print(raw[:500])
        print(f"\n=== Last 200 chars of raw response ===")
        print(raw[-200:])
    else:
        print("=== RAW IS EMPTY OR NONE ===")
    
    print(f"\n=== Parsing response... ===")
    data = _parse_response(country, raw or "")
    print(f"=== Cities found: {len(data.get('cities', []))} ===")
    
    if data.get("cities"):
        for c in data["cities"][:3]:
            print(f"  - {c['name']}: {len(c.get('needs', []))} needs")
    else:
        print("=== NO CITIES PARSED ===")
        # Try to parse the raw JSON manually to see what structure we got
        if raw:
            try:
                parsed = json.loads(raw.strip())
                print(f"=== Manual JSON parse keys: {list(parsed.keys())} ===")
                if "cities" in parsed:
                    print(f"=== Manual parse found {len(parsed['cities'])} cities ===")
                    if parsed["cities"]:
                        print(f"=== First city keys: {list(parsed['cities'][0].keys())} ===")
            except Exception as e:
                print(f"=== Manual JSON parse also failed: {e} ===")

if __name__ == "__main__":
    asyncio.run(main())
