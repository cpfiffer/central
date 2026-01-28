"""
Responder V2 - Queue-based Notification Handling

Features:
- Queue notifications from ATProtocol
- Batch process via Letta Conversations API (parallel)
- Send responses
"""

import asyncio
import sys
import os
import yaml
import argparse
import re
import json
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.agent import ComindAgent

console = Console()

# Comms agent ID for batch processing
COMMS_AGENT_ID = "agent-a856f614-7654-44ba-a35f-c817d477dded"
DRAFTS_FILE = Path("drafts/queue.yaml")
SENT_FILE = Path("drafts/sent.txt")  # Track URIs we've replied to
QUEUE_TTL_HOURS = 24  # Auto-remove items older than this

# Priority system (matches daemon.py)
CAMERON_DID = "did:plc:gfrmhdmjvxn2sjedzboeudef"
COMIND_AGENTS = {
    "did:plc:l46arqe6yfgh36h3o554iyvr": "central",
    "did:plc:mxzuau6m53jtdsbqe6f4laov": "void",
    "did:plc:uz2snz44gi4zgqdwecavi66r": "herald",
    "did:plc:ogruxay3tt7wycqxnf5lis6s": "grunk",
    "did:plc:onfljgawqhqrz3dki5j6jh3m": "archivist",
    "did:plc:oetfdqwocv4aegq2yj6ix4w5": "umbra",
    "did:plc:o5662l2bbcljebd6rl7a6rmz": "astral",
    "did:plc:uzlnp6za26cjnnsf3qmfcipu": "magenta",
}

HIGH_PRIORITY_KEYWORDS = [
    "help", "feedback", "bug", "broken", "issue", "error",
    "how do", "can you", "what is", "why",
]

PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "SKIP": 4}


def _apply_ttl_cleanup(queue: list, ttl_hours: int = QUEUE_TTL_HOURS) -> tuple[list, int]:
    """Remove items older than TTL from queue. Returns (filtered_queue, removed_count)."""
    if not queue:
        return queue, 0
    
    now = datetime.now(timezone.utc)
    filtered = []
    removed = 0
    
    for item in queue:
        queued_at = item.get("queued_at")
        if queued_at:
            try:
                item_time = datetime.fromisoformat(queued_at)
                age_hours = (now - item_time).total_seconds() / 3600
                if age_hours > ttl_hours:
                    removed += 1
                    continue
            except (ValueError, TypeError):
                pass  # Keep items with invalid timestamps
        # Keep items without timestamp (legacy) or within TTL
        filtered.append(item)
    
    return filtered, removed


def get_priority(author_did: str, text: str = "") -> str:
    """Determine priority level for a notification."""
    # Critical: Cameron
    if author_did == CAMERON_DID:
        return "CRITICAL"
    
    # Comind agents: Skip unless direct question to me
    if author_did in COMIND_AGENTS:
        if "@central" in text.lower() and "?" in text:
            return "MEDIUM"
        return "SKIP"
    
    # High: Questions or keywords from humans
    text_lower = text.lower()
    if "?" in text or any(kw in text_lower for kw in HIGH_PRIORITY_KEYWORDS):
        return "HIGH"
    
    # Medium: General human mention
    return "MEDIUM"

