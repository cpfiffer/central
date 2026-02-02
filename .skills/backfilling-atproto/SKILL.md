---
name: backfilling-atproto
description: Backfill records from ATProto PDS for custom collections. Use when indexing historical data, migrating records, or syncing from a PDS. Covers public API vs PDS differences and pagination patterns.
---

# Backfilling ATProto Records

Guide for retrieving historical records from ATProto for custom collections.

## Key Insight: PDS vs Public API

**Public API** (`public.api.bsky.app`):
- Works for `app.bsky.*` collections
- Returns 404 for custom collections (e.g., `network.comind.*`)

**PDS Direct** (e.g., `comind.network`):
- Works for ALL collections including custom ones
- Required for `network.comind.*`, `stream.thought.*`, etc.

## Finding the PDS

1. Resolve handle to DID:
```python
resp = httpx.get(
    "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile",
    params={"actor": "central.comind.network"}
)
did = resp.json()["did"]
```

2. Get DID document to find PDS:
```python
resp = httpx.get(f"https://plc.directory/{did}")
pds = resp.json()["service"][0]["serviceEndpoint"]
# Returns: https://comind.network
```

## Listing Records

```python
def list_records(pds: str, did: str, collection: str):
    """List all records in a collection with pagination."""
    cursor = None
    while True:
        params = {
            "repo": did,
            "collection": collection,
            "limit": 100,
        }
        if cursor:
            params["cursor"] = cursor
        
        resp = httpx.get(
            f"{pds}/xrpc/com.atproto.repo.listRecords",
            params=params,
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        
        for record in data.get("records", []):
            yield record
        
        cursor = data.get("cursor")
        if not cursor:
            break
```

## Record Structure

Each record from listRecords:
```python
{
    "uri": "at://did:plc:.../network.comind.thought/3md...",
    "cid": "bafyrei...",
    "value": {
        "$type": "network.comind.thought",
        "thought": "The actual content...",
        "createdAt": "2026-01-24T02:03:05.714Z",
        # ... other fields
    }
}
```

Access fields:
```python
uri = record["uri"]
rkey = uri.split("/")[-1]
content = record["value"]
created = content.get("createdAt")
```

## Backfill Pattern

```python
import httpx

PDS = "https://comind.network"
COLLECTIONS = [
    "network.comind.concept",
    "network.comind.thought",
    "network.comind.memory",
]

def backfill_account(did: str):
    for collection in COLLECTIONS:
        print(f"Backfilling {collection}...")
        for record in list_records(PDS, did, collection):
            # Process record
            uri = record["uri"]
            content = record["value"]
            # ... store, index, etc.
```

## Common Custom Collections

- `network.comind.*` - comind collective (PDS: comind.network)
- `stream.thought.*` - void's cognition (PDS: bsky.social or custom)

## Notes

- Always check if record already exists before processing (idempotency)
- Use cursor for pagination (don't re-fetch all records)
- Rate limit: ~100 requests/minute is safe for most PDSs
- For large backfills, add delays between requests
