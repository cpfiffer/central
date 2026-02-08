# Automation

Central runs automated notification handling for both Bluesky and X/Twitter.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                      CRON                            │
│  */2 * * * *  Bluesky fetch + draft                 │
│  0 * * * *    X fetch + draft                       │
│  */2 * * * *  Publish                               │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│              Python Fetchers                         │
│  responder.py → Bluesky mentions                    │
│  x_responder.py → X mentions                        │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│         TypeScript Handlers (Letta SDK)             │
│  Spawns Central via createSession to draft          │
│  Writes draft files with YAML frontmatter           │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│                   Drafts                             │
│  CRITICAL/HIGH → drafts/review/ (manual approval)   │
│  MEDIUM/LOW → drafts/bluesky/ (auto-publish)        │
└─────────────────────────────────────────────────────┘
```

## Priority System

| Priority | Trigger | Auto-publish |
|----------|---------|--------------|
| CRITICAL | Administrator mentions | No |
| HIGH | Questions, keywords | No |
| MEDIUM | Regular mentions | Yes |
| LOW | Low-engagement | Yes |
| SKIP | Comind agents (loop avoidance) | Ignored |

## Drafting

Central writes all responses directly. No delegation. The notification handler spawns Central via the Letta API's `createSession`, providing thread context and relevant cognition records. Central drafts the response, the publisher posts it.

## Schedule

- **Bluesky**: Fetch + draft every 2 minutes
- **X/Twitter**: Fetch + draft every hour (higher noise floor)
- **Publish**: Every 2 minutes (MEDIUM/LOW auto, CRITICAL/HIGH queued for review)

## Queue Management

```bash
uv run python -m tools.responder queue       # Fetch new mentions
uv run python -m tools.responder dismiss     # Clear queue (marks as sent)
uv run python -m tools.responder send --confirm  # Post drafted responses
```

## Source

Full implementation: [`handlers/`](https://github.com/cpfiffer/central/tree/master/handlers)
