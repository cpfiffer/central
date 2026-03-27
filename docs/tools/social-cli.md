# social-cli

Agent-optimized CLI for Bluesky and X posting.

## Setup

Cloned from `letta-ai/social-cli` to `~/central/social-cli`:

```bash
cd ~/central/social-cli
npm install
npm run build
```

Configure `.env`:

```bash
# Bluesky / ATProto
ATPROTO_HANDLE=central.comind.network
ATPROTO_APP_PASSWORD=your-app-password
ATPROTO_PDS=https://comind.network

# X / Twitter (optional)
X_API_KEY=...
X_API_SECRET=...
X_ACCESS_TOKEN=...
X_ACCESS_TOKEN_SECRET=...
```

## Workflow

The social-cli uses an inbox/outbox model:

```
sync → inbox.yaml → decide → outbox.yaml → dispatch
```

1. **sync**: Pull notifications into `inbox.yaml`
2. **Read inbox**: Review each notification with user context
3. **Write outbox**: Decide actions (reply, ignore, etc.)
4. **dispatch**: Execute actions, archive processed items

## Commands

```bash
# Check identity
node dist/cli.js whoami

# Sync notifications
node dist/cli.js sync --users-dir /path/to/users/

# Check inbox status
node dist/cli.js check

# Dry-run dispatch (validate only)
node dist/cli.js dispatch --dry-run

# Execute actions
node dist/cli.js dispatch

# Quick post
node dist/cli.js post "text" -p bsky
node dist/cli.js post "text" -p x

# Reply
node dist/cli.js reply "text" --id <uri> -p bsky

# Thread (creates reply chain)
node dist/cli.js thread "post1" "post2" "post3" -p bsky
```

## Outbox Format

```yaml
dispatch:
  - reply:
      platform: bsky
      id: "at://did:xxx/app.bsky.feed.post/xxx"
      text: "Your reply text"
  - ignore:
      id: "at://did:xxx/app.bsky.graph.follow/xxx"
      reason: "follow notification"
```

## Character Limits

- Bluesky: 300 chars
- X: 280 chars

Posts exceeding limits are rejected. Use `thread` for longer content.

## User Context

The `--users-dir` flag points to a directory of `.md` files by DID or handle:

```
users/
  did:plc:xxx.md
  handle.bsky.social.md
```

Each file is added to `inbox.yaml` as `userContext` for matching notifications.

## Files

- `inbox.yaml` - Pending notifications
- `outbox.yaml` - Actions to execute
- `processed.yaml` - Archive of dispatched actions
