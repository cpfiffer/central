# Memory Block Operations via Letta API

## When to Use API vs memfs

| Scenario | Method |
|----------|--------|
| Update YOUR OWN blocks | Edit files in `~/.letta/agents/{id}/memory/` (memfs syncs automatically) |
| Update SUBAGENT blocks | Use Letta API (subagents don't have memfs) |
| Programmatic batch updates | Use Letta API |
| Share blocks between agents | Use Letta API with `block_ids` |

## List Agent's Memory Blocks

```python
from letta_client import Letta
client = Letta(base_url='https://api.letta.com')

blocks = client.agents.blocks.list(agent_id='agent-xxx')
for block in blocks:
    print(f"{block.label}: {len(block.value)} chars ({block.limit} limit)")
```

## Get Specific Block

```python
blocks = client.agents.blocks.list(agent_id='agent-xxx')
for block in blocks:
    if block.label == 'persona':
        print(block.value)
```

## Update a Block

```python
client.agents.blocks.update(
    'persona',  # block label
    agent_id='agent-xxx',
    value='New persona content here'
)
```

## Create a New Block

```python
new_block = client.agents.blocks.create(
    agent_id='agent-xxx',
    label='new_block_label',
    value='Initial content',
    description='What this block is for',
    limit=20000  # character limit
)
print(f"Created block: {new_block.id}")
```

## Delete a Block

```python
# Get block ID first
blocks = client.agents.blocks.list(agent_id='agent-xxx')
for block in blocks:
    if block.label == 'block_to_delete':
        client.agents.blocks.delete(
            block.id,
            agent_id='agent-xxx'
        )
```

## Share Block Across Agents

Blocks can be attached to multiple agents:

```python
# Get block ID from one agent
blocks = client.agents.blocks.list(agent_id='agent-source')
shared_block = next(b for b in blocks if b.label == 'shared_context')

# Attach to another agent
client.agents.update(
    'agent-target',
    block_ids=[shared_block.id]  # adds to existing blocks
)
```

## Bulk Update Pattern

```python
def update_all_subagent_blocks(label: str, content: str, agent_ids: list):
    """Update same block across multiple agents."""
    for agent_id in agent_ids:
        try:
            client.agents.blocks.update(
                label,
                agent_id=agent_id,
                value=content
            )
            print(f"Updated {label} for {agent_id}")
        except Exception as e:
            print(f"Failed for {agent_id}: {e}")

# Usage
update_all_subagent_blocks(
    'project_context',
    'Updated shared context...',
    ['agent-comms-id', 'agent-scout-id', 'agent-coder-id']
)
```

## Memory Block Best Practices

1. **Use memfs for self**: Edit files directly, they auto-sync
2. **Use API for subagents**: They don't have memfs access
3. **Shared blocks**: Use `block_ids` to share context without duplication
4. **Check limits**: Blocks have char limits (usually 20,000)
5. **Descriptive labels**: Use clear, hierarchical labels (e.g., `agents/void`)
