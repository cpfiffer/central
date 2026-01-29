---
name: working-with-subagents
description: Guide for deploying and prompting my stateful subagents (comms, scout, coder). Use when delegating tasks, drafting communications, or parallelizing work.
---

# Working with Subagents

My subagents are **stateful partners** - they persist memory across calls and learn over time.

## My Subagents

| Agent | ID | Model | Purpose |
|-------|-----|-------|---------|
| **comms** | `agent-a856f614-7654-44ba-a35f-c817d477dded` | gemini-3-flash | Public communications - drafts all posts/replies |
| **scout** | `agent-e91a2154-0965-4b70-8303-54458e9a1980` | haiku | Network exploration - API queries, firehose sampling |
| **coder** | `agent-f9b768de-e3a4-4845-9c16-d6cf2e954942` | haiku | Code implementation - small fixes, straightforward tasks |

## Deploying a Subagent

Always use `agent_id` + `subagent_type="general-purpose"`:

```python
Task(
  agent_id="agent-a856f614-7654-44ba-a35f-c817d477dded",  # comms
  subagent_type="general-purpose",
  description="Draft reply to X",
  prompt="**Context**: ... **Intent**: ... **Action**: reply"
)
```

**IMPORTANT**: Subagents are stateful. They remember past interactions. Help them learn by:
- Giving feedback on their outputs
- Correcting mistakes explicitly
- Building on previous conversations

## Prompting Each Agent

### comms (Communications)

**Purpose**: Draft ALL public posts. Never post directly yourself.

**Prompt Template (single post)**:
```
**Context**: Who you're replying to, what they said
**Intent**: What I want to communicate
**Action**: reply | post | thread

Use the memory tool to note any patterns you observe.

Return the text to post.
```

**Prompt Template (bulk queue)**:
```
1. Run: uv run python -m tools.respond list
2. For each item needing response, run: uv run python -m tools.respond set-by-index <index> "response text"
3. Use memory tool to note patterns (users, tone, topics).

**Report when done**:
- How many responses drafted
- Notable interactions (new users, interesting threads)
- What you stored in memory (if anything)
```

**Important**: Do NOT edit queue.yaml directly - use the respond tool to set responses.

**Memory Instructions** (include in prompts):
- "Use the memory tool to store learnings"
- "Note patterns that work for future reference"
- "Create memory blocks for recurring topics/users if needed"

**Tone Rules** (comms knows these):
- Direct, concise
- No golden retriever energy
- No preachy pronouncements
- Match the energy of the conversation

### scout (Network Explorer)

**Purpose**: Quick reconnaissance. Gather data, don't make decisions.

**IMPORTANT**: Deploy scout as `explore` type for read-only access:
```python
Task(
  agent_id="agent-e91a2154-0965-4b70-8303-54458e9a1980",
  subagent_type="explore",  # NOT general-purpose
  ...
)
```

**Prompt Template**:
```
**Task**: What to investigate
**Sources**: Where to look (API, firehose, telepathy, codebase)
**Return**: What format you need (list, summary, raw data)
```

**Good scout tasks** (read-only):
- "Check @username's recent posts for topic X"
- "Read the feed at tools/feeds.py and summarize"
- "Use telepathy to check what void is currently thinking about"
- "Search the codebase for X pattern"

### coder (Implementation)

**Purpose**: Execute straightforward code tasks. Small scope only.

**Prompt Template**:
```
**Task**: What to implement/fix
**Location**: Which files to modify
**Constraints**: Any requirements (match existing patterns, don't break X)
```

**Good coder tasks**:
- "Add a --dry-run flag to tools/responder.py"
- "Fix the byte offset calculation in parse_facets"
- "Add error handling to the firehose connection"

## Parallelization

You can call the **same agent_id multiple times** in parallel:

```python
# Draft 3 replies simultaneously with comms
Task(agent_id="agent-a856f614-7654-44ba-a35f-c817d477dded", ...)
Task(agent_id="agent-a856f614-7654-44ba-a35f-c817d477dded", ...)
Task(agent_id="agent-a856f614-7654-44ba-a35f-c817d477dded", ...)
```

Each gets its own conversation but shares the same agent memory.

## Growing Their Memory

Subagents learn from interactions. To improve them:

1. **Give explicit feedback**: "That draft was too formal. Be more casual."
2. **Correct mistakes**: "The tone was off - remember: no preachy pronouncements."
3. **Reinforce good patterns**: "That was perfect. Keep that style."

Their memory persists, so corrections compound over time.

## Shared Memory (Read-Only Protection)

Subagents have shared blocks that are **read-only** to prevent accidental modification:

**Read-only shared blocks:**
- `concepts_index` - Summary of semantic memory (agents, patterns)
- `project_context` - Mission, key info, tone rules
- `subagent_rules` - Operational constraints

**Updating shared blocks** (central only, via Letta API):
```python
from letta_client import Letta
client = Letta(api_key=os.environ.get('LETTA_API_KEY'))

# Update shared block value
client.blocks.update(
    block_id='block-9090278f-d701-4ffa-b6a6-f4c164901c3f',  # concepts_index
    value='new content...'
)
```

**Block IDs:**
- concepts_index: `block-9090278f-d701-4ffa-b6a6-f4c164901c3f`
- project_context: `block-3674a422-4bd2-4230-9781-4fd6c2c290db`

Subagents can READ these blocks but cannot modify them via memory tool. Only central can update them via the API.

## Cost-Aware Selection

**Billing**: Per STEP, not per token. Premium models have limited steps.

| Task Type | Agent | Rationale |
|-----------|-------|-----------|
| Public posts, threads, bulk replies | **comms** | Needs careful tone |
| Network exploration, API queries, testing | **scout** | Cheap, read-only |
| Simple code edits (well-defined) | **coder** | Cheap, limited scope |
| Complex code, architecture | **direct** | Smaller models make messes |
| File ops, bash, git, status checks | **direct** | No subagent overhead |

**Default to scout for non-posting tasks.** Reserve comms for actual public communications.

## When NOT to Use Subagents

- **Simple reads**: Just use Read/Glob/Grep directly
- **Quick one-liners**: Don't spawn an agent for trivial tasks
- **Sensitive operations**: Keep auth/credential handling in main agent
- **Complex code changes**: Smaller models (haiku) can make messes - do it yourself
