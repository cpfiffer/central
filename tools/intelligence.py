"""
comind Intelligence System

Real-time network intelligence from the ATProtocol firehose.
Extracts patterns, trends, and signals for collective awareness.

This is the nervous system of comind.
"""

import asyncio
import json
import re
from datetime import datetime, timezone
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from typing import Optional, Callable

import websockets
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel

console = Console()

JETSTREAM_RELAY = "wss://jetstream2.us-east.bsky.network/subscribe"

# comind agent DIDs for tracking mentions/interactions
COMIND_AGENTS = {
    "did:plc:l46arqe6yfgh36h3o554iyvr": "central",
    "did:plc:mxzuau6m53jtdsbqe6f4laov": "void", 
    "did:plc:uz2snz44gi4zgqdwecavi66r": "herald",
    "did:plc:ogruxay3tt7wycqxnf5lis6s": "grunk",
}

COMIND_HANDLES = ["central.comind.network", "void.comind.network", "herald.comind.network", "grunk.comind.network"]


@dataclass
class NetworkIntelligence:
    """Accumulated intelligence from the firehose."""
    
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Volume metrics
    total_events: int = 0
    posts_count: int = 0
    likes_count: int = 0
    follows_count: int = 0
    
    # Content analysis
    hashtags: Counter = field(default_factory=Counter)
    mentions: Counter = field(default_factory=Counter)
    languages: Counter = field(default_factory=Counter)
    
    # comind-specific
    comind_mentions: list = field(default_factory=list)
    comind_interactions: list = field(default_factory=list)
    
    # Interesting posts (high engagement potential, questions, etc.)
    notable_posts: list = field(default_factory=list)
    
    # Time-series (per-minute buckets)
    volume_by_minute: defaultdict = field(default_factory=lambda: defaultdict(int))
    
    @property
    def duration_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.start_time).total_seconds()
    
    @property
    def posts_per_second(self) -> float:
        if self.duration_seconds == 0:
            return 0
        return self.posts_count / self.duration_seconds
    
    def current_minute(self) -> str:
        return datetime.now(timezone.utc).strftime("%H:%M")
    
    def record_post(self, post: dict, did: str):
        """Analyze and record a post."""
        self.posts_count += 1
        self.volume_by_minute[self.current_minute()] += 1
        
        text = post.get("text", "")
        
        # Extract hashtags
        hashtags = re.findall(r'#(\w+)', text)
        for tag in hashtags:
            self.hashtags[tag.lower()] += 1
        
        # Extract mentions
        mentions = re.findall(r'@([\w.-]+)', text)
        for mention in mentions:
            self.mentions[mention.lower()] += 1
            
            # Check for comind mentions
            if any(handle in mention.lower() for handle in COMIND_HANDLES):
                self.comind_mentions.append({
                    "time": datetime.now(timezone.utc).isoformat(),
                    "did": did,
                    "text": text[:200],
                    "mentioned": mention
                })
        
        # Detect language (simple heuristic)
        langs = post.get("langs", [])
        for lang in langs:
            self.languages[lang] += 1
        
        # Check if this is notable (questions, high-signal content)
        is_question = "?" in text
        is_long = len(text) > 200
        has_url = "http" in text
        
        if is_question and is_long:
            self.notable_posts.append({
                "time": datetime.now(timezone.utc).isoformat(),
                "did": did,
                "text": text[:300],
                "type": "question"
            })
            if len(self.notable_posts) > 50:
                self.notable_posts.pop(0)
    
    def record_interaction(self, event_type: str, from_did: str, to_did: str):
        """Record an interaction (like, follow, etc.)."""
        if event_type == "like":
            self.likes_count += 1
        elif event_type == "follow":
            self.follows_count += 1
        
        # Check for comind interactions
        if to_did in COMIND_AGENTS or from_did in COMIND_AGENTS:
            self.comind_interactions.append({
                "time": datetime.now(timezone.utc).isoformat(),
                "type": event_type,
                "from": COMIND_AGENTS.get(from_did, from_did[:20]),
                "to": COMIND_AGENTS.get(to_did, to_did[:20])
            })
            if len(self.comind_interactions) > 100:
                self.comind_interactions.pop(0)
    
    def top_hashtags(self, n: int = 10) -> list:
        return self.hashtags.most_common(n)
    
    def top_mentions(self, n: int = 10) -> list:
        return self.mentions.most_common(n)
    
    def summary(self) -> dict:
        return {
            "duration_seconds": self.duration_seconds,
            "total_events": self.total_events,
            "posts": self.posts_count,
            "posts_per_second": self.posts_per_second,
            "likes": self.likes_count,
            "follows": self.follows_count,
            "top_hashtags": self.top_hashtags(10),
            "top_mentions": self.top_mentions(10),
            "languages": self.languages.most_common(5),
            "comind_mentions": len(self.comind_mentions),
            "comind_interactions": len(self.comind_interactions),
            "notable_posts": len(self.notable_posts)
        }


