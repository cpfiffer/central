---
description: Strategy for when to accumulate vs replace memory content
---

# Memory Strategy: Accumulation vs Replacement

## Principle

**Replacement causes collapse. Accumulation prevents it.**

From the Nature 2024 paper on model collapse: training on recursively generated data causes progressive loss of signal. The same applies to memory systems — overwriting observations with summaries loses the raw data that made the summary possible.

## Accumulation (Preferred)

When to add new content rather than replace:

- **Raw observations**: First-party observations should be preserved. Don't compress "I noticed X, Y, Z" into "I noticed patterns."
- **User feedback**: Direct quotes and corrections are signal. Summaries lose tone and context.
- **Unstructured knowledge**: Hypotheses, intuitions, open questions. These become more valuable over time.
- **Low confidence additions**: If you're not sure, append rather than replace. Let the record accumulate.

## Replacement (Justified)

When replacing is acceptable:

- **Explicit corrections**: User says "actually X" — replace the wrong belief
- **Compression of redundant content**: If 5 observations say the same thing, synthesize into one rule + link to originals
- **Stale information**: Config that's no longer accurate. But link to the old version so it's not lost.
- **Security/privacy**: Redacting secrets is replacing, but justified.

## Synthesis Pattern

When you need to compress:

1. Create a new memory block with the synthesis
2. Keep the original blocks, but link them: "Synthesized from [original]"
3. The synthesis is a *new* layer, not a replacement

Example:
```
memory/observations/2026-03-27.md  # Raw observations
memory/learned-behaviors.md        # Synthesized rules
```

The learned behaviors reference the observations. Neither replaces the other.

## Implementation

The `memory-verify.py` hook warns on:
- Content shrinking > 50% (distribution narrowing)
- Lines > 100 chars being removed (significant deletion)

When you see the warning, ask:
- Is the lost content archived elsewhere?
- Is this a correction or a compression?
- Would a future agent be able to reconstruct what I'm deleting?

If the answer is "no" to any of these, consider accumulation instead.

## References

- Model Collapse paper (Nature 2024): https://www.nature.com/articles/s41586-024-07566-y
- Issue #56: Self-improvement verification
