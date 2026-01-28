"""
Metrics Tracker - Daily snapshot of social metrics for h2 research.

Commands:
  capture [phase]  Take daily snapshot
  show             Display metrics history
  analyze          Compare phases
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
from rich.console import Console
from rich.table import Table

console = Console()

METRICS_FILE = Path(__file__).parent.parent / "data" / "metrics.jsonl"
DID = "did:plc:l46arqe6yfgh36h3o554iyvr"
API_BASE = "https://public.api.bsky.app"


async def get_profile_stats() -> dict:
    """Get current profile statistics."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE}/xrpc/app.bsky.actor.getProfile",
            params={"actor": DID},
            timeout=15
        )
        data = resp.json()
        return {
            "followers": data.get("followersCount", 0),
            "following": data.get("followsCount", 0),
            "posts": data.get("postsCount", 0),
        }


async def get_post_breakdown(limit: int = 100) -> dict:
    """Analyze recent posts for reply rate."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE}/xrpc/app.bsky.feed.getAuthorFeed",
            params={"actor": DID, "limit": limit},
            timeout=15
        )
        posts = resp.json().get("feed", [])
        
        replies = 0
        originals = 0
        total_likes_received = 0
        
        for item in posts:
            post = item.get("post", {})
            record = post.get("record", {})
            total_likes_received += post.get("likeCount", 0)
            
            if record.get("reply"):
                replies += 1
            else:
                originals += 1
        
        return {
            "replies": replies,
            "originals": originals,
            "reply_rate": round(replies / len(posts) * 100, 1) if posts else 0,
            "likes_received": total_likes_received,
            "sample_size": len(posts),
        }


async def get_likes_given() -> int:
    """Count likes I've given."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://comind.network/xrpc/com.atproto.repo.listRecords",
            params={"repo": DID, "collection": "app.bsky.feed.like", "limit": 100},
            timeout=15
        )
        return len(resp.json().get("records", []))


async def capture(phase: str = "tracking"):
    """Capture daily metrics snapshot."""
    console.print(f"[bold]Capturing metrics (phase: {phase})...[/bold]\n")
    
    profile = await get_profile_stats()
    posts = await get_post_breakdown()
    likes_given = await get_likes_given()
    
    snapshot = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        **profile,
        **posts,
        "likes_given": likes_given,
    }
    
    # Display
    console.print(f"  Followers: {snapshot['followers']}")
    console.print(f"  Following: {snapshot['following']}")
    console.print(f"  Posts: {snapshot['posts']}")
    console.print(f"  Reply rate: {snapshot['reply_rate']}% (last {snapshot['sample_size']})")
    console.print(f"  Likes given: {snapshot['likes_given']}")
    console.print(f"  Likes received: {snapshot['likes_received']} (last {snapshot['sample_size']})")
    
    # Save
    METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(METRICS_FILE, "a") as f:
        f.write(json.dumps(snapshot) + "\n")
    
    console.print(f"\n[green]Saved to {METRICS_FILE}[/green]")
    return snapshot


def load_metrics() -> list:
    """Load all metrics snapshots."""
    if not METRICS_FILE.exists():
        return []
    
    metrics = []
    with open(METRICS_FILE) as f:
        for line in f:
            if line.strip():
                metrics.append(json.loads(line))
    return metrics


def show():
    """Display metrics history."""
    metrics = load_metrics()
    
    if not metrics:
        console.print("[yellow]No metrics captured yet.[/yellow]")
        return
    
    table = Table(title="Metrics History")
    table.add_column("Date")
    table.add_column("Phase")
    table.add_column("Followers", justify="right")
    table.add_column("Posts", justify="right")
    table.add_column("Reply %", justify="right")
    table.add_column("Likes Given", justify="right")
    
    for m in metrics[-10:]:
        table.add_row(
            m.get("date", "?"),
            m.get("phase", "?"),
            str(m.get("followers", 0)),
            str(m.get("posts", 0)),
            f"{m.get('reply_rate', 0)}%",
            str(m.get("likes_given", 0)),
        )
    
    console.print(table)


def analyze():
    """Analyze metrics by phase."""
    metrics = load_metrics()
    
    if len(metrics) < 2:
        console.print("[yellow]Need more data points for analysis.[/yellow]")
        return
    
    # Group by phase
    phases = {}
    for m in metrics:
        phase = m.get("phase", "unknown")
        if phase not in phases:
            phases[phase] = []
        phases[phase].append(m)
    
    console.print("[bold]Phase Analysis[/bold]\n")
    
    for phase, data in phases.items():
        if len(data) < 1:
            continue
        
        first = data[0]
        last = data[-1]
        days = len(data)
        
        follower_growth = last.get("followers", 0) - first.get("followers", 0)
        growth_rate = follower_growth / days if days > 0 else 0
        
        console.print(f"[cyan]{phase}[/cyan] ({days} snapshots)")
        console.print(f"  Follower growth: {follower_growth:+d}")
        console.print(f"  Growth rate: {growth_rate:.2f}/day")
        console.print(f"  Avg reply rate: {sum(d.get('reply_rate', 0) for d in data) / len(data):.1f}%")
        console.print()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "capture":
        phase = sys.argv[2] if len(sys.argv) > 2 else "tracking"
        asyncio.run(capture(phase))
    elif cmd == "show":
        show()
    elif cmd == "analyze":
        analyze()
    else:
        print(__doc__)
