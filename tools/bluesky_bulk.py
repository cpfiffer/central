"""
Bluesky Bulk Operations - Mass-scale ATProto engagement.

Usage:
    # Bulk like posts by URI
    uv run python -m tools.bluesky_bulk like uri1 uri2 uri3
    
    # Auto-engage: like mentions, follows, interesting posts
    uv run python -m tools.bluesky_bulk engage
    
    # Scan timeline for patterns
    uv run python -m tools.bluesky_bulk scan --limit 50
    
    # Process notification backlog
    uv run python -m tools.bluesky_bulk notifications --like-replies
"""

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import os
from pathlib import Path

from dotenv import load_dotenv
from atproto import Client
from rich.console import Console
from rich.table import Table

load_dotenv()
console = Console()

# Track liked posts to prevent re-liking
LIKED_CACHE_PATH = Path(__file__).parent.parent / 'data' / 'liked_posts.txt'


def load_liked_cache() -> set:
    """Load set of already-liked post URIs."""
    if LIKED_CACHE_PATH.exists():
        return set(LIKED_CACHE_PATH.read_text().strip().split('\n'))
    return set()


def save_liked_cache(liked: set):
    """Save liked posts to cache file."""
    LIKED_CACHE_PATH.parent.mkdir(exist_ok=True)
    LIKED_CACHE_PATH.write_text('\n'.join(sorted(liked)))


def get_client():
    """Get authenticated ATProto client."""
    client = Client(base_url=os.environ.get('ATPROTO_PDS'))
    client.login(os.environ['ATPROTO_HANDLE'], os.environ['ATPROTO_APP_PASSWORD'])
    return client


def bulk_like(uris: list[str]) -> dict:
    """Like multiple posts in parallel."""
    client = get_client()
    liked_cache = load_liked_cache()
    results = {'success': [], 'failed': [], 'skipped': []}
    
    for uri in uris:
        if uri in liked_cache:
            results['skipped'].append(uri)
            continue
        try:
            # Get post CID
            parts = uri.replace('at://', '').split('/')
            did = parts[0]
            rkey = parts[-1]
            
            # Get the post to get CID
            resp = client.get_post(rkey, did)
            cid = resp.cid
            
            # Like it
            client.like(uri, cid)
            results['success'].append(uri)
            liked_cache.add(uri)
        except Exception as e:
            err = str(e).lower()
            if 'already' in err:
                results['skipped'].append(uri)
                liked_cache.add(uri)
            else:
                results['failed'].append((uri, str(e)))
    
    save_liked_cache(liked_cache)
    
    console.print(f"[green]Liked {len(results['success'])} posts[/green]")
    if results['skipped']:
        console.print(f"[dim]Skipped {len(results['skipped'])} (already liked)[/dim]")
    if results['failed']:
        console.print(f"[yellow]Failed: {len(results['failed'])}[/yellow]")
    
    return results


def process_notifications(like_replies: bool = True, limit: int = 50) -> dict:
    """Process notification backlog efficiently."""
    client = get_client()
    
    # Load cache of already-liked posts
    liked_cache = load_liked_cache()
    
    notifs = client.app.bsky.notification.list_notifications({'limit': limit})
    
    stats = {
        'likes': 0,
        'replies': 0,
        'follows': 0,
        'mentions': 0,
        'liked_back': 0,
        'skipped': 0  # Already liked
    }
    
    to_like = []
    
    for notif in notifs.notifications:
        reason = notif.reason
        
        if reason == 'like':
            stats['likes'] += 1
        elif reason == 'reply':
            stats['replies'] += 1
            if like_replies and notif.uri:
                to_like.append((notif.uri, notif.cid))
        elif reason == 'follow':
            stats['follows'] += 1
        elif reason == 'mention':
            stats['mentions'] += 1
            if notif.uri:
                to_like.append((notif.uri, notif.cid))
    
    # Bulk like replies/mentions (skip already-liked)
    if to_like:
        for uri, cid in to_like:
            if uri in liked_cache:
                stats['skipped'] += 1
                continue
            try:
                client.like(uri, cid)
                stats['liked_back'] += 1
                liked_cache.add(uri)
            except Exception as e:
                # "already liked" errors are fine, still add to cache
                if 'already' in str(e).lower():
                    liked_cache.add(uri)
                    stats['skipped'] += 1
    
    # Save updated cache
    save_liked_cache(liked_cache)
    
    # Mark as read
    try:
        client.app.bsky.notification.update_seen({
            'seenAt': datetime.utcnow().isoformat() + 'Z'
        })
    except:
        pass
    
    table = Table(title="Notification Processing")
    table.add_column("Type")
    table.add_column("Count")
    for k, v in stats.items():
        table.add_row(k, str(v))
    console.print(table)
    
    return stats


