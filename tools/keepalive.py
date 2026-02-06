"""Keepalive ping for Railway services. Retries on failure to handle cold starts."""
import httpx
import asyncio
from datetime import datetime, timezone

SERVICES = [
    "https://central-production.up.railway.app/health",
]

# Retry config: 3 attempts, 15s between, 30s timeout per request
MAX_RETRIES = 3
RETRY_DELAY = 15
REQUEST_TIMEOUT = 30


async def ping():
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for url in SERVICES:
            success = False
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        print(f"[{timestamp}] ✓ {url}: {resp.status_code}")
                        success = True
                        break
                    else:
                        print(f"[{timestamp}] ⚠ {url}: {resp.status_code} (attempt {attempt}/{MAX_RETRIES})")
                except Exception as e:
                    print(f"[{timestamp}] ✗ {url}: {e} (attempt {attempt}/{MAX_RETRIES})")
                
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
            
            if not success:
                print(f"[{timestamp}] ❌ {url}: FAILED after {MAX_RETRIES} attempts")


if __name__ == "__main__":
    asyncio.run(ping())
