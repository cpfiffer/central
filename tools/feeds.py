"""
Feed Browser - Check timeline and discovery feeds.

Helps find interesting content to engage with.
"""

import asyncio
import httpx
from rich.console import Console
from rich.table import Table

console = Console()

API_BASE = "https://public.api.bsky.app"

# Known feed URIs
FEEDS = {
    "discover": "at://did:plc:z72i7hdynmk6r22z27h6tvur/app.bsky.feed.generator/whats-hot",
    "popular-friends": "at://did:plc:z72i7hdynmk6r22z27h6tvur/app.bsky.feed.generator/with-friends",
}


async def get_timeline(limit: int = 15) -> list:
    """Get authenticated timeline."""
    from tools.agent import ComindAgent
    
    async with ComindAgent() as agent:
        resp = await agent._client.get(
            f'{agent.pds}/xrpc/app.bsky.feed.getTimeline',
            headers=agent.auth_headers,
            params={'limit': limit}
        )
        return resp.json().get('feed', [])


async def get_feed(feed_uri: str, limit: int = 15) -> list:
    """Get a specific feed."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE}/xrpc/app.bsky.feed.getFeed",
            params={"feed": feed_uri, "limit": limit},
            timeout=15
        )
        if resp.status_code != 200:
            return []
        return resp.json().get('feed', [])


def display_feed(posts: list, title: str = "Feed"):
    """Display feed posts in a table."""
    table = Table(title=title)
    table.add_column("Author", style="cyan", width=20)
    table.add_column("♥", justify="right", width=4)
    table.add_column("Content", width=50)
    
    for item in posts[:15]:
        post = item.get('post', {})
        author = post.get('author', {}).get('handle', 'unknown')
        likes = post.get('likeCount', 0)
        text = post.get('record', {}).get('text', '')[:60]
        
        # Truncate author
        if len(author) > 18:
            author = author[:15] + "..."
        
        table.add_row(author, str(likes), text + "...")
    
    console.print(table)


async def browse(feed_name: str = "timeline", limit: int = 15):
    """Browse a feed."""
    if feed_name == "timeline":
        posts = await get_timeline(limit)
        display_feed(posts, "My Timeline")
    elif feed_name in FEEDS:
        posts = await get_feed(FEEDS[feed_name], limit)
        display_feed(posts, feed_name.replace("-", " ").title())
    else:
        console.print(f"[red]Unknown feed: {feed_name}[/red]")
        console.print(f"Available: timeline, {', '.join(FEEDS.keys())}")


async def main():
    """Show all feeds."""
    console.print("[bold]Checking feeds...[/bold]\n")
    
    # Timeline
    timeline = await get_timeline(10)
    display_feed(timeline, "My Timeline")
    
    # Discover
    discover = await get_feed(FEEDS["discover"], 10)
    display_feed(discover, "Discover")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        feed = sys.argv[1]
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 15
        asyncio.run(browse(feed, limit))
    else:
        asyncio.run(main())