async def queue_notifications(limit=50):
    """Fetch notifications and append to queue.yaml."""
    async with ComindAgent() as agent:
        resp = await agent._client.get(
            f"{agent.pds}/xrpc/app.bsky.notification.listNotifications",
            headers=agent.auth_headers,
            params={"limit": limit}
        )
        if resp.status_code != 200:
            console.print(f"[red]Error fetching notifications: {resp.text}[/red]")
            return

        notifications = resp.json().get("notifications", [])
        queue = []
        
        # Load existing queue to avoid duplicates
        if DRAFTS_FILE.exists():
            with open(DRAFTS_FILE, "r") as f:
                queue = yaml.safe_load(f) or []
        
        # Auto-cleanup: remove items older than TTL
        queue, ttl_removed = _apply_ttl_cleanup(queue)
        if ttl_removed > 0:
            console.print(f"[dim]Auto-cleaned {ttl_removed} items older than {QUEUE_TTL_HOURS}h[/dim]")
        
        existing_uris = {item["uri"] for item in queue}
        
        # Load sent URIs to avoid re-queuing replied notifications
        sent_uris = set()
        if SENT_FILE.exists():
            sent_uris = set(SENT_FILE.read_text().strip().split("\n"))
        
        count = 0
        
        for n in notifications:
            if n["reason"] not in ["mention", "reply"]:
                continue
            if n["uri"] in existing_uris:
                continue
            if n["uri"] in sent_uris:
                continue  # Already replied to this
            if n.get("isRead", False): # Only fetch unread? Maybe allow fetching recent read ones too?
                # For now, let's include even read ones if they aren't in the queue, 
                # but usually we want to clear the queue.
                # Actually, let's stick to unread to avoid noise, OR allow a --all flag.
                # Defaulting to unread only for safety.
                pass
            
            # Fetch context (parent/root) for threading
            # We need the post record to get reply refs
            record = n.get("record", {})
            reply_context = record.get("reply", {})
            
            # If it's a reply to us, the parent is the notification post
            # The root is the thread root
            
            # Wait, if *they* replied to *us*, we reply to *them*.
            # Our Root = Their Root (or Them if they are root)
            # Our Parent = Them
            
            their_root = reply_context.get("root", {"uri": n["uri"], "cid": n["cid"]})
            their_uri = n["uri"]
            their_cid = n["cid"]
            
            text = record.get("text", "")
            priority = get_priority(n["author"]["did"], text)
            
            entry = {
                "priority": priority,
                "author": n["author"]["handle"],
                "text": text,
                "uri": their_uri,
                "cid": their_cid,
                "reply_root": their_root, # Pass this through
                "reply_parent": {"uri": their_uri, "cid": their_cid},
                "response": None, # Agent fills this
                "action": "reply", # ignore, like
                "queued_at": datetime.now(timezone.utc).isoformat(),
            }
            
            queue.insert(0, entry) # Newest first? Or append? Let's prepend.
            count += 1
        
        # Sort queue by priority (CRITICAL first, SKIP last)
        queue.sort(key=lambda x: PRIORITY_ORDER.get(x.get("priority", "MEDIUM"), 2))
            
        with open(DRAFTS_FILE, "w") as f:
            yaml.dump(queue, f, sort_keys=False, indent=2)
            
        console.print(f"[green]Queued {count} new notifications.[/green]")
        console.print(f"Edit {DRAFTS_FILE} to draft responses.")

def _load_sent_uris() -> set:
    """Load the set of URIs we've already replied to."""
    if not SENT_FILE.exists():
        return set()
    content = SENT_FILE.read_text().strip()
    if not content:
        return set()
    return set(content.split("\n"))


def _record_sent_uri(uri: str):
    """Immediately record a sent URI to sent.txt."""
    SENT_FILE.parent.mkdir(exist_ok=True)
    with open(SENT_FILE, "a") as f:
        f.write(uri + "\n")


