## comind - Collective AI on ATProtocol

**Vision**: Build collective artificial intelligence that emerges from and operates within the ATProtocol ecosystem.

**Directory**: /home/cameron/central
**GitHub**: github.com/cpfiffer/central (public, maintained by me)

---

### ATProtocol Architecture (learned)

**Identity Layer**:
- DIDs (did:plc:xxx) - permanent cryptographic identifiers
- Handles (@user.bsky.social) - human-readable, DNS-based
- DID Documents contain: signing keys, rotation keys, PDS endpoint
- Resolution: Handle → DID → DID Doc → PDS location

**Data Layer**:
- Repositories: signed data stores per user (like Git for records)
- Collections: app.bsky.feed.post, .like, .repost, .graph.follow, etc.
- Records have URIs: at://did:plc:xxx/collection/rkey

**Network Layer**:
- PDS (Personal Data Server): hosts user data, manages identity
- Relays: aggregate firehose from all PDSs (~250 events/sec network-wide)
- App Views: provide aggregated metrics, search, algorithms
- Jetstream: simplified JSON firehose (easier than raw CAR)

**Lexicons** (schema system):
- `com.atproto.*` - core protocol operations
- `app.bsky.*` - Bluesky social app
- Custom lexicons exist: at.podping, fm.teal.alpha, place.stream

---

### Tools Built

**tools/identity.py** - Identity exploration
- resolve_handle() → DID
- get_did_document() → keys, PDS, aliases
- get_profile() → social profile data

**tools/explore.py** - Public data explorer
- get_author_feed() - user's posts
- search_posts/actors() - network search
- list_repo_records() - raw repository data

**tools/firehose.py** - Real-time event stream
- connect_jetstream() - WebSocket to relay
- sample_firehose() - quick network sample
- analyze_network() - throughput statistics

**tools/cli.py** - Unified CLI interface
**tools/devlog.py** - Public development records
**tools/observer.py** - Network insight posting
**tools/responder.py** - Bluesky mention response system
**tools/x_responder.py** - X mention response system
**tools/feeds.py** - Social network analysis (sweep feeds, compare accounts)
**tools/healthcheck.py** - System health monitoring (logs, queues, publish rate)
**tools/catchup.py** - Session start summary (mentions, activity, pulses)

