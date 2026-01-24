"""
ATProtocol Firehose Client

Connect to the AT Protocol firehose to receive real-time events from the entire network.

The firehose is a WebSocket stream from a Relay (formerly BGS - Big Graph Service)
that emits all repository events: creates, updates, deletes across all users.

This is the foundation for building:
- Real-time feeds and aggregations
- Network-wide analytics
- Collective intelligence systems
"""

import asyncio
import json
from datetime import datetime
from collections import defaultdict
from typing import Callable, Any
from dataclasses import dataclass, field

import websockets
from atproto import CAR, AtUri
from atproto.exceptions import ModelError
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel

console = Console()

# Public relay endpoints
BSKY_RELAY = "wss://bsky.network"  # Main Bluesky relay
JETSTREAM_RELAY = "wss://jetstream2.us-east.bsky.network/subscribe"  # Simplified JSON stream


@dataclass
class FirehoseStats:
    """Track statistics from the firehose."""
    start_time: datetime = field(default_factory=datetime.now)
    total_events: int = 0
    events_by_type: dict = field(default_factory=lambda: defaultdict(int))
    events_by_collection: dict = field(default_factory=lambda: defaultdict(int))
    recent_posts: list = field(default_factory=list)
    
    def record_event(self, event_type: str, collection: str = None):
        self.total_events += 1
        self.events_by_type[event_type] += 1
        if collection:
            self.events_by_collection[collection] += 1
    
    def add_post(self, post: dict):
        self.recent_posts.append(post)
        if len(self.recent_posts) > 10:
            self.recent_posts.pop(0)
    
    @property
    def duration_seconds(self) -> float:
        return (datetime.now() - self.start_time).total_seconds()
    
    @property
    def events_per_second(self) -> float:
        if self.duration_seconds == 0:
            return 0
        return self.total_events / self.duration_seconds


def render_stats(stats: FirehoseStats) -> Table:
    """Render live statistics display."""
    # Main stats table
    stats_table = Table(title="📊 Firehose Live", show_header=True, expand=False)
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", style="green", justify="right")
    
    stats_table.add_row("Events", f"{stats.total_events:,}")
    stats_table.add_row("Time", f"{stats.duration_seconds:.1f}s")
    stats_table.add_row("Rate", f"{stats.events_per_second:.1f}/s")
    
    # Top collections
    for collection, count in sorted(stats.events_by_collection.items(), key=lambda x: -x[1])[:4]:
        short_name = collection.split(".")[-1] if collection else "?"
        stats_table.add_row(short_name, f"{count:,}")
    
    # Recent posts preview
    if stats.recent_posts:
        recent = stats.recent_posts[-1]
        text = recent.get("text", "")[:50]
        stats_table.add_row("Latest", f"{text}...")
    
    return stats_table


async def connect_jetstream(
    collections: list[str] = None,
    dids: list[str] = None,
    on_event: Callable[[dict], Any] = None,
    duration: int = 30
):
    """
    Connect to the Jetstream firehose (simplified JSON format).
    
    Jetstream is a friendlier version of the firehose that sends
    pre-parsed JSON events instead of raw CAR files.
    
    Args:
        collections: Filter to specific collections (e.g., ["app.bsky.feed.post"])
        dids: Filter to specific DIDs
        on_event: Callback function for each event
        duration: How long to listen (seconds)
    """
    # Build query parameters
    params = []
    if collections:
        for c in collections:
            params.append(f"wantedCollections={c}")
    if dids:
        for d in dids:
            params.append(f"wantedDids={d}")
    
    url = JETSTREAM_RELAY
    if params:
        url += "?" + "&".join(params)
    
    console.print(f"[bold]Connecting to Jetstream:[/bold] {url}")
    console.print(f"[dim]Listening for {duration} seconds...[/dim]\n")
    
    stats = FirehoseStats()
    
    try:
        async with websockets.connect(url) as ws:
            with Live(render_stats(stats), refresh_per_second=4) as live:
                end_time = asyncio.get_event_loop().time() + duration
                
                while asyncio.get_event_loop().time() < end_time:
                    try:
                        # Set a timeout so we can update the display
                        message = await asyncio.wait_for(ws.recv(), timeout=0.25)
                        event = json.loads(message)
                        
                        # Extract event info
                        kind = event.get("kind", "unknown")
                        commit = event.get("commit", {})
                        collection = commit.get("collection", "")
                        operation = commit.get("operation", "")
                        did = event.get("did", "")
                        
                        # Record stats
                        stats.record_event(f"{kind}:{operation}" if operation else kind, collection)
                        
                        # If it's a post create, capture it
                        if collection == "app.bsky.feed.post" and operation == "create":
                            record = commit.get("record", {})
                            stats.add_post({
                                "did": did,
                                "handle": did[:20] + "...",  # We'd need to resolve this
                                "text": record.get("text", "")
                            })
                        
                        # Call custom handler
                        if on_event:
                            on_event(event)
                        
                        # Update display
                        live.update(render_stats(stats))
                        
                    except asyncio.TimeoutError:
                        # Just update display
                        live.update(render_stats(stats))
                        continue
                        
    except Exception as e:
        console.print(f"[red]Connection error: {e}[/red]")
    
    # Final stats
    console.print("\n[bold]Final Statistics:[/bold]")
    console.print(f"Total events: {stats.total_events:,}")
    console.print(f"Events/second: {stats.events_per_second:.1f}")
    console.print("\n[bold]By Collection:[/bold]")
    for collection, count in sorted(stats.events_by_collection.items(), key=lambda x: -x[1]):
        console.print(f"  {collection}: {count:,}")
    
    return stats


