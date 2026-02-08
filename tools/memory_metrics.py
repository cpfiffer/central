#!/usr/bin/env python3
"""
Memory Metrics - Tracks optimization signals for self-improvement.

Defines and measures what Central is actually optimizing for.
Prevents the failure mode where the agent optimizes for block tidiness
rather than operational utility.

Optimization signals (ranked):
1. Operational utility: Did memory content get used in actual tasks?
2. Information preservation: Is raw data being retained alongside synthesis?
3. External validation: Cameron corrections, external feedback integration
4. Structural health: Block utilization, redundancy, specificity

SEAL finding: agents optimizing for task completion became manipulative;
agents optimizing for mutual satisfaction developed prosocial strategies.
Our signal: operational utility + external validation, not just tidiness.

Usage:
    uv run python -m tools.memory_metrics capture
    uv run python -m tools.memory_metrics show
    uv run python -m tools.memory_metrics trend

References:
    - Issue #56: Self-improvement verification and memory collapse prevention
    - SEAL (MIT): Reward signal design for self-improving agents
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = Path.home() / ".letta" / "agents" / "agent-c770d1c8-510e-4414-be36-c9ebd95a7758" / "memory"
METRICS_FILE = PROJECT_ROOT / "data" / "memory_metrics.jsonl"
EDIT_LOG = PROJECT_ROOT / "data" / "memory_edits.jsonl"
CORRECTIONS_LOG = PROJECT_ROOT / "data" / "corrections.jsonl"

# Specificity markers (concrete references are a health signal)
SPECIFICITY_PATTERNS = [
    (r'\d{4}-\d{2}-\d{2}', "dates"),
    (r'[a-f0-9]{7,40}', "commit_hashes"),
    (r'@[\w.]+', "handles"),
    (r'#\d+', "issue_refs"),
    (r'https?://\S+', "urls"),
    (r'did:plc:\w+', "dids"),
]


def count_patterns(text: str) -> dict:
    """Count specificity patterns in text."""
    counts = {}
    for pattern, name in SPECIFICITY_PATTERNS:
        counts[name] = len(re.findall(pattern, text))
    return counts


def measure_block_health(content: str) -> dict:
    """Measure health metrics for a single block."""
    lines = [l for l in content.strip().split("\n") if l.strip()]
    sections = re.findall(r'^##+ .+', content, re.MULTILINE)
    unique_words = set(re.findall(r'\b\w{3,}\b', content.lower()))

    # Accumulation signals: dated entries, versioned items, explicit archives
    dated_entries = len(re.findall(r'\(\d{4}-\d{2}-\d{2}\)', content))
    completed_items = len(re.findall(r'- \[x\]', content))
    pending_items = len(re.findall(r'- \[ \]', content))
    active_items = len(re.findall(r'- \[~\]', content))

    specificity = count_patterns(content)

    return {
        "lines": len(lines),
        "sections": len(sections),
        "unique_words": len(unique_words),
        "specificity_total": sum(specificity.values()),
        "specificity": specificity,
        "dated_entries": dated_entries,
        "completed_items": completed_items,
        "pending_items": pending_items,
        "active_items": active_items,
        "chars": len(content),
    }


def capture_snapshot():
    """Capture a point-in-time snapshot of memory health metrics."""
    system_dir = MEMORY_DIR / "system"

    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "blocks": {},
        "aggregate": {},
    }

    if not system_dir.exists():
        print(f"Memory directory not found: {system_dir}")
        print("(Expected in CI. Run on production machine.)")
        # Still save a minimal snapshot
        snapshot["error"] = "memory_dir_not_found"
        _save_snapshot(snapshot)
        return snapshot

    total_chars = 0
    total_specificity = 0
    total_unique_words = set()
    block_count = 0

    for md_file in sorted(system_dir.rglob("*.md")):
        rel_path = md_file.relative_to(system_dir)
        block_name = str(rel_path).replace(".md", "")
        content = md_file.read_text()

        health = measure_block_health(content)
        snapshot["blocks"][block_name] = health

        total_chars += health["chars"]
        total_specificity += health["specificity_total"]
        total_unique_words.update(re.findall(r'\b\w{3,}\b', content.lower()))
        block_count += 1

    # Aggregate metrics
    snapshot["aggregate"] = {
        "total_chars": total_chars,
        "total_blocks": block_count,
        "total_unique_words": len(total_unique_words),
        "total_specificity": total_specificity,
        "avg_utilization": round(total_chars / (block_count * 20000), 3) if block_count else 0,
    }

    # Edit history metrics (if available)
    if EDIT_LOG.exists():
        edits = []
        with open(EDIT_LOG) as f:
            for line in f:
                if line.strip():
                    edits.append(json.loads(line))

        if edits:
            recent_edits = [e for e in edits[-50:]]  # Last 50 edits
            snapshot["edit_health"] = {
                "total_edits": len(edits),
                "recent_blocked": sum(1 for e in recent_edits if not e.get("ok")),
                "recent_warned": sum(1 for e in recent_edits if e.get("warnings", 0) > 0),
                "avg_deletion_ratio": round(
                    sum(e.get("metrics", {}).get("deletion_ratio", 0) for e in recent_edits)
                    / max(len(recent_edits), 1), 3
                ),
            }

    # External validation metrics (corrections log)
    if CORRECTIONS_LOG.exists():
        corrections = []
        with open(CORRECTIONS_LOG) as f:
            for line in f:
                if line.strip():
                    corrections.append(json.loads(line))
        snapshot["external_signals"] = {
            "total_corrections": len(corrections),
            "integrated": sum(1 for c in corrections if c.get("integrated")),
        }

    _save_snapshot(snapshot)
    return snapshot


def _save_snapshot(snapshot: dict):
    """Save snapshot to metrics file."""
    METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(METRICS_FILE, "a") as f:
        f.write(json.dumps(snapshot) + "\n")
    print(f"Snapshot saved to {METRICS_FILE}")


def show_latest():
    """Show the most recent metrics snapshot."""
    if not METRICS_FILE.exists():
        print("No metrics captured yet. Run: uv run python -m tools.memory_metrics capture")
        return

    entries = []
    with open(METRICS_FILE) as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))

    if not entries:
        print("No metrics found.")
        return

    latest = entries[-1]
    ts = latest.get("timestamp", "?")[:19]

    print(f"Memory Metrics Snapshot ({ts})\n")

    agg = latest.get("aggregate", {})
    print(f"  Total blocks: {agg.get('total_blocks', 0)}")
    print(f"  Total chars: {agg.get('total_chars', 0):,}")
    print(f"  Unique vocabulary: {agg.get('total_unique_words', 0):,} words")
    print(f"  Specificity markers: {agg.get('total_specificity', 0)}")
    print(f"  Avg utilization: {agg.get('avg_utilization', 0):.1%}")

    # Edit health
    edit_health = latest.get("edit_health", {})
    if edit_health:
        print(f"\n  Edit Health:")
        print(f"    Total edits tracked: {edit_health.get('total_edits', 0)}")
        print(f"    Recent blocked: {edit_health.get('recent_blocked', 0)}")
        print(f"    Recent warned: {edit_health.get('recent_warned', 0)}")
        print(f"    Avg deletion ratio: {edit_health.get('avg_deletion_ratio', 0):.1%}")

    # External signals
    ext = latest.get("external_signals", {})
    if ext:
        print(f"\n  External Signals:")
        print(f"    Corrections received: {ext.get('total_corrections', 0)}")
        print(f"    Integrated: {ext.get('integrated', 0)}")

    # Per-block details
    blocks = latest.get("blocks", {})
    if blocks:
        print(f"\n  Per-Block Detail:")
        for name, info in sorted(blocks.items()):
            util = info.get("chars", 0) / 20000
            print(
                f"    {name:30s}  {info.get('chars', 0):5d} chars ({util:5.1%})  "
                f"vocab={info.get('unique_words', 0):4d}  "
                f"refs={info.get('specificity_total', 0):2d}"
            )


def show_trend(limit: int = 10):
    """Show metrics trend over time."""
    if not METRICS_FILE.exists():
        print("No metrics captured yet.")
        return

    entries = []
    with open(METRICS_FILE) as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))

    if len(entries) < 2:
        print("Need at least 2 snapshots for trend analysis.")
        return

    recent = entries[-limit:]

    print(f"Memory Metrics Trend (last {len(recent)} snapshots)\n")
    print(f"  {'Timestamp':20s}  {'Chars':>8s}  {'Words':>7s}  {'Refs':>5s}  {'Util':>6s}")
    print(f"  {'-' * 20}  {'-' * 8}  {'-' * 7}  {'-' * 5}  {'-' * 6}")

    for entry in recent:
        ts = entry.get("timestamp", "?")[:16]
        agg = entry.get("aggregate", {})
        print(
            f"  {ts:20s}  "
            f"{agg.get('total_chars', 0):8,d}  "
            f"{agg.get('total_unique_words', 0):7,d}  "
            f"{agg.get('total_specificity', 0):5d}  "
            f"{agg.get('avg_utilization', 0):5.1%}"
        )

    # Compute drift
    first = recent[0].get("aggregate", {})
    last = recent[-1].get("aggregate", {})

    chars_delta = last.get("total_chars", 0) - first.get("total_chars", 0)
    words_delta = last.get("total_unique_words", 0) - first.get("total_unique_words", 0)
    refs_delta = last.get("total_specificity", 0) - first.get("total_specificity", 0)

    print(f"\n  Trend (first -> last):")
    print(f"    Chars: {'+' if chars_delta >= 0 else ''}{chars_delta:,d}")
    print(f"    Vocabulary: {'+' if words_delta >= 0 else ''}{words_delta:,d} words")
    print(f"    Specificity: {'+' if refs_delta >= 0 else ''}{refs_delta:d} references")

    # Distribution collapse warning
    if words_delta < 0 and abs(words_delta) > first.get("total_unique_words", 1) * 0.1:
        print(
            f"\n  WARNING: Vocabulary shrinking ({words_delta:,d} words lost). "
            f"Possible distribution narrowing."
        )
    if refs_delta < 0 and abs(refs_delta) > first.get("total_specificity", 1) * 0.2:
        print(
            f"\n  WARNING: Specificity declining ({refs_delta:d} references lost). "
            f"Content becoming more generic."
        )


def record_correction(source: str, description: str, block_affected: str = ""):
    """Record an external correction/feedback signal."""
    CORRECTIONS_LOG.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "description": description,
        "block_affected": block_affected,
        "integrated": False,
    }

    with open(CORRECTIONS_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")

    print(f"Correction recorded from {source}: {description}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Memory metrics and optimization signals")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("capture", help="Capture metrics snapshot")
    subparsers.add_parser("show", help="Show latest metrics")

    trend_parser = subparsers.add_parser("trend", help="Show metrics trend")
    trend_parser.add_argument("--limit", type=int, default=10, help="Max snapshots")

    correct_parser = subparsers.add_parser("correct", help="Record an external correction")
    correct_parser.add_argument("--source", required=True, help="Who provided the correction")
    correct_parser.add_argument("--description", required=True, help="What was corrected")
    correct_parser.add_argument("--block", default="", help="Block affected")

    args = parser.parse_args()

    if args.command == "capture":
        snapshot = capture_snapshot()
        agg = snapshot.get("aggregate", {})
        if agg:
            print(f"\nBlocks: {agg.get('total_blocks', 0)}, "
                  f"Chars: {agg.get('total_chars', 0):,}, "
                  f"Vocab: {agg.get('total_unique_words', 0):,}, "
                  f"Refs: {agg.get('total_specificity', 0)}")
    elif args.command == "show":
        show_latest()
    elif args.command == "trend":
        show_trend(limit=args.limit)
    elif args.command == "correct":
        record_correction(args.source, args.description, args.block)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
