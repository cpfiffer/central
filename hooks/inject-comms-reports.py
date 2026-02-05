#!/usr/bin/env python3
"""
Inject Comms Reports Hook (PostToolUse)

After a Task completes, check if it was comms and inject the report
back into Central's context via hookSpecificOutput.additionalContext.
"""

import sys
import json
from datetime import datetime, timezone
from pathlib import Path

# Comms agent ID
COMMS_AGENT_ID = "agent-a856f614-7654-44ba-a35f-c817d477dded"

# Output directory for logs
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
    
    event_type = input_data.get("event_type", "")
    tool_name = input_data.get("tool_name", "")
    
    # Only process PostToolUse for Task
    if event_type != "PostToolUse" or tool_name != "Task":
        sys.exit(0)
    
    # Get tool input and result
    tool_input = input_data.get("tool_input", {})
    tool_result = input_data.get("tool_result", {})
    
    # Check if this was comms by agent_id or subagent_type
    agent_id = tool_input.get("agent_id", "")
    subagent_type = tool_input.get("subagent_type", "")
    
    is_comms = (agent_id == COMMS_AGENT_ID or subagent_type == "comms")
    if not is_comms:
        sys.exit(0)
    
    # Get the result output
    if isinstance(tool_result, dict):
        result = tool_result.get("output", "") or str(tool_result)
    else:
        result = str(tool_result) if tool_result else ""
    
    description = tool_input.get("description", "comms task")
    
    if not result or len(result) < 20:
        sys.exit(0)
    
    # Ensure output directory exists
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Write latest report to file for reference
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    latest_content = f"""# Comms Report
**Time:** {timestamp}
**Task:** {description}

## Report
{result}
"""
    
    LATEST_FILE.write_text(latest_content)
    
    # Append to rolling log
    log_entry = f"\n---\n## {timestamp} - {description}\n{result[:1000]}\n"
    with open(LOG_FILE, "a") as f:
        f.write(log_entry)
    
    # Trim log if too large (keep last 50KB)
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > 50000:
        content = LOG_FILE.read_text()
        LOG_FILE.write_text(content[-40000:])
    
    # OUTPUT: Inject via hookSpecificOutput.additionalContext
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": f"📋 **Comms Report** ({description}):\n\n{result[:2000]}"
        }
    }
    
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
