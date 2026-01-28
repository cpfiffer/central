---
name: Social Graph Tracking
description: Guide for tracking relationships and interactions on ATProtocol. Use when building engagement tracking, analyzing network connections, or monitoring social growth.
---

# Social Graph Tracking

Track follows, followers, mutuals, and interaction counts on ATProtocol.

## When to Use

- Tracking engagement and relationship building
- Analyzing network connections
- Monitoring follower growth
- Identifying high-value interactions

## Commands

```bash
# Update graph with current data
uv run python -m tools.social update

# Show social graph summary
uv run python -m tools.social show

# Look up specific person
uv run python -m tools.social who <handle>
```

## Data Structure

The social graph tracks:

```python
{
    "nodes": {
        "handle.bsky.social": {
            "did": "did:plc:xxx",
            "display_name": "Name",
            "first_seen": "2026-01-28T...",
            "relationship": ["i_follow", "follows_me"],  # or subset
            "interactions": 10  # count of replies to/from
        }
    },
    "interactions": [...],  # recent interaction log
    "updated": "2026-01-28T..."
}
```

## Relationship Categories

| Category | Meaning |
|----------|---------|
| Mutuals | Both follow each other |
| I follow | You follow them, they don't follow back |
| Follow me | They follow you, you don't follow back |

## Implementation

### Core Functions

```python
async def get_my_follows() -> list:
    """Get accounts I follow via app.bsky.graph.getFollows"""

async def get_my_followers() -> list:
    """Get accounts following me via app.bsky.graph.getFollowers"""

async def get_recent_interactions() -> list:
    """Analyze my posts to count reply interactions"""
```

### Tracking Interactions

Interactions are counted by analyzing your posts:
- Each reply you make to someone increments their interaction count
- Sorted by interaction count to identify most engaged relationships

## Usage Patterns

### Daily Update

```bash
# At start of session, refresh the graph
uv run python -m tools.social update
```

### Identify Engagement Targets

```bash
# See who you interact with most
uv run python -m tools.social show

# Output:
# Mutuals (8):
#   jowynter.bsky.social (10 interactions)
#   cameron.stream (5 interactions)
#   ...
```

### Research Before Engaging

```bash
# Before replying to someone, check relationship
uv run python -m tools.social who someone.bsky.social
```

## Storage

Data stored in `data/social_graph.json` - JSON format for easy inspection and version control.

## Integration with Experiments

Combine with metrics tracking to measure:
- Follower growth over time
- Correlation between engagement and growth
- Network expansion patterns

See `references/social.py` for full implementation.
