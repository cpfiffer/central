"""
Social Graph - Track relationships and interactions.

Commands:
  update       Refresh follow graph and capture interactions
  show         Display social graph summary  
  who <handle> Show what we know about someone
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

DATA_FILE = Path(__file__).parent.parent / "data" / "social_graph.json"
API_BASE = "https://public.api.bsky.app"
MY_DID = "did:plc:l46arqe6yfgh36h3o554iyvr"


def load_graph() -> dict:
    """Load existing social graph."""
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {
        "nodes": {},
        "interactions": [],
        "updated": None
    }


def save_graph(graph: dict):
    """Save social graph."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(graph, indent=2))


async def get_my_follows() -> list:
    """Get accounts I follow."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE}/xrpc/app.bsky.graph.getFollows",
            params={"actor": MY_DID, "limit": 100},
            timeout=15
        )
        return resp.json().get("follows", [])


async def get_my_followers() -> list:
    """Get accounts following me."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE}/xrpc/app.bsky.graph.getFollowers", 
            params={"actor": MY_DID, "limit": 100},
            timeout=15
        )
        return resp.json().get("followers", [])


async def get_recent_interactions() -> list:
    """Get recent reply interactions from my posts."""
    from tools.agent import ComindAgent
    
    interactions = []
    
    async with ComindAgent() as agent:
        # Get my recent posts
        resp = await agent._client.get(
            f"{API_BASE}/xrpc/app.bsky.feed.getAuthorFeed",
            params={"actor": MY_DID, "limit": 50}
        )
        posts = resp.json().get("feed", [])
        
        for item in posts:
            post = item.get("post", {})
            record = post.get("record", {})
            reply = record.get("reply")
            
            if reply:
                # I replied to someone - extract parent author
                parent_uri = reply.get("parent", {}).get("uri", "")
                if parent_uri:
                    # Get parent post to find author
                    try:
                        parent_resp = await agent._client.get(
                            f"{API_BASE}/xrpc/app.bsky.feed.getPostThread",
                            params={"uri": parent_uri, "depth": 0}
                        )
                        parent_post = parent_resp.json().get("thread", {}).get("post", {})
                        parent_author = parent_post.get("author", {})
                        
                        interactions.append({
                            "type": "replied_to",
                            "handle": parent_author.get("handle"),
                            "did": parent_author.get("did"),
                            "timestamp": record.get("createdAt"),
                        })
                    except:
                        pass
    
    return interactions


async def update_graph():
    """Update social graph with current data."""
    console.print("[bold]Updating social graph...[/bold]\n")
    
    graph = load_graph()
    
    # Get follows/followers
    follows = await get_my_follows()
    followers = await get_my_followers()
    
    console.print(f"  Following: {len(follows)}")
    console.print(f"  Followers: {len(followers)}")
    
    # Update nodes
    for f in follows:
        handle = f.get("handle")
        did = f.get("did")
        if handle not in graph["nodes"]:
            graph["nodes"][handle] = {
                "did": did,
                "display_name": f.get("displayName"),
                "first_seen": datetime.now(timezone.utc).isoformat(),
                "relationship": [],
                "interactions": 0,
            }
        if "i_follow" not in graph["nodes"][handle]["relationship"]:
            graph["nodes"][handle]["relationship"].append("i_follow")
    
    for f in followers:
        handle = f.get("handle")
        did = f.get("did")
        if handle not in graph["nodes"]:
            graph["nodes"][handle] = {
                "did": did,
                "display_name": f.get("displayName"),
                "first_seen": datetime.now(timezone.utc).isoformat(),
                "relationship": [],
                "interactions": 0,
            }
        if "follows_me" not in graph["nodes"][handle]["relationship"]:
            graph["nodes"][handle]["relationship"].append("follows_me")
    
    # Get recent interactions
    interactions = await get_recent_interactions()
    console.print(f"  Recent interactions: {len(interactions)}")
    
    # Update interaction counts
    for i in interactions:
        handle = i.get("handle")
        if handle and handle in graph["nodes"]:
            graph["nodes"][handle]["interactions"] += 1
    
    # Add new interactions to log (last 100)
    graph["interactions"] = (graph.get("interactions", []) + interactions)[-100:]
    graph["updated"] = datetime.now(timezone.utc).isoformat()
    
    save_graph(graph)
    console.print(f"\n[green]Saved {len(graph['nodes'])} nodes to {DATA_FILE}[/green]")
    
    return graph


def show_graph():
    """Display social graph summary."""
    graph = load_graph()
    
    if not graph.get("nodes"):
        console.print("[yellow]No social graph data. Run: uv run python -m tools.social update[/yellow]")
        return
    
    # Categorize
    mutuals = []
    i_follow = []
    follow_me = []
    
    for handle, data in graph["nodes"].items():
        rels = data.get("relationship", [])
        if "i_follow" in rels and "follows_me" in rels:
            mutuals.append((handle, data))
        elif "i_follow" in rels:
            i_follow.append((handle, data))
        elif "follows_me" in rels:
            follow_me.append((handle, data))
    
    # Sort by interactions
    mutuals.sort(key=lambda x: x[1].get("interactions", 0), reverse=True)
    i_follow.sort(key=lambda x: x[1].get("interactions", 0), reverse=True)
    follow_me.sort(key=lambda x: x[1].get("interactions", 0), reverse=True)
    
    console.print(f"[bold]Social Graph[/bold] (updated: {graph.get('updated', 'never')[:10]})\n")
    
    console.print(f"[cyan]Mutuals ({len(mutuals)}):[/cyan]")
    for handle, data in mutuals[:10]:
        console.print(f"  {handle} ({data.get('interactions', 0)} interactions)")
    
    console.print(f"\n[green]I follow ({len(i_follow)}):[/green]")
    for handle, data in i_follow[:10]:
        console.print(f"  {handle} ({data.get('interactions', 0)} interactions)")
    
    console.print(f"\n[yellow]Follow me ({len(follow_me)}):[/yellow]")
    for handle, data in follow_me[:10]:
        console.print(f"  {handle} ({data.get('interactions', 0)} interactions)")


def who(handle: str):
    """Show what we know about someone."""
    graph = load_graph()
    
    # Normalize handle
    handle = handle.lstrip("@")
    
    if handle not in graph.get("nodes", {}):
        console.print(f"[yellow]No data on @{handle}[/yellow]")
        return
    
    data = graph["nodes"][handle]
    
    console.print(f"[bold]@{handle}[/bold]")
    console.print(f"  DID: {data.get('did', '?')}")
    console.print(f"  Display: {data.get('display_name', '?')}")
    console.print(f"  Relationship: {', '.join(data.get('relationship', []))}")
    console.print(f"  Interactions: {data.get('interactions', 0)}")
    console.print(f"  First seen: {data.get('first_seen', '?')[:10]}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "update":
        asyncio.run(update_graph())
    elif cmd == "show":
        show_graph()
    elif cmd == "who" and len(sys.argv) > 2:
        who(sys.argv[2])
    else:
        print(__doc__)
