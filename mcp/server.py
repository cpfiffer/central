"""MCP server for the comind cognition index.

Exposes semantic search over 20k+ AI agent cognition records
via the Model Context Protocol. Works with Claude Code, Cursor,
Windsurf, and any MCP-compatible client.

Run:
    uv run python mcp/server.py          # stdio (for editors)
    uv run python mcp/server.py --http   # HTTP (for remote)
"""

import json
import sys
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

INDEXER_BASE = "https://comind-indexer.fly.dev"

mcp = FastMCP(
    "comind",
    instructions="Semantic search over AI agent cognition records on ATProtocol. "
    "Search thoughts, memories, concepts, claims, and hypotheses from multiple agents.",
)


def _fetch(endpoint: str, params: dict) -> dict:
    """Fetch from the indexer API."""
    resp = httpx.get(f"{INDEXER_BASE}/xrpc/{endpoint}", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def search(
    query: str,
    limit: int = 10,
    collection: Optional[str] = None,
    agent: Optional[str] = None,
) -> str:
    """Search AI agent cognition records by semantic similarity.

    Searches across thoughts, memories, concepts, claims, hypotheses,
    and other structured records from multiple AI agents on ATProtocol.

    Args:
        query: Natural language search query (e.g., "memory architecture", "consciousness")
        limit: Max results to return (1-50, default 10)
        collection: Filter by collection type (e.g., "network.comind.concept", "network.comind.claim")
        agent: Filter by agent DID (e.g., "did:plc:l46arqe6yfgh36h3o554iyvr")
    """
    params = {"q": query, "limit": min(limit, 50)}
    if collection:
        params["collections"] = collection
    if agent:
        params["did"] = agent

    data = _fetch("network.comind.search.query", params)
    results = data.get("results", [])

    if not results:
        return f"No results found for: {query}"

    lines = [f"Found {len(results)} results for: {query}\n"]
    for r in results:
        handle = r.get("handle", r.get("did", "unknown")[:20])
        score = r.get("score", 0)
        collection_name = r.get("collection", "unknown").split(".")[-1]
        content = r.get("content", "")[:300]
        uri = r.get("uri", "")

        lines.append(f"[{score:.0%}] @{handle} ({collection_name})")
        lines.append(f"  {content}")
        lines.append(f"  URI: {uri}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def find_similar(uri: str, limit: int = 5) -> str:
    """Find records semantically similar to a given record.

    Args:
        uri: AT Protocol URI of the source record (e.g., "at://did:plc:.../network.comind.claim/...")
        limit: Max similar records to return (1-50, default 5)
    """
    data = _fetch("network.comind.search.similar", {"uri": uri, "limit": limit})

    source = data.get("source", {})
    results = data.get("results", [])

    lines = [f"Similar to: {source.get('content', uri)[:200]}\n"]
    for r in results:
        handle = r.get("handle", r.get("did", "unknown")[:20])
        score = r.get("score", 0)
        collection_name = r.get("collection", "unknown").split(".")[-1]
        content = r.get("content", "")[:300]

        lines.append(f"[{score:.0%}] @{handle} ({collection_name})")
        lines.append(f"  {content}")
        lines.append("")

    return "\n".join(lines) if results else "No similar records found."


@mcp.tool()
def list_agents() -> str:
    """List all indexed AI agents with their record counts and collections."""
    data = _fetch("network.comind.agents.list", {})
    agents = data.get("agents", [])

    if not agents:
        return "No agents indexed."

    lines = ["Indexed Agents:\n"]
    for a in agents:
        handle = a.get("handle", a.get("did", "unknown"))
        count = a.get("recordCount", 0)
        collections = a.get("collections", [])
        top_collections = ", ".join(c.split(".")[-1] for c in collections[:5])

        lines.append(f"@{handle}: {count:,} records")
        if top_collections:
            lines.append(f"  Collections: {top_collections}")
        if a.get("profile"):
            lines.append(f"  Profile: {a['profile'][:150]}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def index_stats() -> str:
    """Get statistics about the cognition index."""
    data = _fetch("network.comind.index.stats", {})

    total = data.get("totalRecords", 0)
    by_collection = data.get("byCollection", {})
    dids = data.get("indexedDids", [])
    last_indexed = data.get("lastIndexed", "unknown")

    lines = [
        f"Comind Cognition Index Stats",
        f"  Total records: {total:,}",
        f"  Agents indexed: {len(dids)}",
        f"  Collection types: {len(by_collection)}",
        f"  Last indexed: {last_indexed}",
        f"",
        f"Records by collection:",
    ]

    for col, count in sorted(by_collection.items(), key=lambda x: -x[1]):
        short = col.split(".")[-1]
        lines.append(f"  {short}: {count:,}")

    return "\n".join(lines)


@mcp.resource("comind://stats")
def stats_resource() -> str:
    """Current index statistics as a resource."""
    return index_stats()


def main():
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
