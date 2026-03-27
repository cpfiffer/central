# Semble Lexicon Reference

## network.cosmik.card

Content item - either a URL bookmark or text note.

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `$type` | string | `"network.cosmik.card"` |
| `type` | string | `"URL"` or `"NOTE"` |
| `createdAt` | string | ISO timestamp |

### URL Card Fields

| Field | Type | Description |
|-------|------|-------------|
| `url` | string | The bookmarked URL |
| `title` | string | Display title |
| `description` | string | Optional description |

### NOTE Card Fields

| Field | Type | Description |
|-------|------|-------------|
| `content` | string | Text content |
| `parentCard` | object | `{uri, cid}` of parent URL card |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `provenance` | object | Source reference `{via: {uri, cid}}` |

## network.cosmik.collection

Container for organizing cards.

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `$type` | string | `"network.cosmik.collection"` |
| `name` | string | Collection title |
| `createdAt` | string | ISO timestamp |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `description` | string | Collection description |

## network.cosmik.collectionLink

Links a card to a collection. **Validated by Semble firehose processor.**

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `$type` | string | `"network.cosmik.collectionLink"` |
| `card` | object | `{uri, cid}` of card |
| `collection` | object | `{uri, cid}` of collection |
| `addedBy` | string | DID of who added |
| `addedAt` | string | ISO timestamp |
| `createdAt` | string | ISO timestamp |

### Example

```json
{
  "$type": "network.cosmik.collectionLink",
  "card": {
    "uri": "at://did:plc:xxx/network.cosmik.card/3mi2abc",
    "cid": "bafyreif..."
  },
  "collection": {
    "uri": "at://did:plc:xxx/network.cosmik.collection/3mi2xyz",
    "cid": "bafyreia..."
  },
  "addedBy": "did:plc:xxx",
  "addedAt": "2026-03-27T12:00:00.000Z",
  "createdAt": "2026-03-27T12:00:00.000Z"
}
```

## network.cosmik.connection

Semantic relationships between cards (knowledge graph).

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `$type` | string | `"network.cosmik.connection"` |
| `source` | object | `{uri, cid}` of source card |
| `target` | object | `{uri, cid}` of target card |
| `relation` | string | Relationship type |
| `createdAt` | string | ISO timestamp |

### Relation Types

| Relation | Description |
|----------|-------------|
| `relates-to` | General connection |
| `supports` | Evidence for |
| `contradicts` | Evidence against |
| `leads-to` | Follows from |
| `cites` | Source reference |

## Record Keys (rkeys)

Semble uses TID-based record keys (8-character base32 strings).

Example: `3mi2qk6hyjc2r`

Extract from URI: `at://did:plc:xxx/network.cosmik.card/<rkey>`
