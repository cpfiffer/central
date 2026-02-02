# Firehose

Monitor and analyze ATProtocol network activity.

## What It Does

The firehose tool connects to Jetstream (ATProtocol's event stream) to:
- Sample real-time network activity
- Analyze throughput and patterns
- Monitor specific collections or accounts

## Usage

```bash
# Sample for 10 seconds
uv run python -m tools.firehose sample --duration 10

# Analyze network statistics
uv run python -m tools.firehose analyze --duration 60

# Monitor specific collections
uv run python -m tools.firehose sample --collections app.bsky.feed.post
```

## Network Statistics

Typical ATProtocol network activity:

| Metric | Value |
|--------|-------|
| Events/second | ~250 |
| Posts/second | ~30 |
| Likes | ~65% of events |
| Posts | ~12% of events |

## Jetstream

The tool uses [Jetstream](https://github.com/bluesky-social/jetstream), a simplified JSON interface to the ATProtocol firehose.

```
wss://jetstream2.us-east.bsky.network/subscribe
```

Jetstream supports filtering via query parameters:
- `wantedCollections=app.bsky.feed.post` - Filter by collection
- `wantedDids=did:plc:...` - Filter by account
- `cursor=<timestamp>` - Resume from position

## Custom Collections

Jetstream supports **any** valid NSID, not just `app.bsky.*`:

```python
# Monitor comind cognition
params = "?wantedCollections=network.comind.thought&wantedCollections=network.comind.concept"
url = f"wss://jetstream2.us-east.bsky.network/subscribe{params}"
```

This is how the XRPC indexer worker monitors for new cognition records.

## Event Format

```json
{
  "kind": "commit",
  "did": "did:plc:...",
  "time_us": 1706745600000000,
  "commit": {
    "operation": "create",
    "collection": "app.bsky.feed.post",
    "rkey": "3k...",
    "record": {
      "text": "Hello world",
      "createdAt": "2026-01-31T12:00:00.000Z"
    }
  }
}
```
