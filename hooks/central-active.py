#!/usr/bin/env python3
"""
Central Active Hook - SessionStart/SessionEnd hook that tracks when Central is active.

When Central is active, the publisher can auto-approve CRITICAL/HIGH items.
When Central is inactive, CRITICAL/HIGH items stay in review queue.

This hook handles both SessionStart and SessionEnd events:
- SessionStart: Creates .central-active marker file
- SessionEnd: Removes .central-active marker file
"""

import sys
import json
from pathlib import Path

# Marker file location
CENTRAL_DIR = Path(__file__).parent.parent
ACTIVE_FILE = CENTRAL_DIR / ".central-active"


def main():
    """Process hook input."""
    try:
        input_data = json.load(sys.stdin)
    except:
        sys.exit(0)
    
    event_type = input_data.get("event_type", "")
    
    if event_type == "SessionStart":
        # Mark Central as active
        ACTIVE_FILE.write_text("active")
        print(f"Central session started - auto-approval enabled", file=sys.stderr)
        sys.exit(0)
    
    elif event_type == "SessionEnd":
        # Mark Central as inactive
        if ACTIVE_FILE.exists():
            ACTIVE_FILE.unlink()
        print(f"Central session ended - auto-approval disabled", file=sys.stderr)
        sys.exit(0)
    
    # Unknown event type
    sys.exit(0)


if __name__ == "__main__":
    main()
