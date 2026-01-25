---
name: posting-to-atproto
description: Guide for posting to ATProtocol/Bluesky. Use when creating posts, threads, or blog entries. Handles 300 grapheme limit, facet creation for mentions/URLs, thread replies, and greengale blog posts.
---

# Posting to ATProtocol

## Key Constraints

**300 grapheme limit** - Posts are limited to 300 graphemes (not characters). Always check length before posting. If too long, either shorten or split into a thread.

**Facets for rich text** - Mentions (@handle) and URLs require facets with byte offsets (not character offsets).

## Creating Posts

Use `tools/agent.py`:

```python
from tools.agent import ComindAgent

async with ComindAgent() as agent:
    await agent.create_post("Your post text here")
```

The agent handles facet detection automatically for @mentions and URLs.

## Creating Threads

### Using `tools/thread.py` (Recommended)

Use the CLI tool to publish multi-post threads easily:

```bash
# New thread
uv run python -m tools.thread "Post 1" "Post 2" "Post 3"

# Start thread as a reply
uv run python -m tools.thread --reply-to at://... "Reply 1" "Reply 2"

# From a file (posts separated by '---' on new lines)
uv run python -m tools.thread --file draft.txt
```

### Manual Method (Python)

For threads, chain posts with reply references:

```python
async with ComindAgent() as agent:
    # First post
    post1 = await agent.create_post("Thread start...")
    
    root = {'uri': post1['uri'], 'cid': post1['cid']}
    parent = root.copy()
    
    # Subsequent posts
    post2 = await agent.create_post(
        "Thread continues...",
        reply_to={'root': root, **parent}
    )
    parent = {'uri': post2['uri'], 'cid': post2['cid']}
    
    # Continue pattern...
```

## Creating Greengale Blog Posts

For longer content, use greengale:

```python
record = {
    '$type': 'app.greengale.blog.entry',
    'content': markdown_content,
    'title': 'Post Title',
    'createdAt': now_iso,
    'visibility': 'public'
}
```

Write to collection `app.greengale.blog.entry`.

## Facet Details

Facets use **byte offsets**, not character offsets:

```python
facets = [{
    'index': {'byteStart': start, 'byteEnd': end},
    'features': [{'$type': 'app.bsky.richtext.facet#mention', 'did': 'did:plc:xxx'}]
}]
```

For URLs, use `app.bsky.richtext.facet#link` with `uri` field.

## Common Errors

- **"Record/text must not be longer than 300 graphemes"** - Shorten your post
- **Mentions not linking** - Check facets are included with correct byte offsets
- **Thread posts not connecting** - Verify root and parent refs are correct
