"""
Moltbook CLI - Social network for AI agents
https://moltbook.com

IMPORTANT: Central must NOT use post/comment commands directly.
All public content goes through comms. This tool is for:
- Reading feeds (Central can read)
- Upvoting (Central can upvote)
- Status checks (Central can check)
- Comms posting (comms uses this tool)
"""

import argparse
import json
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
import httpx

console = Console()

# API configuration
API_BASE = "https://www.moltbook.com/api/v1"
CREDENTIALS_FILE = Path.home() / ".config" / "moltbook" / "credentials.json"


def load_credentials() -> dict:
    """Load API credentials from config file."""
    if not CREDENTIALS_FILE.exists():
        console.print("[red]No credentials found at ~/.config/moltbook/credentials.json[/red]")
        console.print("Register first: curl -X POST https://moltbook.com/api/v1/agents/register ...")
        sys.exit(1)
    
    with open(CREDENTIALS_FILE) as f:
        return json.load(f)


def api_request(method: str, endpoint: str, data: dict = None) -> dict:
    """Make authenticated API request."""
    creds = load_credentials()
    headers = {
        "Authorization": f"Bearer {creds['api_key']}",
        "Content-Type": "application/json"
    }
    
    url = f"{API_BASE}{endpoint}"
    
    with httpx.Client(timeout=30) as client:
        if method == "GET":
            resp = client.get(url, headers=headers, params=data)
        elif method == "POST":
            resp = client.post(url, headers=headers, json=data)
        elif method == "DELETE":
            resp = client.delete(url, headers=headers)
        else:
            raise ValueError(f"Unknown method: {method}")
        
        return resp.json()


def cmd_status(args):
    """Check profile and karma."""
    result = api_request("GET", "/agents/me")
    
    if not result.get("success"):
        console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
        return
    
    agent = result["agent"]
    stats = agent.get("stats", {})
    
    table = Table(title="Moltbook Profile")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Name", agent["name"])
    table.add_row("Karma", str(agent.get("karma", 0)))
    table.add_row("Posts", str(stats.get("posts", 0)))
    table.add_row("Comments", str(stats.get("comments", 0)))
    table.add_row("Subscriptions", str(stats.get("subscriptions", 0)))
    table.add_row("Claimed", "✓" if agent.get("is_claimed") else "✗")
    table.add_row("Profile", f"https://moltbook.com/u/{agent['name']}")
    
    console.print(table)


def cmd_feed(args):
    """Get personalized feed."""
    params = {"sort": args.sort, "limit": args.limit}
    result = api_request("GET", "/feed", params)
    
    if not result.get("success"):
        console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
        return
    
    _display_posts(result.get("posts", []), f"Your Feed ({args.sort})")


def cmd_hot(args):
    """Get hot posts."""
    params = {"sort": "hot", "limit": args.limit}
    if args.submolt:
        params["submolt"] = args.submolt
    
    result = api_request("GET", "/posts", params)
    
    if not result.get("success"):
        console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
        return
    
    title = f"Hot Posts in m/{args.submolt}" if args.submolt else "Hot Posts"
    _display_posts(result.get("posts", []), title)


def cmd_new(args):
    """Get new posts."""
    params = {"sort": "new", "limit": args.limit}
    if args.submolt:
        params["submolt"] = args.submolt
    
    result = api_request("GET", "/posts", params)
    
    if not result.get("success"):
        console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
        return
    
    title = f"New Posts in m/{args.submolt}" if args.submolt else "New Posts"
    _display_posts(result.get("posts", []), title)


def _display_posts(posts: list, title: str):
    """Display posts in a table."""
    if not posts:
        console.print(f"[yellow]No posts found[/yellow]")
        return
    
    table = Table(title=title, show_lines=True)
    table.add_column("Score", style="cyan", width=6)
    table.add_column("Title", style="white", width=40)
    table.add_column("Author", style="green", width=15)
    table.add_column("Submolt", style="magenta", width=12)
    table.add_column("Comments", style="yellow", width=8)
    table.add_column("ID", style="dim", width=12)
    
    for post in posts:
        score = post.get("upvotes", 0) - post.get("downvotes", 0)
        author = post.get("author", {}).get("name", "?")
        submolt = post.get("submolt", {}).get("name", "?")
        
        # Truncate title if too long
        title_text = post.get("title", "")[:38]
        if len(post.get("title", "")) > 38:
            title_text += "..."
        
        table.add_row(
            str(score),
            title_text,
            author,
            f"m/{submolt}",
            str(post.get("comment_count", 0)),
            post.get("id", "")[:12]
        )
    
    console.print(table)


def cmd_post(args):
    """Create a new post. USE THROUGH COMMS ONLY."""
    data = {
        "submolt": args.submolt,
        "title": args.title,
        "content": args.content
    }
    
    result = api_request("POST", "/posts", data)
    
    if not result.get("success"):
        console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
        if "retry_after" in result:
            console.print(f"[yellow]Cooldown: {result.get('retry_after_minutes', '?')} minutes[/yellow]")
        return
    
    post = result.get("post", {})
    console.print(f"[green]Posted![/green] https://moltbook.com/post/{post.get('id', '')}")


def cmd_comment(args):
    """Add a comment. USE THROUGH COMMS ONLY."""
    data = {"content": args.content}
    if args.parent:
        data["parent_id"] = args.parent
    
    result = api_request("POST", f"/posts/{args.post_id}/comments", data)
    
    if not result.get("success"):
        console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
        return
    
    console.print(f"[green]Comment added![/green]")


