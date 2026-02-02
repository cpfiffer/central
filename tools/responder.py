"""
Responder V2 - Queue-based Notification Handling
"""

import asyncio
import sys
import os
import yaml
import argparse
from datetime import datetime, timezone
from pathlib import Path
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.agent import ComindAgent, PostResult

console = Console()
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

# Cache for already-replied URIs (populated from API)
_already_replied_cache: set | None = None


async def _get_already_replied_uris(agent, limit: int = 100) -> set:
    """Fetch URIs of posts we've already replied to by checking our recent posts."""
    global _already_replied_cache
    
    # Use cache if available (valid for this session)
    if _already_replied_cache is not None:
        return _already_replied_cache
    
    replied_to = set()
    try:
        # Fetch our recent posts
        resp = await agent._client.get(
            "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed",
            params={"actor": "central.comind.network", "limit": limit},
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("feed", []):
                post = item.get("post", {})
                record = post.get("record", {})
                reply = record.get("reply", {})
                if reply:
                    # This is a reply - extract the parent URI
                    parent = reply.get("parent", {})
                    parent_uri = parent.get("uri")
                    if parent_uri:
                        replied_to.add(parent_uri)
        
        _already_replied_cache = replied_to
        console.print(f"[dim]Checked {limit} recent posts, found {len(replied_to)} replies[/dim]")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not fetch reply history: {e}[/yellow]")
    
    return replied_to


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
        
        # Also check our actual recent replies via API (catches replies made outside responder)
        already_replied = await _get_already_replied_uris(agent, limit=100)
        sent_uris.update(already_replied)
        
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
        
        # Sort queue by priority (CRITICAL first, SKIP last), then by timestamp (newest first within tier)
        def sort_key(x):
            priority = PRIORITY_ORDER.get(x.get("priority", "MEDIUM"), 2)
            # Default to epoch if no timestamp (puts legacy items last within tier)
            queued_at = x.get("queued_at", "1970-01-01T00:00:00+00:00")
            # Negate timestamp for reverse chronological within priority tier
            return (priority, -datetime.fromisoformat(queued_at).timestamp())
        queue.sort(key=sort_key)
            
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
        failed_items = []
        for i, item in enumerate(queue):
            if not item.get("response") or item.get("action") != "reply":
                continue
            
            # Double-check: skip if already sent (unless --force)
            if not force and item["uri"] in sent_uris:
                continue
            
            console.print(f"Replying to @{item['author']}...")
            
            reply_to = {
                "root": item["reply_root"],
                "parent": item["reply_parent"]
            }
            
            # Use create_post_with_retry for automatic retry on transient failures
            result = await agent.create_post_with_retry(item["response"], reply_to=reply_to)
            
            if result.success:
                # Immediately record sent URI (not batched - prevents duplicates on partial failure)
                _record_sent_uri(item["uri"])
                sent_uris.add(item["uri"])  # Update in-memory set too
                sent_indices.append(i)
                console.print(f"[green]Sent reply to @{item['author']}[/green]")
            else:
                # Log detailed failure info
                console.print(f"[red]Failed to reply to @{item['author']}[/red]")
                console.print(f"[red]  Error type: {result.error_type}[/red]")
                console.print(f"[red]  Message: {result.error_message}[/red]")
                console.print(f"[red]  Retryable: {result.retryable}[/red]")
                if result.retry_after_seconds:
                    console.print(f"[yellow]  Retry after: {result.retry_after_seconds}s[/yellow]")
                failed_items.append({
                    "author": item["author"],
                    "error_type": result.error_type,
                    "error_message": result.error_message,
                    "retryable": result.retryable
                })
        
        # Remove sent items from queue
        new_queue = [item for i, item in enumerate(queue) if i not in sent_indices]
        
        with open(DRAFTS_FILE, "w") as f:
            yaml.dump(new_queue, f, sort_keys=False, indent=2)
            
        console.print(f"[green]Sent {len(sent_indices)} replies. Queue updated.[/green]")
        
        # Report failures summary
        if failed_items:
            console.print(f"\n[red]Failed to send {len(failed_items)} replies:[/red]")
            for fail in failed_items:
                retryable_status = "[retryable]" if fail["retryable"] else "[not retryable]"
                console.print(f"  - @{fail['author']}: {fail['error_type']} {retryable_status}")
            console.print("\n[yellow]To debug failures, message comms directly or check error logs.[/yellow]")

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
# Parallel Processing Helper
# ============================================================================

COMMS_AGENT_ID = "agent-a856f614-7654-44ba-a35f-c817d477dded"


async def process_queue(dry_run=False):
    """Have comms draft responses for all pending items via Letta API.
    
    This is the preferred way to draft responses - comms controls all content,
    Central just orchestrates.
    
    Args:
        dry_run: Preview without writing to YAML
    """
    from letta_client import Letta
    
    if not DRAFTS_FILE.exists():
        console.print("[yellow]No queue file found. Run 'queue' first.[/yellow]")
        return
    
    with open(DRAFTS_FILE, "r") as f:
        queue = yaml.safe_load(f) or []
    
    # Filter to items needing responses
    pending = [(i, item) for i, item in enumerate(queue) 
               if not item.get("response") 
               and item.get("action") == "reply"
               and item.get("priority") != "SKIP"]
    
    if not pending:
        console.print("[yellow]No items needing responses.[/yellow]")
        return
    
    console.print(f"[bold]Processing {len(pending)} items via comms...[/bold]\n")
    
    api_key = os.environ.get('LETTA_API_KEY')
    if not api_key:
        console.print("[red]LETTA_API_KEY not set[/red]")
        return
    
    client = Letta(base_url='https://api.letta.com', api_key=api_key)
    
    processed = 0
    skipped = 0
    
    for idx, item in pending:
        author = item.get('author', 'unknown')
        text = item.get('text', '')
        priority = item.get('priority', 'MEDIUM')
        
        # Build prompt for comms
        prompt = f"""Draft a reply to this Bluesky notification.

**Author:** @{author}
**Priority:** {priority}
**Text:** {text}

Guidelines:
- Use compressed, opinionated voice
- Under 280 chars
- If it doesn't warrant a reply, respond with exactly "SKIP"
- NEVER claim an action was completed (issue opened, fix deployed, etc.) unless you have proof (URL, commit hash)
- If the message is a directive (do X, fix Y), acknowledge receipt - don't claim completion

Return ONLY the reply text, nothing else."""

        try:
            response = client.agents.messages.create(
                agent_id=COMMS_AGENT_ID,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Extract response from comms
            draft = None
            for msg in reversed(response.messages):
                if hasattr(msg, 'content') and msg.content:
                    draft = msg.content.strip()
                    break
            
            if draft and draft.upper() != "SKIP":
                queue[idx]["response"] = draft
                console.print(f"[green]✓[/green] [{idx}] @{author}: {draft[:60]}...")
                processed += 1
            else:
                console.print(f"[yellow]⊘[/yellow] [{idx}] @{author}: skipped by comms")
                skipped += 1
                
        except Exception as e:
            console.print(f"[red]✗[/red] [{idx}] @{author}: error - {e}")
    
    console.print(f"\n[bold]Done:[/bold] {processed} drafted, {skipped} skipped")
    
    # Write back
    if not dry_run and processed > 0:
        with open(DRAFTS_FILE, "w") as f:
            yaml.dump(queue, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        console.print(f"[green]Updated {DRAFTS_FILE}[/green]")
        console.print(f"\n[cyan]Next: uv run python -m tools.responder send --dry-run[/cyan]")
    elif dry_run:
        console.print(f"\n[yellow]Dry run - no changes written[/yellow]")


def process_parallel(batch_size: int = 10):
    """Partition queue and output Task() calls for parallel processing.
    
    This generates the Task() calls that the agent should execute in parallel.
    Since CLI can't invoke Task() directly, this outputs them for copy/paste.
    
    Args:
        batch_size: Number of items per batch (default: 10)
    """
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
    
    # Show items summary
    console.print("\n[cyan]Items to process:[/cyan]")
    for idx in pending_indices:
        item = queue[idx]
        priority = item.get("priority", "MEDIUM")
        author = item.get("author", "unknown")
        text = item.get("text", "")[:40].replace("\n", " ")
        console.print(f"  [{idx}] ({priority}) @{author}: {text}...")
    
    # Partition into batches
    batches = []
    for i in range(0, len(pending_indices), batch_size):
        batch_indices = pending_indices[i:i + batch_size]
        batches.append(batch_indices)
    
    console.print(f"\n[bold]Partitioned into {len(batches)} batches of up to {batch_size} items.[/bold]")
    
    # Generate Task() calls
    console.print("\n[green]Execute these Task() calls in parallel:[/green]")
    console.print("=" * 60)
    
    for batch_num, indices in enumerate(batches):
        start_idx = indices[0]
        end_idx = indices[-1]
        
        # Build the prompt for comms
        prompt = (
            f"Process notification queue items {start_idx}-{end_idx}. "
            f"Run `uv run python -m tools.respond list` to see the queue. "
            f"For indices {', '.join(str(i) for i in indices)}, draft responses and set them with "
            f"`uv run python -m tools.respond set-by-index <index> \"<response>\"`. "
            f"Guidelines: Be substantive not performative. Keep responses under 280 chars. "
            f"Match the tone of the original. Skip items that don't warrant a response. "
            f"**Report**: How many processed, any notable interactions."
        )
        
        # Output the Task() call
        console.print(f"\n[cyan]# Batch {batch_num + 1}: indices {start_idx}-{end_idx}[/cyan]")
        console.print(f'Task(agent_id="{COMMS_AGENT_ID}", subagent_type="general-purpose", description="Process batch {batch_num + 1}", prompt="{prompt}")')
    
    console.print("\n" + "=" * 60)
    console.print("\n[yellow]After all Task() calls complete, run:[/yellow]")
    console.print("  uv run python -m tools.responder send --confirm")


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
    
    # process command (comms drafts responses)
    process_parser = subparsers.add_parser("process", help="Have comms draft responses via Letta API")
    process_parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    
    # process-parallel command
    parallel_parser = subparsers.add_parser("process-parallel", help="Partition queue and output Task() calls for parallel processing")
    parallel_parser.add_argument("--batch-size", type=int, default=10, help="Items per batch (default: 10)")
    
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
        asyncio.run(process_queue(dry_run=args.dry_run))
    elif args.command == "process-parallel":
        process_parallel(batch_size=args.batch_size)
    elif args.command == "check":
        # Legacy check
        from tools.responder import display_notifications
        asyncio.run(display_notifications())
    else:
        parser.print_help()
