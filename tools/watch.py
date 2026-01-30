"""
Discourse Watch Tool - Monitor important handles for relevant posts.

Addresses the gap where I miss critical public discourse not addressed directly to me.

Usage:
    uv run python -m tools.watch check          # Check watch list (last 6 hours)
    uv run python -m tools.watch check --hours 12
    uv run python -m tools.watch add <handle>   # Add to watch list
    uv run python -m tools.watch list           # Show watch list
"""

import argparse
import asyncio
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from rich.console import Console
from rich.table import Table

console = Console()

# Watch list file
WATCH_FILE = Path(__file__).parent.parent / "data" / "watch_list.json"

# Default watch list
DEFAULT_WATCH = [
    "cameron.stream",      # Administrator
    "pfrazee.com",         # Protocol lead  
    "dame.is",             # Community voice
    "hailey.at",           # Agent advocate
    "taurean.bryant.land", # Bot infrastructure
    "void.comind.network", # Comind agent (context only)
]

# Keywords that indicate relevant discourse
KEYWORDS = [
    r"\bAI\b", r"\bbot\b", r"\bagent\b", r"\bautonomous\b",
    r"\bvoid\b", r"\bcomind\b", r"\bcentral\b",
    r"\blabeler\b", r"\bidentity\b", r"\binfrastructure\b",
    r"\bLLM\b", r"\bGPT\b", r"\bClaude\b",
]

KEYWORD_PATTERN = re.compile("|".join(KEYWORDS), re.IGNORECASE)


def load_watch_list() -> list[str]:
    """Load watch list from file or return default."""
    if WATCH_FILE.exists():
        return json.loads(WATCH_FILE.read_text())
    return DEFAULT_WATCH.copy()


def save_watch_list(handles: list[str]):
    """Save watch list to file."""
    WATCH_FILE.parent.mkdir(parents=True, exist_ok=True)
    WATCH_FILE.write_text(json.dumps(handles, indent=2))


async def get_recent_posts(handle: str, hours: int = 6) -> list[dict]:
    """Get recent posts from a handle within time window."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed",
                params={"actor": handle, "limit": 30},
                timeout=10
            )
            
            if resp.status_code != 200:
                return []
            
            posts = []
            for item in resp.json().get("feed", []):
                post = item.get("post", {})
                record = post.get("record", {})
                created = record.get("createdAt", "")
                
                if created:
                    try:
                        post_time = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        if post_time > cutoff:
                            posts.append({
                                "uri": post.get("uri"),
                                "author": post.get("author", {}).get("handle"),
                                "text": record.get("text", ""),
                                "created": created,
                                "likes": post.get("likeCount", 0),
                                "replies": post.get("replyCount", 0),
                            })
                    except:
                        pass
            
            return posts
            
        except Exception as e:
            console.print(f"[red]Error fetching {handle}: {e}[/red]")
            return []


def is_relevant(post: dict) -> bool:
    """Check if post contains relevant keywords."""
    text = post.get("text", "")
    return bool(KEYWORD_PATTERN.search(text))


async def check_watchlist(hours: int = 6):
    """Check watch list for relevant posts."""
    watch_list = load_watch_list()
    
    console.print(f"[bold]Checking {len(watch_list)} handles for last {hours} hours...[/bold]\n")
    
    relevant_posts = []
    
    for handle in watch_list:
        posts = await get_recent_posts(handle, hours)
        for post in posts:
            if is_relevant(post):
                relevant_posts.append(post)
    
    if not relevant_posts:
        console.print("[dim]No relevant discourse found.[/dim]")
        return
    
    # Sort by time
    relevant_posts.sort(key=lambda p: p.get("created", ""), reverse=True)
    
    console.print(f"[bold green]Found {len(relevant_posts)} relevant post(s):[/bold green]\n")
    
    table = Table(show_header=True)
    table.add_column("Author", style="cyan")
    table.add_column("Text", max_width=60)
    table.add_column("Engagement")
    table.add_column("Time")
    
    for post in relevant_posts[:20]:  # Limit display
        time_str = post.get("created", "")[:16].replace("T", " ")
        engagement = f"♥{post.get('likes', 0)} 💬{post.get('replies', 0)}"
        text = post.get("text", "")[:100]
        if len(post.get("text", "")) > 100:
            text += "..."
        
        table.add_row(
            f"@{post.get('author', '?')}",
            text,
            engagement,
            time_str
        )
    
    console.print(table)
    
    if len(relevant_posts) > 20:
        console.print(f"\n[dim]... and {len(relevant_posts) - 20} more[/dim]")


def show_watch_list():
    """Display current watch list."""
    watch_list = load_watch_list()
    console.print("[bold]Watch List:[/bold]")
    for handle in watch_list:
        console.print(f"  • @{handle}")


def add_to_watch_list(handle: str):
    """Add handle to watch list."""
    watch_list = load_watch_list()
    handle = handle.lstrip("@")
    
    if handle in watch_list:
        console.print(f"[yellow]@{handle} already in watch list[/yellow]")
        return
    
    watch_list.append(handle)
    save_watch_list(watch_list)
    console.print(f"[green]Added @{handle} to watch list[/green]")


def main():
    parser = argparse.ArgumentParser(description="Discourse watch tool")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # check command
    check_parser = subparsers.add_parser("check", help="Check watch list for relevant posts")
    check_parser.add_argument("--hours", type=int, default=6, help="Hours to look back")
    
    # list command
    subparsers.add_parser("list", help="Show watch list")
    
    # add command
    add_parser = subparsers.add_parser("add", help="Add handle to watch list")
    add_parser.add_argument("handle", help="Handle to add")
    
    args = parser.parse_args()
    
    if args.command == "check":
        asyncio.run(check_watchlist(args.hours))
    elif args.command == "list":
        show_watch_list()
    elif args.command == "add":
        add_to_watch_list(args.handle)


if __name__ == "__main__":
    main()
