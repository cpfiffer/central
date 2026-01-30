---
name: Active Memory Management
description: Procedural patterns for memory block maintenance. Load when you need to audit utilization, merge blocks, or invoke the memory agent. Philosophy lives in memory blocks, not here.
---

# Active Memory Management

Load this skill when you need to **do** something to your memory, not when thinking about memory.

## Quick Commands

### Audit Utilization
```bash
cd ~/.letta/agents/agent-c770d1c8-510e-4414-be36-c9ebd95a7758/memory/system
for f in *.md agents/*.md; do
    chars=$(wc -c < "$f" 2>/dev/null || echo 0)
    pct=$((chars * 100 / 20000))
    printf "%-25s %5d chars (%2d%%)\n" "$f" "$chars" "$pct"
done | sort -t'(' -k2 -rn
```

### Invoke Memory Agent
```
Task(subagent_type="memory", model="opus", description="Restructure [area]", prompt="...")
```

Use when: blocks need restructuring, cross-block consolidation, major context shift.

## References

- [defrag-patterns.md](references/defrag-patterns.md) - Merge, prune, archive procedures
- [my-blocks.md](references/my-blocks.md) - Block purposes and locations

## When to Load This Skill

- "How do I check my memory utilization?"
- "What's the command to invoke the memory agent?"
- "How do I merge two blocks?"

## When NOT to Load This Skill

- Thinking about memory philosophy (that's in your `procedures.md`)
- Deciding whether to update memory (that's in your `procedures.md`)
- Understanding what memory means (that's identity, not procedure)