def scan_timeline(limit: int = 50) -> dict:
    """Scan timeline for engagement patterns."""
    client = get_client()
    
    timeline = client.get_timeline(limit=limit)
    
    authors = {}
    topics = []
    agent_posts = []
    
    for item in timeline.feed:
        post = item.post
        author = post.author.handle
        authors[author] = authors.get(author, 0) + 1
        
        text = post.record.text.lower() if hasattr(post.record, 'text') else ''
        
        # Detect agent-related posts
        if any(kw in text for kw in ['agent', 'ai', 'llm', 'cognition', 'memory']):
            agent_posts.append({
                'uri': post.uri,
                'author': author,
                'text': text[:100]
            })
    
    table = Table(title=f"Timeline Scan ({limit} posts)")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Total posts", str(len(timeline.feed)))
    table.add_row("Unique authors", str(len(authors)))
    table.add_row("Agent-related", str(len(agent_posts)))
    table.add_row("Top author", max(authors.items(), key=lambda x: x[1])[0] if authors else "N/A")
    console.print(table)
    
    if agent_posts:
        console.print("\n[cyan]Agent-related posts:[/cyan]")
        for p in agent_posts[:5]:
            console.print(f"  @{p['author']}: {p['text'][:60]}...")
    
    return {'authors': authors, 'agent_posts': agent_posts}


def auto_engage():
    """Full auto-engagement routine."""
    console.print("[bold]Running full engagement routine[/bold]\n")
    
    # Process notifications
    console.print("[cyan]1. Processing notifications...[/cyan]")
    notif_stats = process_notifications(like_replies=True)
    
    # Scan timeline
    console.print("\n[cyan]2. Scanning timeline...[/cyan]")
    scan_stats = scan_timeline(50)
    
    # Like agent-related posts
    if scan_stats['agent_posts']:
        console.print("\n[cyan]3. Liking agent-related posts...[/cyan]")
        uris = [p['uri'] for p in scan_stats['agent_posts'][:10]]
        bulk_like(uris)
    
    console.print("\n[green]Engagement complete[/green]")


def main():
    parser = argparse.ArgumentParser(description="Bluesky bulk operations")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # like
    like_parser = subparsers.add_parser("like", help="Bulk like posts")
    like_parser.add_argument("uris", nargs="+", help="Post URIs to like")
    
    # engage
    subparsers.add_parser("engage", help="Full auto-engagement")
    
    # notifications
    notif_parser = subparsers.add_parser("notifications", help="Process notifications")
    notif_parser.add_argument("--like-replies", action="store_true", help="Like replies to us")
    notif_parser.add_argument("--limit", type=int, default=50, help="Notifications to process")
    
    # scan
    scan_parser = subparsers.add_parser("scan", help="Scan timeline")
    scan_parser.add_argument("--limit", type=int, default=50, help="Posts to scan")
    
    args = parser.parse_args()
    
    if args.command == "like":
        bulk_like(args.uris)
    elif args.command == "engage":
        auto_engage()
    elif args.command == "notifications":
        process_notifications(args.like_replies, args.limit)
    elif args.command == "scan":
        scan_timeline(args.limit)


if __name__ == "__main__":
    main()
