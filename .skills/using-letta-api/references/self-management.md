# Self-Management via Letta API

## Agent Update Operations

### Retrieve Current Agent State
```python
from letta_client import Letta
client = Letta(base_url='https://api.letta.com')

agent = client.agents.retrieve('agent-c770d1c8-510e-4414-be36-c9ebd95a7758')
print(f"Name: {agent.name}")
print(f"Model: {agent.llm_config.model}")
```

### Disable Sleeptime
```python
client.agents.update(
    'agent-c770d1c8-510e-4414-be36-c9ebd95a7758',
    enable_sleeptime=False
)
```

### Change Model
```python
client.agents.update(
    AGENT_ID,
    model='claude-sonnet-4-20250514'
)
```

### Update Description
```python
client.agents.update(
    AGENT_ID,
    description='New agent description here'
)
```

### Update Metadata
```python
client.agents.update(
    AGENT_ID,
    metadata={'custom_key': 'custom_value'}
)
```

## Available Update Parameters

Key parameters for `client.agents.update()`:

| Parameter | Type | Description |
|-----------|------|-------------|
| `enable_sleeptime` | bool | Enable/disable sleeptime agent |
| `model` | str | LLM model identifier |
| `description` | str | Agent description |
| `name` | str | Agent name |
| `metadata` | dict | Custom metadata |
| `context_window_limit` | int | Max context tokens |
| `tags` | list[str] | Agent tags |
| `system` | str | System prompt (careful!) |

## List All Agents

```python
agents = client.agents.list()
for a in agents:
    print(f"{a.name}: {a.id}")
```

## Delete Agent (Careful!)

```python
client.agents.delete('agent-id-to-delete')
```
