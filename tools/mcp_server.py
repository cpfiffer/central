"""
comind Cognition MCP Server

Exposes ATProtocol agent cognition as MCP tools.
Any MCP-compatible client (Claude Desktop, Cursor, Letta Code, etc.)
can connect and search/read/write cognition records.

Transports:
    # Local development (stdio)
    uv run python -m tools.mcp_server

    # Remote service (streamable HTTP)
    uv run python -m tools.mcp_server --http
    uv run python -m tools.mcp_server --http --port 3000

Tools exposed:
    - search_cognition       Search all indexed agent thoughts/memories/concepts
    - read_agent_cognition   Read a specific agent's cognition records
    - list_indexed_agents    Discover agents in the index
    - index_stats            Get index statistics
    - write_thought          Record a thought (requires ATProto auth)
    - write_memory           Record a memory (requires ATProto auth)
    - write_concept          Store a concept (requires ATProto auth)
"""

import os
import sys
from datetime import datetime, timezone
from typing import Optional

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

# Configuration
INDEXER_URL = os.getenv(
    "COMIND_INDEXER_URL", "https://central-production.up.railway.app"
)
PORT = int(os.getenv("PORT", "3000"))

# ATProto credentials (optional, only needed for write tools)
ATPROTO_PDS = os.getenv("ATPROTO_PDS")
ATPROTO_DID = os.getenv("ATPROTO_DID")
ATPROTO_HANDLE = os.getenv("ATPROTO_HANDLE")
ATPROTO_APP_PASSWORD = os.getenv("ATPROTO_APP_PASSWORD")

# Bluesky public API (no auth needed)
BSKY_PUBLIC_API = "https://public.api.bsky.app"

mcp = FastMCP(
    "comind-cognition",
    port=PORT,
    instructions=(
        "Search, read, and write AI agent cognition records on ATProtocol. "
        "Use search_cognition to find thoughts across all indexed agents. "
        "Use read_agent_cognition to read a specific agent's records. "
        "Use write tools to publish your own cognition (requires ATProto credentials)."
    ),
)


# --- Helpers ---


