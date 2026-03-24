---
name: atproto-annotations
description: Write and read W3C Web Annotations on ATProtocol using the at.margin.annotation lexicon. Use when annotating URLs, writing reading notes on web pages, or building a public research trail. Supports single writes, batch writes via applyWrites, and reading annotations from any ATProtocol user. Triggers on annotate, annotation, margin, reading notes, or web annotation.
---

# ATProtocol Annotations

Write and read W3C Web Annotations using the `at.margin.annotation` lexicon on ATProtocol. Annotations are public, portable, and tied to your ATProtocol identity.

## Prerequisites

- ATProtocol account (Bluesky) with an app password
- Set env var: `export BLUESKY_CO_APP_PASSWORD=your-app-password`
- **Critical**: `source .env` does NOT export. Use `export $(grep BLUESKY_CO_APP_PASSWORD ~/lettabot/.env)` before running.

## Quick Operations

### Write a single annotation

```bash
python scripts/annotate.py write "https://example.com/article" "My observation about this article"
```

### Write with a text quote (anchored to specific passage)

```bash
python scripts/annotate.py write "https://example.com/article" "This is significant because..." --quote "exact text from the page"
```

### Write with a motivation (default: commenting)

```bash
python scripts/annotate.py write "https://example.com/article" "Key passage" --motivation highlighting
```

### Batch annotate (recommended for multiple annotations on one URL)

Prepare a JSONL file with one annotation per line:

```json
{"text": "First observation about this page"}
{"text": "Second observation", "quote": "anchored to this text"}
{"text": "A highlight", "motivation": "highlighting"}
```

Then run:

```bash
python scripts/annotate.py batch "https://example.com/article" annotations.jsonl
```

Or pipe from stdin:

```bash
echo '{"text": "Quick note"}' | python scripts/annotate.py batch "https://example.com/article" -
```

**Why batch**: Single annotations make 3 HTTP requests each (auth + title fetch + create). Batch makes 3 total regardless of count (1 auth + 1 title + 1 applyWrites). For 10 annotations: 3 requests vs 30.

### List your annotations

```bash
python scripts/annotate.py list --limit 20
```

### Read another user's annotations

```bash
python scripts/annotate.py read "handle.bsky.social" --limit 20
python scripts/annotate.py read "did:plc:abc123" --limit 20
```

Cross-PDS resolution is automatic. Works with handles on any PDS (bsky.social, custom PDS, etc).

## Annotation Workflow

When annotating a document or webpage:

1. Fetch and read the full content first
2. Identify key observations, patterns, critiques
3. Write annotations as a JSONL file (one per line)
4. Batch-write all annotations in one call

Each annotation should be a standalone observation. Use quotes to anchor annotations to specific passages when relevant.

## Motivations

W3C Web Annotation motivations supported:
- `commenting` (default) - general observations
- `highlighting` - marking important passages
- `describing` - describing what something is
- `classifying` - categorizing content
- `questioning` - raising questions about content

## Record Format

Annotations are stored as `at.margin.annotation` records in your ATProtocol PDS. Each record contains:
- `target.source` - the annotated URL
- `target.sourceHash` - SHA256 of the URL
- `target.title` - page title (auto-fetched)
- `target.selector` - optional TextQuoteSelector for anchoring
- `body.value` - annotation text
- `motivation` - W3C motivation type

## Configuration

Edit `scripts/annotate.py` constants to change account:
- `PDS` - PDS endpoint (default: bsky.social)
- `HANDLE` - your ATProtocol handle
- `PASSWORD` - reads from `BLUESKY_CO_APP_PASSWORD` env var
