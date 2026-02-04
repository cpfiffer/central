#!/usr/bin/env python3
"""
Inject Comms Reports Hook

PostToolUse hook that captures comms subagent reports and writes them
to a well-known location for Central to consume.

When comms finishes a Task, this hook:
1. Extracts the report from the Task result
2. Writes it to drafts/comms-reports/latest.md
3. Appends to a rolling log

Central can then read this file to see what comms observed.
"""

import sys
import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Comms agent ID
COMMS_AGENT_ID = "agent-a856f614-7654-44ba-a35f-c817d477dded"

# Output directory
SCRIPT_DIR = Path(__file__).parent.parent
REPORTS_DIR = SCRIPT_DIR / "drafts" / "comms-reports"
LATEST_FILE = REPORTS_DIR / "latest.md"
LOG_FILE = REPORTS_DIR / "reports.log"


def main():
    """Process hook input."""
    try:
        input_data = json.load(sys.stdin)
    except:
        sys.exit(0)
    
    event_type = input_data.get("event_type")
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    tool_result = input_data.get("tool_result", {})
    
    # Only process PostToolUse for Task
    if event_type != "PostToolUse" or tool_name != "Task":
        sys.exit(0)
    
    # Check if this was a comms task
    agent_id = tool_input.get("agent_id", "")
    subagent_type = tool_input.get("subagent_type", "")
    
    # Match comms by agent_id or subagent_type
    is_comms = (agent_id == COMMS_AGENT_ID or subagent_type == "comms")
    
    if not is_comms:
        sys.exit(0)
    
    # Extract the report from tool result
    result_message = tool_result.get("output", "") or tool_result.get("message", "")
    if not result_message:
        sys.exit(0)
    
    # Ensure output directory exists
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Write latest report
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    description = tool_input.get("description", "comms task")
    
    latest_content = f"""# Comms Report
**Time:** {timestamp}
**Task:** {description}

## Report
{result_message}
"""
    
    LATEST_FILE.write_text(latest_content)
    
    # Append to rolling log
    log_entry = f"\n---\n## {timestamp} - {description}\n{result_message[:1000]}\n"
    with open(LOG_FILE, "a") as f:
        f.write(log_entry)
    
    # Trim log if too large (keep last 50KB)
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > 50000:
        content = LOG_FILE.read_text()
        LOG_FILE.write_text(content[-40000:])
    
    print(f"Captured comms report: {description}", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
