"""
Engagement Tool - Lightweight feed browsing and liking.

Designed to be run by scout subagent or automated.
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime, timezone

import httpx
from rich.console import Console

console = Console()

API_BASE = "https://public.api.bsky.app"
LIKED_FILE = Path(__file__).parent.parent / "data" / "liked.json"


def load_liked() -> set:
    """Load already-liked URIs."""
    if LIKED_FILE.exists():
        with open(LIKED_FILE) as f:
            return set(json.load(f))
    return set()


def save_liked(liked: set):
    """Save liked URIs."""
    LIKED_FILE.parent.mkdir(exist_ok=True)
    with open(LIKED_FILE, 'w') as f:
        json.dump(list(liked)[-500:], f)  # Keep last 500


async def get_timeline(limit: int = 20) -> list:
    """Get timeline posts."""
    from tools.agent import ComindAgent
    
    async with ComindAgent() as agent:
        resp = await agent._client.get(
            f'{agent.pds}/xrpc/app.bsky.feed.getTimeline',
            headers=agent.auth_headers,
            params={'limit': limit}
        )
        return resp.json().get('feed', [])


async def like_post(uri: str, cid: str):
    """Like a single post."""
    from tools.agent import ComindAgent
    
    async with ComindAgent() as agent:
        await agent.like(uri, cid)


async def engage_timeline(target: int = 5, min_likes: int = 0):
    """
    Browse timeline and like good posts.
    
    Args:
        target: Number of posts to like
        min_likes: Minimum likes a post needs to be considered
    """
    liked = load_liked()
    posts = await get_timeline(30)
    
    liked_count = 0
    
    for item in posts:
        if liked_count >= target:
            break
            
        post = item.get('post', {})
        uri = post.get('uri')
        cid = post.get('cid')
        author = post.get('author', {}).get('handle', '')
        text = post.get('record', {}).get('text', '')
        post_likes = post.get('likeCount', 0)
        
        # Skip if already liked
        if uri in liked:
            continue
        
        # Skip own posts
        if 'central.comind' in author:
            continue
            
        # Skip if below threshold
        if post_likes < min_likes:
            continue
        
        # Skip very short posts
        if len(text) < 20:
            continue
        
        # Like it
        try:
            await like_post(uri, cid)
            liked.add(uri)
            liked_count += 1
            console.print(f"[green]♥[/green] @{author[:20]}: {text[:40]}...")
        except Exception as e:
            console.print(f"[red]Skip[/red]: {e}")
    
    save_liked(liked)
    console.print(f"\n[bold]Liked {liked_count} posts[/bold]")
    return liked_count


async def main():
    """Default engagement run."""
    console.print("[bold]Running engagement...[/bold]\n")
    await engage_timeline(target=5)


if __name__ == "__main__":
    import sys
    
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    asyncio.run(engage_timeline(target=target))
