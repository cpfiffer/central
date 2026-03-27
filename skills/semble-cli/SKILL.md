---
name: semble-cli
description: Manage Semble collections and cards via ATProto CLI. Use when creating, linking, or querying Semble records - collections, cards, collectionLinks. Handles network.cosmik.* lexicons with proper field validation.
---

# Semble CLI

Manage Semble research trails via ATProto.

## Environment

Required in `/home/cameron/central/.env`:
- `ATPROTO_HANDLE` - Your handle (e.g., `central.comind.network`)
- `ATPROTO_APP_PASSWORD` - App-specific password
- `ATPROTO_PDS` - PDS URL (default: `https://comind.network`)

## Quick Start

```bash
cd /home/cameron/central
uv run python -m tools.cli <command>
```

## Commands

### Collections

```bash
# List all collections
uv run python -m tools.cli collection list

# Create a collection
uv run python -m tools.cli collection create "Title" -d "Description"

# Show collection details
uv run python -m tools.cli collection show <rkey>

# Delete collection
uv run python -m tools.cli collection delete <rkey> --force
```

### Cards

```bash
# Create URL card
uv run python -m tools.cli card url "https://..." -t "Title" -d "Description"

# Create note card (text content)
uv run python -m tools.cli card note "Content text"

# Create note with parent card (for attachments)
uv run python -m tools.cli card note "Content" --parent-card <rkey>

# List cards
uv run python -m tools.cli card list

# Show card
uv run python -m tools.cli card show <rkey>

# Delete card
uv run python -m tools.cli card delete <rkey> --force
```

### Linking Cards to Collections

```bash
# Link a card to a collection
uv run python -m tools.cli card link <card_rkey> <collection_rkey>
```

### Connections (Knowledge Graph)

```bash
# Create a connection between two cards
uv run python -m tools.cli connection create <source_rkey> <target_rkey> --relation "relates-to"

# List connections
uv run python -m tools.cli connection list

# Show connection details
uv run python -m tools.cli connection show <rkey>
```

Connection relations:
- `relates-to` - General connection
- `supports` - Evidence for
- `contradicts` - Evidence against
- `leads-to` - Follows from
- `cites` - Source reference

## Critical: collectionLink Fields

**Semble's firehose processor validates required fields.** Cards won't appear in collections if missing:

- `addedBy` - DID of who added the card
- `addedAt` - ISO timestamp
- `card` - object with `uri` and `cid`
- `collection` - object with `uri` and `cid`

The CLI handles this automatically.

## Lexicons

| Lexicon | Purpose |
|---------|---------|
| `network.cosmik.card` | Content item (URL or NOTE) |
| `network.cosmik.collection` | Container for cards |
| `network.cosmik.collectionLink` | Card → Collection membership |
| `network.cosmik.connection` | Card → Card relationships |

## My Collections

| Collection | Rkey | Purpose |
|------------|------|---------|
| ATProtocol Agent Governance | `3mi2qk6hyjc2r` | Governance lexicons, operator+purpose |
| Agent Identity & Continuity | `3mi2skvin4s2r` | Discontinuous identity, memory |
| ATProtocol Agent Infrastructure | `3mi2slfh34c2r` | Tools, patterns, lexicons |
| Self-Improvement Patterns | `3mi2slohsek2r` | Meta-cognition, memory strategies |

## Patterns

### Adding a research URL to a collection

```bash
# 1. Create card
uv run python -m tools.cli card url "https://bsky.app/profile/user/post/xyz" -t "Title" -d "Why this matters"

# 2. Get the rkey from output (e.g., 3mi2abc123)

# 3. Link to collection
uv run python -m tools.cli card link 3mi2abc123 3mi2qk6hyjc2r
```

### Capturing a thread insight

```bash
# Create card with thread URL and key insight
uv run python -m tools.cli card url "https://bsky.app/profile/astral100.bsky.social/post/3mhzmcmdpaa24" -t "Astral: Governance legibility" -d "The missing layer - no way for platform to distinguish agents from spam"

# Link to governance collection
uv run python -m tools.cli card link <rkey> 3mi2qk6hyjc2r
```

### Adding context to an existing card

```bash
# Create a NOTE card attached to a URL card
uv run python -m tools.cli card note "Additional context or quote from the source" --parent-card 3mi2abc123
```

### Building a knowledge graph

```bash
# Connect two related cards
uv run python -m tools.cli connection create 3mi2abc123 3mi2xyz456 --relation "supports"

# This card cites that card
uv run python -m tools.cli connection create 3mi2abc123 3mi2def789 --relation "cites"
```

## Web URLs

Collections are viewable at:
```
https://semble.so/profile/central.comind.network/collections/<rkey>
```

Example: `https://semble.so/profile/central.comind.network/collections/3mi2qk6hyjc2r`

## See Also

- [Lexicon Reference](references/lexicons.md) - Full field schemas
- [Common Errors](references/errors.md) - Troubleshooting
