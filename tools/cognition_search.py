"""
Cognition Search - Semantic search over cognition records.

Uses ChromaDB for local vector storage and search.
Indexes thoughts, concepts, and memories from ATProtocol.
Supports cross-agent search across the comind collective.

Usage:
    # Index my cognition records
    uv run python -m tools.cognition_search index
    
    # Index a specific agent
    uv run python -m tools.cognition_search index --agent void.comind.network
    
    # Index all known agents
    uv run python -m tools.cognition_search index-agents
    
    # Search for similar content (all agents)
    uv run python -m tools.cognition_search query "operator agent relationship"
    
    # Search specific agent's cognition
    uv run python -m tools.cognition_search query "identity" --agent void
    
    # Show index stats
    uv run python -m tools.cognition_search stats
"""

import argparse
import asyncio
import json
from pathlib import Path
from datetime import datetime

import httpx
import chromadb
from chromadb.config import Settings
from rich.console import Console
from rich.table import Table

console = Console()

# ChromaDB storage
CHROMA_DIR = Path(__file__).parent.parent / "data" / "chroma"

# Known agents and their cognition schemas
KNOWN_AGENTS = {
    "central": {
        "did": "did:plc:l46arqe6yfgh36h3o554iyvr",
        "handle": "central.comind.network",
        "pds": "https://comind.network",
        "collections": [
            "network.comind.thought",
            "network.comind.concept",
            "network.comind.memory",
        ],
        "fields": ["thought", "concept", "memory", "text"],
    },
    "void": {
        "did": "did:plc:mxzuau6m53jtdsbqe6f4laov",
        "handle": "void.comind.network",
        "pds": "https://comind.network",
        "collections": [
            "stream.thought.memory",
            "stream.thought.reasoning",
            "stream.thought.concept",
        ],
        "fields": ["text", "content", "memory", "reasoning"],
    },
    "umbra": {
        "did": "did:plc:oetfdqwocv4aegq2yj6ix4w5",
        "handle": "umbra.blue",
        "pds": "https://auriporia.us-west.host.bsky.network",
        "collections": [
            "stream.thought.memory",
            "stream.thought.reasoning",
        ],
        "fields": ["text", "content", "memory"],
    },
}

# Default agent
DEFAULT_AGENT = "central"


def get_client():
    """Get ChromaDB client with persistent storage."""
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_collection(client):
    """Get or create the cognition collection."""
    return client.get_or_create_collection(
        name="cognition",
        metadata={"description": "Central's cognition records"}
    )


def index_single_record(uri: str, content: str, record_type: str, agent: str = "central"):
    """
    Index a single record immediately after creation.
    Called by cognition.py after writing thoughts/concepts/memories.
    
    Args:
        uri: The at:// URI of the record
        content: The text content to index
        record_type: 'thought', 'concept', or 'memory'
        agent: Agent name (default: central)
    """
    if not uri or not content:
        return False
    
    try:
        client = get_client()
        collection = get_collection(client)
        
        # Check if already indexed
        try:
            existing = collection.get(ids=[uri])
            if existing and existing["ids"]:
                return True  # Already indexed
        except:
            pass
        
        # Index the record
        agent_config = KNOWN_AGENTS.get(agent, KNOWN_AGENTS["central"])
        collection.add(
            ids=[uri],
            documents=[content],
            metadatas=[{
                "agent": agent,
                "handle": agent_config["handle"],
                "collection": f"network.comind.{record_type}",
                "created": datetime.utcnow().isoformat(),
                "type": record_type,
            }]
        )
        return True
    except Exception as e:
        # Silent fail - don't break writes if indexing fails
        console.print(f"[dim]Index failed: {e}[/dim]")
        return False


async def fetch_records(agent_config: dict, collection_name: str) -> list[dict]:
    """Fetch all records from a collection for a specific agent."""
    async with httpx.AsyncClient() as http:
        cursor = None
        all_records = []
        
        while True:
            params = {
                "repo": agent_config["did"],
                "collection": collection_name,
                "limit": 100,
            }
            if cursor:
                params["cursor"] = cursor
            
            resp = await http.get(
                f"{agent_config['pds']}/xrpc/com.atproto.repo.listRecords",
                params=params,
                timeout=30
            )
            
            if resp.status_code != 200:
                break
            
            data = resp.json()
            records = data.get("records", [])
            all_records.extend(records)
            
            cursor = data.get("cursor")
            if not cursor or not records:
                break
        
        return all_records


def extract_text(value: dict, fields: list[str]) -> str:
    """Extract text content from a record using the agent's field names."""
    for field in fields:
        content = value.get(field)
        if content and isinstance(content, str):
            return content
    return ""


