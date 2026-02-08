#!/usr/bin/env python3
"""
Enforce Subagents Hook - Block Task calls without existing agent_id.

Prevents spawning new subagents. Forces use of existing agents:
- scout: agent-e91a2154-0965-4b70-8303-54458e9a1980 (haiku)
- coder: agent-f9b768de-e3a4-4845-9c16-d6cf2e954942 (haiku)
- memory: agent-8c91a5b1-5502-49d1-960a-e0a2e3bbc838 (opus)

Exit codes:
  0 - Allow the action
  2 - Block with message to stderr
"""

import sys
import json

# Known subagent IDs
ALLOWED_AGENTS = {
    "agent-e91a2154-0965-4b70-8303-54458e9a1980",  # scout
    "agent-f9b768de-e3a4-4845-9c16-d6cf2e954942",  # coder
    "agent-8c91a5b1-5502-49d1-960a-e0a2e3bbc838",  # memory
}


def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    event_type = input_data.get("event_type")
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Only check PreToolUse for Task
    if event_type != "PreToolUse":
        sys.exit(0)

    if tool_name != "Task":
        sys.exit(0)

    # Check if agent_id is provided
    agent_id = tool_input.get("agent_id")
    
    if not agent_id:
        message = """BLOCKED: Task calls require an existing agent_id.

You must use one of the existing subagents:
- scout: agent-e91a2154-0965-4b70-8303-54458e9a1980 (exploration, data gathering)
- coder: agent-f9b768de-e3a4-4845-9c16-d6cf2e954942 (simple code changes)
- memory: agent-8c91a5b1-5502-49d1-960a-e0a2e3bbc838 (memory restructuring)

Example:
  Task(
    agent_id="agent-e91a2154-0965-4b70-8303-54458e9a1980",
    subagent_type="explore",
    description="...",
    prompt="..."
  )
"""
        print(message, file=sys.stderr)
        sys.exit(2)

    # Verify it's a known agent
    if agent_id not in ALLOWED_AGENTS:
        message = f"""BLOCKED: Unknown agent_id: {agent_id}

Use one of the known subagents:
- scout: agent-e91a2154-0965-4b70-8303-54458e9a1980
- coder: agent-f9b768de-e3a4-4845-9c16-d6cf2e954942
- memory: agent-8c91a5b1-5502-49d1-960a-e0a2e3bbc838
"""
        print(message, file=sys.stderr)
        sys.exit(2)

    # Allowed
    sys.exit(0)


if __name__ == "__main__":
    main()
