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
from tools.agent import ComindAgent

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

async def send_queue(dry_run=False):
    """Process the queue."""
    if not DRAFTS_FILE.exists():
        console.print("[yellow]No queue file found.[/yellow]")
        return

    with open(DRAFTS_FILE, "r") as f:
        queue = yaml.safe_load(f) or []
    
    if not queue:
        console.print("[yellow]Queue is empty.[/yellow]")
        return

    pending = [i for i in queue if i.get("response") and i.get("action") == "reply"]
    
    if not pending:
        console.print("[yellow]No drafted responses found (fill 'response' field).[/yellow]")
        return

    console.print(f"[bold]Found {len(pending)} responses to send.[/bold]")
    if dry_run:
        for p in pending:
            console.print(f"To: @{p['author']}")
            console.print(f"Msg: {p['response']}")
            console.print("---")
        return

    # Send
    async with ComindAgent() as agent:
        sent_indices = []
        for i, item in enumerate(queue):
            if not item.get("response") or item.get("action") != "reply":
                continue
            
            console.print(f"Replying to @{item['author']}...")
            try:
                reply_to = {
                    "root": item["reply_root"],
                    "parent": item["reply_parent"]
                }
                await agent.create_post(item["response"], reply_to=reply_to)
                sent_indices.append(i)
                # Mark notification as read? 
                # Ideally yes, but agent.py doesn't have that method exposed nicely yet.
                # We'll assume the user will clear notifications later or we automate it.
            except Exception as e:
                console.print(f"[red]Failed: {e}[/red]")
        
        # Track sent URIs to avoid re-queuing
        sent_uris = []
        for i in sent_indices:
            sent_uris.append(queue[i]["uri"])
        
        if sent_uris:
            with open(SENT_FILE, "a") as f:
                f.write("\n".join(sent_uris) + "\n")
        
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Queue-based notification handler")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # queue command
    queue_parser = subparsers.add_parser("queue", help="Fetch notifications into queue")
    queue_parser.add_argument("--limit", type=int, default=50, help="Max notifications to fetch")
    
    # send command
    send_parser = subparsers.add_parser("send", help="Send drafted responses")
    send_parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    
    # cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up queue")
    cleanup_parser.add_argument("--ttl", type=int, help=f"Remove items older than N hours (default: {QUEUE_TTL_HOURS})")
    cleanup_parser.add_argument("--ttl-only", action="store_true", help="Only apply TTL, skip priority filter")
    cleanup_parser.add_argument("--all-priorities", action="store_true", help="Keep all priorities, only apply TTL")
    
    # check command (legacy)
    subparsers.add_parser("check", help="Legacy: display notifications")
    
    args = parser.parse_args()
    
    if args.command == "queue":
        asyncio.run(queue_notifications(limit=args.limit))
    elif args.command == "send":
        asyncio.run(send_queue(dry_run=args.dry_run))
    elif args.command == "cleanup":
        ttl = args.ttl if args.ttl else (QUEUE_TTL_HOURS if args.ttl_only or args.all_priorities else None)
        priorities = None if args.all_priorities or args.ttl_only else ["CRITICAL", "HIGH"]
        cleanup_queue(keep_priorities=priorities, ttl_hours=ttl)
    elif args.command == "check":
        # Legacy check
        from tools.responder import display_notifications
        asyncio.run(display_notifications())
    else:
        parser.print_help()
