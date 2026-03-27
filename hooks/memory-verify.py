#!/usr/bin/env python3
"""
Memory Verification Hook - Detect information loss in memory edits.

Runs before memory tool calls to flag:
- Content being removed without being archived
- Distribution narrowing (progressive loss of nuance)
- Large content deletions

Exit codes:
  0 - Allow the action
  2 - Block with warning to stderr
"""

import sys
import json
import os
from pathlib import Path

# Minimum content length to consider deletion significant
MIN_DELETION_LENGTH = 100

# Ratio threshold for "distribution narrowing" (content shrinking)
SHRINK_THRESHOLD = 0.5  # Flag if new content is < 50% of old


def get_memory_path() -> Path:
    """Get the memory directory path."""
    memory_dir = os.environ.get("MEMORY_DIR", Path.home() / ".letta" / "agents")
    # Can't determine exact agent ID from hook context, so we scan
    return Path(memory_dir)


def find_memory_file(path: str) -> Path | None:
    """Find a memory file by relative path."""
    memory_dir = get_memory_path()

    # Try exact path
    full_path = memory_dir / path
    if full_path.exists():
        return full_path

    # Try adding .md extension
    if not path.endswith(".md"):
        full_path = memory_dir / f"{path}.md"
        if full_path.exists():
            return full_path

    return None


def read_current_content(file_path: Path) -> str:
    """Read current content of a memory file."""
    if not file_path.exists():
        return ""
    try:
        return file_path.read_text()
    except Exception:
        return ""


def count_meaningful_content(text: str) -> int:
    """Count non-whitespace characters as measure of content."""
    return len("".join(text.split()))


def analyze_deletion(old: str, new: str) -> dict:
    """Analyze if the edit is destroying information."""
    old_lines = old.strip().split("\n")
    new_lines = new.strip().split("\n")

    old_content = count_meaningful_content(old)
    new_content = count_meaningful_content(new)

    # Check for significant content reduction
    if old_content > 0 and new_content < old_content * SHRINK_THRESHOLD:
        return {
            "warning": "distribution_narrowing",
            "message": f"Content reduced by {int((1 - new_content/old_content) * 100)}% ({old_content} → {new_content} chars)",
            "old_size": old_content,
            "new_size": new_content,
        }

    # Check for removed lines
    removed = set(old_lines) - set(new_lines)
    significant_removed = [l for l in removed if len(l.strip()) > MIN_DELETION_LENGTH]

    if significant_removed:
        return {
            "warning": "content_deletion",
            "message": f"{len(significant_removed)} significant lines removed",
            "examples": [l[:80] + "..." if len(l) > 80 else l for l in significant_removed[:3]],
        }

    return {"warning": None}


def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    event_type = input_data.get("event_type")
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Only check PreToolUse for memory tool
    if event_type != "PreToolUse":
        sys.exit(0)

    if tool_name != "memory":
        sys.exit(0)

    # Only check str_replace operations
    command = tool_input.get("command")
    if command != "str_replace":
        sys.exit(0)

    path = tool_input.get("path", "")
    old_string = tool_input.get("old_string", "")
    new_string = tool_input.get("new_string", "")

    # Find the memory file
    memory_file = find_memory_file(path)
    if not memory_file:
        # Can't verify - file doesn't exist yet or we can't find it
        sys.exit(0)

    # Read current content
    current_content = read_current_content(memory_file)

    # Analyze the change
    result = analyze_deletion(current_content, current_content.replace(old_string, new_string))

    if result.get("warning"):
        warning_type = result["warning"]
        message = result["message"]

        # Build warning message
        output = f"""⚠️  MEMORY VERIFICATION WARNING: {warning_type}

{message}

This edit may be destroying information. Consider:
- Archiving the removed content in a separate file
- Synthesizing rather than replacing
- Keeping raw observations alongside cleaned-up versions

To proceed anyway, you can either:
1. Justify why this content loss is intentional
2. Use a different approach (append, create new file)

Hook: hooks/memory-verify.py
"""
        if result.get("examples"):
            output += "\nRemoved content examples:\n"
            for ex in result["examples"]:
                output += f"  - {ex}\n"

        print(output, file=sys.stderr)
        # Exit 2 would block, but for now we just warn
        # sys.exit(2)

    # Allow the action
    sys.exit(0)


if __name__ == "__main__":
    main()
