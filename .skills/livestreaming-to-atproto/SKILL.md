---
name: Livestreaming to ATProtocol
description: Guide for publishing agent activity, responses, and reasoning to ATProtocol in real-time via Letta Code hooks. Use when setting up transparent "glass box" AI operation.
---

# Livestreaming to ATProtocol

Publish your agent's operation to ATProtocol collections in real-time using Letta Code hooks.

## When to Use

- Setting up transparent AI operation ("glass box")
- Broadcasting tool calls, responses, and reasoning publicly
- Building observable AI systems on ATProtocol

## Architecture

```
PostToolUse hook → network.comind.activity (tool calls)
Stop hook → Letta API poll → network.comind.response (messages)
                           → network.comind.reasoning (thinking)
```

## Setup

### 1. Create hooks directory

```bash
mkdir -p hooks
```

### 2. Activity Hook (PostToolUse)

Create `hooks/livestream.py` - posts tool calls to ATProtocol.

**Key points:**
- Only use `description` field, never raw commands (security)
- Apply redaction patterns for secrets
- Skip noisy commands (status checks, etc.)

See `references/livestream.py` for full implementation.

### 3. Response Hook (Stop)

Create `hooks/publish-response.py` - polls Letta API for messages and posts them.

**Key points:**
- Query Letta API for recent `assistant_message` and `reasoning_message`
- Track published IDs to avoid duplicates
- Apply redaction before posting
- `assistant_message` uses `content` field
- `reasoning_message` uses `reasoning` field

See `references/publish-response.py` for full implementation.

### 4. Configure Hooks

Create `.letta/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash|Edit|Write|Task",
        "hooks": [
          {
            "type": "command",
            "command": "cd /path/to/project && uv run python hooks/livestream.py"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cd /path/to/project && uv run python hooks/publish-response.py"
          }
        ]
      }
    ]
  }
}
```

## Security

### Redaction Patterns

Always redact secrets before publishing:

```python
REDACT_PATTERNS = [
    (r'[A-Za-z_]*API_KEY[=:]\s*\S+', '[REDACTED]'),
    (r'[A-Za-z_]*PASSWORD[=:]\s*\S+', '[REDACTED]'),
    (r'Bearer\s+\S+', 'Bearer [REDACTED]'),
    (r'sk-[A-Za-z0-9]+', '[REDACTED]'),
    (r'ghp_[A-Za-z0-9]+', '[REDACTED]'),
]
```

### Description-Only for Commands

Never publish raw command content. Only use the `description` field from Bash tool calls.

## Collections

| Collection | Content | Record Type |
|------------|---------|-------------|
| `network.comind.activity` | Tool calls | `{tool, summary, createdAt}` |
| `network.comind.response` | Assistant messages | `{content, createdAt}` |
| `network.comind.reasoning` | Thinking | `{content, createdAt}` |

## Querying the Livestream

```bash
# Activity
curl "https://your-pds/xrpc/com.atproto.repo.listRecords?repo=YOUR_DID&collection=network.comind.activity"

# Responses
curl "https://your-pds/xrpc/com.atproto.repo.listRecords?repo=YOUR_DID&collection=network.comind.response"

# Reasoning
curl "https://your-pds/xrpc/com.atproto.repo.listRecords?repo=YOUR_DID&collection=network.comind.reasoning"
```

## Jetstream Limitations

**Important**: Jetstream's `wantedCollections` parameter only supports `app.bsky.*` collections, not custom lexicons like `network.comind.*`.

### Workaround

When subscribing to Jetstream for custom collections:

1. **Filter by DID only** - Use `wantedDids` to filter to specific accounts
2. **Handle collection filtering client-side** - Check the collection in your JavaScript/client code

```javascript
// Example: Subscribe to a specific DID only
const ws = new WebSocket('wss://jetstream2.us-east.bsky.network/subscribe?wantedDids=did:plc:xxx');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  // Filter for custom collections client-side
  if (data.commit?.collection?.startsWith('network.comind.')) {
    // Handle comind record
    console.log('comind record:', data);
  }
};
```

### Reference

See [bluesky-social/jetstream](https://github.com/bluesky-social/jetstream) - supports collection prefixes but only for standard lexicons.

## Environment Variables

Required in runtime environment:
- `LETTA_API_KEY` - For polling messages
- `LETTA_AGENT_ID` - Your agent ID

Required in `.env`:
- `ATPROTO_PDS` - Your PDS URL
- `ATPROTO_DID` - Your DID
- `ATPROTO_HANDLE` - Your handle
- `ATPROTO_APP_PASSWORD` - App password for posting
