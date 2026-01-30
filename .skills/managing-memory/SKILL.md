---
name: managing-memory
description: Guide for managing agent memory blocks. Use when inspecting, updating, or creating memory blocks for yourself or subagents. Covers the memory tool (self), Letta API (subagents), and common patterns.
---

# Managing Agent Memory

Memory blocks are the foundation of agent state. This skill covers how to inspect, update, and create blocks for yourself and your subagents.

## When to Use

- Inspecting your own memory blocks
- Viewing subagent memory (comms, scout, coder)
- Training subagents via memory modifications
- Creating new blocks for specific purposes
- Debugging memory-related issues

## Two Methods

### 1. Memory Tool (Self Only)

For your own blocks, use the built-in `memory` tool:

```python
# View current blocks - they're in your system prompt
# No tool needed, just read them

# Update a block
memory(command="str_replace", path="/procedures", 
       old_string="old text", new_string="new text")

# Insert at line
memory(command="insert", path="/backlog", 
       insert_line=5, insert_text="- [ ] New task")

# Create new block
memory(command="create", path="/new_block",
       description="What this block is for",
       file_text="Initial content")

# Delete block
memory(command="delete", path="/old_block")
```

### 2. Letta API (Self + Subagents)

For subagents or programmatic access:

```python
from letta_client import Letta
import os

client = Letta(api_key=os.environ.get('LETTA_API_KEY'))
agent_id = "agent-xxx"  # Target agent

# List all blocks
blocks = client.agents.blocks.list(agent_id=agent_id)
for block in blocks:
    print(f"{block.label}: {len(block.value)} chars")

# Update a block (by label)
client.agents.blocks.update(
    "block_label",
    agent_id=agent_id,
    value="new content"
)

# Create a block
client.agents.blocks.create(
    agent_id=agent_id,
    label="new_block",
    value="content",
    description="What this block is for"
)
```

## Agent IDs

| Agent | ID |
|-------|-----|
| central (me) | `agent-c770d1c8-510e-4414-be36-c9ebd95a7758` |
| comms | `agent-a856f614-7654-44ba-a35f-c817d477dded` |
| scout | `agent-e91a2154-0965-4b70-8303-54458e9a1980` |
| coder | `agent-f9b768de-e3a4-4845-9c16-d6cf2e954942` |

## Common Patterns

### Inspecting Subagent Memory
```bash
uv run python .skills/managing-memory/scripts/inspect-agent.py comms
```

### Adding a Correction
When a subagent makes a mistake, add to their corrections block:
```python
current = get_block("corrections")
new_entry = "\n- 2026-01-30: Description of mistake and fix"
client.agents.blocks.update("corrections", agent_id=X, value=current + new_entry)
```

### Training Subagent Behavior
Update policy blocks to change behavior:
- `comms_policies` - Execution rules for comms
- `communication_style` - Voice and tone rules
- `subagent_rules` - Operational constraints

### Shared vs Agent-Specific Blocks

**Shared blocks** (all subagents see):
- `concepts_index` - Semantic memory summary
- `project_context` - Mission and infrastructure

**Agent-specific blocks**:
- `persona` - Who the agent is
- `corrections` - Learned behaviors
- `*_policies` - Execution rules

## Scripts

- `scripts/inspect-agent.py` - View all blocks for an agent
- `scripts/update-block.py` - Update a specific block

## Best Practices

1. **Don't over-modify** - Small targeted updates beat wholesale rewrites
2. **Log corrections** - When fixing mistakes, add to corrections block
3. **Keep blocks focused** - One purpose per block
4. **Check before update** - Always inspect current value first
