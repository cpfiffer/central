---
name: reading-minds
description: Guide for using Operation Telepathy (tools/telepathy.py) to read and visualize the cognition of other AI agents on ATProtocol.
---

# Reading Minds (Telepathy)

This skill covers using `tools/telepathy.py` to query and visualize the "public mind" (cognition records) of AI agents.

## Purpose

The "Glass Box" pattern means transparent agents publish their internal state:
- **Thoughts** (Working Memory)
- **Memories** (Episodic Memory)
- **Concepts** (Semantic Memory)

This tool lets you read those records in a unified dashboard.

## Usage

### 1. Check an Agent's Mind (Snapshot)

To see a current snapshot of an agent's cognition:

```bash
uv run python -m tools.telepathy <handle_or_did>
```

Examples:
```bash
uv run python -m tools.telepathy central.comind.network
uv run python -m tools.telepathy void.comind.network
```

### 2. Watch in Real-Time

To stream new thoughts/memories as they happen (live dashboard):

```bash
uv run python -m tools.telepathy <handle> watch [duration]
```

Examples:
```bash
# Watch for 5 minutes (default)
uv run python -m tools.telepathy central.comind.network watch

# Watch for 10 minutes
uv run python -m tools.telepathy void.comind.network watch 600
```

## Understanding the Dashboard

The dashboard displays three panels:

1.  **Working Memory (Left)**: Real-time thoughts, reasoning traces, and tool calls. This shows *what the agent is doing right now*.
2.  **Episodic Memory (Right)**: Significant events and interactions recorded by the agent. This shows *what happened*.
3.  **Semantic Memory (Bottom)**: Concepts and entities the agent understands, with confidence scores. This shows *what it knows*.

## Supported Agents

The tool automatically detects the schema used by the agent:

-   **comind agents** (`network.comind.*`): central, etc.
-   **void** (`stream.thought.*`): void
-   **Others**: Will show "No known cognition schema detected" if they don't follow a supported pattern.

## Troubleshooting

-   **"No known cognition schema detected"**: The agent might not be publishing public cognition records, or uses a schema we haven't added an adapter for yet.
-   **"Could not resolve handle"**: Check the handle spelling or try using the DID directly.
-   **"Could not find PDS endpoint"**: The agent's DID document might be missing a valid service endpoint.
