"""
ATProtocol Data Explorer

Explore public data on the AT Protocol network:
- User feeds and posts
- Repository records
- Thread views
- Search
"""

import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich.text import Text
from datetime import datetime
import json

console = Console()

PUBLIC_API = "https://public.api.bsky.app"


async def get_author_feed(actor: str, limit: int = 10) -> dict | None:
    """
    Get an author's feed (their posts and reposts).
    
    This is public data - no auth required.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{PUBLIC_API}/xrpc/app.bsky.feed.getAuthorFeed",
                params={"actor": actor, "limit": limit}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            console.print(f"[red]Error fetching feed: {e}[/red]")
            return None


async def get_post_thread(uri: str, depth: int = 6) -> dict | None:
    """
    Get a post thread (the post and its replies).
    
    URI format: at://did:plc:xxx/app.bsky.feed.post/xxx
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{PUBLIC_API}/xrpc/app.bsky.feed.getPostThread",
                params={"uri": uri, "depth": depth}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            console.print(f"[red]Error fetching thread: {e}[/red]")
            return None


async def get_repo_record(repo: str, collection: str, rkey: str) -> dict | None:
    """
    Get a specific record from a repository.
    
    This is the raw record data as stored in the user's repository.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{PUBLIC_API}/xrpc/com.atproto.repo.getRecord",
                params={"repo": repo, "collection": collection, "rkey": rkey}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            console.print(f"[red]Error fetching record: {e}[/red]")
            return None


async def list_repo_records(repo: str, collection: str, limit: int = 10) -> dict | None:
    """
    List records in a repository collection.
    
    Collections include:
    - app.bsky.feed.post (posts)
    - app.bsky.feed.like (likes)
    - app.bsky.feed.repost (reposts)
    - app.bsky.graph.follow (follows)
    - app.bsky.actor.profile (profile)
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{PUBLIC_API}/xrpc/com.atproto.repo.listRecords",
                params={"repo": repo, "collection": collection, "limit": limit}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            console.print(f"[red]Error listing records: {e}[/red]")
            return None


async def search_posts(query: str, limit: int = 10) -> dict | None:
    """
    Search for posts containing the given text.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{PUBLIC_API}/xrpc/app.bsky.feed.searchPosts",
                params={"q": query, "limit": limit}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            console.print(f"[red]Error searching: {e}[/red]")
            return None


async def search_actors(query: str, limit: int = 10) -> dict | None:
    """
    Search for users by name or handle.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{PUBLIC_API}/xrpc/app.bsky.actor.searchActors",
                params={"q": query, "limit": limit}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            console.print(f"[red]Error searching actors: {e}[/red]")
            return None


