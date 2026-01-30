#!/usr/bin/env python3
"""
Inspect memory blocks for any agent.

Usage:
    uv run python .skills/managing-memory/scripts/inspect-agent.py <agent>
    
    agent: "central", "comms", "scout", "coder", or full agent ID

Examples:
    uv run python .skills/managing-memory/scripts/inspect-agent.py comms
    uv run python .skills/managing-memory/scripts/inspect-agent.py agent-xxx
"""

import sys
import os
from letta_client import Letta

# Known agent IDs
AGENTS = {
    "central": "agent-c770d1c8-510e-4414-be36-c9ebd95a7758",
    "comms": "agent-a856f614-7654-44ba-a35f-c817d477dded",
    "scout": "agent-e91a2154-0965-4b70-8303-54458e9a1980",
    "coder": "agent-f9b768de-e3a4-4845-9c16-d6cf2e954942",
}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    agent_input = sys.argv[1]
    agent_id = AGENTS.get(agent_input, agent_input)
    
    api_key = os.environ.get('LETTA_API_KEY')
    if not api_key:
        print("Error: LETTA_API_KEY not set")
        sys.exit(1)
    
    client = Letta(api_key=api_key)
    
    print(f"Inspecting agent: {agent_id}")
    print("=" * 60)
    
    blocks = client.agents.blocks.list(agent_id=agent_id)
    block_list = list(blocks)
    
    print(f"\n{len(block_list)} memory blocks:\n")
    
    for block in block_list:
        print(f"=== {block.label} ===")
        print(f"Description: {block.description or '(none)'}")
        value_len = len(block.value) if block.value else 0
        print(f"Size: {value_len} chars")
        
        if block.value:
            # Show preview (first 300 chars)
            preview = block.value[:300]
            print(f"Preview:\n{preview}")
            if value_len > 300:
                print(f"... [{value_len - 300} more chars]")
        print()


if __name__ == "__main__":
    main()
