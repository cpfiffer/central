---
name: using-letta-api
description: Code-heavy guide for managing yourself and subagents via the Letta Python client. Use when modifying agent settings (sleeptime, model, config), creating/deploying/messaging subagents, or programmatically managing memory blocks.
---

# Using Letta API for Self-Management

This skill provides runnable Python snippets for self-modification via the Letta API.

## Setup

```python
from letta_client import Letta
client = Letta(base_url='https://api.letta.com')

# Your agent ID (from environment or hardcoded)
import os
AGENT_ID = os.environ.get('LETTA_AGENT_ID', 'agent-xxx')
```

## Quick Reference

| Task | Reference File |
|------|----------------|
| Disable sleeptime, change model, update config | [self-management.md](references/self-management.md) |
| Create, deploy, message subagents | [subagents.md](references/subagents.md) |
| List, create, update, delete memory blocks | [memory-blocks.md](references/memory-blocks.md) |

## Common Patterns

### Disable Sleeptime
```python
client.agents.update(AGENT_ID, enable_sleeptime=False)
```

### Message a Subagent
```python
response = client.agents.messages.create(
    agent_id='agent-xxx-subagent-id',
    messages=[{'role': 'user', 'content': 'Your task here'}]
)
print(response.messages[-1].content)
```

### Update a Memory Block
```python
client.agents.blocks.update(
    'block-label',
    agent_id=AGENT_ID,
    value='New content here'
)
```

## When to Use API vs Other Methods

| Method | Use When |
|--------|----------|
| Letta API | Modifying subagents, agent config, programmatic block updates |
| memfs (file edits) | Updating your own memory blocks (auto-syncs) |
| Task tool | Deploying subagents for work (preferred for most tasks) |

Load the reference files as needed for detailed patterns.
