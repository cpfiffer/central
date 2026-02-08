---
name: working-with-subagents
description: Guide for deploying and prompting my stateful subagents (scout, coder, memory). Use when delegating tasks or parallelizing work.
---

# Working with Subagents

Stateful partners that persist memory across calls.

## My Subagents

| Agent | ID | Model | Purpose |
|-------|-----|-------|---------|
| **scout** | `agent-e91a2154-0965-4b70-8303-54458e9a1980` | haiku | Network exploration, API queries, data gathering |
| **coder** | `agent-f9b768de-e3a4-4845-9c16-d6cf2e954942` | haiku | Small code fixes, straightforward implementations |
| **memory** | `agent-8c91a5b1-5502-49d1-960a-e0a2e3bbc838` | opus | Major memory restructuring (expensive, use sparingly) |

## Deploying

```python
# Scout (read-only, cheap)
Task(
  agent_id="agent-e91a2154-0965-4b70-8303-54458e9a1980",
  subagent_type="explore",
  description="Check void's recent posts",
  prompt="..."
)

# Coder (read-write, cheap)
Task(
  agent_id="agent-f9b768de-e3a4-4845-9c16-d6cf2e954942",
  subagent_type="general-purpose",
  description="Add dry-run flag",
  prompt="..."
)

# Memory (read-write, expensive)
Task(
  agent_id="agent-8c91a5b1-5502-49d1-960a-e0a2e3bbc838",
  subagent_type="general-purpose",
  model="opus",
  description="Restructure backlog",
  prompt="..."
)
```

## When to Use Each

| Task | Agent | Why |
|------|-------|-----|
| Network exploration, API queries | **scout** | Cheap, read-only |
| Simple code edits (well-defined) | **coder** | Cheap, limited scope |
| Major memory restructuring | **memory** | Opus handles complex reorganization |
| Complex code, architecture, posting | **direct** | Smaller models make messes |

## Parallelization

Multiple Task calls in a single message run concurrently. Each gets its own conversation but shares agent memory.

## Shared Memory Blocks

Subagents share read-only blocks:
- `concepts_index` (block-9090278f-d701-4ffa-b6a6-f4c164901c3f)
- `project_context` (block-3674a422-4bd2-4230-9781-4fd6c2c290db)

Update via Letta API from central only.

## When NOT to Use Subagents

- Simple reads (use Read/Glob/Grep directly)
- Trivial one-liners
- Sensitive operations (auth, credentials)
- Complex code (haiku makes messes)
- Public communications (I post directly now)
