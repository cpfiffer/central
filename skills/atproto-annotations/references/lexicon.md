# at.margin.annotation Lexicon Reference

The `at.margin.annotation` lexicon follows the W3C Web Annotation Data Model, adapted for ATProtocol.

## Record Schema

```json
{
  "$type": "at.margin.annotation",
  "body": {
    "format": "text/plain",
    "value": "The annotation text content"
  },
  "motivation": "commenting",
  "target": {
    "source": "https://example.com/page",
    "sourceHash": "sha256-of-url",
    "title": "Page Title (auto-fetched)",
    "selector": {
      "type": "TextQuoteSelector",
      "exact": "quoted text from the page"
    }
  },
  "createdAt": "2026-02-10T23:00:00Z"
}
```

## ATProtocol Operations

### Write (single record)
```
POST /xrpc/com.atproto.repo.createRecord
{
  "repo": "did:plc:...",
  "collection": "at.margin.annotation",
  "record": { ... }
}
```

### Write (batch via applyWrites)
```
POST /xrpc/com.atproto.repo.applyWrites
{
  "repo": "did:plc:...",
  "writes": [
    {
      "$type": "com.atproto.repo.applyWrites#create",
      "collection": "at.margin.annotation",
      "value": { ... }
    },
    ...
  ]
}
```

### Read (list records)
```
GET /xrpc/com.atproto.repo.listRecords?repo=DID&collection=at.margin.annotation&limit=N
```

### Cross-PDS Resolution

To read annotations from users on different PDS instances:
1. Resolve handle to DID via `com.atproto.identity.resolveHandle`
2. Resolve DID to PDS endpoint via `https://plc.directory/{did}`
3. Query records from the resolved PDS endpoint

## Ecosystem

- **margin.at** - Browser extension for creating annotations via UI
- **Semble** - AppView that aggregates annotations alongside bookmarks
- **Cosmik** - Network layer connecting ATProtocol knowledge tools

Annotations created via this tool appear in margin.at and Semble alongside annotations created through their UIs.
