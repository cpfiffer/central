"""
Respond Tool - Set responses in the notification queue.

Usage:
    python -m tools.respond set <uri> <response_text>
    python -m tools.respond list  # Show queue with indices
    python -m tools.respond set-by-index <index> <response_text>

This tool handles YAML manipulation properly so subagents don't corrupt the file.
"""

import sys
import yaml
from pathlib import Path
from datetime import datetime, timezone

QUEUE_FILE = Path("drafts/queue.yaml")
SENT_FILE = Path("drafts/sent.txt")
NEW_THRESHOLD_MINUTES = 30  # Items newer than this get 🆕 indicator


def load_queue():
    """Load the queue, return empty list if missing/corrupt."""
    if not QUEUE_FILE.exists():
        return []
    try:
        with open(QUEUE_FILE, "r") as f:
            return yaml.safe_load(f) or []
    except yaml.YAMLError as e:
        print(f"Error loading queue: {e}")
        return []


def save_queue(queue):
    """Save queue to YAML."""
    QUEUE_FILE.parent.mkdir(exist_ok=True)
    with open(QUEUE_FILE, "w") as f:
        yaml.dump(queue, f, sort_keys=False, allow_unicode=True, width=1000)


def load_sent_uris() -> set:
    """Load the set of URIs we've already replied to."""
    if not SENT_FILE.exists():
        return set()
    content = SENT_FILE.read_text().strip()
    if not content:
        return set()
    return set(content.split("\n"))


def is_new(queued_at: str | None) -> bool:
    """Check if item was queued within NEW_THRESHOLD_MINUTES."""
    if not queued_at:
        return False
    try:
        item_time = datetime.fromisoformat(queued_at)
        now = datetime.now(timezone.utc)
        age_minutes = (now - item_time).total_seconds() / 60
        return age_minutes <= NEW_THRESHOLD_MINUTES
    except (ValueError, TypeError):
        return False


def list_queue():
    """List queue items with indices."""
    queue = load_queue()
    if not queue:
        print("Queue is empty.")
        return
    
    sent_uris = load_sent_uris()
    
    for i, item in enumerate(queue):
        author = item.get("author", "unknown")
        priority = item.get("priority", "MEDIUM")
        text = item.get("text", "")[:50].replace("\n", " ")
        response = item.get("response")
        uri = item.get("uri", "")
        queued_at = item.get("queued_at")
        
        # Status: ✓ = has response, ○ = no response, ⚠ = already sent (duplicate)
        if uri in sent_uris:
            status = "⚠SENT"  # Already in sent.txt - would be skipped
        elif response:
            status = "✓"
        else:
            status = "○"
        
        # NEW indicator for recent items
        new_indicator = "🆕" if is_new(queued_at) else "  "
        
        print(f"{i}: {new_indicator} [{status}] [{priority}] @{author}: {text}...")


def set_response(uri: str, response: str):
    """Set response for a specific URI."""
    queue = load_queue()
    
    # Check if already sent
    sent_uris = load_sent_uris()
    if uri in sent_uris:
        print(f"⚠️  WARNING: URI already sent. Skipping.")
        return
    
    found = False
    for item in queue:
        if item.get("uri") == uri:
            author = item.get("author", "unknown")
            if item.get("response"):
                print(f"⚠️  WARNING: @{author} already has response. Overwriting.")
            item["response"] = response
            found = True
            break
    
    if found:
        save_queue(queue)
        print(f"Set response for {uri[:50]}...")
    else:
        print(f"URI not found in queue: {uri[:50]}...")


def set_response_by_index(index: int, response: str):
    """Set response by queue index."""
    queue = load_queue()
    
    if index < 0 or index >= len(queue):
        print(f"Invalid index {index}. Queue has {len(queue)} items.")
        return
    
    item = queue[index]
    uri = item.get("uri", "")
    author = item.get("author", "unknown")
    
    # Check if already sent
    sent_uris = load_sent_uris()
    if uri in sent_uris:
        print(f"⚠️  WARNING: Item {index} (@{author}) already sent. Skipping.")
        return
    
    # Check if already has a response (prevent accidental overwrite)
    if item.get("response"):
        print(f"⚠️  WARNING: Item {index} (@{author}) already has response. Overwriting.")
    
    item["response"] = response
    save_queue(queue)
    print(f"Set response for item {index} (@{author})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "list":
        list_queue()
    
    elif cmd == "set" and len(sys.argv) >= 4:
        uri = sys.argv[2]
        response = sys.argv[3]
        set_response(uri, response)
    
    elif cmd == "set-by-index" and len(sys.argv) >= 4:
        index = int(sys.argv[2])
        response = sys.argv[3]
        set_response_by_index(index, response)
    
    else:
        print(__doc__)
        sys.exit(1)
