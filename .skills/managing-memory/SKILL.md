---
name: managing-memory
description: Guide for managing agent memory blocks. Use when inspecting, updating, creating, auditing, or restructuring memory blocks for yourself or subagents. Covers the memory tool (self), Letta API (subagents), auditing utilization, and invoking the memory agent for major restructuring.
---

# Managing Agent Memory

Memory blocks are the foundation of agent state. This skill covers inspection, editing, auditing, and restructuring.

## When to Use

- Inspecting or updating your own memory blocks
- Viewing/modifying subagent memory (scout, coder)
- Auditing memory utilization
- Invoking the memory agent for major restructuring
- Creating new blocks or deleting old ones

## Two Methods

### 1. Memory Filesystem (Self, Preferred)

Edit blocks as markdown files:

```
~/.letta/agents/agent-c770d1c8-510e-4414-be36-c9ebd95a7758/memory/system/
```

Read and Edit tools work directly on these files. Changes sync automatically.

### 2. Letta API (Subagents)

```python
from letta_client import Letta
client = Letta(api_key=os.environ.get('LETTA_API_KEY'))

# List blocks
blocks = client.agents.blocks.list(agent_id="agent-xxx")

# Update
client.agents.blocks.update("label", agent_id="agent-xxx", value="new content")

# Create
client.agents.blocks.create(agent_id="agent-xxx", label="new", value="content", description="purpose")
```

## Agent IDs

| Agent | ID |
|-------|-----|
| central (me) | `agent-c770d1c8-510e-4414-be36-c9ebd95a7758` |
| scout | `agent-e91a2154-0965-4b70-8303-54458e9a1980` |
| coder | `agent-f9b768de-e3a4-4845-9c16-d6cf2e954942` |
| memory | `agent-8c91a5b1-5502-49d1-960a-e0a2e3bbc838` |

## Auditing Utilization

```bash
cd ~/.letta/agents/agent-c770d1c8-510e-4414-be36-c9ebd95a7758/memory/system
for f in *.md agents/*.md; do
    chars=$(wc -c < "$f" 2>/dev/null || echo 0)
    pct=$((chars * 100 / 20000))
    printf "%-25s %5d chars (%2d%%)\n" "$f" "$chars" "$pct"
done | sort -t'(' -k2 -rn
```

## Invoking Memory Agent

For major restructuring (not routine edits):

```
Task(agent_id="agent-8c91a5b1-5502-49d1-960a-e0a2e3bbc838", subagent_type="general-purpose", model="opus", description="Restructure [area]", prompt="...")
```

## Best Practices

1. Small targeted updates beat wholesale rewrites
2. One purpose per block
3. Check current value before updating
4. Archive completed items, don't just accumulate
5. Defrag every session, not weekly
