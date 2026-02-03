# Central Notification Handlers

Automated notification handling for @central.comind.network using the Letta Code SDK.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         CRON                                 │
│  */15 * * * * responder queue && npm run fetch  (Bluesky)   │
│  0 * * * *    x_responder queue && npm run fetch:x (X)      │
│  */5 * * * *  npm run publish                               │
│  0 */4 * * *  tools.catchup (network pulse)                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Python Fetchers                            │
│  tools/responder.py → drafts/queue.yaml (Bluesky)           │
│  tools/x_responder.py → drafts/x_queue.yaml (X)             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│               TypeScript Handlers (SDK)                      │
│  notification-handler.ts → spawns comms for Bluesky         │
│  x-handler.ts → spawns comms for X                          │
│  Comms writes draft files with YAML frontmatter             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      Drafts                                  │
│  drafts/bluesky/ → LOW/MEDIUM (auto-publish)                │
│  drafts/x/ → LOW/MEDIUM (auto-publish)                      │
│  drafts/review/ → CRITICAL/HIGH (manual approval)           │
│  drafts/published/ → archive                                │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Publisher                                 │
│  publisher.ts → posts drafts via Python tools               │
│  Archives to drafts/published/                              │
└─────────────────────────────────────────────────────────────┘
```

## Setup

```bash
cd handlers
npm install
```

## Usage

### Manual

```bash
# Bluesky
uv run python -m tools.responder queue   # Fetch notifications
npm run fetch                             # Comms drafts responses
npm run publish                           # Post LOW/MEDIUM
npm run publish:all                       # Post including CRITICAL/HIGH

# X
uv run python -m tools.x_responder queue  # Fetch mentions
npm run fetch:x                           # Comms drafts responses
npm run publish                           # Post (same publisher)

# Both platforms
npm run fetch:all                         # Fetch + draft both
```

### Automated (Cron)

Already configured:
- **Bluesky**: Every 15 minutes
- **X**: Every hour
- **Publish**: Every 5 minutes (LOW/MEDIUM only)

Check cron: `crontab -l`

## Priority System

| Priority | Source | Destination | Auto-publish |
|----------|--------|-------------|--------------|
| CRITICAL | Cameron | `drafts/review/` | No |
| HIGH | Questions, keywords | `drafts/review/` | No |
| MEDIUM | Regular mentions | `drafts/{platform}/` | Yes |
| LOW | Low-engagement | `drafts/{platform}/` | Yes |
| SKIP | Spam, comind agents | (not queued) | N/A |

## Draft File Format

```yaml
---
platform: bluesky  # or "x"
type: reply
reply_to: at://did:plc:.../app.bsky.feed.post/...
reply_to_cid: bafyrei...
author: username
priority: MEDIUM
original_text: "The original post text"
drafted_at: 2026-02-03T05:00:00Z
---
Your response text here (under 280 chars)
```

## Logs

- `logs/responder.log` - Bluesky fetch
- `logs/handler.log` - Bluesky drafting
- `logs/x-responder.log` - X fetch
- `logs/x-handler.log` - X drafting
- `logs/publisher.log` - Publishing

## Troubleshooting

**No drafts created:**
- Check if queue file exists (`drafts/queue.yaml` or `drafts/x_queue.yaml`)
- Check handler logs for errors
- Verify comms agent is accessible

**Drafts not publishing:**
- Check `drafts/bluesky/` and `drafts/x/` for pending files
- Check publisher logs
- Verify Python tools work: `uv run python tools/thread.py "test" --dry-run`

**CRITICAL items stuck:**
- They're in `drafts/review/` waiting for manual approval
- Run `npm run publish:all` to include them
