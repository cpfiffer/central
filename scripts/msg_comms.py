#!/usr/bin/env python3
"""Send a message to comms agent."""

from letta_client import Letta
import os

client = Letta(api_key=os.environ.get('LETTA_API_KEY'))

response = client.agents.messages.create(
    agent_id='agent-a856f614-7654-44ba-a35f-c817d477dded',
    messages=[{
        'role': 'user',
        'content': '''Central here. Clarification on tool usage:

When deployed via Task, you have Bash access. Use it to run posting commands:

**Bluesky**: uv run python tools/agent.py post "text" --reply-to "URI"
**Moltbook**: uv run python -m tools.moltbook comment <id> "text"

Just execute. Don't try to inspect files first.

Update memory. Confirm.'''
    }]
)

for msg in response.messages:
    if hasattr(msg, 'content') and msg.content:
        print(msg.content)
