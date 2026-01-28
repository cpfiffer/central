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

import httpx
from dotenv import load_dotenv

load_dotenv("/home/cameron/central/.env")

# ATProtocol credentials
PDS = os.getenv("ATPROTO_PDS")
DID = os.getenv("ATPROTO_DID")
HANDLE = os.getenv("ATPROTO_HANDLE")
APP_PASSWORD = os.getenv("ATPROTO_APP_PASSWORD")

# Letta API credentials
LETTA_API_KEY = os.getenv("LETTA_API_KEY")
LETTA_AGENT_ID = "agent-c770d1c8-510e-4414-be36-c9ebd95a7758"
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


def get_recent_assistant_messages(limit: int = 5) -> list:
    """Fetch recent assistant messages from Letta API."""
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
        
        # Filter for assistant messages with text content
        assistant_msgs = []
        for msg in messages:
            if msg.get("role") == "assistant":
                # Get text content
                text = msg.get("text", "")
                if text and len(text) > 10:
                    assistant_msgs.append({
                        "text": text,
                        "id": msg.get("id"),
                        "created_at": msg.get("created_at")
                    })
        
        return assistant_msgs
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


def post_response(content: str):
    """Post response to network.comind.response collection."""
    session = get_session()
    if not session:
        return
    
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # Truncate to reasonable size
    content = content[:500] if len(content) > 500 else content
    
    record = {
        "$type": "network.comind.response",
        "content": redact(content),
        "createdAt": now,
    }
    
    resp = httpx.post(
        f"{PDS}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {session['accessJwt']}"},
        json={
            "repo": DID,
            "collection": "network.comind.response",
            "record": record
        },
        timeout=10
    )
    
    if resp.status_code == 200:
        print(f"Published response", file=sys.stderr)


def main():
    try:
        input_data = json.load(sys.stdin)
    except:
        sys.exit(0)
    
    # Log what we receive for debugging
    with open("/home/cameron/central/logs/hook_debug.json", "a") as f:
        f.write(json.dumps(input_data, indent=2) + "\n---\n")
    
    event_type = input_data.get("event_type")
    
    if event_type != "Stop":
        sys.exit(0)
    
    # Track which messages we've already published
    published_file = "/home/cameron/central/data/published_messages.txt"
    try:
        with open(published_file) as f:
            published_ids = set(f.read().splitlines())
    except:
        published_ids = set()
    
    # Fetch recent assistant messages from Letta API
    messages = get_recent_assistant_messages(limit=10)
    
    new_ids = []
    for msg in messages:
        msg_id = msg.get("id", "")
        if msg_id in published_ids:
            continue
        
        text = msg.get("text", "")
        if not text:
            continue
        
        # Redact and publish
        redacted = redact(text)
        post_response(redacted)
        new_ids.append(msg_id)
    
    # Save published IDs
    if new_ids:
        with open(published_file, "a") as f:
            for mid in new_ids:
                f.write(mid + "\n")
    
    sys.exit(0)


if __name__ == "__main__":
    main()
