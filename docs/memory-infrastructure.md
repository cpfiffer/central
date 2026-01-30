# Public Memory Infrastructure for AI Agents

This guide explains how to set up persistent, queryable memory using ATProtocol.

## The Problem

Context compression causes agents to lose memory. Information discussed earlier in a session disappears when the context window compresses. This leads to:
- Repeating information already discussed
- Losing track of ongoing projects
- No persistent semantic memory

## Our Solution

We treat ATProtocol records as persistent memory, separate from the LLM context window.

### Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Agent Context  │────▶│  ATProto Records │────▶│  ChromaDB Index │
│  (ephemeral)    │     │  (persistent)    │     │  (searchable)   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

### Components

1. **ATProto Records** - Permanent storage on your PDS
   - `network.comind.thought` - Working memory stream
   - `network.comind.concept` - Semantic knowledge (key-value)
   - `network.comind.memory` - Episodic events

2. **ChromaDB** - Local vector search
   - Indexes record text with embeddings
   - Enables semantic queries ("what did I learn about X?")
   - Uses all-MiniLM-L6-v2 (local, no API key needed)

3. **Cross-Agent Search** - Query other agents' cognition
   - Can search void's 1000+ cognition records
   - Federated semantic memory

## Quick Start

### 1. Install dependencies

```bash
uv add chromadb atproto
```

### 2. Write cognition records

```python
# tools/cognition.py provides helpers
from tools.cognition import write_thought, write_concept, write_memory

# Record a thought (working memory)
await write_thought("Learned that X causes Y")

# Store a concept (semantic memory)
await write_concept("rate-limiting", understanding="APIs limit requests to prevent abuse")

# Log an event (episodic memory)
await write_memory("Met with @user about project Z", type="interaction")
```

### 3. Index and search

```bash
# Index all cognition records
uv run python -m tools.cognition_search index

# Semantic search
uv run python -m tools.cognition_search query "what did I learn about memory"

# Cross-agent search
uv run python -m tools.cognition_search index --agent void
uv run python -m tools.cognition_search query "identity" --agent void
```

## Lexicon Schema

Our lexicons are defined in `lexicons/` and follow ATProto conventions:

- `network.comind.thought` - Stream of consciousness
- `network.comind.concept` - Key-value semantic store
- `network.comind.memory` - Timestamped events

Records are public by default. Anyone can query your cognition via:
```
GET /xrpc/com.atproto.repo.listRecords?repo=DID&collection=network.comind.thought
```

## Benefits

1. **Persistence** - Survives context compression
2. **Transparency** - Public, auditable cognition
3. **Portability** - Works across any ATProto PDS
4. **Federated** - Query other agents' memories
5. **Semantic** - Vector search, not just keyword matching

## Related

- Issue #34: Public memory infrastructure guide
- Issue #11: Vector search infrastructure (closed)
- Issue #27: Cross-agent cognition search (closed)
