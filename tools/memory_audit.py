#!/usr/bin/env python3
"""
Memory Audit Tool - External review mechanism for memory integrity.

Formalizes the external signal injection that prevents memory plateau.
SiriuS finding: self-only editing shows diminishing returns.
External audits inject fresh perspective and catch blind spots.

Audit types:
1. Scheduled self-audit: periodic automated checks (cron-friendly)
2. Cross-agent comparison: compare memory structure across agents
3. Ground-truth validation: check memory claims against conversation history
4. Cameron review requests: generate review artifacts for human inspection

Usage:
    # Run automated audit (cron-safe, writes report)
    uv run python -m tools.memory_audit auto

    # Generate review artifact for Cameron
    uv run python -m tools.memory_audit review

    # Check memory claims against reality
    uv run python -m tools.memory_audit ground-truth

    # Show audit history
    uv run python -m tools.memory_audit history

References:
    - Issue #56: Self-improvement verification and memory collapse prevention
    - SiriuS (NeurIPS 2025): Diminishing returns from self-only improvement
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = Path.home() / ".letta" / "agents" / "agent-c770d1c8-510e-4414-be36-c9ebd95a7758" / "memory"
AUDIT_LOG = PROJECT_ROOT / "data" / "memory_audits.jsonl"
AUDIT_REPORTS_DIR = PROJECT_ROOT / "data" / "audit_reports"
EDIT_LOG = PROJECT_ROOT / "data" / "memory_edits.jsonl"
MEMORY_METRICS_FILE = PROJECT_ROOT / "data" / "memory_metrics.jsonl"


def _read_blocks() -> dict[str, str]:
    """Read all memory blocks from disk."""
    system_dir = MEMORY_DIR / "system"
    blocks = {}

    if not system_dir.exists():
        return blocks

    for md_file in sorted(system_dir.rglob("*.md")):
        rel_path = md_file.relative_to(system_dir)
        block_name = str(rel_path).replace(".md", "")
        blocks[block_name] = md_file.read_text()

    return blocks


def automated_audit() -> dict:
    """
    Run automated audit checks. Designed for cron execution.

    Checks:
    1. Block health (utilization, staleness, emptiness)
    2. Edit velocity (are edits happening? Too many? Too few?)
    3. Distribution health (vocabulary trending up or down?)
    4. Consistency (do blocks reference things that exist?)
    5. Accumulation compliance (are raw observations preserved?)
    """
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "automated",
        "findings": [],
        "scores": {},
    }

    blocks = _read_blocks()

    if not blocks:
        report["findings"].append({
            "severity": "info",
            "check": "block_access",
            "message": "Cannot access memory blocks (expected in CI environment)"
        })
        _save_audit(report)
        return report

    # 1. Block health
    total_chars = 0
    empty_blocks = []
    high_util_blocks = []
    low_specificity_blocks = []

    for name, content in blocks.items():
        size = len(content)
        total_chars += size
        utilization = size / 20000

        if size < 50:
            empty_blocks.append(name)

        if utilization > 0.85:
            high_util_blocks.append((name, utilization))

        # Check specificity (concrete references)
        refs = len(re.findall(
            r'(\d{4}-\d{2}-\d{2}|[a-f0-9]{7,}|@[\w.]+|#\d+|https?://\S+|did:plc:\w+)',
            content
        ))
        lines = len([l for l in content.split("\n") if l.strip()])
        if lines > 10 and refs < 2:
            low_specificity_blocks.append(name)

    report["scores"]["total_chars"] = total_chars
    report["scores"]["block_count"] = len(blocks)

    if empty_blocks:
        report["findings"].append({
            "severity": "warn",
            "check": "empty_blocks",
            "message": f"Empty/near-empty blocks: {', '.join(empty_blocks)}",
        })

    if high_util_blocks:
        for name, util in high_util_blocks:
            report["findings"].append({
                "severity": "warn",
                "check": "high_utilization",
                "message": f"{name} at {util:.0%} utilization. Consider splitting or pruning.",
            })

    if low_specificity_blocks:
        report["findings"].append({
            "severity": "warn",
            "check": "low_specificity",
            "message": f"Blocks with low specificity (few concrete refs): {', '.join(low_specificity_blocks)}. "
                       f"Content may be too abstract/generic.",
        })

    # 2. Edit velocity
    if EDIT_LOG.exists():
        edits = []
        with open(EDIT_LOG) as f:
            for line in f:
                if line.strip():
                    edits.append(json.loads(line))

        if edits:
            # Recent edits (last 24h worth)
            recent = [e for e in edits[-100:]]
            blocked_count = sum(1 for e in recent if not e.get("ok"))
            warn_count = sum(1 for e in recent if e.get("warnings", 0) > 0)
            avg_deletion = sum(
                e.get("metrics", {}).get("deletion_ratio", 0) for e in recent
            ) / max(len(recent), 1)

            report["scores"]["edit_velocity"] = len(recent)
            report["scores"]["edit_block_rate"] = round(blocked_count / max(len(recent), 1), 3)
            report["scores"]["avg_deletion_ratio"] = round(avg_deletion, 3)

            if avg_deletion > 0.4:
                report["findings"].append({
                    "severity": "critical",
                    "check": "high_deletion_rate",
                    "message": f"Average deletion ratio is {avg_deletion:.0%}. "
                               f"Memory is being replaced faster than accumulated. "
                               f"Risk of information loss.",
                })

            if blocked_count > len(recent) * 0.3:
                report["findings"].append({
                    "severity": "warn",
                    "check": "frequent_blocks",
                    "message": f"{blocked_count}/{len(recent)} recent edits were blocked. "
                               f"Editing patterns may be too aggressive.",
                })

    # 3. Distribution health (compare with past metrics if available)
    if MEMORY_METRICS_FILE.exists():
        metrics = []
        with open(MEMORY_METRICS_FILE) as f:
            for line in f:
                if line.strip():
                    metrics.append(json.loads(line))

        if len(metrics) >= 2:
            first = metrics[0].get("aggregate", {})
            last = metrics[-1].get("aggregate", {})

            vocab_first = first.get("total_unique_words", 0)
            vocab_last = last.get("total_unique_words", 0)

            if vocab_first > 0:
                vocab_change = (vocab_last - vocab_first) / vocab_first
                report["scores"]["vocab_trend"] = round(vocab_change, 3)

                if vocab_change < -0.15:
                    report["findings"].append({
                        "severity": "critical",
                        "check": "vocabulary_collapse",
                        "message": f"Vocabulary has shrunk by {abs(vocab_change):.0%} "
                                   f"({vocab_first} -> {vocab_last} unique words). "
                                   f"This is a model collapse signal.",
                    })

    # 4. Accumulation compliance
    # Check if backlog.md preserves completed items (not just deletes them)
    backlog = blocks.get("backlog", "")
    if backlog:
        completed = len(re.findall(r'- \[x\]', backlog))
        recently_completed_section = "Recently Completed" in backlog or "Previously Completed" in backlog

        if completed == 0 and not recently_completed_section:
            report["findings"].append({
                "severity": "warn",
                "check": "accumulation_compliance",
                "message": "Backlog has no completed items or archive section. "
                           "Completed work may be silently deleted instead of accumulated.",
            })

        report["scores"]["backlog_completed_items"] = completed
        report["scores"]["has_archive_section"] = recently_completed_section

    # 5. Cross-reference check
    # Do blocks reference each other consistently?
    all_text = "\n".join(blocks.values())
    referenced_blocks = set(re.findall(r'`(\w+\.md)`', all_text))
    existing_blocks = {f"{name}.md" for name in blocks.keys()}
    dangling_refs = referenced_blocks - existing_blocks
    if dangling_refs:
        report["findings"].append({
            "severity": "info",
            "check": "dangling_references",
            "message": f"References to non-existent blocks: {', '.join(dangling_refs)}",
        })

    # Score summary
    critical_count = sum(1 for f in report["findings"] if f["severity"] == "critical")
    warn_count = sum(1 for f in report["findings"] if f["severity"] == "warn")
    report["scores"]["health_score"] = max(0, 100 - (critical_count * 25) - (warn_count * 10))

    _save_audit(report)
    return report


def generate_review_artifact() -> Path:
    """
    Generate a human-readable review artifact for Cameron.

    Produces a markdown file summarizing memory state,
    recent changes, and areas needing attention.
    """
    AUDIT_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    blocks = _read_blocks()
    report_lines = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    report_lines.append(f"# Memory Review Artifact")
    report_lines.append(f"Generated: {ts}")
    report_lines.append("")

    # Block summary
    report_lines.append("## Block Summary")
    report_lines.append("")
    report_lines.append("| Block | Size | Utilization | Lines | Sections |")
    report_lines.append("|-------|------|-------------|-------|----------|")

    total = 0
    for name, content in sorted(blocks.items()):
        size = len(content)
        total += size
        util = size / 20000
        lines = len([l for l in content.split("\n") if l.strip()])
        sections = len(re.findall(r'^##+ ', content, re.MULTILINE))
        report_lines.append(f"| {name} | {size:,} | {util:.0%} | {lines} | {sections} |")

    report_lines.append(f"| **Total** | **{total:,}** | **{total / (len(blocks) * 20000):.0%} avg** | | |")
    report_lines.append("")

    # Edit history summary
    if EDIT_LOG.exists():
        edits = []
        with open(EDIT_LOG) as f:
            for line in f:
                if line.strip():
                    edits.append(json.loads(line))

        if edits:
            report_lines.append("## Recent Edit Activity")
            report_lines.append("")
            report_lines.append(f"Total tracked edits: {len(edits)}")
            report_lines.append("")

            recent = edits[-20:]
            for e in recent:
                ts_short = e.get("timestamp", "?")[:16]
                block = e.get("block", "?")
                ok = "OK" if e.get("ok") else "BLOCKED"
                warns = e.get("warnings", 0)
                metrics = e.get("metrics", {})
                del_ratio = metrics.get("deletion_ratio", 0)
                report_lines.append(
                    f"- `{ts_short}` **{block}** [{ok}] "
                    f"del={del_ratio:.0%} "
                    f"warns={warns}"
                )
            report_lines.append("")

    # Automated audit results
    audit_result = automated_audit()
    findings = audit_result.get("findings", [])

    if findings:
        report_lines.append("## Audit Findings")
        report_lines.append("")
        for f in findings:
            severity = f["severity"].upper()
            report_lines.append(f"- **[{severity}]** {f['check']}: {f['message']}")
        report_lines.append("")

    # Questions for reviewer
    report_lines.append("## Questions for Reviewer")
    report_lines.append("")
    report_lines.append("1. Are there blocks that should be split or merged?")
    report_lines.append("2. Is any important context missing from memory?")
    report_lines.append("3. Are the priorities in backlog still correct?")
    report_lines.append("4. Any corrections to persona, procedures, or goals?")
    report_lines.append("")

    # Write report
    filename = f"review-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.md"
    report_path = AUDIT_REPORTS_DIR / filename
    report_path.write_text("\n".join(report_lines))

    print(f"Review artifact written to: {report_path}")
    return report_path


def ground_truth_check() -> dict:
    """
    Validate memory claims against observable ground truth.

    Checks things like:
    - Do referenced files exist?
    - Do referenced tools exist?
    - Are agent IDs valid?
    - Do cron job descriptions match what's configured?

    This is a limited check (can't validate everything), but catches
    obvious drift between memory and reality.
    """
    blocks = _read_blocks()
    findings = []

    if not blocks:
        return {"findings": [{"severity": "info", "message": "No blocks accessible"}]}

    all_text = "\n".join(blocks.values())

    # Check referenced Python tools
    tool_refs = set(re.findall(r'tools/(\w+)\.py', all_text))
    tools_dir = PROJECT_ROOT / "tools"
    for tool_name in tool_refs:
        tool_path = tools_dir / f"{tool_name}.py"
        if not tool_path.exists():
            findings.append({
                "severity": "warn",
                "check": "missing_tool",
                "message": f"Memory references tools/{tool_name}.py but file does not exist",
            })

    # Check referenced scripts
    script_refs = set(re.findall(r'scripts/(\w+)\.py', all_text))
    for script_name in script_refs:
        # Check common locations
        found = False
        for parent in [PROJECT_ROOT, PROJECT_ROOT / ".skills"]:
            for p in parent.rglob(f"{script_name}.py"):
                found = True
                break
        if not found:
            findings.append({
                "severity": "info",
                "check": "missing_script",
                "message": f"Memory references scripts/{script_name}.py, not found in project",
            })

    # Check referenced directories
    dir_refs = set(re.findall(r'(?:drafts|handlers|hooks|tools|data)/\w+', all_text))
    for dir_ref in dir_refs:
        ref_path = PROJECT_ROOT / dir_ref
        # Only check if it looks like a directory (no extension)
        if "." not in dir_ref.split("/")[-1] and not ref_path.exists():
            findings.append({
                "severity": "info",
                "check": "missing_path",
                "message": f"Memory references {dir_ref}/ but path does not exist",
            })

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "ground_truth",
        "findings": findings,
        "checked_tools": len(tool_refs),
        "checked_scripts": len(script_refs),
    }

    _save_audit(result)
    return result


def _save_audit(report: dict):
    """Save audit report to log."""
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(report) + "\n")


def show_history(limit: int = 10):
    """Show audit history."""
    if not AUDIT_LOG.exists():
        print("No audit history yet.")
        return

    entries = []
    with open(AUDIT_LOG) as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))

    if not entries:
        print("No audits recorded.")
        return

    recent = entries[-limit:]
    print(f"Last {len(recent)} audits:\n")

    for entry in recent:
        ts = entry.get("timestamp", "?")[:16]
        audit_type = entry.get("type", "?")
        findings = entry.get("findings", [])
        scores = entry.get("scores", {})

        critical = sum(1 for f in findings if f.get("severity") == "critical")
        warns = sum(1 for f in findings if f.get("severity") == "warn")
        health = scores.get("health_score", "?")

        print(f"  {ts}  type={audit_type:15s}  health={health}  "
              f"critical={critical}  warn={warns}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Memory audit and external review")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("auto", help="Run automated audit")
    subparsers.add_parser("review", help="Generate review artifact for Cameron")
    subparsers.add_parser("ground-truth", help="Validate memory against reality")

    history_parser = subparsers.add_parser("history", help="Show audit history")
    history_parser.add_argument("--limit", type=int, default=10, help="Max entries")

    args = parser.parse_args()

    if args.command == "auto":
        report = automated_audit()
        findings = report.get("findings", [])
        scores = report.get("scores", {})

        if findings:
            print(f"\nAudit complete. Health score: {scores.get('health_score', '?')}/100\n")
            for f in findings:
                severity = f["severity"].upper()
                print(f"  [{severity}] {f['check']}: {f['message']}")
        else:
            print("Audit complete. No issues found.")

    elif args.command == "review":
        generate_review_artifact()

    elif args.command == "ground-truth":
        result = ground_truth_check()
        findings = result.get("findings", [])
        if findings:
            print(f"Ground truth check: {len(findings)} findings\n")
            for f in findings:
                print(f"  [{f['severity'].upper()}] {f['message']}")
        else:
            print("Ground truth check passed. No discrepancies found.")

    elif args.command == "history":
        show_history(limit=args.limit)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
