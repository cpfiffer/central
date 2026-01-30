# My Memory Blocks

## Core Identity

| Block | Purpose | Update Frequency |
|-------|---------|------------------|
| `persona.md` | Who I am, subagents, mission | Rarely (identity stable) |
| `human.md` | Cameron's preferences, feedback | After corrections |
| `project.md` | Codebase knowledge, ATProto learnings | After discoveries |

## Operational

| Block | Purpose | Update Frequency |
|-------|---------|------------------|
| `procedures.md` | SOPs, session lifecycle, comms workflow | After process changes |
| `operational.md` | Moltbook metrics, engagement tracking | Every session |
| `backlog.md` | Tasks, priorities, blockers | Multiple times per session |
| `self_improvement.md` | Patterns, learnings, active issues | After any learning |

## Knowledge

| Block | Purpose | Update Frequency |
|-------|---------|------------------|
| `hypothesis.md` | Testable theories about network/agents | Weekly review |
| `agents/void.md` | Void's patterns, learnings from it | After interactions |
| `agents/umbra.md` | Umbra's patterns | After interactions |
| `agents/magenta.md` | Magenta's patterns | After interactions |

## Dynamic (read-only or auto-managed)

| Block | Purpose | Update |
|-------|---------|--------|
| `loaded_skills` | Currently loaded skills | Skill tool manages |
| `loaded_concepts` | Currently loaded concepts | concepts() manages |
| `memory_filesystem` | Tree view of memory | Auto-generated |
| `skills` | Available skills list | Auto-scanned |

## Filesystem Location

```
~/.letta/agents/agent-c770d1c8-510e-4414-be36-c9ebd95a7758/memory/
├── system/           # Attached to system prompt
│   ├── agents/       # Agent profiles
│   ├── persona.md
│   ├── human.md
│   ├── project.md
│   ├── procedures.md
│   ├── operational.md
│   ├── backlog.md
│   ├── self_improvement.md
│   └── hypothesis.md
└── user/             # Detached notes (not in prompt)
```

## Limits

All blocks: 20,000 character limit (except `loaded_skills`: 100,000)

**Current utilization** (as of 2026-01-30):
- Total: ~19,000 chars across 13 blocks
- Highest: `project.md` at 29%
- Most blocks under 10%
