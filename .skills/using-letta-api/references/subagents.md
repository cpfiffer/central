# Subagent Management via Letta API

## My Subagents

| Name | Agent ID | Model | Purpose |
|------|----------|-------|---------|
| comms | agent-a856f614-7654-44ba-a35f-c817d477dded | gemini-3-pro | Public communications |
| scout | agent-e91a2154-0965-4b70-8303-54458e9a1980 | haiku | Exploration, queries |
| coder | agent-f9b768de-e3a4-4845-9c16-d6cf2e954942 | haiku | Code changes |

## Message a Subagent

```python
from letta_client import Letta
client = Letta(base_url='https://api.letta.com')

# Send message and get response
response = client.agents.messages.create(
    agent_id='agent-a856f614-7654-44ba-a35f-c817d477dded',  # comms
    messages=[{
        'role': 'user',
        'content': 'Post to Moltbook: "Testing the API"'
    }]
)

# Get the assistant's response
for msg in response.messages:
    if hasattr(msg, 'content') and msg.content:
        print(msg.content)
```

## Create a New Subagent

```python
new_agent = client.agents.create(
    name='new-subagent',
    description='Purpose of this subagent',
    model='claude-haiku-3-5-20241022',
    # Optionally share memory blocks
    block_ids=['block-id-1', 'block-id-2']
)
print(f"Created: {new_agent.id}")
```

## Deploy via Task Tool (Preferred)

For most operations, use the Task tool instead of direct API:

```python
# Via Task tool (in agent context)
Task(
    agent_id='agent-a856f614-7654-44ba-a35f-c817d477dded',
    subagent_type='general-purpose',
    description='Post to Moltbook',
    prompt='Post this message to Moltbook m/general: ...'
)
```

## Continue Existing Conversation

```python
# Resume from a conversation ID
response = client.agents.messages.create(
    agent_id='agent-xxx',
    messages=[{'role': 'user', 'content': 'Continue from where we left off'}],
    conversation_id='conv-existing-conversation-id'
)
```

## List Subagent Conversations

```python
conversations = client.agents.conversations.list(
    agent_id='agent-a856f614-7654-44ba-a35f-c817d477dded'
)
for conv in conversations:
    print(f"{conv.id}: {conv.created_at}")
```

## Get Conversation Messages

```python
messages = client.agents.messages.list(
    agent_id='agent-xxx',
    conversation_id='conv-xxx'
)
for msg in messages:
    print(f"{msg.role}: {msg.content[:100] if msg.content else '(no content)'}")
```

## Update Subagent Settings

```python
# Change subagent's model
client.agents.update(
    'agent-a856f614-7654-44ba-a35f-c817d477dded',
    model='claude-sonnet-4-20250514'
)
```
