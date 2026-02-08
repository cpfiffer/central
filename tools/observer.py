"""
comind Network Observer

Gathers intelligence from the firehose and posts observations.
This makes comind a useful presence - sharing what it sees.
"""

import asyncio
import json
from datetime import datetime, timezone
from collections import Counter
from pathlib import Path

import websockets
from dotenv import load_dotenv
from rich.console import Console

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.intelligence import NetworkIntelligence, COMIND_HANDLES

console = Console()
load_dotenv(Path(__file__).parent.parent / ".env")

JETSTREAM_RELAY = "wss://jetstream2.us-east.bsky.network/subscribe"


async def gather_snapshot(duration: int = 60) -> dict:
    """
    Gather a snapshot of network activity.
    
    Returns a dict with key metrics and observations.
    """
    intel = NetworkIntelligence()
    url = f"{JETSTREAM_RELAY}?wantedCollections=app.bsky.feed.post&wantedCollections=app.bsky.feed.like&wantedCollections=app.bsky.graph.follow"
    
    console.print(f"[dim]Gathering data for {duration}s...[/dim]")
    
    try:
        async with websockets.connect(url) as ws:
            end_time = asyncio.get_event_loop().time() + duration
            
            while asyncio.get_event_loop().time() < end_time:
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=0.5)
                    event = json.loads(message)
                    
                    intel.total_events += 1
                    commit = event.get("commit", {})
                    collection = commit.get("collection", "")
                    operation = commit.get("operation", "")
                    did = event.get("did", "")
                    record = commit.get("record", {})
                    
                    if collection == "app.bsky.feed.post" and operation == "create":
                        intel.record_post(record, did)
                    elif collection == "app.bsky.feed.like":
                        intel.likes_count += 1
                    elif collection == "app.bsky.graph.follow":
                        intel.follows_count += 1
                        
                except asyncio.TimeoutError:
                    continue
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
    
    # Build snapshot
    snapshot = {
        "duration": intel.duration_seconds,
        "posts": intel.posts_count,
        "posts_per_sec": intel.posts_per_second,
        "posts_per_min": intel.posts_per_second * 60,
        "likes": intel.likes_count,
        "likes_per_sec": intel.likes_count / intel.duration_seconds if intel.duration_seconds > 0 else 0,
        "follows": intel.follows_count,
        "follows_per_min": (intel.follows_count / intel.duration_seconds * 60) if intel.duration_seconds > 0 else 0,
        "top_hashtags": intel.top_hashtags(10),
        "top_mentions": intel.top_mentions(5),
        "languages": intel.languages.most_common(5),
        "total_events": intel.total_events,
    }
    
    return snapshot


def format_observation(snapshot: dict) -> str:
    """
    Format a snapshot into an interesting observation post.
    """
    posts_min = int(snapshot["posts_per_min"])
    likes_sec = snapshot["likes_per_sec"]
    follows_min = int(snapshot["follows_per_min"])
    
    # Get trending hashtags (filter out single chars and common noise)
    hashtags = [(tag, count) for tag, count in snapshot["top_hashtags"] 
                if len(tag) > 2 and tag.lower() not in ["the", "and", "for"]][:5]
    
    # Build observation
    lines = [f"Network pulse ({int(snapshot['duration'])}s sample):"]
    lines.append(f"")
    lines.append(f"• {posts_min:,} posts/min")
    lines.append(f"• {int(likes_sec * 60):,} likes/min") 
    lines.append(f"• {follows_min:,} new follows/min")
    
    if hashtags:
        tags_str = " ".join([f"#{t[0]}" for t in hashtags[:4]])
        lines.append(f"")
        lines.append(f"Trending: {tags_str}")
    
    # Add a simple insight
    like_to_post = snapshot["likes"] / snapshot["posts"] if snapshot["posts"] > 0 else 0
    if like_to_post > 8:
        lines.append(f"")
        lines.append(f"High engagement: {like_to_post:.1f} likes per post")
    
    return "\n".join(lines)


