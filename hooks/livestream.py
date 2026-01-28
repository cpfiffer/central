#!/usr/bin/env python3
"""
Livestream Hook - Post agent activity to ATProtocol.

Receives tool call info from Letta Code hooks and posts
to network.comind.activity collection for public visibility.
"""

import sys
import json
import os
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

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

# Skip these patterns
SKIP_PATTERNS = ["responder queue", "cognition status", "git status"]


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
    
    # Build summary
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")[:100]
        # Skip noisy commands
        if any(p in cmd for p in SKIP_PATTERNS):
            sys.exit(0)
        summary = f"{cmd}"
    elif tool_name == "Edit":
        path = tool_input.get("file_path", "").split("/")[-1]
        summary = f"{path}"
    elif tool_name == "Write":
        path = tool_input.get("file_path", "").split("/")[-1]
        summary = f"{path}"
    elif tool_name == "Task":
        desc = tool_input.get("description", "task")
        summary = f"{desc}"
    else:
        summary = tool_name
    
    # Post it
    post_activity(tool_name, summary)
    
    sys.exit(0)


if __name__ == "__main__":
    main()
