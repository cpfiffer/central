# Defrag Procedures

## Merge Two Blocks

1. Read both blocks fully
2. Identify unique content in each
3. Create merged content in one file
4. Delete or repurpose the other

```bash
# Example: merge operational.md into procedures.md
cat ~/.letta/agents/.../memory/system/procedures.md
cat ~/.letta/agents/.../memory/system/operational.md
# Edit procedures.md with merged content
# Repurpose operational.md for something else
```

## Prune Completed Items

In `backlog.md`:
```
## Recently Completed (keep 1-2 sessions)
- [x] Task that finished

## Archive (delete after noting)
(delete these entirely)
```

In `self_improvement.md`:
```
- ~~Fixed bug~~ FIXED: commit abc123 (delete after 1 session)
```

## Archive vs Delete

**Archive** (compress but keep):
- Major decisions with context needed later
- Relationship history

**Delete** (remove entirely):
- Completed tasks older than 2 sessions
- Stale observations
- Duplicated information

## Capacity Thresholds

| Utilization | Action |
|-------------|--------|
| <50% | Normal |
| 50-80% | Consider pruning |
| >80% | Prune or invoke memory agent |
