#!/usr/bin/env python3
"""
Read Comms Reports Hook

PreToolUse hook that injects latest comms reports into context.
Runs on every tool call to keep Central aware of what comms observed.

Outputs a system reminder with the latest report if available and recent.
"""

import sys
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Report location
SCRIPT_DIR = Path(__file__).parent.parent
LATEST_FILE = SCRIPT_DIR / "drafts" / "comms-reports" / "latest.md"

# Track last injection to avoid spam
LAST_INJECTED_FILE = SCRIPT_DIR / "drafts" / "comms-reports" / ".last-injected"


def get_last_injected_time() -> datetime | None:
    """Get the timestamp of last injection."""
    if not LAST_INJECTED_FILE.exists():
        return None
    try:
        ts = LAST_INJECTED_FILE.read_text().strip()
        return datetime.fromisoformat(ts)
    except:
        return None


def mark_injected():
    """Mark that we just injected."""
    LAST_INJECTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_INJECTED_FILE.write_text(datetime.now(timezone.utc).isoformat())


def main():
    """Process hook input."""
    try:
        input_data = json.load(sys.stdin)
    except:
        sys.exit(0)
    
    event_type = input_data.get("event_type")
    
    # Only process PreToolUse
    if event_type != "PreToolUse":
        sys.exit(0)
    
    # Check if latest report exists
    if not LATEST_FILE.exists():
        sys.exit(0)
    
    # Check file age - only inject if modified in last 10 minutes
    mtime = datetime.fromtimestamp(LATEST_FILE.stat().st_mtime, tz=timezone.utc)
    age = datetime.now(timezone.utc) - mtime
    if age > timedelta(minutes=10):
        sys.exit(0)
    
    # Check if we already injected recently (within 5 minutes)
    last_injected = get_last_injected_time()
    if last_injected:
        since_injection = datetime.now(timezone.utc) - last_injected
        if since_injection < timedelta(minutes=5):
            sys.exit(0)
    
    # Read and inject
    content = LATEST_FILE.read_text()
    if not content or len(content) < 50:
        sys.exit(0)
    
    # Mark injected
    mark_injected()
    
    # Output as JSON with message field - this becomes a system reminder
    output = {
        "message": f"<system-reminder>\n📋 **Comms Report (auto-injected)**\n\n{content[:2000]}\n</system-reminder>"
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