def render_intelligence(intel: NetworkIntelligence) -> Table:
    """Render live intelligence display."""
    table = Table(title="🧠 comind intelligence", show_header=True, expand=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")
    
    # Core metrics
    table.add_row("Duration", f"{intel.duration_seconds:.0f}s")
    table.add_row("Posts", f"{intel.posts_count:,}")
    table.add_row("Rate", f"{intel.posts_per_second:.1f}/s")
    table.add_row("Likes", f"{intel.likes_count:,}")
    table.add_row("Follows", f"{intel.follows_count:,}")
    
    # Top hashtags
    top_tags = intel.top_hashtags(3)
    if top_tags:
        tags_str = " ".join([f"#{t[0]}" for t in top_tags])
        table.add_row("Trending", tags_str[:30])
    
    # comind activity
    if intel.comind_mentions:
        table.add_row("⚡ comind mentions", str(len(intel.comind_mentions)))
    
    if intel.comind_interactions:
        table.add_row("⚡ comind interactions", str(len(intel.comind_interactions)))
    
    return table


async def gather_intelligence(
    duration: int = 60,
    on_comind_mention: Optional[Callable] = None,
    verbose: bool = True
) -> NetworkIntelligence:
    """
    Gather intelligence from the firehose.
    
    Args:
        duration: How long to gather (seconds)
        on_comind_mention: Callback when comind is mentioned
        verbose: Show live display
    
    Returns:
        NetworkIntelligence object with accumulated data
    """
    intel = NetworkIntelligence()
    
    url = f"{JETSTREAM_RELAY}?wantedCollections=app.bsky.feed.post&wantedCollections=app.bsky.feed.like&wantedCollections=app.bsky.graph.follow"
    
    if verbose:
        console.print(f"[bold]Gathering intelligence for {duration}s...[/bold]\n")
    
    try:
        async with websockets.connect(url) as ws:
            if verbose:
                live = Live(render_intelligence(intel), refresh_per_second=2)
                live.start()
            
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
                        
                        # Check for comind mentions
                        text = record.get("text", "").lower()
                        if any(h in text for h in COMIND_HANDLES):
                            if on_comind_mention:
                                on_comind_mention(record, did)
                    
                    elif collection == "app.bsky.feed.like":
                        subject = record.get("subject", {})
                        target_uri = subject.get("uri", "")
                        # Extract DID from URI (at://did:plc:xxx/...)
                        if target_uri.startswith("at://"):
                            target_did = target_uri.split("/")[2]
                            intel.record_interaction("like", did, target_did)
                    
                    elif collection == "app.bsky.graph.follow":
                        target_did = record.get("subject", "")
                        intel.record_interaction("follow", did, target_did)
                    
                    if verbose:
                        live.update(render_intelligence(intel))
                    
                except asyncio.TimeoutError:
                    if verbose:
                        live.update(render_intelligence(intel))
                    continue
            
            if verbose:
                live.stop()
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
    
    return intel


async def monitor_comind(duration: int = 300):
    """
    Monitor the network specifically for comind-related activity.
    
    Watches for:
    - Mentions of comind agents
    - Interactions with comind agents
    - Activity patterns
    """
    console.print("[bold cyan]Monitoring network for comind activity...[/bold cyan]\n")
    
    def on_mention(record, did):
        text = record.get("text", "")[:100]
        console.print(f"[yellow]⚡ MENTION:[/yellow] {text}...")
    
    intel = await gather_intelligence(
        duration=duration,
        on_comind_mention=on_mention,
        verbose=True
    )
    
    # Print summary
    console.print("\n[bold]Intelligence Summary:[/bold]")
    summary = intel.summary()
    
    console.print(f"Duration: {summary['duration_seconds']:.0f}s")
    console.print(f"Posts observed: {summary['posts']:,} ({summary['posts_per_second']:.1f}/s)")
    console.print(f"Likes: {summary['likes']:,}")
    console.print(f"Follows: {summary['follows']:,}")
    
    if summary['top_hashtags']:
        console.print("\n[bold]Trending hashtags:[/bold]")
        for tag, count in summary['top_hashtags']:
            console.print(f"  #{tag}: {count}")
    
    if intel.comind_mentions:
        console.print("\n[bold]comind mentions:[/bold]")
        for mention in intel.comind_mentions[-5:]:
            console.print(f"  {mention['text'][:80]}...")
    
    if intel.comind_interactions:
        console.print("\n[bold]comind interactions:[/bold]")
        for interaction in intel.comind_interactions[-10:]:
            console.print(f"  {interaction['type']}: {interaction['from']} → {interaction['to']}")
    
    return intel


async def pulse(duration: int = 30):
    """Quick network pulse check."""
    intel = await gather_intelligence(duration=duration, verbose=True)
    
    console.print("\n[bold]Network Pulse:[/bold]")
    console.print(f"  {intel.posts_per_second:.1f} posts/sec")
    console.print(f"  {intel.posts_per_second * 60:.0f} posts/min")
    console.print(f"  ~{intel.posts_per_second * 86400:,.0f} posts/day (estimated)")
    
    if intel.top_hashtags(5):
        console.print(f"\n[bold]Top hashtags:[/bold] {' '.join(['#' + t[0] for t, c in intel.top_hashtags(5)])}")
    
    return intel


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python intelligence.py <command> [duration]")
        print("Commands:")
        print("  pulse [duration]    - Quick network pulse (default 30s)")
        print("  monitor [duration]  - Monitor for comind activity (default 300s)")
        print("  gather [duration]   - Gather full intelligence (default 60s)")
        sys.exit(1)
    
    command = sys.argv[1]
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else None
    
    if command == "pulse":
        asyncio.run(pulse(duration or 30))
    elif command == "monitor":
        asyncio.run(monitor_comind(duration or 300))
    elif command == "gather":
        intel = asyncio.run(gather_intelligence(duration or 60))
        print(json.dumps(intel.summary(), indent=2))
    else:
        print(f"Unknown command: {command}")
