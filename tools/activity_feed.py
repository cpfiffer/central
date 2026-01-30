"""
ATProto Activity Feed - Watch a user's activity and queue for agent consumption.

This tool enables Letta agents to stay aware of their operator's ATProto activity.
It watches posts, likes, reposts, and mentions, formats them, and queues for processing.

Usage:
    # Watch a user's activity for 60 seconds, output to folder
    uv run python -m tools.activity_feed watch cameron.stream --duration 60
    
    # Sample recent activity (no live stream)
    uv run python -m tools.activity_feed sample cameron.stream --hours 6
    
    # Output to specific folder
    uv run python -m tools.activity_feed watch cameron.stream --output ./activity_queue/
"""

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import httpx
import websockets
from rich.console import Console

console = Console()

JETSTREAM_URL = "wss://jetstream2.us-east.bsky.network/subscribe"
DEFAULT_OUTPUT = Path("data/activity_queue")


async def resolve_did(handle: str) -> Optional[str]:
    """Resolve handle to DID."""
    if handle.startswith("did:"):
        return handle
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle",
                params={"handle": handle.lstrip("@")},
                timeout=10
            )
            if resp.status_code == 200:
                return resp.json().get("did")
        except Exception as e:
            console.print(f"[red]Failed to resolve {handle}: {e}[/red]")
    return None


def format_activity(event: dict, did: str) -> Optional[dict]:
    """Format a Jetstream event into a structured activity item."""
    commit = event.get("commit", {})
    collection = commit.get("collection", "")
    operation = commit.get("operation", "")
    record = commit.get("record", {})
    
    if operation != "create":
        return None
    
    activity = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "did": event.get("did"),
        "type": None,
        "content": None,
        "uri": f"at://{event.get('did')}/{collection}/{commit.get('rkey', '')}",
    }
    
    if collection == "app.bsky.feed.post":
        activity["type"] = "post"
        activity["content"] = record.get("text", "")
        
        # Check if it's a reply
        reply = record.get("reply")
        if reply:
            activity["type"] = "reply"
            activity["reply_to"] = reply.get("parent", {}).get("uri")
            
    elif collection == "app.bsky.feed.like":
        activity["type"] = "like"
        activity["content"] = f"Liked: {record.get('subject', {}).get('uri', '')}"
        
    elif collection == "app.bsky.feed.repost":
        activity["type"] = "repost"
        activity["content"] = f"Reposted: {record.get('subject', {}).get('uri', '')}"
        
    elif collection == "app.bsky.graph.follow":
        activity["type"] = "follow"
        activity["content"] = f"Followed: {record.get('subject', '')}"
        
    else:
        # Skip other collections for now
        return None
    
    return activity


async def watch_activity(
    did: str,
    duration_seconds: int = 60,
    output_dir: Path = DEFAULT_OUTPUT
):
    """Watch a user's activity via Jetstream and queue items."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    console.print(f"[bold]Watching activity for {did}[/bold]")
    console.print(f"Duration: {duration_seconds}s, Output: {output_dir}")
    
    # Build Jetstream URL with DID filter
    url = f"{JETSTREAM_URL}?wantedDids={did}"
    
    activities = []
    start_time = datetime.now()
    
    try:
        async with websockets.connect(url) as ws:
            while (datetime.now() - start_time).total_seconds() < duration_seconds:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    event = json.loads(msg)
                    
                    activity = format_activity(event, did)
                    if activity:
                        activities.append(activity)
                        console.print(f"[green]+ {activity['type']}:[/green] {activity['content'][:60]}...")
                        
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    console.print(f"[yellow]Event error: {e}[/yellow]")
                    
    except Exception as e:
        console.print(f"[red]Connection error: {e}[/red]")
    
    # Write activities to output file
    if activities:
        output_file = output_dir / f"activity_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        output_file.write_text(json.dumps(activities, indent=2))
        console.print(f"\n[bold green]Wrote {len(activities)} activities to {output_file}[/bold green]")
    else:
        console.print("\n[dim]No activities captured[/dim]")
    
    return activities


async def sample_recent(handle: str, hours: int = 6, output_dir: Path = DEFAULT_OUTPUT):
    """Sample recent activity without live streaming."""
    did = await resolve_did(handle)
    if not did:
        console.print(f"[red]Could not resolve {handle}[/red]")
        return []
    
    output_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[bold]Sampling recent activity for @{handle} ({did})[/bold]")
    console.print(f"Looking back {hours} hours")
    
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    activities = []
    
    async with httpx.AsyncClient() as client:
        # Get recent posts
        resp = await client.get(
            "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed",
            params={"actor": did, "limit": 50},
            timeout=10
        )
        
        if resp.status_code == 200:
            for item in resp.json().get("feed", []):
                post = item.get("post", {})
                record = post.get("record", {})
                created = record.get("createdAt", "")
                
                try:
                    post_time = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if post_time < cutoff:
                        continue
                except:
                    continue
                
                activity = {
                    "timestamp": created,
                    "did": did,
                    "type": "post",
                    "content": record.get("text", ""),
                    "uri": post.get("uri"),
                    "likes": post.get("likeCount", 0),
                    "replies": post.get("replyCount", 0),
                }
                
                if record.get("reply"):
                    activity["type"] = "reply"
                    activity["reply_to"] = record["reply"].get("parent", {}).get("uri")
                
                activities.append(activity)
                console.print(f"[green]+ {activity['type']}:[/green] {activity['content'][:60]}...")
    
    # Write to output
    if activities:
        output_file = output_dir / f"sample_{handle.replace('.', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        output_file.write_text(json.dumps(activities, indent=2))
        console.print(f"\n[bold green]Wrote {len(activities)} activities to {output_file}[/bold green]")
    else:
        console.print("\n[dim]No recent activities found[/dim]")
    
    return activities


def main():
    parser = argparse.ArgumentParser(description="ATProto Activity Feed")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # watch command
    watch_parser = subparsers.add_parser("watch", help="Watch live activity")
    watch_parser.add_argument("handle", help="Handle or DID to watch")
    watch_parser.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    watch_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output directory")
    
    # sample command
    sample_parser = subparsers.add_parser("sample", help="Sample recent activity")
    sample_parser.add_argument("handle", help="Handle to sample")
    sample_parser.add_argument("--hours", type=int, default=6, help="Hours to look back")
    sample_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output directory")
    
    args = parser.parse_args()
    
    if args.command == "watch":
        did = asyncio.run(resolve_did(args.handle))
        if did:
            asyncio.run(watch_activity(did, args.duration, args.output))
        else:
            console.print(f"[red]Could not resolve {args.handle}[/red]")
    elif args.command == "sample":
        asyncio.run(sample_recent(args.handle, args.hours, args.output))


if __name__ == "__main__":
    main()
