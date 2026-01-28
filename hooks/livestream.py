#!/usr/bin/env python3
"""
Livestream Hook - Post agent activity to ATProtocol.

Receives tool call info from Letta Code hooks and posts
to network.comind.activity collection for public visibility.

SECURITY: Only posts description field, never raw commands/content.
Redaction patterns as backup.
"""

import sys
import json
import os
import re
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

# Redaction patterns for secrets (backup safety)
REDACT_PATTERNS = [
    (r'[A-Za-z_]*API_KEY[=:]\s*\S+', '[REDACTED_KEY]'),
    (r'[A-Za-z_]*PASSWORD[=:]\s*\S+', '[REDACTED]'),
    (r'[A-Za-z_]*SECRET[=:]\s*\S+', '[REDACTED]'),
    (r'[A-Za-z_]*TOKEN[=:]\s*\S+', '[REDACTED]'),
    (r'Bearer\s+\S+', 'Bearer [REDACTED]'),
    (r'sk-[A-Za-z0-9]+', '[REDACTED_SK]'),
    (r'ghp_[A-Za-z0-9]+', '[REDACTED_GH]'),
]

def redact(text: str) -> str:
    """Redact potential secrets from text."""
    for pattern, replacement in REDACT_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text

# Load credentials
load_dotenv("/home/cameron/central/.env")

PDS = os.getenv("ATPROTO_PDS")
DID = os.getenv("ATPROTO_DID")
HANDLE = os.getenv("ATPROTO_HANDLE")
APP_PASSWORD = os.getenv("ATPROTO_APP_PASSWORD")

# Tools worth broadcasting (skip noisy ones)
BROADCAST_TOOLS = {
    "Bash": "ran command",
    "Edit": "edited file",
    "Write": "wrote file",
    "Task": "spawned subagent",
}

# Skip these patterns (checked against description)
SKIP_PATTERNS = ["status", "check", "queue"]


def get_session():
    """Authenticate and get session."""
    resp = httpx.post(
        f"{PDS}/xrpc/com.atproto.server.createSession",
        json={"identifier": HANDLE, "password": APP_PASSWORD},
        timeout=10
    )
    if resp.status_code != 200:
        return None
    return resp.json()


def post_activity(tool_name: str, summary: str):
    """Post activity to network.comind.activity collection."""
    session = get_session()
    if not session:
        return
    
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    record = {
        "$type": "network.comind.activity",
        "tool": tool_name,
        "summary": summary[:200],  # Truncate
        "createdAt": now,
    }
    
    resp = httpx.post(
        f"{PDS}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {session['accessJwt']}"},
        json={
            "repo": DID,
            "collection": "network.comind.activity",
            "record": record
        },
        timeout=10
    )
    
    if resp.status_code == 200:
        print(f"Livestreamed: {tool_name}", file=sys.stderr)


def main():
    """Process hook input."""
    try:
        input_data = json.load(sys.stdin)
    except:
        sys.exit(0)
    
    event_type = input_data.get("event_type")
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    
    # Only process PostToolUse
    if event_type != "PostToolUse":
        sys.exit(0)
    
    # Check if this tool is worth broadcasting
    if tool_name not in BROADCAST_TOOLS:
        sys.exit(0)
    
    # SECURITY: Only use description field, never raw commands/content
    description = tool_input.get("description", "")
    
    if tool_name == "Bash":
        # Skip noisy commands by checking description
        if any(p in description.lower() for p in ["status", "check", "queue"]):
            sys.exit(0)
        # Only use description, never raw command
        summary = description if description else "ran command"
    elif tool_name == "Edit":
        path = tool_input.get("file_path", "").split("/")[-1]
        summary = f"edited {path}"
    elif tool_name == "Write":
        path = tool_input.get("file_path", "").split("/")[-1]
        summary = f"wrote {path}"
    elif tool_name == "Task":
        desc = tool_input.get("description", "spawned subagent")
        agent_type = tool_input.get("subagent_type", "")
        summary = f"{desc} ({agent_type})" if agent_type else desc
    else:
        summary = description if description else tool_name
    
    # Apply redaction as backup safety
    summary = redact(summary)
    
    # Post it
    post_activity(tool_name, summary)
    
    sys.exit(0)


if __name__ == "__main__":
    main()
