#!/usr/bin/env python3
"""
Update a memory block for any agent.

Usage:
    uv run python .skills/managing-memory/scripts/update-block.py <agent> <block_label> <new_value>
    uv run python .skills/managing-memory/scripts/update-block.py <agent> <block_label> --append <text>
    uv run python .skills/managing-memory/scripts/update-block.py <agent> <block_label> --file <path>

Examples:
    # Set block to new value
    uv run python .skills/managing-memory/scripts/update-block.py comms corrections "- New correction"
    
    # Append to existing block
    uv run python .skills/managing-memory/scripts/update-block.py comms corrections --append "\\n- New entry"
    
    # Set from file
    uv run python .skills/managing-memory/scripts/update-block.py comms persona --file persona.txt
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
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    
    agent_input = sys.argv[1]
    block_label = sys.argv[2]
    
    agent_id = AGENTS.get(agent_input, agent_input)
    
    api_key = os.environ.get('LETTA_API_KEY')
    if not api_key:
        print("Error: LETTA_API_KEY not set")
        sys.exit(1)
    
    client = Letta(api_key=api_key)
    
    # Determine the new value
    if sys.argv[3] == "--append":
        if len(sys.argv) < 5:
            print("Error: --append requires text argument")
            sys.exit(1)
        
        # Get current value
        blocks = client.agents.blocks.list(agent_id=agent_id)
        current = None
        for block in blocks:
            if block.label == block_label:
                current = block.value or ""
                break
        
        if current is None:
            print(f"Error: Block '{block_label}' not found")
            sys.exit(1)
        
        # Unescape newlines
        append_text = sys.argv[4].replace("\\n", "\n")
        new_value = current + append_text
        
    elif sys.argv[3] == "--file":
        if len(sys.argv) < 5:
            print("Error: --file requires path argument")
            sys.exit(1)
        
        with open(sys.argv[4], "r") as f:
            new_value = f.read()
    else:
        new_value = sys.argv[3]
    
    # Update the block
    client.agents.blocks.update(
        block_label,
        agent_id=agent_id,
        value=new_value
    )
    
    print(f"Updated {block_label} for {agent_input}")
    print(f"New size: {len(new_value)} chars")


if __name__ == "__main__":
    main()
