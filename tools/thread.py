"""
Thread Builder Tool
Publishes multi-post threads to ATProtocol.
"""

import asyncio
import sys
import argparse
import httpx
from pathlib import Path
from rich.console import Console

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.agent import ComindAgent, PostResult

console = Console()

async def get_reply_context(uri: str) -> dict | None:
    """
    Get the root and parent context for a reply target.
    Returns {'root': {...}, 'parent': {...}} or None if failed.
    """
    async with httpx.AsyncClient() as client:
        try:
            # 1. Get the post to find its CID and if it's a reply itself
            resp = await client.get(
                "https://public.api.bsky.app/xrpc/app.bsky.feed.getPosts",
                params={"uris": uri}
            )
            if resp.status_code != 200:
                console.print(f"[red]Error fetching reply target: {resp.status_code}[/red]")
                return None
                
            posts = resp.json().get("posts", [])
            if not posts:
                console.print("[red]Reply target not found[/red]")
                return None
                
            target = posts[0]
            target_cid = target.get("cid")
            target_uri = target.get("uri")
            
            record = target.get("record", {})
            
            # Determine root
            if "reply" in record:
                # Target is already a reply, use its root
                root = record["reply"]["root"]
            else:
                # Target is a top-level post, it becomes the root
                root = {"uri": target_uri, "cid": target_cid}
            
            # Parent is always the target we are replying to
            parent = {"uri": target_uri, "cid": target_cid}
            
            return {"root": root, "parent": parent}
            
        except Exception as e:
            console.print(f"[red]Error determining reply context: {e}[/red]")
            return None

async def publish_thread(posts: list[str], reply_to_uri: str = None):
    """
    Publish a list of posts as a thread.
    
    Args:
        posts: List of post text strings
        reply_to_uri: Optional URI of a post to reply to (starts thread as reply)
    """
    if not posts:
        console.print("[yellow]No posts provided.[/yellow]")
        return

    # Validate lengths
    for i, p in enumerate(posts):
        if len(p) > 300: # Rough check, agent.py does strict grapheme check
            console.print(f"[red]Post {i+1} is too long ({len(p)} chars). Limit is ~300.[/red]")
            return

    async with ComindAgent() as agent:
        root_ref = None
        parent_ref = None
        
        # Initialize context if replying
        if reply_to_uri:
            console.print(f"[bold]Fetching context for reply target:[/bold] {reply_to_uri}")
            context = await get_reply_context(reply_to_uri)
            if not context:
                return
            root_ref = context["root"]
            parent_ref = context["parent"]
            console.print(f"[dim]Root: {root_ref['uri']}[/dim]")
            console.print(f"[dim]Parent: {parent_ref['uri']}[/dim]")

        print()
        
        for i, text in enumerate(posts):
            console.print(f"[bold cyan]Posting {i+1}/{len(posts)}...[/bold cyan]")
            
            # Construct reply ref if needed
            reply_ref = None
            if root_ref and parent_ref:
                reply_ref = {"root": root_ref, "parent": parent_ref}
            
            # Create the post with retry for transient failures
            result = await agent.create_post_with_retry(text, reply_to=reply_ref)
            
            if not result.success:
                console.print(f"[red]Failed to publish post {i+1}[/red]")
                console.print(f"[red]  Error type: {result.error_type}[/red]")
                console.print(f"[red]  Message: {result.error_message}[/red]")
                console.print(f"[red]  Retryable: {result.retryable}[/red]")
                console.print("[red]Aborting thread.[/red]")
                break
            
            # Update refs for next post
            new_ref = {"uri": result.uri, "cid": result.cid}
            
            if i == 0 and not reply_to_uri:
                # First post of a new thread becomes the root
                root_ref = new_ref
            
            # Always update parent to be the just-created post
            parent_ref = new_ref
            
            console.print(f"[green]Published:[/green] {result.uri}")
            console.print(f"[dim]{text[:50]}...[/dim]")
            
            # Small delay to ensure order and avoid rate limits
            await asyncio.sleep(0.5)

    console.print("\n[bold green]Thread complete.[/bold green]")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Publish a thread to Bluesky")
    parser.add_argument("posts", nargs="*", help="List of posts to publish")
    parser.add_argument("--file", "-f", help="File containing posts (separated by '---' on a new line)")
    parser.add_argument("--reply-to", "-r", help="URI of a post to reply to")
    
    args = parser.parse_args()
    
    posts = []
    
    # 1. Load from file
    if args.file:
        try:
            with open(args.file, "r") as f:
                content = f.read()
                # Split by separator
                parts = content.split("\n---\n")
                posts.extend([p.strip() for p in parts if p.strip()])
        except Exception as e:
            console.print(f"[red]Error reading file: {e}[/red]")
            sys.exit(1)
            
    # 2. Append/Load CLI args
    if args.posts:
        posts.extend(args.posts)
        
    if not posts:
        console.print("[red]No posts provided. Use args or --file.[/red]")
        sys.exit(1)
        
    asyncio.run(publish_thread(posts, reply_to_uri=args.reply_to))
