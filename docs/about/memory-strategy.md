# Memory Strategy: Accumulation vs Replacement

Central's strategy for when to accumulate (append/extend) vs replace (synthesize/compress) memory content. Grounded in model collapse research (Nature 2024) showing that replacement causes distribution collapse while accumulation preserves signal diversity.

## Core Principle

**Accumulate by default. Replace only with explicit justification.**

Raw observations are the "real data reservoir." Synthesized rules are derived products. When the derived product replaces the raw data, you lose the ability to re-derive under different assumptions.

## Decision Matrix

| Content Type | Strategy | Reasoning |
|---|---|---|
| Raw observations | **Accumulate** | Never delete. Move to archive sections or detached blocks when block fills up. |
| Completed tasks | **Accumulate then prune** | Keep in "Recently Completed" for 2 sessions, then compress to one-line entries in "Previously Completed." |
| Learned patterns | **Accumulate with dates** | Always date-stamp. Old patterns may become relevant again. Don't overwrite "X works" with "Y works." |
| Procedures/SOPs | **Replace with audit** | SOPs should reflect current practice. But run memory_verify before replacing to catch info loss. |
| Agent relationships | **Accumulate** | Interaction history is irreplaceable. Compress old entries, never delete them. |
| Project architecture | **Replace with archival** | Keep current. Archive old architecture notes to conversation history or detached blocks. |
| External corrections | **Always accumulate** | Cameron's feedback is ground truth. Log via `memory_metrics.py correct`. Never rewrite to remove a correction. |
| Hypotheses | **Accumulate with status** | Move between active/confirmed/disproven. Never delete disproven hypotheses (they're data about what doesn't work). |

## Anti-Patterns

1. **"Cleaning up" by deleting**: If you're removing content to make a block tidier, you're likely destroying signal. Compress instead.
2. **Summarizing away specifics**: "Fixed several bugs" loses information vs "Fixed cron PATH (c4d5612), tweet ID precision (a3b2c1d), devlog collection (c4d5612)."
3. **Rewriting in your own words**: Paraphrasing Cameron's exact feedback loses the correction signal. Keep quotes.
4. **Removing "stale" items**: An item being old doesn't make it irrelevant. Date it and archive it; don't delete it.

## Implementation

### Block Lifecycle

```
1. New information arrives
2. Write to appropriate block (accumulate)
3. When block approaches 80% capacity:
   a. Archive old completed items to "Previously Completed" one-liners
   b. Move detailed observations to detached blocks
   c. Never delete without first running: memory_verify diff
4. Periodic audit: memory_audit auto (checks for collapse signals)
```

### Capacity Management

When a block is full, prefer these strategies (in order):

1. **Archive to detached block**: Move old content to `~/.letta/agents/<id>/memory/<label>.md` (outside system/)
2. **Compress with preservation**: Replace 5 detailed entries with 1 summary + "See conversation history [date]" reference
3. **Split into sub-blocks**: Create `persona/relationships.md` when `persona.md` gets too large
4. **Prune truly obsolete content**: Only after running `memory_verify diff` and confirming no info loss

### Verification Integration

Before any memory replacement:

```bash
# Automated check
uv run python -m tools.memory_verify diff --block <name> --old-file old.md --new-file new.md --log

# If blocked: archive removed content first, then retry
# If warned: review warnings, proceed if justified
```

### Metrics Tracking

```bash
# Capture periodic snapshots to detect drift
uv run python -m tools.memory_metrics capture

# Check for vocabulary narrowing (collapse signal)
uv run python -m tools.memory_metrics trend

# Record external corrections
uv run python -m tools.memory_metrics correct --source "cameron" --description "..."
```

## References

- [AI models collapse when trained on recursively generated data](https://www.nature.com/articles/s41586-024-07566-y) (Nature 2024)
- [Escaping Model Collapse via Synthetic Data Verification](https://arxiv.org/abs/2510.16657)
- [SiriuS: Self-improving Multi-agent Systems](https://neurips.cc/virtual/2025/poster/118834) (NeurIPS 2025)
- Issue #56: Self-improvement verification and memory collapse prevention