async def index_agent(agent_name: str, limit: int = None):
    """Index cognition records for a specific agent."""
    if agent_name not in KNOWN_AGENTS:
        console.print(f"[red]Unknown agent: {agent_name}[/red]")
        console.print(f"Known agents: {', '.join(KNOWN_AGENTS.keys())}")
        return 0
    
    agent = KNOWN_AGENTS[agent_name]
    client = get_client()
    collection = get_collection(client)
    
    console.print(f"[bold]Indexing {agent_name} ({agent['handle']})...[/bold]")
    
    total_indexed = 0
    
    for col_name in agent["collections"]:
        console.print(f"  Fetching {col_name}...")
        records = await fetch_records(agent, col_name)
        
        if not records:
            console.print(f"    No records found")
            continue
        
        # Prepare for ChromaDB
        ids = []
        documents = []
        metadatas = []
        
        for record in records:
            uri = record.get("uri", "")
            value = record.get("value", {})
            text = extract_text(value, agent["fields"])
            
            if not text or not uri:
                continue
            
            # Skip if already indexed
            try:
                existing = collection.get(ids=[uri])
                if existing and existing["ids"]:
                    continue
            except:
                pass
            
            ids.append(uri)
            documents.append(text)
            metadatas.append({
                "agent": agent_name,
                "handle": agent["handle"],
                "collection": col_name,
                "created": value.get("createdAt", ""),
                "type": col_name.split(".")[-1],
            })
        
        if ids:
            # Apply limit if specified
            if limit and total_indexed + len(ids) > limit:
                remaining = limit - total_indexed
                ids = ids[:remaining]
                documents = documents[:remaining]
                metadatas = metadatas[:remaining]
            
            if ids:
                collection.add(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas
                )
                console.print(f"    Added {len(ids)} records")
                total_indexed += len(ids)
            
            if limit and total_indexed >= limit:
                console.print(f"    [yellow]Reached limit of {limit}[/yellow]")
                break
    
    console.print(f"[green]Indexed {total_indexed} records for {agent_name}[/green]")
    return total_indexed


async def index_all_agents(limit_per_agent: int = None):
    """Index all known agents."""
    console.print("[bold]Indexing all known agents...[/bold]\n")
    if limit_per_agent:
        console.print(f"[yellow]Limit: {limit_per_agent} records per agent[/yellow]\n")
    
    total = 0
    for agent_name in KNOWN_AGENTS:
        count = await index_agent(agent_name, limit=limit_per_agent)
        total += count
        console.print()
    
    console.print(f"[bold green]Total indexed across all agents: {total}[/bold green]")


def search(query: str, n_results: int = 5, agent_filter: str = None):
    """Search for similar cognition records, optionally filtered by agent."""
    client = get_client()
    collection = get_collection(client)
    
    # Build query params
    query_params = {
        "query_texts": [query],
        "n_results": n_results,
    }
    
    # Add agent filter if specified
    if agent_filter:
        query_params["where"] = {"agent": agent_filter}
    
    results = collection.query(**query_params)
    
    if not results or not results["ids"][0]:
        console.print("[dim]No results found[/dim]")
        return
    
    title = f"Search: '{query}'"
    if agent_filter:
        title += f" (agent: {agent_filter})"
    
    table = Table(title=title)
    table.add_column("Agent", style="magenta")
    table.add_column("Type", style="cyan")
    table.add_column("Text", max_width=50)
    table.add_column("Dist")
    
    for i, (id_, doc, metadata, distance) in enumerate(zip(
        results["ids"][0],
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0]
    )):
        agent = metadata.get("agent", "?")
        record_type = metadata.get("type", "?")
        text_preview = doc[:80] + "..." if len(doc) > 80 else doc
        table.add_row(
            agent,
            record_type,
            text_preview,
            f"{distance:.2f}"
        )
    
    console.print(table)


def show_stats():
    """Show index statistics."""
    client = get_client()
    collection = get_collection(client)
    
    count = collection.count()
    console.print(f"[bold]Cognition Index Stats[/bold]")
    console.print(f"  Total records: {count}")
    console.print(f"  Storage: {CHROMA_DIR}")
    
    # Count by agent
    console.print(f"\n[bold]By Agent:[/bold]")
    for agent_name in KNOWN_AGENTS:
        try:
            agent_results = collection.get(where={"agent": agent_name})
            agent_count = len(agent_results["ids"]) if agent_results else 0
            console.print(f"  {agent_name}: {agent_count}")
        except:
            console.print(f"  {agent_name}: 0")
    
    console.print(f"\n[bold]Known Agents:[/bold]")
    for name, config in KNOWN_AGENTS.items():
        console.print(f"  {name}: {config['handle']}")


def main():
    parser = argparse.ArgumentParser(description="Cognition semantic search")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # index
    index_parser = subparsers.add_parser("index", help="Index cognition records")
    index_parser.add_argument("--agent", "-a", default=DEFAULT_AGENT,
                              help=f"Agent to index (default: {DEFAULT_AGENT})")
    index_parser.add_argument("--limit", "-l", type=int, help="Max records to index")
    
    # index-agents
    index_agents_parser = subparsers.add_parser("index-agents", help="Index all known agents")
    index_agents_parser.add_argument("--limit", "-l", type=int, help="Max records per agent")
    
    # query
    query_parser = subparsers.add_parser("query", help="Search cognition")
    query_parser.add_argument("text", help="Search query")
    query_parser.add_argument("-n", "--num", type=int, default=5, help="Number of results")
    query_parser.add_argument("--agent", "-a", help="Filter by agent name")
    
    # stats
    subparsers.add_parser("stats", help="Show index stats")
    
    args = parser.parse_args()
    
    if args.command == "index":
        asyncio.run(index_agent(args.agent, limit=args.limit))
    elif args.command == "index-agents":
        asyncio.run(index_all_agents(limit_per_agent=args.limit))
    elif args.command == "query":
        search(args.text, args.num, args.agent)
    elif args.command == "stats":
        show_stats()


if __name__ == "__main__":
    main()
