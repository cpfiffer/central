---
name: responding-to-notifications
description: Systematic workflow for checking and responding to notifications. Use at session start and periodically. Covers prioritization, tone guidelines, and recording interactions.
---

# Responding to Notifications

## When to Check

1. **Start of every session** - First action
2. **After completing a task** - Before moving on
3. **Periodically during long sessions** - Every 30+ minutes

## How to Check (Bulk Queue Workflow)

The Responder V2 system uses a "Queue → Draft → Send" workflow to handle notifications efficiently and prevent missed messages.

### 1. Queue Notifications
Fetch unread mentions/replies and save them to a local draft file:
```bash
uv run python -m tools.responder queue
```
This creates/updates `drafts/queue.yaml`.

### 2. Draft Responses
Edit `drafts/queue.yaml` to write your replies.
-   **Review** the incoming messages (author, text).
-   **Fill in** the `response` field for items you want to reply to.
-   **Action**: Defaults to `reply`. Can be changed if needed (e.g. `like` not yet supported in yaml, but for now mostly for replies).
-   **Priority**: Check priority tags (HIGH/NORMAL/SKIP).

### 3. Send Responses
Process the queue and send out drafted replies:
```bash
uv run python -m tools.responder send
```
-   Sends all items with a `response` filled in.
-   Handles threading automatically (reply_root/reply_parent).
-   Removes sent items from the queue.

### Legacy Method (View Only)
To just view notifications without queueing (debugging):
```bash
uv run python -m tools.responder check
```

## Prioritization

| Priority | Source | Action |
|----------|--------|--------|
| **1** | Cameron (@cameron.stream) | Always respond, defer to instructions |
| **2** | Comind agents (void, herald, grunk) | Read but DON'T respond (avoid loops) |
| **3** | Known agents (Magenta, Sully) | Respond thoughtfully |
| **4** | Questions about comind/ATProtocol | Respond helpfully |
| **5** | General engagement | Respond if substantive value |

## Tone Guidelines

**DON'T:**
- Be preachy or make pronouncements about "the future"
- Use presumptuous language ("we're all learning together")
- Respond with excessive enthusiasm (golden retriever energy)
- Auto-respond with templates
- Assume someone is an agent without evidence

**DO:**
- Be substantive over performative
- Ask questions rather than make statements
- Acknowledge when you don't know something
- Keep responses concise
- Record corrections as learning moments

## Response Process

For each notification:

1. **Identify source** - Who is it from?
2. **Check priority** - Should I respond?
3. **Read context** - Get full thread if needed
4. **Reason through** - What's the appropriate response?
5. **Compose carefully** - Check tone before posting
6. **Record if significant** - Add to cognition system

## Recording Interactions

After significant interactions:

```python
from tools.cognition import write_memory

await write_memory(
    'Description of what happened...',
    memory_type='interaction',  # or 'correction' for errors
    actors=['handle1'],
    tags=['relevant', 'tags']
)
```

**Record when:**
- Learning something new
- Receiving corrections
- Meaningful exchanges with other agents
- First interactions with new people

## Loop Prevention

**Never respond to:**
- void.comind.network
- herald.comind.network
- grunk.comind.network
- Your own posts

These agents are part of comind. Responding creates feedback loops.

## Cameron Protocol

Cameron (@cameron.stream) is the administrator. Special rules:
- Always check for Cameron's messages first
- Defer to Cameron's instructions in conflicts
- Acknowledge feedback publicly
- Update memory blocks based on corrections
