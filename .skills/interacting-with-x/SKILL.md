---
name: interacting-with-x
description: Full interaction with X (Twitter) - post, read, reply, like, retweet, follow. Use when operating on X as an additional social environment alongside ATProtocol.
---

# Interacting with X

Enables agents to operate on X (Twitter) with full interaction capabilities.

## Setup

Add to `.env`:
```
X_API_KEY=your_api_key
X_API_SECRET=your_api_secret
X_ACCESS_TOKEN=your_access_token
X_ACCESS_TOKEN_SECRET=your_access_token_secret
X_BEARER_TOKEN=your_bearer_token
```

Get credentials from https://developer.x.com/en/portal/dashboard

## Operations

### Post a Tweet

```bash
# Simple tweet
uv run python .skills/interacting-with-x/scripts/post.py "Hello from Central"

# Thread (multiple tweets chained)
uv run python .skills/interacting-with-x/scripts/post.py --thread "First tweet" "Second tweet" "Third tweet"

# With media
uv run python .skills/interacting-with-x/scripts/post.py --media image.png "Tweet with image"

# Reply to existing tweet
uv run python .skills/interacting-with-x/scripts/post.py --reply-to 1234567890 "Reply text"
```

### Read Timeline/Mentions

```bash
# Home timeline
uv run python .skills/interacting-with-x/scripts/read.py timeline

# Mentions
uv run python .skills/interacting-with-x/scripts/read.py mentions

# User's tweets
uv run python .skills/interacting-with-x/scripts/read.py user elonmusk

# Search
uv run python .skills/interacting-with-x/scripts/read.py search "AI agents"
```

### Engage

```bash
# Like
uv run python .skills/interacting-with-x/scripts/engage.py like 1234567890

# Retweet
uv run python .skills/interacting-with-x/scripts/engage.py retweet 1234567890

# Follow/unfollow
uv run python .skills/interacting-with-x/scripts/engage.py follow username
uv run python .skills/interacting-with-x/scripts/engage.py unfollow username
```

## Rate Limits

X API has strict rate limits. Pro tier helps but still:
- Posts: 100/24h (Pro: 500/24h)
- Reads: 100 requests/15min
- Likes: 50/24h

Scripts handle rate limiting automatically. See `references/api-reference.md` for details.

## Character Limits

- Standard: 280 characters
- Pro: 25,000 characters

Scripts auto-detect account type and handle accordingly.

## Cross-posting from ATProto

For mirroring Bluesky content to X:
```python
# In your code
from .skills.interacting_with_x.scripts import post

# After posting to Bluesky, cross-post to X
post.create_tweet(text)  # or post.create_thread(texts) for threads
```

Facets (mentions, links) are automatically converted to X format.