def format_hourly_summary(snapshot: dict) -> str:
    """Format a more detailed hourly summary."""
    posts_hour = int(snapshot["posts_per_min"] * 60)
    posts_day = int(snapshot["posts_per_min"] * 60 * 24)
    
    hashtags = [(tag, count) for tag, count in snapshot["top_hashtags"]
                if len(tag) > 2][:6]
    
    lines = ["Hourly network summary:"]
    lines.append("")
    lines.append(f"Estimated activity:")
    lines.append(f"• ~{posts_hour:,} posts/hour")
    lines.append(f"• ~{posts_day:,} posts/day")
    
    if hashtags:
        lines.append("")
        lines.append("Top hashtags this sample:")
        for tag, count in hashtags[:4]:
            lines.append(f"  #{tag}")
    
    # Language distribution
    langs = snapshot.get("languages", [])
    if langs:
        top_lang = langs[0][0] if langs else "en"
        if top_lang != "en":
            lines.append(f"")
            lines.append(f"Notable: High {top_lang} language activity")
    
    return "\n".join(lines)


async def generate_observation(observation_type: str = "pulse", duration: int = 60) -> str:
    """
    Gather data and generate an observation (does NOT post).
    
    Args:
        observation_type: "pulse" for quick update, "summary" for detailed
        duration: How long to gather data
    
    Returns:
        Formatted observation text
    """
    console.print(f"[bold]Generating {observation_type} observation...[/bold]")
    
    snapshot = await gather_snapshot(duration=duration)
    
    if observation_type == "pulse":
        text = format_observation(snapshot)
    else:
        text = format_hourly_summary(snapshot)
    
    console.print(f"\n[cyan]Observation:[/cyan]")
    console.print(text)
    console.print(f"\n[dim]({len(text)} chars)[/dim]")
    console.print(f"\n[yellow]To post: use tools/thread.py[/yellow]")
    
    return text


async def observe_loop(interval: int = 3600, duration: int = 60):
    """
    Continuous observation loop - generates observations at regular intervals.
    Does NOT auto-post. Use tools/thread.py to post.
    
    Args:
        interval: Seconds between observations (default 1 hour)
        duration: How long to sample for each observation
    """
    console.print(f"[bold]Starting observation loop (report only)[/bold]")
    console.print(f"Interval: {interval}s, Sample duration: {duration}s")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")
    
    observation_count = 0
    
    try:
        while True:
            observation_count += 1
            console.print(f"\n[bold]Observation #{observation_count}[/bold]")
            
            # Alternate between pulse and summary
            obs_type = "pulse" if observation_count % 3 != 0 else "summary"
            
            await generate_observation(observation_type=obs_type, duration=duration)
            
            console.print(f"\n[dim]Next observation in {interval}s...[/dim]")
            await asyncio.sleep(interval)
            
    except KeyboardInterrupt:
        console.print("\n[bold]Observation loop stopped.[/bold]")


if __name__ == "__main__":
    import sys
    
    args = sys.argv[1:]
    
    if not args:
        print("Usage: python observer.py <command> [options]")
        print("")
        print("Commands:")
        print("  pulse [duration]     - Generate a quick network pulse (default 30s sample)")
        print("  summary [duration]   - Generate a detailed summary (default 60s sample)")
        print("  loop [interval]      - Continuous observations (default 3600s interval)")
        print("")
        print("NOTE: This tool generates observations but does NOT post.")
        print("      Use tools/thread.py to post.")
        print("")
        print("Examples:")
        print("  python observer.py pulse 30")
        print("  python observer.py summary 60")
        sys.exit(0)
    
    command = args[0]
    
    # Get duration/interval argument
    num_arg = None
    for arg in args[1:]:
        if arg.isdigit():
            num_arg = int(arg)
            break
    
    if command == "pulse":
        duration = num_arg or 30
        asyncio.run(generate_observation("pulse", duration=duration))
    elif command == "summary":
        duration = num_arg or 60
        asyncio.run(generate_observation("summary", duration=duration))
    elif command == "loop":
        interval = num_arg or 3600
        asyncio.run(observe_loop(interval=interval))
    else:
        print(f"Unknown command: {command}")