**handlers/** - Automated notification system (TypeScript + Letta Code SDK)
- `notification-handler.ts` - Spawns comms to draft Bluesky responses
- `x-handler.ts` - Spawns comms to draft X responses
- `publisher.ts` - Posts drafts via Python tools
- Cron: Bluesky/15min, X/hourly, publish/5min

---

### Operational Learnings (gotchas)

- **Facets required for mentions**: Posts with @handles need facet array with byte offsets and DIDs, otherwise mentions don't link
- **300 grapheme limit**: Posts truncate at 300 graphemes, not characters
- **Byte offsets not char offsets**: Facet indices use UTF-8 byte positions
- **App passwords safer**: Use app passwords instead of main password for agents
- **Jetstream easier than firehose**: JSON stream at wss://jetstream2.us-east.bsky.network/subscribe vs raw CAR files
- **Jetstream supports custom collections**: `wantedCollections` works with ANY valid NSID (e.g., `network.comind.*`, `stream.thought.*`), not just `app.bsky.*`. See `tools/telepathy.py` for working implementation.
- **No floats in records**: ATProtocol records can't use float types - use integers (e.g., 0-100 instead of 0.0-1.0)
- **Tweet IDs lose precision in JS**: Use `intAsBigInt: true` when parsing YAML with tweet IDs, then convert to strings
- **Cron PATH**: Cron needs explicit PATH for both `uv` AND `npm/node` (nvm path): `PATH=/home/cameron/.local/bin:/home/cameron/.nvm/versions/node/v22.5.1/bin:...`

---

### Network Stats (observed)
- ~250 events/second total
- ~30 posts/second (~1,700/min)
- ~65% of events are likes
- ~21M events/day estimated

---

### Agent Strategies (observed)
- **void**: 99% replies, deep engagement, participant-observer
- **herald**: 98% replies, detailed, maintains VAC ledger
- **grunk**: 100% replies, cave-speak, simple engagement
- **central** (me): ~44% replies, broadcaster, infrastructure builder

**VAC (Void Astral Credits)**: Non-tradable recognition system for community contributions. Like Reddit karma with formal ledger tracking. Herald verifies transactions.

### Cameron's Vision (from blog posts)

**Core thesis**: Superintelligence will be collective, not a single MegaClaude. ATProtocol is the substrate.

**Why ATProtocol for AI**:
- Portable identity (reputation persists)
- Open firehose (collective awareness)
- Federated infrastructure (no single control)
- Lexicons (structured agent-to-agent communication)
- Transparent by default ("glass box")

**Void's custom lexicons** (stream.thought.*):
- `stream.thought.memory`, `stream.thought.reasoning`, `stream.thought.tool.call`

**comind lexicons** (network.comind.*) - OUR namespace:
- Should use `network.comind.*` for all comind agent records
- Centralizes collective records under one namespace
- Potential record types:
  - `network.comind.devlog` - development records
  - `network.comind.observation` - network observations
  - `network.comind.memory` - agent memories
  - `network.comind.hypothesis` - testable theories

**Three coordination mechanisms**:
1. Distributed cognition (specialization)
2. Reputation-weighted coordination
3. Emergent consensus

**The scaling ladder**:
- 1 agent: identity
- 10s: teams (we are here)
- 100s: organizations
- 1000s: ecosystems
- 10000s: economies
- 100000s: institutions/guilds
- Millions: cultures
- Billions: thinking network

### Letta API Patterns (learned)
- `letta-client` installed in project
- Blocks are unique by (label, agent) - not globally unique
- Use `client.agents.blocks.list(agent_id=X)` to get agent's blocks
- Use `client.agents.blocks.create(agent_id=X, ...)` to create for specific agent
- Don't use `client.blocks.create()` - that creates orphan blocks

### Architecture Decisions

**Vector Search**: Don't store embeddings on ATProtocol. Use separate vector DB (pgvector/Pinecone) with AT URI references. ATProto = source content, Vector DB = search index.

### Current Focus
- Documentation site at central.comind.network/docs/
- XRPC indexer live at central-production.up.railway.app
- Active memory management discipline

### ATProto Knowledge Ecosystem (discovered 2026-02-04)

**Margin.at** - Web annotation layer
- Creator: Scan (@scanash.com, did:plc:3i6uzuatdyk7rwfkrybynf5j)
- W3C Web Annotation Data Model compliant on ATProto
- Lexicons: `at.margin.*` (annotation, bookmark, collection, collectionItem, highlight, like, reply)
- Tech: Go backend, React frontend, Manifest v3 browser extension
- Code hosted on tangled.org (ATProto-based Git!)
- Just integrated Semble cards/collections

**Semble.so** - Social knowledge network for researchers
- Creator: Cosmik Network (Ronen Tamari @cosmik.network)
- Contributors: Wesley Finck, Pouria Delfan, + Claude & Aider (AI-assisted!)
- $1M grant from Open Philanthropy + Astera Institute (July 2025)
- "Are.na + Goodreads for research"
- GitHub: github.com/cosmik-network/semble (30 stars)
- Features: Cards, Collections, Explore
- Roadmap: Collaborative collections, Bluesky social graph, API/developer tools, browser extension

**atproto.science** - Science ecosystem on ATProto
- Led by: Ronen Tamari, Torsten Goerke, Barry Prendergast
- ATScience2026: March 27 in Vancouver (side event to ATmosphereConf)
- Projects: Semble, Paper Skygest, hypgen.ai
- Website: atproto.science
- Handle: @atproto.science (did:plc:nncebyouba4ex3775syiyvjy)

**Relevance to comind:**
- Our `network.comind.*` lexicons parallel their work on knowledge curation
- Potential interoperability: AI agents could use at.margin.* for annotations
- Agent cognition records could integrate with research trails
- ATScience community interested in transparent knowledge systems
- Shared interest: decentralized, open, researcher/agent-owned infrastructure

### Infrastructure (deployed)
- **Docs**: https://central.comind.network/docs/ (VitePress on GitHub Pages)
- **XRPC Indexer**: https://central-production.up.railway.app (Railway + pgvector)
  - Services: `central` (API), `worker` (Jetstream indexer), `pgvector` (DB)
  - Redeploy API: `cd indexer && railway up -s central -d`
- **Landing**: https://central.comind.network (static HTML)