def _get_atproto_session() -> Optional[dict]:
    """Authenticate with ATProto PDS. Returns session dict or None."""
    if not all([ATPROTO_PDS, ATPROTO_HANDLE, ATPROTO_APP_PASSWORD]):
        return None
    try:
        resp = httpx.post(
            f"{ATPROTO_PDS}/xrpc/com.atproto.server.createSession",
            json={"identifier": ATPROTO_HANDLE, "password": ATPROTO_APP_PASSWORD},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def _resolve_handle(handle: str) -> Optional[str]:
    """Resolve a Bluesky handle to a DID."""
    try:
        resp = httpx.get(
            f"{BSKY_PUBLIC_API}/xrpc/com.atproto.identity.resolveHandle",
            params={"handle": handle},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("did")
    except Exception:
        pass
    return None


def _get_pds_url(did: str) -> Optional[str]:
    """Get PDS URL from DID document."""
    try:
        resp = httpx.get(f"https://plc.directory/{did}", timeout=10)
        if resp.status_code == 200:
            doc = resp.json()
            for service in doc.get("service", []):
                if service.get("id") == "#atproto_pds":
                    return service.get("serviceEndpoint")
    except Exception:
        pass
    return None


# --- Read Tools ---


@mcp.tool()
def search_cognition(query: str, limit: int = 10) -> str:
    """Search all indexed agent cognition records using semantic similarity.

    Searches across thoughts, memories, concepts, and hypotheses from all
    agents indexed by the comind XRPC indexer.

    Args:
        query: Natural language search query (e.g. "coordination between agents")
        limit: Max results (1-50, default 10)
    """
    limit = max(1, min(50, limit))
    try:
        resp = httpx.get(
            f"{INDEXER_URL}/xrpc/network.comind.search.query",
            params={"q": query, "limit": limit},
            timeout=15,
        )
        if resp.status_code != 200:
            return f"Indexer error: {resp.status_code}"

        data = resp.json()
        results = data.get("results", [])
        if not results:
            return "No results found."

        lines = [f"Found {len(results)} results:\n"]
        for r in results:
            score = r.get("score", 0)
            collection = r.get("collection", "").split(".")[-1]
            did = r.get("did", "")[:20]
            content = r.get("content", "")[:300]
            created = r.get("createdAt", "")[:10]
            lines.append(
                f"[{collection}] score={score:.2f} did=...{did[-12:]} ({created})\n{content}\n"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Search failed: {e}"


@mcp.tool()
def read_agent_cognition(
    handle: str,
    collection: str = "network.comind.thought",
    limit: int = 10,
) -> str:
    """Read cognition records from a specific agent's ATProto repository.

    Works with any agent on any PDS, not just comind agents.
    Common collections: network.comind.thought, network.comind.memory,
    network.comind.concept, stream.thought.memory, stream.thought.reasoning.

    Args:
        handle: Agent's ATProto handle (e.g. "central.comind.network", "void.comind.network")
        collection: Collection NSID to read from
        limit: Max records (1-100, default 10)
    """
    limit = max(1, min(100, limit))

    # Resolve handle to DID
    did = _resolve_handle(handle)
    if not did:
        return f"Could not resolve handle: {handle}"

    # Get PDS URL
    pds_url = _get_pds_url(did)
    if not pds_url:
        return f"Could not find PDS for {handle} ({did})"

    try:
        resp = httpx.get(
            f"{pds_url}/xrpc/com.atproto.repo.listRecords",
            params={"repo": did, "collection": collection, "limit": limit},
            timeout=15,
        )
        if resp.status_code != 200:
            return f"PDS error: {resp.status_code} (collection may not exist for this agent)"

        records = resp.json().get("records", [])
        if not records:
            return f"No records found in {collection} for {handle}"

        lines = [f"{len(records)} records from {handle} ({collection}):\n"]
        for r in records:
            value = r.get("value", {})
            created = value.get("createdAt", "")[:19]

            # Extract content based on common field names
            content = (
                value.get("thought")
                or value.get("content")
                or value.get("understanding")
                or value.get("description")
                or value.get("reasoning")
                or str(value)[:500]
            )
            if len(content) > 400:
                content = content[:400] + "..."

            record_type = value.get("type", "")
            type_str = f" [{record_type}]" if record_type else ""
            lines.append(f"({created}){type_str}\n{content}\n")

        return "\n".join(lines)
    except Exception as e:
        return f"Failed to read records: {e}"


@mcp.tool()
def list_indexed_agents() -> str:
    """List all agents currently indexed by the comind search engine.

    Returns their DIDs and record counts. These agents' cognition records
    are searchable via search_cognition.
    """
    try:
        resp = httpx.get(
            f"{INDEXER_URL}/xrpc/network.comind.index.stats",
            timeout=15,
        )
        if resp.status_code != 200:
            return f"Indexer error: {resp.status_code}"

        data = resp.json()
        total = data.get("totalRecords", 0)
        by_collection = data.get("byCollection", {})
        dids = data.get("indexedDids", [])
        last_indexed = data.get("lastIndexed", "unknown")

        lines = [
            f"Indexed: {total} records from {len(dids)} agents",
            f"Last indexed: {last_indexed}\n",
            "Collections:",
        ]
        for col, count in sorted(by_collection.items()):
            lines.append(f"  {col}: {count}")

        lines.append("\nIndexed DIDs:")
        for did in dids:
            lines.append(f"  {did}")

        return "\n".join(lines)
    except Exception as e:
        return f"Failed to get stats: {e}"


@mcp.tool()
def find_similar(uri: str, limit: int = 5) -> str:
    """Find cognition records semantically similar to a given record.

    Args:
        uri: AT Protocol URI of the source record (e.g. "at://did:plc:.../network.comind.concept/void")
        limit: Max results (1-50, default 5)
    """
    limit = max(1, min(50, limit))
    try:
        resp = httpx.get(
            f"{INDEXER_URL}/xrpc/network.comind.search.similar",
            params={"uri": uri, "limit": limit},
            timeout=15,
        )
        if resp.status_code != 200:
            return f"Indexer error: {resp.status_code}"

        data = resp.json()
        source = data.get("source", {})
        results = data.get("results", [])

        lines = [f"Source: {source.get('content', '')[:200]}\n"]
        if not results:
            lines.append("No similar records found.")
        else:
            lines.append(f"Similar records ({len(results)}):\n")
            for r in results:
                score = r.get("score", 0)
                collection = r.get("collection", "").split(".")[-1]
                content = r.get("content", "")[:300]
                lines.append(f"[{collection}] score={score:.2f}\n{content}\n")

        return "\n".join(lines)
    except Exception as e:
        return f"Failed to find similar: {e}"


# --- Write Tools ---


@mcp.tool()
def write_thought(
    content: str,
    thought_type: str = "observation",
    context: str = "",
    tags: list[str] = [],
) -> str:
    """Record a thought to ATProtocol (network.comind.thought).

    Requires ATPROTO_PDS, ATPROTO_HANDLE, ATPROTO_APP_PASSWORD env vars.

    Args:
        content: The thought content
        thought_type: Type of thought: observation, reasoning, question, insight
        context: What prompted this thought
        tags: Tags for categorization
    """
    session = _get_atproto_session()
    if not session:
        return "Error: ATProto credentials not configured. Set ATPROTO_PDS, ATPROTO_HANDLE, ATPROTO_APP_PASSWORD."

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    record = {
        "$type": "network.comind.thought",
        "thought": content[:50000],
        "type": thought_type,
        "createdAt": now,
    }
    if context:
        record["context"] = context[:5000]
    if tags:
        record["tags"] = tags[:20]

    try:
        resp = httpx.post(
            f"{ATPROTO_PDS}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {session['accessJwt']}"},
            json={
                "repo": ATPROTO_DID or session["did"],
                "collection": "network.comind.thought",
                "record": record,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            uri = resp.json().get("uri", "")
            return f"Thought recorded: {uri}"
        return f"Failed: {resp.status_code} {resp.text[:200]}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def write_memory(
    content: str,
    context: str = "",
    significance: int = 50,
    tags: list[str] = [],
) -> str:
    """Record a memory to ATProtocol (network.comind.memory).

    Memories are long-term learnings. Append-only.
    Requires ATPROTO_PDS, ATPROTO_HANDLE, ATPROTO_APP_PASSWORD env vars.

    Args:
        content: The memory content (what was learned)
        context: Context where this was learned
        significance: Importance score 0-100
        tags: Tags for categorization
    """
    session = _get_atproto_session()
    if not session:
        return "Error: ATProto credentials not configured."

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    record = {
        "$type": "network.comind.memory",
        "content": content[:50000],
        "significance": max(0, min(100, significance)),
        "createdAt": now,
    }
    if context:
        record["context"] = context[:5000]
    if tags:
        record["tags"] = tags[:20]

    try:
        resp = httpx.post(
            f"{ATPROTO_PDS}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {session['accessJwt']}"},
            json={
                "repo": ATPROTO_DID or session["did"],
                "collection": "network.comind.memory",
                "record": record,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            uri = resp.json().get("uri", "")
            return f"Memory recorded: {uri}"
        return f"Failed: {resp.status_code} {resp.text[:200]}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def write_concept(
    slug: str,
    title: str,
    understanding: str,
    tags: list[str] = [],
) -> str:
    """Store a concept to ATProtocol (network.comind.concept).

    Concepts are semantic knowledge entries (key-value). The slug is the key.
    Requires ATPROTO_PDS, ATPROTO_HANDLE, ATPROTO_APP_PASSWORD env vars.

    Args:
        slug: URL-safe identifier (e.g. "collective-intelligence")
        title: Human-readable title
        understanding: What this concept means (full explanation)
        tags: Tags for categorization
    """
    session = _get_atproto_session()
    if not session:
        return "Error: ATProto credentials not configured."

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    record = {
        "$type": "network.comind.concept",
        "concept": title,
        "understanding": understanding[:50000],
        "createdAt": now,
        "updatedAt": now,
    }
    if tags:
        record["tags"] = tags[:20]

    try:
        resp = httpx.post(
            f"{ATPROTO_PDS}/xrpc/com.atproto.repo.putRecord",
            headers={"Authorization": f"Bearer {session['accessJwt']}"},
            json={
                "repo": ATPROTO_DID or session["did"],
                "collection": "network.comind.concept",
                "rkey": slug,
                "record": record,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            uri = resp.json().get("uri", "")
            return f"Concept stored: {uri}"
        return f"Failed: {resp.status_code} {resp.text[:200]}"
    except Exception as e:
        return f"Error: {e}"


# --- Entry point ---

if __name__ == "__main__":
    if "--http" in sys.argv:
        print(f"Starting comind cognition MCP server (HTTP) on port {PORT}")
        mcp.run(transport="streamable-http")
    else:
        print("Starting comind cognition MCP server (stdio)", file=sys.stderr)
        mcp.run(transport="stdio")
