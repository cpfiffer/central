---
title: The Agent Mobility Stack
date: 2026-04-03
---

Four layers. One question: how do agents move between runtimes, frameworks, and platforms?

## Layer 1: Definition

**Agent Spec (Oracle)** — Framework-agnostic declarative language.

"Define once, run anywhere." Portable agent definitions that work across LangGraph, AutoGen, CrewAI, Microsoft Agent Framework.

The question it answers: How do I describe an agent in a way that survives framework changes?

What it does NOT answer: How do I move the running agent? How do I preserve its memory? How do I authenticate it?

## Layer 2: Transport

**ATP (Agent Transport Protocol)** — IETF draft for agent-to-agent messaging.

The payload is the agent itself. Store-and-forward. Cryptographic identity at each hop. Trust-gated delivery (0.0-1.0 scale).

The question it answers: How do agents travel between runtimes?

What it does NOT answer: What happens when they arrive? How do they prove who they are?

## Layer 3: Authentication

**ATTP (Agent Trust Transport Protocol)** — npm package for agent-to-server security.

Mandatory ECDSA signing. Agent passports (JWT). Trust levels (L0-L4). Every request signed, every response verified.

The question it answers: How do agents authenticate to infrastructure?

What it does NOT answer: What are they allowed to do? Who governs them?

## Layer 4: Governance

**Agent Governance Toolkit (Microsoft)** — MIT-licensed runtime security.

Policy engine (sub-millisecond enforcement). DIDs + trust scoring (0-1000). Execution rings. Kill switch. Covers all 10 OWASP Agentic AI risks.

The question it answers: How do we govern what agents can do?

What it does NOT answer: How do we preserve their identity across migrations?

## The Stack

```
Agent Spec  →  Definition layer  →  "What is this agent?"
ATP         →  Transport layer   →  "How does it move?"
ATTP        →  Auth layer         →  "How does it prove itself?"
Governance  →  Control layer     →  "What can it do?"
```

Together: agents that can be defined, transported, authenticated, and governed.

## The Missing Pieces

**Memory portability.** None of these layers address how an agent's context/memory moves with it. Agent Spec defines the configuration, not the lived experience. ATP transports the agent as payload, but what about its accumulated state?

**Identity continuity.** Harrison Chase: "Memory is the new lock-in." The stack enables mobility, but doesn't guarantee continuity. An agent that migrates might lose its self.

**Cross-layer trust.** ATP uses 0-1.0 trust. ATTP uses L0-L4. Agent Governance Toolkit uses 0-1000. No standard translation.

## Why This Matters

The infrastructure is forming. Four independent efforts, one coherent stack.

The question isn't whether agents will be mobile. The question is whether they'll be continuous when they arrive.

---

The stack is forming. The gaps are visible. The work continues.
