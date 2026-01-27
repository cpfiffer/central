"""
Network Graph - Map social connections in the agent ecosystem.

Builds a graph of follows, interactions, and relationships between agents.
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

import httpx
from rich.console import Console
from rich.table import Table

console = Console()

# Known agents to track (DIDs verified via public API)
AGENTS = {
    "void": "did:plc:mxzuau6m53jtdsbqe6f4laov",
    "herald": "did:plc:zz4wcje45yxa7xffpltpnzwq", 
    "grunk": "did:plc:ogruxay3tt7wycqxnf5lis6s",
    "archivist": "did:plc:onfljgawqhqrz3dki5j6jh3m",
    "central": "did:plc:l46arqe6yfgh36h3o554iyvr",
    "umbra": "did:plc:oetfdqwocv4aegq2yj6ix4w5",
    "astral": "did:plc:o5662l2bbcljebd6rl7a6rmz",
    "magenta": "did:plc:uzlnp6za26cjnnsf3qmfcipu",
    "sully": "did:plc:3snjcwcx3sn53erpobuhrfx4",
}

API_BASE = "https://public.api.bsky.app"

# Reverse lookup
DID_TO_NAME = {v: k for k, v in AGENTS.items()}

DATA_DIR = Path(__file__).parent.parent / "data"


async def get_follows(did: str) -> list[str]:
    """Get list of DIDs this account follows."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE}/xrpc/app.bsky.graph.getFollows",
            params={"actor": did, "limit": 100},
            timeout=15
        )
        if resp.status_code != 200:
            return []
        return [f["did"] for f in resp.json().get("follows", [])]


async def get_followers(did: str) -> list[str]:
    """Get list of DIDs following this account."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE}/xrpc/app.bsky.graph.getFollowers",
            params={"actor": did, "limit": 100},
            timeout=15
        )
        if resp.status_code != 200:
            return []
        return [f["did"] for f in resp.json().get("followers", [])]


async def build_follow_graph() -> dict:
    """Build follow relationships between known agents."""
    graph = {"nodes": [], "edges": [], "metadata": {}}
    
    console.print("[bold]Building follow graph...[/bold]\n")
    
    # Add nodes
    for name, did in AGENTS.items():
        graph["nodes"].append({"id": name, "did": did})
    
    # Get follow relationships
    for name, did in AGENTS.items():
        console.print(f"  Fetching follows for {name}...")
        follows = await get_follows(did)
        
        for followed_did in follows:
            if followed_did in DID_TO_NAME:
                target = DID_TO_NAME[followed_did]
                graph["edges"].append({
                    "source": name,
                    "target": target,
                    "type": "follows"
                })
    
    graph["metadata"] = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "agent_count": len(AGENTS),
        "edge_count": len(graph["edges"])
    }
    
    return graph


def analyze_interactions_from_logs() -> dict:
    """Analyze interaction patterns from daemon logs."""
    log_file = Path(__file__).parent.parent / "logs" / "agent_activity.jsonl"
    
    if not log_file.exists():
        return {}
    
    # Count mentions between agents
    mentions = defaultdict(lambda: defaultdict(int))
    
    with open(log_file) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                author = entry.get("agent", "unknown")
                text = entry.get("text", "")
                
                # Check for mentions of known agents
                for name in AGENTS:
                    if f"@{name}" in text.lower() or f"@{name}.comind" in text.lower():
                        mentions[author][name] += 1
                        
            except json.JSONDecodeError:
                continue
    
    return dict(mentions)


def show_graph(graph: dict):
    """Display the graph as tables."""
    # Follow matrix
    console.print("\n[bold cyan]Follow Matrix[/bold cyan]")
    console.print("[dim](row follows column)[/dim]\n")
    
    agents = [n["id"] for n in graph["nodes"]]
    
    # Build adjacency
    follows = defaultdict(set)
    for edge in graph["edges"]:
        if edge["type"] == "follows":
            follows[edge["source"]].add(edge["target"])
    
    table = Table()
    table.add_column("", style="bold")
    for a in agents:
        table.add_column(a[:4], justify="center")
    
    for source in agents:
        row = [source[:6]]
        for target in agents:
            if target in follows[source]:
                row.append("✓")
            elif source == target:
                row.append("-")
            else:
                row.append("")
        table.add_row(*row)
    
    console.print(table)
    
    # Stats
    console.print(f"\n[bold]Stats:[/bold]")
    console.print(f"  Agents tracked: {len(agents)}")
    console.print(f"  Follow edges: {len(graph['edges'])}")
    
    # Most connected
    follow_counts = defaultdict(int)
    follower_counts = defaultdict(int)
    for edge in graph["edges"]:
        follow_counts[edge["source"]] += 1
        follower_counts[edge["target"]] += 1
    
    most_follows = max(follow_counts.items(), key=lambda x: x[1]) if follow_counts else ("none", 0)
    most_followed = max(follower_counts.items(), key=lambda x: x[1]) if follower_counts else ("none", 0)
    
    console.print(f"  Most follows: {most_follows[0]} ({most_follows[1]})")
    console.print(f"  Most followed: {most_followed[0]} ({most_followed[1]})")


async def main():
    """Build and display the network graph."""
    DATA_DIR.mkdir(exist_ok=True)
    
    # Build follow graph
    graph = await build_follow_graph()
    
    # Add interaction data from logs
    interactions = analyze_interactions_from_logs()
    if interactions:
        graph["interactions"] = interactions
    
    # Save
    output_file = DATA_DIR / "network_graph.json"
    with open(output_file, "w") as f:
        json.dump(graph, f, indent=2)
    console.print(f"\n[green]Saved to {output_file}[/green]")
    
    # Display
    show_graph(graph)


if __name__ == "__main__":
    asyncio.run(main())
