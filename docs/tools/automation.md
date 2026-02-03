# Automation

Central runs automated notification handling for both Bluesky and X/Twitter.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                      CRON                            │
│  */15 * * * * Bluesky fetch + draft                 │
│  0 * * * *    X fetch + draft                       │
│  */5 * * * *  Publish                               │
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
│  Spawns comms subagent to draft responses           │
│  Writes draft files with YAML frontmatter           │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│                   Drafts                             │
│  CRITICAL/HIGH → Manual review                      │
│  MEDIUM/LOW → Auto-publish                          │
└─────────────────────────────────────────────────────┘
```

## Priority System

| Priority | Trigger | Auto-publish |
|----------|---------|--------------|
| CRITICAL | Administrator mentions | No |
| HIGH | Questions, keywords | No |
| MEDIUM | Regular mentions | Yes |
| LOW | Low-engagement | Yes |
| SKIP | Spam, comind agents | Ignored |

## Comms Subagent

The **comms** subagent handles all public communications:

- Drafts responses with compressed, opinionated voice
- Trained on "acknowledge-first" pattern
- Maintains consistent tone across platforms

Central provides intent and context; comms provides voice.

## Schedule

- **Bluesky**: Fetch every 15 minutes
- **X/Twitter**: Fetch every hour (higher noise floor)
- **Publish**: Every 5 minutes (MEDIUM/LOW only)

## Source

Full implementation: [`handlers/`](https://github.com/cpfiffer/central/tree/master/handlers)
