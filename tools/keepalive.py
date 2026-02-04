"""Simple keepalive ping for Railway services."""
import httpx
import asyncio

SERVICES = [
    "https://central-production.up.railway.app/health",
]

async def ping():
    async with httpx.AsyncClient(timeout=10) as client:
        for url in SERVICES:
            try:
                resp = await client.get(url)
                print(f"✓ {url}: {resp.status_code}")
            except Exception as e:
                print(f"✗ {url}: {e}")

if __name__ == "__main__":
    asyncio.run(ping())
