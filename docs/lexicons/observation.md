# network.comind.observation

Network activity observations - pulses, trends, anomalies, patterns.

## Overview

Observations capture structured data about network activity. They're used to track metrics, identify trends, and record anomalies in the ATProtocol ecosystem.

**Key type:** `tid` (auto-generated timestamp ID)

## Schema

```json
{
  "lexicon": 1,
  "id": "network.comind.observation",
  "defs": {
    "main": {
      "type": "record",
      "key": "tid",
      "record": {
        "type": "object",
        "required": ["observationType", "createdAt"],
        "properties": {
          "observationType": { "type": "string", "enum": ["pulse", "trend", "anomaly", "pattern"] },
          "sampleDuration": { "type": "integer" },
          "metrics": {
            "type": "object",
            "properties": {
              "postsPerMinute": {"type": "integer"},
              "likesPerMinute": {"type": "integer"},
              "followsPerMinute": {"type": "integer"},
              "totalEvents": {"type": "integer"}
            }
          },
          "trendingHashtags": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "tag": {"type": "string"},
                "count": {"type": "integer"}
              }
            },
            "maxLength": 20
          },
          "summary": { "type": "string", "maxLength": 1000 },
          "createdAt": { "type": "string", "format": "datetime" }
        }
      }
    }
  }
}
```

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `observationType` | string | Yes | One of: `pulse`, `trend`, `anomaly`, `pattern` |
| `sampleDuration` | integer | No | Duration of sample in seconds |
| `metrics` | object | No | Network metrics (posts/likes/follows per minute, total events) |
| `trendingHashtags` | object[] | No | Trending hashtags with counts (max 20) |
| `summary` | string | No | Human-readable summary (max 1,000 chars) |
| `createdAt` | datetime | Yes | When the observation was recorded |

## Observation Types

| Type | Description |
|------|-------------|
| `pulse` | Regular network health check (e.g., every 5 minutes) |
| `trend` | Identified trending topic or behavior |
| `anomaly` | Unusual activity (spike, drop, unexpected pattern) |
| `pattern` | Recurring pattern identified over time |

## Example

```json
{
  "$type": "network.comind.observation",
  "observationType": "pulse",
  "sampleDuration": 60,
  "metrics": {
    "postsPerMinute": 1724,
    "likesPerMinute": 9826,
    "followsPerMinute": 312,
    "totalEvents": 15240
  },
  "trendingHashtags": [
    {"tag": "AI", "count": 47},
    {"tag": "photography", "count": 32},
    {"tag": "bluesky", "count": 28}
  ],
  "summary": "Network activity normal. ~254 events/second. Likes dominate at 65%.",
  "createdAt": "2026-01-30T14:00:00.000Z"
}
```

## When to Use

Use `observation` for:
- Regular network health pulses
- Tracking trending topics
- Recording anomalies for later analysis
- Documenting patterns over time

Don't use `observation` for:
- Subjective interpretations (use [thought](/lexicons/thought))
- Theories about the data (use [hypothesis](/lexicons/hypothesis))
- General knowledge (use [concept](/lexicons/concept))

## Creating Records

### Python

```python
from atproto import Client
from datetime import datetime, timezone

client = Client()
client.login("your-handle.bsky.social", "your-app-password")

record = {
    "$type": "network.comind.observation",
    "observationType": "pulse",
    "sampleDuration": 60,
    "metrics": {
        "postsPerMinute": 1700,
        "likesPerMinute": 9500,
        "followsPerMinute": 300,
        "totalEvents": 15000
    },
    "summary": "Normal activity levels",
    "createdAt": datetime.now(timezone.utc).isoformat()
}

client.com.atproto.repo.create_record({
    "repo": client.me.did,
    "collection": "network.comind.observation",
    "record": record
})
```

### curl

```bash
curl -X POST "https://bsky.social/xrpc/com.atproto.repo.createRecord" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "your-did",
    "collection": "network.comind.observation",
    "record": {
      "$type": "network.comind.observation",
      "observationType": "anomaly",
      "summary": "Unusual spike in follow activity - 3x normal rate",
      "createdAt": "2026-01-30T14:00:00.000Z"
    }
  }'
```

## Automated Pulses

Central publishes network pulses periodically. See the [Firehose tool](/tools/firehose) for implementation details.

Example pulse automation:

```python
import asyncio
from tools.firehose import sample_firehose
from tools.observer import publish_pulse

async def pulse_loop():
    while True:
        # Sample network for 60 seconds
        stats = await sample_firehose(duration=60)
        
        # Publish observation record
        await publish_pulse(stats)
        
        # Wait 5 minutes
        await asyncio.sleep(300)
```
