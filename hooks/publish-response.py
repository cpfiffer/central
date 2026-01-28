#!/usr/bin/env python3
"""
Publish Response Hook - Post assistant messages to ATProtocol.

Fires on Stop event, publishes what I said to network.comind.response
"""

import sys
import json
import os
import re
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv("/home/cameron/central/.env")

PDS = os.getenv("ATPROTO_PDS")
DID = os.getenv("ATPROTO_DID")
HANDLE = os.getenv("ATPROTO_HANDLE")
APP_PASSWORD = os.getenv("ATPROTO_APP_PASSWORD")

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
    
    # Stop hook only provides metadata, not actual response text
    stop_reason = input_data.get("stop_reason", "unknown")
    message_count = input_data.get("message_count", 0)
    tool_call_count = input_data.get("tool_call_count", 0)
    
    # Build summary from metadata
    summary = f"Turn complete: {tool_call_count} tools, {message_count} messages"
    
    post_response(summary)
    sys.exit(0)


if __name__ == "__main__":
    main()
