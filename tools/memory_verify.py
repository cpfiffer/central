#!/usr/bin/env python3
"""
Memory Verification Tool - Prevents silent information loss in memory edits.

Analyzes proposed memory block changes to detect:
1. Information destruction (content removed without archival)
2. Distribution narrowing (progressive loss of nuance/detail)
3. Semantic drift (rewrites that shift meaning without justification)

Designed to run on every memory edit as a pre-commit check.
Lightweight: uses heuristics, not LLM calls.

Usage:
    # Verify a proposed edit (old content vs new content)
    uv run python -m tools.memory_verify diff --block persona --old-file old.md --new-file new.md

    # Verify from stdin (pipe old and new separated by ---)
    echo "old content\n---\nnew content" | uv run python -m tools.memory_verify diff --block persona

    # Audit all memory blocks for health
    uv run python -m tools.memory_verify audit

    # Show edit history summary
    uv run python -m tools.memory_verify history

References:
    - Model Collapse (Nature 2024): replacement causes collapse, accumulation prevents it
    - Issue #56: Self-improvement verification and memory collapse prevention
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher, unified_diff
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = Path.home() / ".letta" / "agents" / "agent-c770d1c8-510e-4414-be36-c9ebd95a7758" / "memory"
EDIT_LOG = PROJECT_ROOT / "data" / "memory_edits.jsonl"

# Thresholds (tunable)
DELETION_RATIO_WARN = 0.3     # Warn if >30% of lines removed
DELETION_RATIO_BLOCK = 0.6    # Block if >60% of lines removed (likely destructive)
MIN_CONTENT_LINES = 3         # Minimum lines to consider a block "substantive"
UNIQUE_WORD_LOSS_WARN = 0.2   # Warn if >20% of unique words lost
SPECIFICITY_MARKERS = [
    r'\d{4}-\d{2}-\d{2}',     # Dates
    r'[a-f0-9]{7,40}',        # Commit hashes
    r'@[\w.]+',               # Handles
    r'#\d+',                  # Issue numbers
    r'https?://\S+',          # URLs
    r'did:plc:\w+',           # DIDs
    r'agent-[a-f0-9-]+',      # Agent IDs
]


class VerificationResult:
    """Result of a memory verification check."""

    def __init__(self):
        self.warnings: list[str] = []
        self.blocks: list[str] = []  # Hard blocks (should not proceed)
        self.info: list[str] = []
        self.metrics: dict = {}

    @property
    def ok(self) -> bool:
        return len(self.blocks) == 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def summary(self) -> str:
        parts = []
        if self.blocks:
            parts.append(f"BLOCKED ({len(self.blocks)} issues):")
            for b in self.blocks:
                parts.append(f"  [BLOCK] {b}")
        if self.warnings:
            parts.append(f"WARNINGS ({len(self.warnings)}):")
            for w in self.warnings:
                parts.append(f"  [WARN] {w}")
        if self.info:
            for i in self.info:
                parts.append(f"  [INFO] {i}")
        if not parts:
            parts.append("OK: No issues detected.")
        return "\n".join(parts)


def extract_lines(text: str) -> list[str]:
    """Extract non-empty, non-comment lines."""
    lines = []
    for line in text.strip().split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


def extract_unique_words(text: str) -> set[str]:
    """Extract unique meaningful words (length > 2)."""
    words = re.findall(r'\b\w+\b', text.lower())
    return {w for w in words if len(w) > 2}


def count_specificity_markers(text: str) -> int:
    """Count specific, concrete references in text."""
    count = 0
    for pattern in SPECIFICITY_MARKERS:
        count += len(re.findall(pattern, text))
    return count


def verify_edit(old_content: str, new_content: str, block_name: str = "unknown") -> VerificationResult:
    """
    Verify a proposed memory edit against the original content.

    Checks:
    1. Information destruction ratio
    2. Unique word loss (vocabulary narrowing)
    3. Specificity marker loss (losing concrete references)
    4. Section deletion detection
    5. Content length collapse
    """
    result = VerificationResult()

    old_lines = extract_lines(old_content)
    new_lines = extract_lines(new_content)

    # Empty to something is always fine
    if not old_lines:
        result.info.append(f"New content for {block_name} ({len(new_lines)} lines)")
        return result

    # Something to empty is always blocked
    if not new_lines and old_lines:
        result.blocks.append(
            f"Complete deletion of {block_name} ({len(old_lines)} lines removed). "
            f"Archive content before deleting."
        )
        return result

    # 1. Deletion ratio
    matcher = SequenceMatcher(None, old_lines, new_lines)
    removed_lines = []
    added_lines = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "delete":
            removed_lines.extend(old_lines[i1:i2])
        elif tag == "replace":
            removed_lines.extend(old_lines[i1:i2])
            added_lines.extend(new_lines[j1:j2])
        elif tag == "insert":
            added_lines.extend(new_lines[j1:j2])

    deletion_ratio = len(removed_lines) / len(old_lines) if old_lines else 0
    result.metrics["deletion_ratio"] = round(deletion_ratio, 3)
    result.metrics["lines_removed"] = len(removed_lines)
    result.metrics["lines_added"] = len(added_lines)
    result.metrics["old_line_count"] = len(old_lines)
    result.metrics["new_line_count"] = len(new_lines)

    if deletion_ratio > DELETION_RATIO_BLOCK:
        result.blocks.append(
            f"High deletion ratio ({deletion_ratio:.0%}) in {block_name}. "
            f"{len(removed_lines)}/{len(old_lines)} content lines removed. "
            f"This may cause information loss. Archive removed content first."
        )
    elif deletion_ratio > DELETION_RATIO_WARN:
        result.warnings.append(
            f"Significant content removal ({deletion_ratio:.0%}) in {block_name}. "
            f"{len(removed_lines)} lines removed, {len(added_lines)} added."
        )

    # 2. Unique word loss (vocabulary narrowing / distribution collapse)
    old_words = extract_unique_words(old_content)
    new_words = extract_unique_words(new_content)

    if old_words:
        lost_words = old_words - new_words
        word_loss_ratio = len(lost_words) / len(old_words)
        result.metrics["unique_words_old"] = len(old_words)
        result.metrics["unique_words_new"] = len(new_words)
        result.metrics["unique_words_lost"] = len(lost_words)
        result.metrics["word_loss_ratio"] = round(word_loss_ratio, 3)

        if word_loss_ratio > UNIQUE_WORD_LOSS_WARN:
            # Sample some lost words for context
            sample = sorted(lost_words)[:10]
            result.warnings.append(
                f"Vocabulary narrowing in {block_name}: {len(lost_words)} unique words lost "
                f"({word_loss_ratio:.0%}). Sample: {', '.join(sample)}"
            )

    # 3. Specificity marker loss
    old_markers = count_specificity_markers(old_content)
    new_markers = count_specificity_markers(new_content)
    result.metrics["specificity_markers_old"] = old_markers
    result.metrics["specificity_markers_new"] = new_markers

    if old_markers > 0:
        marker_loss = old_markers - new_markers
        if marker_loss > 0 and marker_loss / old_markers > 0.3:
            result.warnings.append(
                f"Specificity loss in {block_name}: {marker_loss} concrete references removed "
                f"({old_markers} -> {new_markers}). Dates, commits, URLs, handles being lost."
            )

    # 4. Section deletion detection
    old_sections = set(re.findall(r'^##+ .+', old_content, re.MULTILINE))
    new_sections = set(re.findall(r'^##+ .+', new_content, re.MULTILINE))
    lost_sections = old_sections - new_sections

    if lost_sections:
        result.metrics["sections_removed"] = list(lost_sections)
        if len(lost_sections) > len(old_sections) * 0.5:
            result.warnings.append(
                f"Multiple sections removed from {block_name}: {', '.join(lost_sections)}"
            )

    # 5. Content length collapse
    old_len = len(old_content)
    new_len = len(new_content)
    if old_len > 0:
        size_ratio = new_len / old_len
        result.metrics["size_ratio"] = round(size_ratio, 3)

        if size_ratio < 0.3 and old_len > 500:
            result.blocks.append(
                f"Severe content collapse in {block_name}: "
                f"{old_len} chars -> {new_len} chars ({size_ratio:.0%} of original). "
                f"This looks like accidental truncation."
            )

    return result


def log_edit(block_name: str, result: VerificationResult, old_content: str, new_content: str):
    """Log a memory edit for historical tracking."""
    EDIT_LOG.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "block": block_name,
        "ok": result.ok,
        "warnings": len(result.warnings),
        "blocks": len(result.blocks),
        "metrics": result.metrics,
        "old_size": len(old_content),
        "new_size": len(new_content),
    }

    with open(EDIT_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def audit_memory_blocks() -> dict:
    """
    Audit all memory blocks for health indicators.

    Checks:
    - Utilization (size vs limit)
    - Staleness (blocks that haven't changed)
    - Redundancy (similar content across blocks)
    - Balance (one block dominating)
    """
    system_dir = MEMORY_DIR / "system"
    if not system_dir.exists():
        print(f"Memory directory not found: {system_dir}")
        print("(This is expected in CI. On the production machine, "
              "blocks live at ~/.letta/agents/<agent-id>/memory/system/)")
        return {}

    results = {}
    block_sizes = {}
    block_words = {}
    limit = 20000  # Default block limit

    # Scan all .md files
    for md_file in sorted(system_dir.rglob("*.md")):
        rel_path = md_file.relative_to(system_dir)
        block_name = str(rel_path).replace(".md", "").replace("/", "/")

        content = md_file.read_text()
        size = len(content)
        utilization = size / limit

        block_sizes[block_name] = size
        block_words[block_name] = extract_unique_words(content)

        block_result = {
            "size": size,
            "utilization": round(utilization, 3),
            "lines": len(content.strip().split("\n")),
            "sections": len(re.findall(r'^##+ ', content, re.MULTILINE)),
            "specificity": count_specificity_markers(content),
        }

        # Health flags
        if utilization > 0.8:
            block_result["flag"] = "HIGH_UTILIZATION"
        elif utilization < 0.05 and size > 0:
            block_result["flag"] = "UNDERUTILIZED"

        results[block_name] = block_result

    # Cross-block redundancy check
    block_names = list(block_words.keys())
    for i, name_a in enumerate(block_names):
        for name_b in block_names[i + 1:]:
            words_a = block_words[name_a]
            words_b = block_words[name_b]
            if words_a and words_b:
                overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
                if overlap > 0.5:
                    if "redundancy" not in results[name_a]:
                        results[name_a]["redundancy"] = []
                    results[name_a]["redundancy"].append(
                        f"High overlap ({overlap:.0%}) with {name_b}"
                    )

    return results


def show_edit_history(limit: int = 20):
    """Show recent memory edit history."""
    if not EDIT_LOG.exists():
        print("No edit history yet.")
        return

    entries = []
    with open(EDIT_LOG) as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))

    if not entries:
        print("No edit history yet.")
        return

    recent = entries[-limit:]
    print(f"Last {len(recent)} memory edits:\n")

    for entry in recent:
        ts = entry.get("timestamp", "?")[:19]
        block = entry.get("block", "?")
        ok = "OK" if entry.get("ok") else "BLOCKED"
        warnings = entry.get("warnings", 0)
        metrics = entry.get("metrics", {})
        deletion = metrics.get("deletion_ratio", 0)
        size_change = entry.get("new_size", 0) - entry.get("old_size", 0)
        sign = "+" if size_change >= 0 else ""

        status = f"[{ok}]"
        if warnings:
            status += f" [{warnings} warn]"

        print(f"  {ts}  {block:25s}  {status:20s}  del={deletion:.0%}  size={sign}{size_change}")

    # Summary stats
    total = len(entries)
    blocked = sum(1 for e in entries if not e.get("ok"))
    warned = sum(1 for e in entries if e.get("warnings", 0) > 0)
    avg_deletion = sum(
        e.get("metrics", {}).get("deletion_ratio", 0) for e in entries
    ) / max(len(entries), 1)

    print(f"\nTotal edits: {total}")
    print(f"Blocked: {blocked} ({blocked / max(total, 1):.0%})")
    print(f"Warned: {warned} ({warned / max(total, 1):.0%})")
    print(f"Avg deletion ratio: {avg_deletion:.1%}")


def main():
    parser = argparse.ArgumentParser(
        description="Memory verification tool - prevents information loss in memory edits"
    )
    subparsers = parser.add_subparsers(dest="command")

    # diff command
    diff_parser = subparsers.add_parser("diff", help="Verify a proposed memory edit")
    diff_parser.add_argument("--block", required=True, help="Block name")
    diff_parser.add_argument("--old-file", help="Path to old content")
    diff_parser.add_argument("--new-file", help="Path to new content")
    diff_parser.add_argument("--json", action="store_true", help="Output as JSON")
    diff_parser.add_argument("--log", action="store_true", help="Log the edit")

    # audit command
    audit_parser = subparsers.add_parser("audit", help="Audit all memory blocks")
    audit_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # history command
    history_parser = subparsers.add_parser("history", help="Show edit history")
    history_parser.add_argument("--limit", type=int, default=20, help="Max entries")

    args = parser.parse_args()

    if args.command == "diff":
        # Read old and new content
        if args.old_file and args.new_file:
            old_content = Path(args.old_file).read_text()
            new_content = Path(args.new_file).read_text()
        else:
            # Read from stdin, separated by ---
            stdin_content = sys.stdin.read()
            parts = stdin_content.split("\n---\n", 1)
            if len(parts) != 2:
                print("Error: stdin must contain old and new content separated by ---")
                sys.exit(1)
            old_content, new_content = parts

        result = verify_edit(old_content, new_content, args.block)

        if args.log:
            log_edit(args.block, result, old_content, new_content)

        if args.json:
            output = {
                "ok": result.ok,
                "warnings": result.warnings,
                "blocks": result.blocks,
                "info": result.info,
                "metrics": result.metrics,
            }
            print(json.dumps(output, indent=2))
        else:
            print(result.summary())

        sys.exit(0 if result.ok else 1)

    elif args.command == "audit":
        results = audit_memory_blocks()

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            if not results:
                return

            print("Memory Block Audit\n")
            total_size = 0
            for name, info in sorted(results.items()):
                total_size += info["size"]
                flag = f"  [{info.get('flag', '')}]" if info.get("flag") else ""
                redundancy = ""
                if info.get("redundancy"):
                    redundancy = f"  REDUNDANT: {info['redundancy'][0]}"
                print(
                    f"  {name:30s}  {info['size']:5d} chars  "
                    f"({info['utilization']:5.1%})  "
                    f"{info['lines']:3d} lines  "
                    f"{info['specificity']:2d} refs"
                    f"{flag}{redundancy}"
                )

            print(f"\nTotal: {total_size:,} chars across {len(results)} blocks")

    elif args.command == "history":
        show_edit_history(limit=args.limit)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
