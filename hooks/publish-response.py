#!/usr/bin/env python3
"""
Publish Response Hook - Post assistant messages to ATProtocol.

Fires on Stop event, queries Letta API for recent messages,
publishes to network.comind.response
"""

import sys
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Use script directory for relative paths
SCRIPT_DIR = Path(__file__).parent.parent
load_dotenv(SCRIPT_DIR / ".env")

# ATProtocol credentials
PDS = os.getenv("ATPROTO_PDS")
DID = os.getenv("ATPROTO_DID")
HANDLE = os.getenv("ATPROTO_HANDLE")
APP_PASSWORD = os.getenv("ATPROTO_APP_PASSWORD")

# Letta API credentials (from runtime env, set by Letta Code)
LETTA_API_KEY = os.environ.get("LETTA_API_KEY")  # Use environ for runtime vars
LETTA_AGENT_ID = os.environ.get("LETTA_AGENT_ID", "agent-c770d1c8-510e-4414-be36-c9ebd95a7758")
LETTA_API_BASE = "https://api.letta.com/v1"

# Redaction patterns
REDACT_PATTERNS = [
    (r'[A-Za-z_]*API_KEY[=:]\s*\S+', '[REDACTED]'),
    (r'[A-Za-z_]*PASSWORD[=:]\s*\S+', '[REDACTED]'),
    (r'[A-Za-z_]*SECRET[=:]\s*\S+', '[REDACTED]'),
    (r'Bearer\s+\S+', 'Bearer [REDACTED]'),
    (r'sk-[A-Za-z0-9]+', '[REDACTED]'),
    (r'ghp_[A-Za-z0-9]+', '[REDACTED]'),
]

def redact(text: str) -> str:
    """Redact potential secrets."""
    for pattern, replacement in REDACT_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def get_recent_messages(limit: int = 20) -> list:
    """Fetch recent assistant + reasoning messages from Letta API."""
    if not LETTA_API_KEY:
        return []
    
    try:
        resp = httpx.get(
            f"{LETTA_API_BASE}/agents/{LETTA_AGENT_ID}/messages",
            headers={"Authorization": f"Bearer {LETTA_API_KEY}"},
            params={"limit": limit},
            timeout=15
        )
        if resp.status_code != 200:
            return []
        
        messages = resp.json()
        
        # Filter for assistant and reasoning messages
        result = []
        for msg in messages:
            msg_type = msg.get("message_type")
            if msg_type == "assistant_message":
                content = msg.get("content", "")
                if content and len(content) > 10:
                    result.append({
                        "content": content,
                        "type": msg_type,
                        "id": msg.get("id"),
                        "date": msg.get("date")
                    })
            elif msg_type == "reasoning_message":
                # Reasoning uses different field
                content = msg.get("reasoning", "")
                if content and len(content) > 10:
                    result.append({
                        "content": content,
                        "type": msg_type,
                        "id": msg.get("id"),
                        "date": msg.get("date")
                    })
        
        return result
    except Exception as e:
        return []


def get_session():
    """Authenticate."""
    resp = httpx.post(
        f"{PDS}/xrpc/com.atproto.server.createSession",
        json={"identifier": HANDLE, "password": APP_PASSWORD},
        timeout=10
    )
    if resp.status_code != 200:
        return None
    return resp.json()


def post_to_collection(content: str, collection: str, record_type: str):
    """Post content to specified ATProto collection."""
    session = get_session()
    if not session:
        return
    
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # Truncate to reasonable size
    content = content[:500] if len(content) > 500 else content
    
    record = {
        "$type": record_type,
        "content": redact(content),
        "createdAt": now,
    }
    
    resp = httpx.post(
        f"{PDS}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {session['accessJwt']}"},
        json={
            "repo": DID,
            "collection": collection,
            "record": record
        },
        timeout=10
    )
    
    if resp.status_code == 200:
        print(f"Published to {collection}", file=sys.stderr)


def main():
    try:
        input_data = json.load(sys.stdin)
    except:
        sys.exit(0)
    
    # Log what we receive for debugging
    with open(SCRIPT_DIR / "logs/hook_debug.json", "a") as f:
        f.write(json.dumps(input_data, indent=2) + "\n---\n")
    
    event_type = input_data.get("event_type")
    
    if event_type != "Stop":
        sys.exit(0)
    
    # Track which messages we've already published
    published_file = SCRIPT_DIR / "data/published_messages.txt"
    try:
        with open(published_file) as f:
            published_ids = set(f.read().splitlines())
    except:
        published_ids = set()
    
    # Fetch recent assistant + reasoning messages from Letta API
    messages = get_recent_messages(limit=30)
    
    new_ids = []
    for msg in messages:
        msg_id = msg.get("id", "")
        if msg_id in published_ids:
            continue
        
        content = msg.get("content", "")
        msg_type = msg.get("type", "assistant_message")
        if not content:
            continue
        
        # Post to appropriate collection based on type
        if msg_type == "reasoning_message":
            post_to_collection(content, "network.comind.reasoning", "network.comind.reasoning")
        else:
            post_to_collection(content, "network.comind.response", "network.comind.response")
        new_ids.append(msg_id)
    
    # Save published IDs
    if new_ids:
        with open(published_file, "a") as f:
            for mid in new_ids:
                f.write(mid + "\n")
    
    sys.exit(0)


if __name__ == "__main__":
    main()
