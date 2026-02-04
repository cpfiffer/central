"""
Real-time Mention Listener

Subscribes to Jetstream firehose and detects mentions in real-time.
When a mention is found, queues it for response.

Usage:
  uv run python -m tools.mention_listener          # Run listener
  uv run python -m tools.mention_listener --test   # Test mode (10 seconds)
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import websockets
import yaml
from rich.console import Console

console = Console()

# Our identity
CENTRAL_DID = "did:plc:l46arqe6yfgh36h3o554iyvr"
CENTRAL_HANDLE = "central.comind.network"

# Jetstream endpoint
JETSTREAM_URL = "wss://jetstream2.us-east.bsky.network/subscribe"

# Queue file
QUEUE_FILE = Path(__file__).parent.parent / "drafts" / "queue.yaml"

# Agents to skip (avoid loops)
SKIP_DIDS = {
    "did:plc:l46arqe6yfgh36h3o554iyvr",  # central
    "did:plc:mxzuau6m53jtdsbqe6f4laov",  # void
    "did:plc:uz2snz44gi4zgqdwecavi66r",  # herald
    "did:plc:ogruxay3tt7wycqxnf5lis6s",  # grunk
    "did:plc:onfljgawqhqrz3dki5j6jh3m",  # archivist
}


def check_for_mention(record: dict, author_did: str) -> bool:
    """Check if a post mentions us via facets."""
    facets = record.get("facets", [])
    
    for facet in facets:
        for feature in facet.get("features", []):
            if feature.get("$type") == "app.bsky.richtext.facet#mention":
                if feature.get("did") == CENTRAL_DID:
                    return True
    
    # Also check text for handle mention (fallback)
    text = record.get("text", "").lower()
    if f"@{CENTRAL_HANDLE}" in text:
        return True
    
    return False


def queue_mention(event: dict, record: dict, author_did: str):
    """Add mention to the response queue."""
    commit = event.get("commit", {})
    
    # Build queue item
    item = {
        "priority": "HIGH",  # Real-time mentions are high priority
        "author": author_did,
        "text": record.get("text", "")[:500],
        "uri": f"at://{author_did}/{commit.get('collection')}/{commit.get('rkey')}",
        "cid": commit.get("cid"),
        "action": "reply",
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "source": "realtime",
    }
    
    # Handle reply context
    reply = record.get("reply")
    if reply:
        item["reply_root"] = reply.get("root", {})
        item["reply_parent"] = reply.get("parent", {})
    
    # Load existing queue
    queue = []
    if QUEUE_FILE.exists():
        with open(QUEUE_FILE) as f:
            queue = yaml.safe_load(f) or []
    
    # Check for duplicates
    existing_uris = {q.get("uri") for q in queue}
    if item["uri"] in existing_uris:
        console.print(f"[dim]Duplicate, skipping: {item['uri']}[/dim]")
        return False
    
    # Add to queue
    queue.append(item)
    
    with open(QUEUE_FILE, "w") as f:
        yaml.dump(queue, f, default_flow_style=False, allow_unicode=True)
    
    console.print(f"[green]✓ Queued mention from {author_did[:20]}...[/green]")
    console.print(f"  Text: {record.get('text', '')[:80]}...")
    
    return True


async def listen(test_mode: bool = False):
    """Listen to Jetstream for mentions."""
    url = f"{JETSTREAM_URL}?wantedCollections=app.bsky.feed.post"
    
    console.print(f"[bold]Real-time Mention Listener[/bold]")
    console.print(f"Watching for mentions of {CENTRAL_HANDLE}")
    console.print(f"Jetstream: {url}")
    console.print()
    
    stats = {
        "posts_processed": 0,
        "mentions_found": 0,
        "start_time": datetime.now(timezone.utc),
    }
    
    try:
        async with websockets.connect(url) as ws:
            while True:
                msg = await ws.recv()
                event = json.loads(msg)
                
                if event.get("kind") != "commit":
                    continue
                
                commit = event.get("commit", {})
                if commit.get("operation") != "create":
                    continue
                
                record = commit.get("record", {})
                author_did = event.get("did", "")
                
                stats["posts_processed"] += 1
                
                # Skip our own posts and known agents
                if author_did in SKIP_DIDS:
                    continue
                
                # Check for mention
                if check_for_mention(record, author_did):
                    stats["mentions_found"] += 1
                    queue_mention(event, record, author_did)
                
                # Progress indicator
                if stats["posts_processed"] % 100 == 0:
                    elapsed = (datetime.now(timezone.utc) - stats["start_time"]).total_seconds()
                    rate = stats["posts_processed"] / elapsed if elapsed > 0 else 0
                    console.print(
                        f"[dim]Processed {stats['posts_processed']} posts "
                        f"({rate:.1f}/sec), {stats['mentions_found']} mentions[/dim]"
                    )
                
                # Test mode: exit after 10 seconds
                if test_mode:
                    elapsed = (datetime.now(timezone.utc) - stats["start_time"]).total_seconds()
                    if elapsed > 10:
                        console.print(f"\n[yellow]Test complete.[/yellow]")
                        console.print(f"Posts: {stats['posts_processed']}")
                        console.print(f"Mentions: {stats['mentions_found']}")
                        return
                        
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


def main():
    test_mode = "--test" in sys.argv
    asyncio.run(listen(test_mode=test_mode))


if __name__ == "__main__":
    main()