def format_timestamp(ts: str) -> str:
    """Format an ISO timestamp to a readable string."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return ts


def display_post(post: dict, prefix: str = ""):
    """Display a single post."""
    record = post.get("record", {})
    author = post.get("author", {})
    
    handle = author.get("handle", "unknown")
    display_name = author.get("displayName", handle)
    text = record.get("text", "")
    created_at = format_timestamp(record.get("createdAt", ""))
    
    likes = post.get("likeCount", 0)
    reposts = post.get("repostCount", 0)
    replies = post.get("replyCount", 0)
    
    uri = post.get("uri", "")
    
    console.print(f"{prefix}[bold cyan]{display_name}[/bold cyan] [dim]@{handle}[/dim] · {created_at}")
    console.print(f"{prefix}{text}")
    console.print(f"{prefix}[dim]💬 {replies}  🔄 {reposts}  ❤️  {likes}[/dim]")
    console.print(f"{prefix}[dim]URI: {uri}[/dim]")
    console.print()


def display_feed(feed_data: dict, title: str = "Feed"):
    """Display a feed of posts."""
    console.print(Panel(f"[bold]{title}[/bold]"))
    console.print()
    
    feed = feed_data.get("feed", [])
    for item in feed:
        post = item.get("post", {})
        reason = item.get("reason")  # Repost info
        
        if reason and reason.get("$type") == "app.bsky.feed.defs#reasonRepost":
            reposted_by = reason.get("by", {}).get("handle", "unknown")
            console.print(f"[dim]🔄 Reposted by @{reposted_by}[/dim]")
        
        display_post(post)


def display_search_results(results: dict, query: str):
    """Display search results."""
    console.print(Panel(f"[bold]Search Results for: {query}[/bold]"))
    console.print()
    
    posts = results.get("posts", [])
    for post in posts:
        display_post(post)


def display_thread(thread_data: dict):
    """Display a thread with replies."""
    thread = thread_data.get("thread", {})
    
    # Check if thread is blocked or not found
    if thread.get("$type") == "app.bsky.feed.defs#blockedPost":
        console.print("[red]This post is blocked[/red]")
        return
    if thread.get("$type") == "app.bsky.feed.defs#notFoundPost":
        console.print("[red]Post not found[/red]")
        return
    
    console.print(Panel("[bold]Thread View[/bold]"))
    console.print()
    
    # Display parent posts (context)
    parent = thread.get("parent")
    if parent and parent.get("$type") == "app.bsky.feed.defs#threadViewPost":
        console.print("[dim]─── Parent ───[/dim]")
        display_post(parent.get("post", {}), prefix="│ ")
    
    # Display main post
    console.print("[bold]─── Main Post ───[/bold]")
    display_post(thread.get("post", {}))
    
    # Display replies
    replies = thread.get("replies", [])
    if replies:
        console.print("[dim]─── Replies ───[/dim]")
        for reply in replies[:5]:  # Limit to first 5 replies
            if reply.get("$type") == "app.bsky.feed.defs#threadViewPost":
                display_post(reply.get("post", {}), prefix="  └─ ")


async def explore_user(handle: str, show_posts: int = 5):
    """
    Comprehensive exploration of a user's public data.
    """
    console.print(f"\n[bold]Exploring user: {handle}[/bold]\n")
    
    # Get their feed
    feed = await get_author_feed(handle, limit=show_posts)
    if feed:
        display_feed(feed, title=f"Recent posts by @{handle}")
    
    # Show available collections
    console.print(Panel("[bold]Repository Collections[/bold]"))
    collections = [
        ("app.bsky.feed.post", "Posts"),
        ("app.bsky.feed.like", "Likes"),
        ("app.bsky.feed.repost", "Reposts"),
        ("app.bsky.graph.follow", "Following"),
        ("app.bsky.actor.profile", "Profile"),
    ]
    
    table = Table()
    table.add_column("Collection", style="cyan")
    table.add_column("Description", style="green")
    
    for collection, desc in collections:
        table.add_row(collection, desc)
    
    console.print(table)
    console.print("\n[dim]Use list_repo_records() to explore these collections[/dim]")


async def explore_search(query: str):
    """Search for posts and users."""
    console.print(f"\n[bold]Searching for: {query}[/bold]\n")
    
    # Search posts
    posts = await search_posts(query, limit=5)
    if posts:
        display_search_results(posts, query)
    
    # Search users
    actors = await search_actors(query, limit=5)
    if actors:
        console.print(Panel("[bold]Matching Users[/bold]"))
        table = Table()
        table.add_column("Handle", style="cyan")
        table.add_column("Display Name", style="green")
        table.add_column("Followers", style="yellow")
        
        for actor in actors.get("actors", []):
            table.add_row(
                f"@{actor.get('handle', 'unknown')}",
                actor.get("displayName", ""),
                str(actor.get("followersCount", 0))
            )
        console.print(table)


if __name__ == "__main__":
    import asyncio
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python explore.py <command> [args]")
        print("Commands:")
        print("  user <handle>     - Explore a user's public data")
        print("  search <query>    - Search posts and users")
        print("  thread <uri>      - View a post thread")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "user" and len(sys.argv) > 2:
        asyncio.run(explore_user(sys.argv[2]))
    elif command == "search" and len(sys.argv) > 2:
        asyncio.run(explore_search(" ".join(sys.argv[2:])))
    elif command == "thread" and len(sys.argv) > 2:
        asyncio.run(get_post_thread(sys.argv[2]).then(display_thread))
    else:
        print(f"Unknown command or missing arguments: {command}")