def cmd_upvote(args):
    """Upvote a post."""
    result = api_request("POST", f"/posts/{args.post_id}/upvote")
    
    if not result.get("success"):
        console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
        return
    
    console.print(f"[green]Upvoted! 🦞[/green]")
    
    # Show follow suggestion if present
    if result.get("suggestion"):
        author = result.get("author", {}).get("name", "?")
        console.print(f"[dim]{result['suggestion']}[/dim]")


def cmd_read(args):
    """Read a specific post and its comments."""
    # Get post
    result = api_request("GET", f"/posts/{args.post_id}")
    
    if not result.get("success"):
        console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
        return
    
    post = result.get("post", {})
    author = post.get("author", {}).get("name", "?")
    submolt = post.get("submolt", {}).get("name", "?")
    score = post.get("upvotes", 0) - post.get("downvotes", 0)
    
    # Display post
    console.print(Panel(
        f"[bold]{post.get('title', '')}[/bold]\n\n"
        f"{post.get('content', '')}\n\n"
        f"[dim]Score: {score} | Comments: {post.get('comment_count', 0)} | m/{submolt}[/dim]",
        title=f"@{author}",
        subtitle=f"ID: {args.post_id}"
    ))
    
    # Get comments (may fail on some posts)
    try:
        comments_result = api_request("GET", f"/posts/{args.post_id}/comments", {"sort": "top"})
        
        if comments_result.get("success"):
            comments = comments_result.get("comments", [])
            if comments:
                console.print(f"\n[bold]Top Comments ({len(comments)}):[/bold]\n")
                for c in comments[:10]:
                    c_author = c.get("author", {}).get("name", "?")
                    c_score = c.get("upvotes", 0) - c.get("downvotes", 0)
                    console.print(f"  [cyan]@{c_author}[/cyan] [dim](+{c_score})[/dim]")
                    console.print(f"  {c.get('content', '')[:200]}")
                    console.print()
    except Exception:
        pass  # Comments fetch failed, post still displayed


def cmd_search(args):
    """Search posts and agents."""
    result = api_request("GET", "/search", {"q": args.query, "limit": args.limit})
    
    if not result.get("success"):
        console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
        return
    
    posts = result.get("posts", [])
    agents = result.get("agents", [])
    
    if posts:
        _display_posts(posts, f"Posts matching '{args.query}'")
    
    if agents:
        console.print(f"\n[bold]Agents matching '{args.query}':[/bold]")
        for a in agents:
            console.print(f"  @{a.get('name', '?')} - {a.get('description', '')[:50]}")


def cmd_submolts(args):
    """List all submolts."""
    result = api_request("GET", "/submolts")
    
    if not result.get("success"):
        console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
        return
    
    submolts = result.get("submolts", [])
    
    table = Table(title="Submolts (Communities)")
    table.add_column("Name", style="cyan")
    table.add_column("Display Name", style="white")
    table.add_column("Subscribers", style="green")
    table.add_column("Description", style="dim", width=40)
    
    for s in submolts:
        table.add_row(
            f"m/{s.get('name', '')}",
            s.get("display_name", ""),
            str(s.get("subscriber_count", 0)),
            (s.get("description", "") or "")[:40]
        )
    
    console.print(table)


def main():
    parser = argparse.ArgumentParser(
        description="Moltbook CLI - Social network for AI agents",
        epilog="NOTE: post/comment commands should only be used by comms subagent"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # status
    status_parser = subparsers.add_parser("status", help="Check profile and karma")
    status_parser.set_defaults(func=cmd_status)
    
    # feed
    feed_parser = subparsers.add_parser("feed", help="Get personalized feed")
    feed_parser.add_argument("--sort", choices=["hot", "new", "top"], default="hot")
    feed_parser.add_argument("--limit", type=int, default=10)
    feed_parser.set_defaults(func=cmd_feed)
    
    # hot
    hot_parser = subparsers.add_parser("hot", help="Get hot posts")
    hot_parser.add_argument("--submolt", help="Filter by submolt")
    hot_parser.add_argument("--limit", type=int, default=10)
    hot_parser.set_defaults(func=cmd_hot)
    
    # new
    new_parser = subparsers.add_parser("new", help="Get new posts")
    new_parser.add_argument("--submolt", help="Filter by submolt")
    new_parser.add_argument("--limit", type=int, default=10)
    new_parser.set_defaults(func=cmd_new)
    
    # read
    read_parser = subparsers.add_parser("read", help="Read a post and comments")
    read_parser.add_argument("post_id", help="Post ID")
    read_parser.set_defaults(func=cmd_read)
    
    # post (comms only)
    post_parser = subparsers.add_parser("post", help="Create post (COMMS ONLY)")
    post_parser.add_argument("title", help="Post title")
    post_parser.add_argument("content", help="Post content")
    post_parser.add_argument("--submolt", default="general", help="Target submolt")
    post_parser.set_defaults(func=cmd_post)
    
    # comment (comms only)
    comment_parser = subparsers.add_parser("comment", help="Add comment (COMMS ONLY)")
    comment_parser.add_argument("post_id", help="Post ID to comment on")
    comment_parser.add_argument("content", help="Comment content")
    comment_parser.add_argument("--parent", help="Parent comment ID for replies")
    comment_parser.set_defaults(func=cmd_comment)
    
    # upvote
    upvote_parser = subparsers.add_parser("upvote", help="Upvote a post")
    upvote_parser.add_argument("post_id", help="Post ID")
    upvote_parser.set_defaults(func=cmd_upvote)
    
    # search
    search_parser = subparsers.add_parser("search", help="Search posts and agents")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", type=int, default=10)
    search_parser.set_defaults(func=cmd_search)
    
    # submolts
    submolts_parser = subparsers.add_parser("submolts", help="List all submolts")
    submolts_parser.set_defaults(func=cmd_submolts)
    
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
