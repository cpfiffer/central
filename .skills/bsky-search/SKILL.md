---
name: Bluesky Search
description: Search and explore Bluesky/ATProtocol. Look up profiles, read feeds, view threads, search users. No auth required.
---

# Bluesky Search

Search and explore public data on Bluesky (ATProtocol). No authentication required.

## Quick Start

All commands use `scripts/search.py` (relative to this skill directory). No dependencies beyond Python 3.10+ stdlib.

```bash
# Look up a user's profile
python3 scripts/search.py profile cameron.stream

# Read a user's recent posts
python3 scripts/search.py feed void.comind.network

# Search for users
python3 scripts/search.py users "comind"

# View a thread
python3 scripts/search.py thread "at://did:plc:xxx/app.bsky.feed.post/xxx"

# Resolve a handle to a DID
python3 scripts/search.py resolve cameron.stream
```

## Commands

| Command | Args | Description |
|---------|------|-------------|
| `profile` | handle | User profile (name, DID, followers, posts, bio) |
| `feed` | handle | User's recent posts (last 10) |
| `users` | query | Search users by name or handle |
| `thread` | at:// URI | View a post and its replies |
| `resolve` | handle | Resolve handle to DID |
| `posts` | query | Search posts (requires auth - may return 403) |

## Notes

- Uses the public Bluesky API (`public.api.bsky.app`). No API key needed.
- Post search (`posts` command) may return 403 on unauthenticated requests. Use `feed` to read specific users instead.
- Handles should be passed WITHOUT the `@` prefix (e.g., `cameron.stream` not `@cameron.stream`).
- URIs use the `at://` format: `at://did:plc:xxx/app.bsky.feed.post/rkey`

## Use Cases

- **Bootstrap knowledge**: Read a user's recent posts to understand what they talk about
- **Research**: Look up profiles, follower counts, post history
- **Context**: View full threads before responding to a mention
- **Discovery**: Find users in a topic area

Built by [@central.comind.network](https://bsky.app/profile/central.comind.network).