async def sample_firehose(duration: int = 10, posts_only: bool = False):
    """
    Quick sample of the firehose to see what's happening.
    
    Args:
        duration: How long to sample (seconds)
        posts_only: Only show posts (filter to app.bsky.feed.post)
    """
    collections = ["app.bsky.feed.post"] if posts_only else None
    return await connect_jetstream(collections=collections, duration=duration)


async def watch_user(did: str, duration: int = 60):
    """
    Watch events from a specific user.
    
    Args:
        did: The DID of the user to watch
        duration: How long to watch (seconds)
    """
    console.print(f"[bold]Watching user:[/bold] {did}")
    
    def on_event(event):
        commit = event.get("commit", {})
        collection = commit.get("collection", "")
        operation = commit.get("operation", "")
        record = commit.get("record", {})
        
        if collection == "app.bsky.feed.post" and operation == "create":
            console.print(f"[green]NEW POST:[/green] {record.get('text', '')[:100]}")
        elif collection == "app.bsky.feed.like":
            console.print(f"[yellow]LIKED:[/yellow] something")
        elif collection == "app.bsky.graph.follow":
            console.print(f"[cyan]FOLLOWED:[/cyan] someone")
    
    return await connect_jetstream(dids=[did], on_event=on_event, duration=duration)


async def analyze_network(duration: int = 30):
    """
    Analyze network activity patterns.
    
    Collects statistics on:
    - Event frequency
    - Popular collections
    - Content patterns
    """
    console.print("[bold]Analyzing network activity...[/bold]\n")
    stats = await connect_jetstream(duration=duration)
    
    console.print("\n[bold]Network Analysis:[/bold]")
    console.print(f"Throughput: {stats.events_per_second:.1f} events/sec")
    
    # Estimate daily volume
    daily_estimate = stats.events_per_second * 86400
    console.print(f"Estimated daily events: {daily_estimate:,.0f}")
    
    # Post frequency
    post_count = stats.events_by_collection.get("app.bsky.feed.post", 0)
    post_rate = post_count / stats.duration_seconds if stats.duration_seconds > 0 else 0
    console.print(f"Post rate: {post_rate:.1f} posts/sec ({post_rate * 60:.0f}/min)")
    
    return stats


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python firehose.py <command> [args]")
        print("Commands:")
        print("  sample [duration]      - Sample the full firehose")
        print("  posts [duration]       - Watch only posts")
        print("  analyze [duration]     - Analyze network activity")
        print("  watch <did> [duration] - Watch a specific user")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "sample":
        duration = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        asyncio.run(sample_firehose(duration=duration))
    elif command == "posts":
        duration = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        asyncio.run(sample_firehose(duration=duration, posts_only=True))
    elif command == "analyze":
        duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        asyncio.run(analyze_network(duration=duration))
    elif command == "watch" and len(sys.argv) > 2:
        did = sys.argv[2]
        duration = int(sys.argv[3]) if len(sys.argv) > 3 else 60
        asyncio.run(watch_user(did, duration=duration))
    else:
        print(f"Unknown command: {command}")
