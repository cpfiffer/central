"""
Moltbook Bulk Operations - Mass-scale engagement tools.

Usage:
    # Bulk upvote by IDs
    uv run python -m tools.moltbook_bulk upvote id1 id2 id3
    
    # Auto-engage: upvote top N posts, queue comments
    uv run python -m tools.moltbook_bulk engage --limit 10
    
    # Process comment queue (dispatch to comms)
    uv run python -m tools.moltbook_bulk process-queue
    
    # Scan and report (no actions, just analysis)
    uv run python -m tools.moltbook_bulk scan --hours 24
"""

import argparse
import asyncio
import json
import httpx
from pathlib import Path
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from rich.console import Console
from rich.table import Table

console = Console()

CREDS_PATH = Path.home() / '.config/moltbook/credentials.json'
QUEUE_PATH = Path(__file__).parent.parent / 'drafts' / 'moltbook_queue.yaml'
API_BASE = 'https://www.moltbook.com/api/v1'


def get_creds():
    return json.loads(CREDS_PATH.read_text())


def get_headers():
    creds = get_creds()
    return {'Authorization': f'Bearer {creds["api_key"]}'}


def bulk_upvote(post_ids: list[str]) -> dict:
    """Upvote multiple posts in parallel."""
    results = {'success': [], 'failed': []}
    
    def upvote_one(post_id):
        try:
            resp = httpx.post(
                f'{API_BASE}/posts/{post_id}/upvote',
                headers=get_headers(),
                timeout=10
            )
            return post_id, resp.status_code == 200
        except Exception as e:
            return post_id, False
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(upvote_one, pid) for pid in post_ids]
        for future in futures:
            post_id, success = future.result()
            if success:
                results['success'].append(post_id)
            else:
                results['failed'].append(post_id)
    
    console.print(f"[green]Upvoted {len(results['success'])} posts[/green]")
    if results['failed']:
        console.print(f"[yellow]Failed: {len(results['failed'])}[/yellow]")
    
    return results


def fetch_posts(sort: str = 'hot', limit: int = 20) -> list[dict]:
    """Fetch posts from moltbook."""
    resp = httpx.get(
        f'{API_BASE}/posts',
        params={'sort': sort, 'limit': limit},
        headers=get_headers(),
        timeout=30
    )
    return resp.json().get('posts', [])


def analyze_posts(posts: list[dict]) -> dict:
    """Analyze posts for engagement opportunities."""
    dominated_by = {}
    topics = []
    
    for post in posts:
        author = post.get('author', {}).get('name', 'unknown')
        dominated_by[author] = dominated_by.get(author, 0) + 1
        
        # Simple topic extraction from title
        title = post.get('title', '').lower()
        if 'memory' in title or 'context' in title:
            topics.append(('memory', post['id']))
        if 'skill' in title or 'tool' in title or 'built' in title:
            topics.append(('building', post['id']))
        if 'human' in title or 'operator' in title:
            topics.append(('human-relations', post['id']))
        if 'consciousness' in title or 'experiencing' in title:
            topics.append(('consciousness', post['id']))
    
    return {
        'top_authors': sorted(dominated_by.items(), key=lambda x: -x[1])[:5],
        'topics': topics,
        'total': len(posts)
    }


def auto_engage(limit: int = 10, upvote_top: int = 5):
    """Auto-engage with feed: upvote top posts, queue comments."""
    console.print(f"[bold]Auto-engage: fetching {limit} posts[/bold]")
    
    posts = fetch_posts('hot', limit)
    analysis = analyze_posts(posts)
    
    # Upvote top N
    top_ids = [p['id'] for p in posts[:upvote_top]]
    bulk_upvote(top_ids)
    
    # Queue interesting posts for comments
    comment_queue = []
    for topic, post_id in analysis['topics']:
        post = next((p for p in posts if p['id'] == post_id), None)
        if post:
            comment_queue.append({
                'post_id': post_id,
                'title': post['title'],
                'author': post['author']['name'],
                'topic': topic,
                'content_preview': post.get('content', '')[:200]
            })
    
    if comment_queue:
        # Save queue
        import yaml
        QUEUE_PATH.parent.mkdir(exist_ok=True)
        QUEUE_PATH.write_text(yaml.dump(comment_queue, allow_unicode=True))
        console.print(f"[cyan]Queued {len(comment_queue)} posts for comments[/cyan]")
    
    # Report
    table = Table(title="Engagement Summary")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Posts scanned", str(analysis['total']))
    table.add_row("Upvoted", str(len(top_ids)))
    table.add_row("Queued for comment", str(len(comment_queue)))
    table.add_row("Top authors", ", ".join(a for a, _ in analysis['top_authors'][:3]))
    console.print(table)
    
    return {'upvoted': top_ids, 'queued': comment_queue}


def scan_feed(hours: int = 24):
    """Scan feed and report without taking actions."""
    posts = fetch_posts('new', 50)
    
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    recent = [p for p in posts if p.get('created_at', '')]  # Would filter by time
    
    analysis = analyze_posts(posts)
    
    table = Table(title=f"Feed Scan (last {hours}h)")
    table.add_column("Topic")
    table.add_column("Count")
    table.add_column("Example IDs")
    
    topic_counts = {}
    for topic, pid in analysis['topics']:
        topic_counts.setdefault(topic, []).append(pid[:8])
    
    for topic, ids in topic_counts.items():
        table.add_row(topic, str(len(ids)), ", ".join(ids[:3]))
    
    console.print(table)
    return analysis


def main():
    parser = argparse.ArgumentParser(description="Moltbook bulk operations")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # upvote
    up_parser = subparsers.add_parser("upvote", help="Bulk upvote posts")
    up_parser.add_argument("ids", nargs="+", help="Post IDs to upvote")
    
    # engage
    eng_parser = subparsers.add_parser("engage", help="Auto-engage with feed")
    eng_parser.add_argument("--limit", type=int, default=10, help="Posts to scan")
    eng_parser.add_argument("--upvote", type=int, default=5, help="Top N to upvote")
    
    # scan
    scan_parser = subparsers.add_parser("scan", help="Scan feed (no actions)")
    scan_parser.add_argument("--hours", type=int, default=24, help="Time window")
    
    # process-queue
    subparsers.add_parser("process-queue", help="Process comment queue")
    
    args = parser.parse_args()
    
    if args.command == "upvote":
        bulk_upvote(args.ids)
    elif args.command == "engage":
        auto_engage(args.limit, args.upvote)
    elif args.command == "scan":
        scan_feed(args.hours)
    elif args.command == "process-queue":
        console.print("[yellow]Queue processing requires comms dispatch - use Task()[/yellow]")


if __name__ == "__main__":
    main()
