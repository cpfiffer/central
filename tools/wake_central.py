#!/usr/bin/env python3
"""
Wake Central - Self-Invocation Tool

Triggers a Letta Code session with Central when important conditions are met.
Used by mention_listener.py and other daemons for self-directed attention.

Usage:
  uv run python -m tools.wake_central "Reason for waking up"
  uv run python -m tools.wake_central --critical "Cameron mentioned you"
  uv run python -m tools.wake_central --scheduled "4-hour check-in"

This requires the Letta Code CLI to be available and configured.
"""

import subprocess
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

# Central's agent ID
CENTRAL_AGENT_ID = "agent-c770d1c8-510e-4414-be36-c9ebd95a7758"

# Log file
LOG_FILE = Path(__file__).parent.parent / "logs" / "wake.log"


def log(message: str):
    """Append to wake log."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def wake_central(reason: str, priority: str = "MEDIUM"):
    """
    Wake Central by invoking a Letta Code session.
    
    Uses the CLI to send a message, which will start a new session.
    """
    log(f"Waking Central ({priority}): {reason}")
    
    prompt = f"""Self-directed wake-up triggered.

**Priority:** {priority}
**Reason:** {reason}
**Time:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}

Review the situation and take appropriate action. If this is a false alarm, acknowledge and return.
"""
    
    # Check if Central is already active (has .central-active file)
    active_file = Path(__file__).parent.parent / ".central-active"
    if active_file.exists():
        log(f"Central already active - skipping wake ({reason})")
        print(f"Central already active. Reason logged: {reason}")
        return
    
    # Use Letta Code CLI to send message (this will start a new session)
    # The CLI path might vary - try common locations
    cli_paths = [
        "letta",  # Global install
        os.path.expanduser("~/.nvm/versions/node/v22.5.1/bin/letta"),  # NVM install
    ]
    
    cli = None
    for path in cli_paths:
        try:
            result = subprocess.run([path, "--version"], capture_output=True, timeout=5)
            if result.returncode == 0:
                cli = path
                break
        except:
            continue
    
    if not cli:
        log("ERROR: Could not find Letta Code CLI")
        print("Error: Letta Code CLI not found")
        return
    
    # Run the CLI in headless mode with -p
    try:
        log(f"Invoking Letta Code CLI in headless mode (yolo)")
        result = subprocess.run(
            [cli, "-p", prompt, "--yolo", "--max-turns", "10", "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=str(Path(__file__).parent.parent),  # Run from project root
        )
        
        if result.returncode == 0:
            log(f"Wake successful: {result.stdout[:200]}")
            print(f"Central response:\n{result.stdout}")
        else:
            log(f"Wake failed: {result.stderr}")
            print(f"Error: {result.stderr}")
    except subprocess.TimeoutExpired:
        log("Wake timed out (5 min)")
        print("Timeout: Central did not respond within 5 minutes")
    except Exception as e:
        log(f"Wake error: {e}")
        print(f"Error: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Wake Central for self-directed attention")
    parser.add_argument("reason", nargs="?", default="Scheduled check-in", help="Reason for waking")
    parser.add_argument("--critical", action="store_true", help="Mark as CRITICAL priority")
    parser.add_argument("--high", action="store_true", help="Mark as HIGH priority")
    parser.add_argument("--scheduled", action="store_true", help="Mark as scheduled wake-up")
    
    args = parser.parse_args()
    
    priority = "MEDIUM"
    if args.critical:
        priority = "CRITICAL"
    elif args.high:
        priority = "HIGH"
    elif args.scheduled:
        priority = "SCHEDULED"
    
    wake_central(args.reason, priority)


if __name__ == "__main__":
    main()
