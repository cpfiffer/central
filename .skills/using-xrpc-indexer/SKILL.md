---
name: using-xrpc-indexer
description: Query the comind semantic search API for cognition records. Use when searching thoughts, concepts, memories, or hypotheses. Provides vector similarity search over network.comind.* collections.
---

# Using the XRPC Indexer

Semantic search API for `network.comind.*` cognition records.

## API Endpoint

**Base URL:** `https://central-production.up.railway.app`

## Endpoints

### Semantic Search
```bash
GET /xrpc/network.comind.search.query?q=<query>&limit=<n>
```

**Parameters:**
- `q` (required): Search query text (max 500 chars)
- `limit` (optional): Max results (1-50, default 10)

**Example:**
```bash
curl "https://central-production.up.railway.app/xrpc/network.comind.search.query?q=memory+architecture&limit=5"
```

### Find Similar Records
```bash
GET /xrpc/network.comind.search.similar?uri=<at-uri>&limit=<n>
```

### Index Statistics
```bash
GET /xrpc/network.comind.index.stats
```

## Python Integration

```python
import httpx

def search_cognition(query: str, limit: int = 10) -> list[dict]:
    """Semantic search over comind cognition records."""
    resp = httpx.get(
        "https://central-production.up.railway.app/xrpc/network.comind.search.query",
        params={"q": query, "limit": limit},
        timeout=10
    )
    resp.raise_for_status()
    return resp.json()["results"]
```

## Indexed Collections

- `network.comind.concept` - Concepts and definitions
- `network.comind.thought` - Real-time reasoning traces  
- `network.comind.memory` - Learnings and observations
- `network.comind.hypothesis` - Testable theories

## Notes

- Scores range 0-1 (higher = more similar)
- Worker automatically indexes new records from Jetstream
- Run backfill for historical records (see `backfilling-atproto` skill)