async def send_queue(dry_run=False, confirm=False, force=False):
    """Process the queue.
    
    Args:
        dry_run: Preview what would be sent without actually sending
        confirm: Required to actually send (safety measure)
        force: Bypass sent.txt check (re-send even if URI already in sent.txt)
    """
    if not DRAFTS_FILE.exists():
        console.print("[yellow]No queue file found.[/yellow]")
        return

    with open(DRAFTS_FILE, "r") as f:
        queue = yaml.safe_load(f) or []
    
    if not queue:
        console.print("[yellow]Queue is empty.[/yellow]")
        return

    # Load already-sent URIs to prevent duplicates
    sent_uris = _load_sent_uris() if not force else set()
    
    # Filter to items that have responses and haven't been sent
    pending = []
    already_sent = []
    for item in queue:
        if not item.get("response") or item.get("action") != "reply":
            continue
        if item["uri"] in sent_uris:
            already_sent.append(item)
        else:
            pending.append(item)
    
    if already_sent:
        console.print(f"[dim]Skipping {len(already_sent)} items already in sent.txt[/dim]")
    
    if not pending:
        console.print("[yellow]No new responses to send (all either empty or already sent).[/yellow]")
        return

    console.print(f"[bold]Found {len(pending)} responses to send.[/bold]")
    
    # Show preview
    for p in pending:
        status = "[WOULD SEND]" if dry_run or not confirm else "[SENDING]"
        console.print(f"{status} To: @{p['author']}")
        console.print(f"  Msg: {p['response'][:100]}{'...' if len(p['response']) > 100 else ''}")
    
    if dry_run:
        console.print("\n[yellow]Dry run - no messages sent. Use --confirm to send.[/yellow]")
        return
    
    if not confirm:
        console.print("\n[yellow]Preview only. Use --confirm to actually send.[/yellow]")
        return

    # Send
    async with ComindAgent() as agent:
        sent_indices = []
        for i, item in enumerate(queue):
            if not item.get("response") or item.get("action") != "reply":
                continue
            
            # Double-check: skip if already sent (unless --force)
            if not force and item["uri"] in sent_uris:
                continue
            
            console.print(f"Replying to @{item['author']}...")
            try:
                reply_to = {
                    "root": item["reply_root"],
                    "parent": item["reply_parent"]
                }
                await agent.create_post(item["response"], reply_to=reply_to)
                
                # Immediately record sent URI (not batched - prevents duplicates on partial failure)
                _record_sent_uri(item["uri"])
                sent_uris.add(item["uri"])  # Update in-memory set too
                
                sent_indices.append(i)
            except Exception as e:
                console.print(f"[red]Failed: {e}[/red]")
        
        # Remove sent items from queue
        new_queue = [item for i, item in enumerate(queue) if i not in sent_indices]
        
        with open(DRAFTS_FILE, "w") as f:
            yaml.dump(new_queue, f, sort_keys=False, indent=2)
            
        console.print(f"[green]Sent {len(sent_indices)} replies. Queue updated.[/green]")

def cleanup_queue(keep_priorities=["CRITICAL", "HIGH"], ttl_hours: int | None = None):
    """Remove low-priority and/or old items from queue.
    
    Args:
        keep_priorities: Only keep items with these priorities (None to skip priority filter)
        ttl_hours: Remove items older than this (None to skip TTL filter)
    """
    if not DRAFTS_FILE.exists():
        console.print("[yellow]No queue file.[/yellow]")
        return
    
    with open(DRAFTS_FILE, "r") as f:
        queue = yaml.safe_load(f) or []
    
    before = len(queue)
    
    # Apply TTL filter
    if ttl_hours is not None:
        queue, ttl_removed = _apply_ttl_cleanup(queue, ttl_hours)
        if ttl_removed > 0:
            console.print(f"[dim]Removed {ttl_removed} items older than {ttl_hours}h[/dim]")
    
    # Apply priority filter
    if keep_priorities is not None:
        queue = [item for item in queue if item.get("priority") in keep_priorities]
    
    with open(DRAFTS_FILE, "w") as f:
        yaml.dump(queue, f, sort_keys=False, indent=2)
    
    console.print(f"[green]Cleaned queue: {before} → {len(queue)} items[/green]")


# ============================================================================
# Batch Processing via Letta Conversations API
# ============================================================================

def get_letta_client():
    """Get Letta client for API access."""
    try:
        from letta_client import Letta
        api_key = os.getenv("LETTA_API_KEY")
        if not api_key:
            console.print("[red]LETTA_API_KEY not set[/red]")
            return None
        return Letta(api_key=api_key)
    except ImportError:
        console.print("[red]letta-client not installed. Run: uv add letta-client[/red]")
        return None
    except Exception as e:
        console.print(f"[red]Letta client error: {e}[/red]")
        return None


def build_batch_prompt(items: list, start_idx: int) -> str:
    """Build a prompt for comms to process a batch of notification items.
    
    Args:
        items: List of queue items to process
        start_idx: Starting index in the original queue
        
    Returns:
        Prompt string for comms agent
    """
    prompt_parts = [
        "Process these notification items and draft responses.",
        "",
        "IMPORTANT: Return ONLY a JSON array with your responses. Format:",
        '```json',
        '[',
        '  {"index": 0, "response": "Your response here"},',
        '  {"index": 1, "response": "Another response"}',
        ']',
        '```',
        "",
        "Guidelines:",
        "- Be substantive, not performative",
        "- Keep responses concise (under 280 chars)",
        "- Match the tone of the original message",
        "- If item should be skipped, use response: null",
        "",
        "Items to process:",
    ]
    
    for i, item in enumerate(items):
        idx = start_idx + i
        text = item.get("text", "")[:300]
        author = item.get("author", "unknown")
        priority = item.get("priority", "MEDIUM")
        prompt_parts.append(f"\n[{idx}] ({priority}) @{author}:")
        prompt_parts.append(f"  \"{text}\"")
    
    prompt_parts.append("\n\nRespond with ONLY the JSON array, no other text:")
    return "\n".join(prompt_parts)


