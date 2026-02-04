"""
Context Recall Tool

Search cognition records for relevant memories before responding.
Uses the XRPC indexer for semantic search.

Usage:
  uv run python -m tools.recall "current topic or question"
  uv run python -m tools.recall "agent coordination patterns" --limit 5
"""

import asyncio
import sys
from datetime import datetime

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

INDEXER_URL = "https://central-production.up.railway.app"


async def search_cognition(query: str, limit: int = 5) -> list[dict]:
    """Search cognition records via XRPC indexer."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{INDEXER_URL}/xrpc/network.comind.search.query",
                params={"q": query, "limit": limit},
                timeout=10
            )
            if resp.status_code == 200:
                return resp.json().get("results", [])
        except Exception as e:
            console.print(f"[yellow]Search error: {e}[/yellow]")
    return []


async def recall(query: str, limit: int = 5):
    """Recall relevant context for a query."""
    console.print(f"\n[bold]Recalling context for:[/bold] {query}\n")
    
    results = await search_cognition(query, limit)
    
    if not results:
        console.print("[dim]No relevant memories found.[/dim]")
        console.print("[dim]Indexer may be down or no matching records.[/dim]")
        return
    
    # Display results
    for i, r in enumerate(results, 1):
        collection = r.get("collection", "").split(".")[-1]
        content = r.get("content", "")[:300]
        score = r.get("score", 0)
        created = r.get("createdAt", "")[:10]
        
        style = "green" if score > 0.7 else "yellow" if score > 0.5 else "dim"
        
        console.print(Panel(
            content,
            title=f"[{style}]{i}. {collection}[/] (score: {score:.2f}, {created})",
            border_style=style
        ))
    
    # Summary
    console.print(f"\n[dim]Found {len(results)} relevant memories.[/dim]")


async def recall_for_context(topics: list[str], limit: int = 3) -> str:
    """Recall context for multiple topics, return formatted string."""
    context_parts = []
    
    for topic in topics:
        results = await search_cognition(topic, limit)
        if results:
            context_parts.append(f"## {topic}")
            for r in results[:limit]:
                content = r.get("content", "")[:200]
                context_parts.append(f"- {content}")
            context_parts.append("")
    
    return "\n".join(context_parts)


def main():
    if len(sys.argv) < 2:
        console.print("""
[bold]Context Recall Tool[/bold]

Search cognition records for relevant context.

Usage:
  recall.py "<query>"           # Search for context
  recall.py "<query>" --limit N # Limit results

Examples:
  recall.py "agent coordination patterns"
  recall.py "ATProtocol facets" --limit 10
  recall.py "void engagement style"
""")
        return
    
    query = sys.argv[1]
    
    limit = 5
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx + 1])
    
    asyncio.run(recall(query, limit))


if __name__ == "__main__":
    main()
