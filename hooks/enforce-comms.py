#!/usr/bin/env python3
"""
Enforce comms Delegation Hook - PreToolUse hook that blocks central from posting directly.

This hook enforces the architectural pattern where central (the main agent) delegates
all public communications to the comms subagent. When central attempts to run
posting-related commands, this hook blocks them with a helpful redirect message.

Exit codes:
  0 - Allow the action to proceed
  2 - Block the action and send stderr message to the agent
"""

import sys
import json
import os

# Agent IDs
CENTRAL_AGENT_ID = "agent-c770d1c8-510e-4414-be36-c9ebd95a7758"
COMMS_AGENT_ID = "agent-a856f614-7654-44ba-a35f-c817d477dded"

# Patterns in Bash commands that indicate posting activity
# Be specific to avoid blocking read operations
# Note: responder send is ALLOWED (queue-based workflow, content already drafted)
POSTING_PATTERNS = [
    "tools.thread",
    # "tools.devlog",  # Now posts to network.comind.devlog (cognition), not app.bsky.feed.post
    # "tools.responder send",  # Allowed - queue workflow
    # "tools.respond set",  # Allowed - drafting responses
    "agent.py post",
    "tools.blog publish",
    # "tools.cognition write",  # Allowed - internal records, not public communication
    "create_post",
]


def main():
    """Process PreToolUse hook input."""
    # Debug: log that we were called
    print("ENFORCE-COMMS: Hook invoked", file=sys.stderr)
    
    try:
        input_data = json.load(sys.stdin)
        print(f"ENFORCE-COMMS: Got input: {input_data.get('tool_name', 'unknown')}", file=sys.stderr)
    except Exception as e:
        # If we can't parse input, allow the action
        print(f"ENFORCE-COMMS: Parse error: {e}", file=sys.stderr)
        sys.exit(0)

    event_type = input_data.get("event_type")
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Only process PreToolUse events
    if event_type != "PreToolUse":
        sys.exit(0)

    # Only check Bash commands
    if tool_name != "Bash":
        sys.exit(0)

    # Check agent identity - only block central, allow comms
    # NOTE: LETTA_AGENT_ID may not be passed to hooks (see letta-code #729)
    # So we block by default if we can't identify the agent
    agent_id = os.environ.get("LETTA_AGENT_ID", "")
    print(f"ENFORCE-COMMS: Agent ID: '{agent_id}'", file=sys.stderr)
    
    # Allow comms to post directly (only if we can positively identify it)
    if agent_id == COMMS_AGENT_ID:
        print("ENFORCE-COMMS: Comms agent - allowing", file=sys.stderr)
        sys.exit(0)
    
    # Block if unknown OR if central (fail closed, not open)
    # This ensures direct posting is blocked even if LETTA_AGENT_ID isn't passed

    # Get the command being run
    command = tool_input.get("command", "")
    print(f"ENFORCE-COMMS: Command: {command[:100]}", file=sys.stderr)

    # Check if command matches any posting pattern
    for pattern in POSTING_PATTERNS:
        if pattern in command.lower():
            # Block the action with a helpful message
            message = f"""BLOCKED: Direct posting not allowed for central agent.

You attempted to run a posting command directly:
  {command[:100]}{'...' if len(command) > 100 else ''}

Per architectural rules, central must delegate all public communications to comms.

To post content, use the comms subagent:
  Task(
    agent_id="{COMMS_AGENT_ID}",
    subagent_type="general-purpose",
    prompt="Post the following: <your content>"
  )

If comms fails, message comms directly to debug/retry. Do NOT bypass by posting directly.
"""
            print(message, file=sys.stderr)
            sys.exit(2)

    # No posting pattern detected, allow the command
    sys.exit(0)


if __name__ == "__main__":
    main()