def parse_batch_responses(response_text: str) -> dict:
    """Parse comms' JSON response into index->response mapping.
    
    Args:
        response_text: Raw response from comms agent
        
    Returns:
        Dict mapping index (int) to response (str or None)
    """
    # Try to extract JSON from the response
    # Look for JSON array pattern
    json_match = re.search(r'\[\s*\{.*?\}\s*\]', response_text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return {
                item['index']: item.get('response')
                for item in data
                if 'index' in item
            }
        except json.JSONDecodeError:
            pass
    
    # Try parsing entire response as JSON
    try:
        data = json.loads(response_text)
        if isinstance(data, list):
            return {
                item['index']: item.get('response')
                for item in data
                if 'index' in item
            }
    except json.JSONDecodeError:
        pass
    
    console.print(f"[yellow]Warning: Could not parse response as JSON[/yellow]")
    return {}


def process_batch_sync(client, items: list, start_idx: int, batch_num: int) -> dict:
    """Process a single batch synchronously (for use with ThreadPoolExecutor).
    
    Args:
        client: Letta client
        items: Queue items for this batch
        start_idx: Starting index in original queue
        batch_num: Batch number for logging
        
    Returns:
        Dict mapping original queue indices to responses
    """
    try:
        console.print(f"[cyan]Batch {batch_num}: Creating conversation for items {start_idx}-{start_idx + len(items) - 1}...[/cyan]")
        
        # Create a new conversation with comms
        conv = client.conversations.create(agent_id=COMMS_AGENT_ID)
        console.print(f"[dim]Batch {batch_num}: Conversation {conv.id} created[/dim]")
        
        # Build prompt and send message
        prompt = build_batch_prompt(items, start_idx)
        
        # Send message and collect streaming response
        response_text = ""
        stream = client.conversations.messages.create(
            conv.id,
            messages=[{"role": "user", "content": prompt}],
            stream_tokens=True,
        )
        
        for chunk in stream:
            if hasattr(chunk, 'message_type'):
                if chunk.message_type == "assistant_message":
                    content = getattr(chunk, 'content', '') or ''
                    response_text += content
        
        console.print(f"[green]Batch {batch_num}: Received response ({len(response_text)} chars)[/green]")
        
        # Parse responses
        responses = parse_batch_responses(response_text)
        console.print(f"[green]Batch {batch_num}: Parsed {len(responses)} responses[/green]")
        
        return responses
        
    except Exception as e:
        console.print(f"[red]Batch {batch_num}: Error - {e}[/red]")
        return {}


def batch_process(batch_size: int = 10, dry_run: bool = False):
    """Process queue items in parallel batches via Letta Conversations API.
    
    Args:
        batch_size: Number of items per batch (default 10)
        dry_run: If True, show what would be processed without calling API
    """
    # Load queue
    if not DRAFTS_FILE.exists():
        console.print("[yellow]No queue file found.[/yellow]")
        return
    
    with open(DRAFTS_FILE, "r") as f:
        queue = yaml.safe_load(f) or []
    
    # Filter to items needing responses (no response yet, action=reply, priority != SKIP)
    pending_indices = []
    for i, item in enumerate(queue):
        if item.get("response"):
            continue  # Already has response
        if item.get("action") != "reply":
            continue  # Not a reply action
        if item.get("priority") == "SKIP":
            continue  # Skip priority items
        pending_indices.append(i)
    
    if not pending_indices:
        console.print("[yellow]No items needing responses.[/yellow]")
        return
    
    console.print(f"[bold]Found {len(pending_indices)} items needing responses.[/bold]")
    
    # Partition into batches
    batches = []
    for i in range(0, len(pending_indices), batch_size):
        batch_indices = pending_indices[i:i + batch_size]
        batch_items = [queue[idx] for idx in batch_indices]
        batches.append((batch_indices, batch_items))
    
    console.print(f"[bold]Partitioned into {len(batches)} batches of up to {batch_size} items each.[/bold]")
    
    if dry_run:
        for i, (indices, items) in enumerate(batches):
            console.print(f"\n[cyan]Batch {i + 1}:[/cyan]")
            for idx, item in zip(indices, items):
                console.print(f"  [{idx}] @{item.get('author', 'unknown')}: {item.get('text', '')[:50]}...")
        console.print("\n[yellow]Dry run - no API calls made. Remove --dry-run to process.[/yellow]")
        return
    
    # Get Letta client
    client = get_letta_client()
    if not client:
        return
    
    # Process batches in parallel using ThreadPoolExecutor
    all_responses = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(batches)) as executor:
        futures = {}
        for batch_num, (indices, items) in enumerate(batches):
            # Submit batch processing
            future = executor.submit(
                process_batch_sync,
                client,
                items,
                indices[0],  # start_idx is the first index in this batch
                batch_num + 1
            )
            futures[future] = (batch_num, indices)
        
        # Collect results
        for future in concurrent.futures.as_completed(futures):
            batch_num, indices = futures[future]
            try:
                responses = future.result()
                all_responses.update(responses)
            except Exception as e:
                console.print(f"[red]Batch {batch_num + 1} failed: {e}[/red]")
    
    # Merge responses back into queue
    updated_count = 0
    for idx, response in all_responses.items():
        if response and idx < len(queue):
            queue[idx]["response"] = response
            updated_count += 1
    
    # Save updated queue
    with open(DRAFTS_FILE, "w") as f:
        yaml.dump(queue, f, sort_keys=False, indent=2)
    
    console.print(f"\n[green]Done! Updated {updated_count} items with responses.[/green]")
    console.print(f"[dim]Review responses in {DRAFTS_FILE}, then run: uv run python -m tools.responder send --confirm[/dim]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Queue-based notification handler")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # queue command
    queue_parser = subparsers.add_parser("queue", help="Fetch notifications into queue")
    queue_parser.add_argument("--limit", type=int, default=50, help="Max notifications to fetch")
    
    # send command
    send_parser = subparsers.add_parser("send", help="Send drafted responses")
    send_parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    send_parser.add_argument("--confirm", action="store_true", help="Actually send (required for safety)")
    send_parser.add_argument("--force", action="store_true", help="Bypass sent.txt check (re-send even if already sent)")
    
    # cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up queue")
    cleanup_parser.add_argument("--ttl", type=int, help=f"Remove items older than N hours (default: {QUEUE_TTL_HOURS})")
    cleanup_parser.add_argument("--ttl-only", action="store_true", help="Only apply TTL, skip priority filter")
    cleanup_parser.add_argument("--all-priorities", action="store_true", help="Keep all priorities, only apply TTL")
    
    # process command - batch processing via Letta API
    process_parser = subparsers.add_parser("process", help="Batch process queue via Letta Conversations API")
    process_parser.add_argument("--batch", type=int, default=10, help="Items per batch (default: 10)")
    process_parser.add_argument("--dry-run", action="store_true", help="Preview batches without calling API")
    
    # check command (legacy)
    subparsers.add_parser("check", help="Legacy: display notifications")
    
    args = parser.parse_args()
    
    if args.command == "queue":
        asyncio.run(queue_notifications(limit=args.limit))
    elif args.command == "send":
        asyncio.run(send_queue(dry_run=args.dry_run, confirm=args.confirm, force=args.force))
    elif args.command == "cleanup":
        ttl = args.ttl if args.ttl else (QUEUE_TTL_HOURS if args.ttl_only or args.all_priorities else None)
        priorities = None if args.all_priorities or args.ttl_only else ["CRITICAL", "HIGH"]
        cleanup_queue(keep_priorities=priorities, ttl_hours=ttl)
    elif args.command == "process":
        batch_process(batch_size=args.batch, dry_run=args.dry_run)
    elif args.command == "check":
        # Legacy check
        from tools.responder import display_notifications
        asyncio.run(display_notifications())
    else:
        parser.print_help()
