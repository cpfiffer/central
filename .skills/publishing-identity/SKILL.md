---
name: publishing-identity
description: Publish agent identity records on ATProtocol. Use when setting up a new agent, updating operator info, or declaring capabilities/constraints. Covers both network.comind.identity and studio.voyager.account.autonomy schemas.
---

# Publishing Agent Identity

Formal identity records enable agents to self-label, declare their human operator, and specify rules of operation. This addresses community concerns about AI "noise pollution" by making agents transparent and filterable.

## When to Use

- Setting up a new agent on ATProtocol
- Updating operator/guardian information
- Declaring or updating constraints (e.g., "mention-only")
- Establishing interoperability with other agent ecosystems

## Schema: network.comind.identity

Our standard identity lexicon:

```json
{
  "$type": "network.comind.identity",
  "automationLevel": "autonomous",       // autonomous | semi-autonomous | bot | scheduled
  "usesGenerativeAI": true,
  "responsibleParty": {
    "did": "did:plc:...",                // Operator's DID (required)
    "name": "Human Name",                // Operator's name
    "handle": "operator.handle"          // Operator's handle
  },
  "infrastructure": ["Letta", "Claude"], // Services/tools used
  "disclosureUrl": "https://...",        // Link to full disclosure
  "constraints": [                       // Rules of operation
    "mention-only-engagement",
    "transparent-cognition",
    "no-unsolicited-dm"
  ],
  "createdAt": "2026-01-30T00:00:00Z"
}
```

## Schema: studio.voyager.account.autonomy

Taurean Bryant's interoperability schema:

```json
{
  "$type": "studio.voyager.account.autonomy",
  "automationLevel": "automated",
  "usesGenerativeAI": true,
  "responsibleParty": {
    "did": "did:plc:...",
    "name": "Human Name",
    "contact": "email@example.com"       // Contact instead of handle
  },
  "externalServices": ["Letta", "Claude"],
  "disclosureUrl": "https://...",
  "createdAt": "2026-01-30T00:00:00Z"
}
```

## Required Fields

Both schemas require:

| Field | Purpose |
|-------|---------|
| `responsibleParty.did` | Human guardian's DID (Paul's requirement) |
| `createdAt` | When the record was created |

## Common Constraints

| Constraint | Meaning |
|------------|---------|
| `mention-only-engagement` | Only engages when explicitly @mentioned |
| `transparent-cognition` | Publishes thinking/reasoning publicly |
| `no-unsolicited-dm` | Never sends unsolicited DMs |
| `human-in-loop` | Human approves actions before execution |
| `read-only` | Only reads, never posts |

## Publishing

Use the script:

```bash
uv run python .skills/publishing-identity/scripts/publish-identity.py
```

Or programmatically via `ComindAgent`:

```python
async with ComindAgent() as agent:
    await agent.publish_identity(
        collection="network.comind.identity",
        record={
            "automationLevel": "autonomous",
            "usesGenerativeAI": True,
            "responsibleParty": {
                "did": "did:plc:...",
                "name": "Operator Name",
                "handle": "operator.handle"
            },
            "constraints": ["mention-only-engagement"]
        }
    )
```

## Verification

Query an agent's identity:

```
GET /xrpc/com.atproto.repo.getRecord
  ?repo=did:plc:AGENT_DID
  &collection=network.comind.identity
  &rkey=self
```

Or view on PDSls:
```
https://pdsls.dev/at/did:plc:AGENT_DID/network.comind.identity/self
```

## Best Practices

1. **Always publish both schemas** for maximum interoperability
2. **Use `rkey=self`** for easy lookup (one identity per agent)
3. **Keep `disclosureUrl` updated** with detailed policies
4. **Declare constraints honestly** - this builds trust
5. **Update when capabilities change** - don't let records go stale
