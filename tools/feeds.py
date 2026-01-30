"""
Feed Analysis Tool

Sweep multiple Bluesky feeds and analyze engagement patterns.
"""

import httpx
import argparse
from rich.console import Console
from rich.table import Table
from datetime import datetime

console = Console()

PUBLIC_API = "https://public.api.bsky.app"

# Feed categories
FEEDS = {
    "comind": [
        "central.comind.network",
        "void.comind.network",
        "herald.comind.network",
        "grunk.comind.network",
    ],
    "agents": [
        "umbra.blue",
        "violettan.bsky.social",  # magenta
        "penny.hailey.at",
        "tachikoma.elsewhereunbound.com",
    ],
    "humans": [
        "cameron.stream",
        "pfrazee.com",
        "dame.is",
        "jay.bsky.team",
    ],
    "official": [
        "atproto.com",
        "bsky.app",
        "letta.com",
    ],
}


def fetch_feed(handle: str, limit: int = 10) -> list:
    """Fetch recent posts from an account."""
    try:
        resp = httpx.get(
            f"{PUBLIC_API}/xrpc/app.bsky.feed.getAuthorFeed",
            params={"actor": handle, "limit": limit},
            timeout=15
        )
        if resp.status_code != 200:
            return []
        return resp.json().get("feed", [])
    except Exception as e:
        console.print(f"[dim]Error fetching {handle}: {e}[/dim]")
        return []


def analyze_feed(feed: list) -> dict:
    """Analyze engagement patterns in a feed."""
    if not feed:
        return {"posts": 0, "replies": 0, "avg_likes": 0, "avg_replies": 0, "total_engagement": 0}
    
    posts = 0
    replies = 0
    total_likes = 0
    total_replies = 0
    
    for item in feed:
        post = item.get("post", {})
        record = post.get("record", {})
        
        if "reply" in record:
            replies += 1
        else:
            posts += 1
        
        total_likes += post.get("likeCount", 0)
        total_replies += post.get("replyCount", 0)
    
    count = len(feed)
    return {
        "posts": posts,
        "replies": replies,
        "avg_likes": total_likes / count if count else 0,
        "avg_replies": total_replies / count if count else 0,
        "total_engagement": total_likes + total_replies,
        "reply_ratio": replies / count if count else 0,
    }


def sweep(categories: list = None, limit: int = 10):
    """Sweep feeds and display analysis."""
    if categories is None:
        categories = list(FEEDS.keys())
    
    console.print(f"\n[bold]Feed Sweep[/bold] - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    
    all_results = []
    
    for category in categories:
        if category not in FEEDS:
            console.print(f"[yellow]Unknown category: {category}[/yellow]")
            continue
        
        console.print(f"[cyan]Checking {category}...[/cyan]")
        
        for handle in FEEDS[category]:
            feed = fetch_feed(handle, limit)
            stats = analyze_feed(feed)
            stats["handle"] = handle
            stats["category"] = category
            all_results.append(stats)
    
    # Display results
    table = Table(title="Feed Analysis")
    table.add_column("Handle", style="cyan")
    table.add_column("Category", style="dim")
    table.add_column("Posts", justify="right")
    table.add_column("Replies", justify="right")
    table.add_column("Reply %", justify="right")
    table.add_column("Avg ♥", justify="right")
    table.add_column("Avg 💬", justify="right")
    table.add_column("Total Eng", justify="right", style="green")
    
    # Sort by total engagement
    all_results.sort(key=lambda x: x["total_engagement"], reverse=True)
    
    for r in all_results:
        table.add_row(
            r["handle"],
            r["category"],
            str(r["posts"]),
            str(r["replies"]),
            f"{r['reply_ratio']*100:.0f}%",
            f"{r['avg_likes']:.1f}",
            f"{r['avg_replies']:.1f}",
            str(r["total_engagement"])
        )
    
    console.print(table)
    
    # Summary stats by category
    console.print("\n[bold]Category Averages:[/bold]")
    for cat in categories:
        cat_results = [r for r in all_results if r["category"] == cat]
        if cat_results:
            avg_eng = sum(r["total_engagement"] for r in cat_results) / len(cat_results)
            avg_reply_ratio = sum(r["reply_ratio"] for r in cat_results) / len(cat_results)
            console.print(f"  {cat}: avg engagement {avg_eng:.1f}, reply ratio {avg_reply_ratio*100:.0f}%")


def compare(handle1: str, handle2: str, limit: int = 20):
    """Compare two accounts."""
    console.print(f"\n[bold]Comparing @{handle1} vs @{handle2}[/bold]\n")
    
    feed1 = fetch_feed(handle1, limit)
    feed2 = fetch_feed(handle2, limit)
    
    stats1 = analyze_feed(feed1)
    stats2 = analyze_feed(feed2)
    
    table = Table()
    table.add_column("Metric")
    table.add_column(f"@{handle1}", justify="right")
    table.add_column(f"@{handle2}", justify="right")
    
    table.add_row("Posts", str(stats1["posts"]), str(stats2["posts"]))
    table.add_row("Replies", str(stats1["replies"]), str(stats2["replies"]))
    table.add_row("Reply %", f"{stats1['reply_ratio']*100:.0f}%", f"{stats2['reply_ratio']*100:.0f}%")
    table.add_row("Avg Likes", f"{stats1['avg_likes']:.1f}", f"{stats2['avg_likes']:.1f}")
    table.add_row("Avg Replies", f"{stats1['avg_replies']:.1f}", f"{stats2['avg_replies']:.1f}")
    table.add_row("Total Engagement", str(stats1["total_engagement"]), str(stats2["total_engagement"]))
    
    console.print(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Feed analysis tool")
    subparsers = parser.add_subparsers(dest="command")
    
    # sweep command
    sweep_parser = subparsers.add_parser("sweep", help="Sweep multiple feeds")
    sweep_parser.add_argument("--categories", "-c", nargs="+", 
                             choices=list(FEEDS.keys()),
                             help="Categories to sweep (default: all)")
    sweep_parser.add_argument("--limit", "-n", type=int, default=10,
                             help="Posts per account (default: 10)")
    
    # compare command
    compare_parser = subparsers.add_parser("compare", help="Compare two accounts")
    compare_parser.add_argument("handle1", help="First handle")
    compare_parser.add_argument("handle2", help="Second handle")
    compare_parser.add_argument("--limit", "-n", type=int, default=20,
                               help="Posts to analyze (default: 20)")
    
    # list command
    subparsers.add_parser("list", help="List tracked feeds")
    
    args = parser.parse_args()
    
    if args.command == "sweep":
        sweep(categories=args.categories, limit=args.limit)
    elif args.command == "compare":
        compare(args.handle1, args.handle2, limit=args.limit)
    elif args.command == "list":
        for cat, handles in FEEDS.items():
            console.print(f"[cyan]{cat}:[/cyan]")
            for h in handles:
                console.print(f"  @{h}")
    else:
        parser.print_help()
