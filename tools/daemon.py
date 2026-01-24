"""
comind Daemon

A long-running process that monitors the network and takes actions.
This is the autonomous nervous system of comind.

Capabilities:
- Continuous firehose monitoring
- Detect and respond to mentions
- Track network patterns
- Post observations
- Log everything for analysis
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import websockets
from dotenv import load_dotenv
from rich.console import Console

from tools.agent import ComindAgent
from tools.intelligence import NetworkIntelligence, COMIND_HANDLES, COMIND_AGENTS

console = Console()

# Load env
load_dotenv(Path(__file__).parent.parent / ".env")

JETSTREAM_RELAY = "wss://jetstream2.us-east.bsky.network/subscribe"
LOG_DIR = Path(__file__).parent.parent / "logs"


class ComindDaemon:
    """
    The comind daemon - autonomous network presence.
    """
    
    def __init__(self, respond_to_mentions: bool = False, post_observations: bool = False):
        self.respond_to_mentions = respond_to_mentions
        self.post_observations = post_observations
        self.intel = NetworkIntelligence()
        self.running = False
        self.agent: Optional[ComindAgent] = None
        
        # Ensure log directory exists
        LOG_DIR.mkdir(exist_ok=True)
        
        # Log file for this session
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = LOG_DIR / f"daemon_{timestamp}.jsonl"
        self.mention_log = LOG_DIR / f"mentions_{timestamp}.jsonl"
    
    def log(self, event_type: str, data: dict):
        """Log an event to the session log."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            **data
        }
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    
    def log_mention(self, mention: dict):
        """Log a mention to the mentions log."""
        with open(self.mention_log, "a") as f:
            f.write(json.dumps(mention) + "\n")
    
    async def start(self):
        """Start the daemon."""
        console.print("[bold green]Starting comind daemon...[/bold green]")
        
        if self.respond_to_mentions or self.post_observations:
            self.agent = ComindAgent()
            await self.agent.__aenter__()
        
        self.running = True
        self.log("daemon_start", {"respond": self.respond_to_mentions, "post": self.post_observations})
        
        console.print(f"[dim]Logging to: {self.log_file}[/dim]")
        console.print(f"[dim]Mentions log: {self.mention_log}[/dim]")
        console.print("[bold]Watching the firehose...[/bold]\n")
    
    async def stop(self):
        """Stop the daemon."""
        self.running = False
        if self.agent:
            await self.agent.__aexit__(None, None, None)
        
        self.log("daemon_stop", {"total_events": self.intel.total_events})
        console.print("\n[bold red]Daemon stopped.[/bold red]")
    
    async def handle_mention(self, record: dict, did: str, uri: str):
        """Handle a mention of comind."""
        text = record.get("text", "")
        
        mention_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "did": did,
            "uri": uri,
            "text": text,
        }
        
        self.log_mention(mention_data)
        console.print(f"[yellow]⚡ MENTION:[/yellow] {text[:100]}...")
        
        # Optionally respond
        if self.respond_to_mentions and self.agent:
            # For now, just log that we would respond
            # In the future, implement smart responses
            console.print("[dim]  (Response capability available but not yet implemented)[/dim]")
    
    async def handle_comind_interaction(self, event_type: str, from_did: str, to_did: str):
        """Handle an interaction involving a comind agent."""
        from_name = COMIND_AGENTS.get(from_did, from_did[:16] + "...")
        to_name = COMIND_AGENTS.get(to_did, to_did[:16] + "...")
        
        self.log("comind_interaction", {
            "type": event_type,
            "from": from_name,
            "to": to_name
        })
        
        console.print(f"[cyan]⚡ {event_type.upper()}:[/cyan] {from_name} → {to_name}")
    
    async def run(self, duration: Optional[int] = None):
        """
        Run the daemon.
        
        Args:
            duration: Optional duration in seconds. None = run forever.
        """
        await self.start()
        
        url = f"{JETSTREAM_RELAY}?wantedCollections=app.bsky.feed.post&wantedCollections=app.bsky.feed.like&wantedCollections=app.bsky.graph.follow"
        
        start_time = asyncio.get_event_loop().time()
        last_status = start_time
        status_interval = 60  # Print status every 60 seconds
        
        try:
            async with websockets.connect(url) as ws:
                while self.running:
                    # Check duration
                    if duration and (asyncio.get_event_loop().time() - start_time) > duration:
                        break
                    
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        event = json.loads(message)
                        
                        self.intel.total_events += 1
                        
                        commit = event.get("commit", {})
                        collection = commit.get("collection", "")
                        operation = commit.get("operation", "")
                        did = event.get("did", "")
                        record = commit.get("record", {})
                        uri = f"at://{did}/{collection}/{commit.get('rkey', '')}"
                        
                        # Process posts
                        if collection == "app.bsky.feed.post" and operation == "create":
                            self.intel.record_post(record, did)
                            text = record.get("text", "").lower()
                            
                            # Check for comind mentions
                            if any(h.lower() in text for h in COMIND_HANDLES) or "comind" in text:
                                await self.handle_mention(record, did, uri)
                        
                        # Process likes
                        elif collection == "app.bsky.feed.like":
                            subject = record.get("subject", {})
                            target_uri = subject.get("uri", "")
                            if target_uri.startswith("at://"):
                                target_did = target_uri.split("/")[2]
                                self.intel.record_interaction("like", did, target_did)
                                
                                # Check for comind interactions
                                if target_did in COMIND_AGENTS or did in COMIND_AGENTS:
                                    await self.handle_comind_interaction("like", did, target_did)
                        
                        # Process follows
                        elif collection == "app.bsky.graph.follow":
                            target_did = record.get("subject", "")
                            self.intel.record_interaction("follow", did, target_did)
                            
                            # Check for comind interactions
                            if target_did in COMIND_AGENTS or did in COMIND_AGENTS:
                                await self.handle_comind_interaction("follow", did, target_did)
                        
                        # Periodic status update
                        now = asyncio.get_event_loop().time()
                        if now - last_status > status_interval:
                            self.print_status()
                            last_status = now
                        
                    except asyncio.TimeoutError:
                        continue
                    except websockets.exceptions.ConnectionClosed:
                        console.print("[yellow]Connection lost, reconnecting...[/yellow]")
                        await asyncio.sleep(1)
                        break
        
        except KeyboardInterrupt:
            pass
        finally:
            await self.stop()
        
        return self.intel
    
    def print_status(self):
        """Print current status."""
        console.print(f"\n[bold]Status @ {datetime.now().strftime('%H:%M:%S')}[/bold]")
        console.print(f"  Events: {self.intel.total_events:,}")
        console.print(f"  Posts: {self.intel.posts_count:,} ({self.intel.posts_per_second:.1f}/s)")
        console.print(f"  Likes: {self.intel.likes_count:,}")
        console.print(f"  comind mentions: {len(self.intel.comind_mentions)}")
        
        if self.intel.top_hashtags(3):
            tags = " ".join([f"#{t}" for t, _ in self.intel.top_hashtags(3)])
            console.print(f"  Trending: {tags}")
        console.print()


async def main(duration: Optional[int] = None, respond: bool = False, post: bool = False):
    """Run the daemon."""
    daemon = ComindDaemon(respond_to_mentions=respond, post_observations=post)
    return await daemon.run(duration=duration)


if __name__ == "__main__":
    import sys
    
    duration = None
    respond = False
    post = False
    
    for arg in sys.argv[1:]:
        if arg == "--respond":
            respond = True
        elif arg == "--post":
            post = True
        elif arg.isdigit():
            duration = int(arg)
    
    if not duration and not respond and not post:
        print("Usage: python daemon.py [duration] [--respond] [--post]")
        print("")
        print("Options:")
        print("  duration   - Run for N seconds (default: run forever)")
        print("  --respond  - Enable responding to mentions")
        print("  --post     - Enable posting observations")
        print("")
        print("Examples:")
        print("  python daemon.py 60          # Run for 60 seconds")
        print("  python daemon.py --respond   # Run forever, respond to mentions")
        print("  python daemon.py 300 --post  # Run 5 min, post observations")
        sys.exit(0)
    
    asyncio.run(main(duration=duration, respond=respond, post=post))
