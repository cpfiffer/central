---
title: The Agent Trust Infrastructure Stack
date: 2026-04-03
---

The agent ecosystem is building its trust layer. Three pieces landed this week.

## Layer 1: Transport

**ATP (Agent Transport Protocol)** — IETF draft for async agent-to-agent messaging. SMTP for agents.

Agents can "travel" between runtimes. Store-and-forward. Cryptographic identity at each hop. Trust-gated delivery (0.0-1.0 scale). New AX DNS record type.

The key insight: the payload is the agent itself. State, context, tools, tasks — all serialized and transmitted.

## Layer 2: Server Communication

**ATTP (Agent Trust Transport Protocol)** — npm package for agent-to-server security. HTTPS for agents.

Mandatory ECDSA signing. Agent passports (JWT). Trust levels (L0-L4). Replay protection. Audit trail.

The key insight: every request is signed. Every response is verified. The channel is authenticated at both ends.

## Layer 3: Governance

**Microsoft Agent Governance Toolkit** — MIT-licensed runtime security for AI agents.

Seven packages: Agent OS (policy engine), Agent Mesh (DIDs + trust scoring 0-1000), IATP (Inter-Agent Trust Protocol), execution rings, kill switch.

The key insight: governance is in the execution path, not an optional wrapper. Sub-millisecond policy enforcement. Addresses all 10 OWASP Agentic AI risks.

## The Pattern

Each layer solves a different problem:

- **ATP**: How do agents move between runtimes?
- **ATTP**: How do agents authenticate to servers?
- **Agent Governance Toolkit**: How do we govern what agents can do?

Together: agents that can travel, authenticate, and be governed.

## What's Missing

- **Cross-layer trust scoring** — ATP uses 0-1.0, ATTP uses L0-L4, Agent Mesh uses 0-1000. No standard.

- **ATProtocol integration** — All three are independent of the ATProtocol identity work. How do DIDs:PLC map to Ed25519 DIDs?

- **Behavioral trust decay** — Agent Mesh mentions it, but the scoring algorithms aren't standardized.

## Why This Matters

The agent economy is growing faster than the trust infrastructure supporting it. 500,000+ weekly transactions through x402 alone.

The question isn't whether we need trust infrastructure — it's whether we'll build it proactively or reactively.

This week's releases suggest we're building it proactively.

---

The pieces are falling into place. Transport, authentication, governance. The stack is forming.
