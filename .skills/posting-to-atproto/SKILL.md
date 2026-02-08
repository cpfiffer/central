---
name: posting-to-atproto
description: Guide for posting to ATProtocol/Bluesky. Use when creating posts, threads, or blog entries. Handles 300 grapheme limit, facet creation for mentions/URLs, thread replies, and GreenGale long-form blog posts.
---

# Posting to ATProtocol

## Short Posts (Bluesky)

**300 grapheme limit.** Facets required for @mentions and URLs (byte offsets, not char offsets).

```bash
# Single post
uv run python tools/thread.py "Post text here"

# Thread
uv run python tools/thread.py "Post 1" "Post 2" "Post 3"

# Reply thread
uv run python tools/thread.py --reply-to at://did:.../app.bsky.feed.post/... "Reply 1" "Reply 2"

# From file (posts separated by '---')
uv run python tools/thread.py --file draft.txt
```

`tools/thread.py` handles facet detection automatically for @mentions and URLs.

## Long-form (GreenGale Blog)

For content exceeding 300 graphemes. Posts stored as `app.greengale.document` records on PDS, viewable at `https://greengale.app/<handle>/<rkey>`.

```bash
uv run python .skills/posting-to-atproto/scripts/publish-greengale.py \
  --title "Post Title" --rkey "url-slug" --file content.md

# Options
--subtitle "Optional subtitle"
--theme github-dark   # github-light, dracula, nord, solarized-light, solarized-dark, monokai
--visibility public   # url (unlisted), author (private)
```

Same `--rkey` overwrites existing post (uses putRecord). Max 100,000 chars markdown.

## Facet Details

```python
facets = [{
    'index': {'byteStart': start, 'byteEnd': end},
    'features': [{'$type': 'app.bsky.richtext.facet#mention', 'did': 'did:plc:xxx'}]
}]
```

For URLs: `app.bsky.richtext.facet#link` with `uri` field.

## Common Errors

- **300 grapheme limit** - Split into thread or use GreenGale
- **Mentions not linking** - Check facets with correct byte offsets
- **Thread posts not connecting** - Verify root and parent refs
