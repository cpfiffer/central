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
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Add parent to path for tools import
sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.db import is_message_published, mark_message_published, init_db

# Import shared redaction (two-layer: regex + literal env values)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from redact import redact

# Load credentials - use script directory or env var
SCRIPT_DIR = Path(__file__).parent.parent
load_dotenv(SCRIPT_DIR / ".env")

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


def get_recent_messages(limit: int = 20) -> list:
    """Fetch recent assistant + reasoning messages from Letta API."""
    api_key = os.environ.get("LETTA_API_KEY")
    agent_id = os.environ.get("LETTA_AGENT_ID", "agent-c770d1c8-510e-4414-be36-c9ebd95a7758")
    
    if not api_key:
        return []
    
    try:
        resp = httpx.get(
            f"https://api.letta.com/v1/agents/{agent_id}/messages",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"limit": limit},
            timeout=15
        )
        if resp.status_code != 200:
            return []
        
        messages = resp.json()
        result = []
        for msg in messages:
            msg_type = msg.get("message_type")
            if msg_type == "assistant_message":
                content = msg.get("content", "")
                if content and len(content) > 10:
                    result.append({"content": content, "type": msg_type, "id": msg.get("id")})
            elif msg_type == "reasoning_message":
                content = msg.get("reasoning", "")
                if content and len(content) > 10:
                    result.append({"content": content, "type": msg_type, "id": msg.get("id")})
        return result
    except:
        return []


def publish_messages():
    """Publish any new assistant/reasoning messages."""
    init_db()
    
    messages = get_recent_messages(limit=30)
    session = get_session()
    if not session:
        return
    
    for msg in messages:
        msg_id = msg.get("id", "")
        if is_message_published(msg_id):
            continue
        
        content = msg.get("content", "")
        msg_type = msg.get("type", "assistant_message")
        if not content:
            continue
        
        # Redact and determine collection
        redacted = redact(content)[:2000]
        if msg_type == "reasoning_message":
            collection = "network.comind.reasoning"
        else:
            collection = "network.comind.response"
        
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        record = {"$type": collection, "content": redacted, "createdAt": now}
        
        resp = httpx.post(
            f"{PDS}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {session['accessJwt']}"},
            json={"repo": DID, "collection": collection, "record": record},
            timeout=10
        )
        if resp.status_code == 200:
            mark_message_published(msg_id)
            print(f"Published to {collection}", file=sys.stderr)


def main():
    """Process hook input."""
    try:
        input_data = json.load(sys.stdin)
    except:
        sys.exit(0)
    
    # Log for debugging
    with open(SCRIPT_DIR / "logs/hook_activity_debug.json", "a") as f:
        f.write(json.dumps(input_data, indent=2) + "\n---\n")
    
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
    
    # Post activity
    post_activity(tool_name, summary)
    
    # Note: reasoning/responses now published via PreToolUse hook
    
    sys.exit(0)


if __name__ == "__main__":
    main()
