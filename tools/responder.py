"""
Responder V2 - Queue-based Notification Handling
"""

import asyncio
import sys
import os
import yaml
import argparse
from pathlib import Path
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.agent import ComindAgent

console = Console()
DRAFTS_FILE = Path("drafts/queue.yaml")

# Reuse prioritization from old responder
CAMERON_DID = "did:plc:gfrmhdmjvxn2sjedzboeudef"
COMIND_AGENTS = {
    "did:plc:l46arqe6yfgh36h3o554iyvr": "central",
    "did:plc:mxzuau6m53jtdsbqe6f4laov": "void",
    "did:plc:uz2snz44gi4zgqdwecavi66r": "herald",
    "did:plc:ogruxay3tt7wycqxnf5lis6s": "grunk",
}

def get_priority(author_did):
    if author_did == CAMERON_DID: return "HIGH (Cameron)"
    if author_did in COMIND_AGENTS: return "SKIP (Comind Agent)"
    return "NORMAL"

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
        
        existing_uris = {item["uri"] for item in queue}
        count = 0
        
        for n in notifications:
            if n["reason"] not in ["mention", "reply"]:
                continue
            if n["uri"] in existing_uris:
                continue
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
            
            entry = {
                "priority": get_priority(n["author"]["did"]),
                "author": n["author"]["handle"],
                "text": record.get("text", ""),
                "uri": their_uri,
                "cid": their_cid,
                "reply_root": their_root, # Pass this through
                "reply_parent": {"uri": their_uri, "cid": their_cid},
                "response": None, # Agent fills this
                "action": "reply" # ignore, like
            }
            
            queue.insert(0, entry) # Newest first? Or append? Let's prepend.
            count += 1
            
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
        
        # Remove sent items from queue (or move to archive)
        # For now, just remove from the list
        new_queue = [item for i, item in enumerate(queue) if i not in sent_indices]
        
        with open(DRAFTS_FILE, "w") as f:
            yaml.dump(new_queue, f, sort_keys=False, indent=2)
            
        console.print(f"[green]Sent {len(sent_indices)} replies. Queue updated.[/green]")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: responder.py [queue|send|check]")
        sys.exit(1)
        
    cmd = sys.argv[1]
    if cmd == "queue":
        asyncio.run(queue_notifications())
    elif cmd == "send":
        asyncio.run(send_queue())
    elif cmd == "check":
        # Legacy check
        from tools.responder import display_notifications
        asyncio.run(display_notifications())
    else:
        print("Unknown command")
