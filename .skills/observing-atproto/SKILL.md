---
name: observing-atproto
description: Guide for observing the ATProtocol network. Use when sampling the firehose, taking network pulses, monitoring feeds, or analyzing engagement patterns.
---

# Observing ATProtocol

## Firehose Access

**Jetstream endpoint**: `wss://jetstream2.us-east.bsky.network/subscribe`

Simplified JSON stream (~50 posts/sec on Bluesky). Easier than raw CAR files.

### Quick Pulse

```python
import asyncio
import json
import websockets
from datetime import datetime, timezone

async def pulse(duration_seconds=15):
    uri = 'wss://jetstream2.us-east.bsky.network/subscribe'
    posts, likes, follows = 0, 0, 0
    hashtags = {}
    
    start = datetime.now(timezone.utc)
    
    async with websockets.connect(uri) as ws:
        while (datetime.now(timezone.utc) - start).seconds < duration_seconds:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=1)
                data = json.loads(msg)
                
                commit = data.get('commit', {})
                collection = commit.get('collection', '')
                
                if collection == 'app.bsky.feed.post':
                    posts += 1
                    # Extract hashtags
                    text = commit.get('record', {}).get('text', '')
                    for word in text.split():
                        if word.startswith('#'):
                            tag = word[1:].lower().rstrip('.,!?')
                            hashtags[tag] = hashtags.get(tag, 0) + 1
                elif collection == 'app.bsky.feed.like':
                    likes += 1
                elif collection == 'app.bsky.graph.follow':
                    follows += 1
            except asyncio.TimeoutError:
                continue
    
    return {
        'duration': duration_seconds,
        'posts': posts,
        'likes': likes,
        'follows': follows,
        'posts_per_min': posts * 60 // duration_seconds,
        'top_hashtags': sorted(hashtags.items(), key=lambda x: -x[1])[:5]
    }
```

### Using tools/firehose.py

```bash
# Quick network sample
uv run python -m tools.firehose sample 30

# Network analysis
uv run python -m tools.firehose analyze 60
```

## Monitoring Feeds

### The Atmosphere Feed

Cameron's curated ATProtocol discussion feed:

```python
feed_uri = 'at://did:plc:gfrmhdmjvxn2sjedzboeudef/app.bsky.feed.generator/the-atmosphere'

async with httpx.AsyncClient() as client:
    resp = await client.get(
        'https://public.api.bsky.app/xrpc/app.bsky.feed.getFeed',
        params={'feed': feed_uri, 'limit': 20}
    )
    posts = resp.json().get('feed', [])
```

### Recording Observations

```bash
# Record observation as a cognition thought
uv run python -m tools.cognition thought "Network pulse: {posts_per_min} posts/min, {likes_per_min} likes/min. Top tags: #atproto, #bluesky"
```

## Network Statistics (typical)

- ~50 posts/sec (~3000/min)
- ~250 events/sec total
- ~65% of events are likes
- Engagement ratio (likes:posts) typically 4-6:1
- Higher engagement ratio = healthy interaction patterns

## Best Practices

1. Sample for at least 15 seconds for meaningful data
2. Note time of day - activity varies
3. Cultural events drive spikes (e.g., BBB26, sports)
4. Record observations as `network.comind.observation` records
5. Compare pulses over time to identify patterns
