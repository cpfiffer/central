#!/usr/bin/env python3
"""
Central Health Check

Monitors automation health and reports issues.
Run via cron or manually to check system status.

Usage:
    uv run python -m tools.healthcheck
    uv run python -m tools.healthcheck --alert  # Post alert if issues found
"""

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"
DRAFTS_DIR = Path(__file__).parent.parent / "drafts"
ALERT_STATE_FILE = LOG_DIR / "healthcheck_state.json"
ALERT_COOLDOWN_HOURS = 6  # Don't spam alerts


def check_log_errors(log_file: Path, hours: int = 24) -> list[str]:
    """Check log file for errors in the last N hours."""
    if not log_file.exists():
        return [f"{log_file.name}: File not found"]
    
    errors = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    
    content = log_file.read_text()
    lines = content.strip().split("\n") if content.strip() else []
    
    # Check for common error patterns
    error_patterns = ["error", "Error", "ERROR", "failed", "Failed", "FAILED", "not found"]
    
    recent_errors = 0
    for line in lines[-100:]:  # Check last 100 lines
        if any(p in line for p in error_patterns):
            recent_errors += 1
    
    if recent_errors > 5:
        errors.append(f"{log_file.name}: {recent_errors} errors in recent logs")
    
    return errors


def check_queue_depth() -> dict:
    """Check pending items in draft queues."""
    queues = {
        "bluesky": len(list(DRAFTS_DIR.glob("bluesky/*.txt"))),
        "x": len(list(DRAFTS_DIR.glob("x/*.txt"))),
        "review": len(list(DRAFTS_DIR.glob("review/*.txt"))),
    }
    return queues


def check_last_publish() -> tuple[datetime | None, int]:
    """Check when we last published and how many in last 24h."""
    published_dir = DRAFTS_DIR / "published"
    if not published_dir.exists():
        return None, 0
    
    files = list(published_dir.glob("*.txt"))
    if not files:
        return None, 0
    
    # Get most recent by filename (timestamp prefix)
    files.sort(key=lambda f: f.name, reverse=True)
    
    # Count last 24h
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_count = 0
    latest_time = None
    
    for f in files:
        try:
            # Filename format: 1770098232238-platform-...
            ts = int(f.name.split("-")[0])
            file_time = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            if latest_time is None:
                latest_time = file_time
            if file_time > cutoff:
                recent_count += 1
        except (ValueError, IndexError):
            continue
    
    return latest_time, recent_count


def check_xrpc_indexer() -> bool:
    """Check if XRPC indexer API is healthy."""
    import urllib.request
    import urllib.error
    
    try:
        req = urllib.request.Request(
            "https://comind-indexer.fly.dev/health",
            headers={"User-Agent": "central-healthcheck"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


def check_cron_running() -> bool:
    """Check if cron jobs are configured."""
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        return "central" in result.stdout.lower() or "responder" in result.stdout
    except:
        return False


def run_healthcheck() -> dict:
    """Run all health checks and return status."""
    status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "healthy": True,
        "issues": [],
        "metrics": {},
    }
    
    # Check logs for errors
    for log_name in ["responder.log", "handler.log", "publisher.log", "x-responder.log", "x-handler.log"]:
        log_path = LOG_DIR / log_name
        errors = check_log_errors(log_path)
        status["issues"].extend(errors)
    
    # Check queue depths
    queues = check_queue_depth()
    status["metrics"]["queues"] = queues
    
    # Alert if review queue is large
    if queues["review"] > 10:
        status["issues"].append(f"Review queue backlog: {queues['review']} items")
    
    # Check last publish
    last_publish, recent_count = check_last_publish()
    status["metrics"]["last_publish"] = last_publish.isoformat() if last_publish else None
    status["metrics"]["published_24h"] = recent_count
    
    # Alert if no publishes in 24h (and cron is running)
    if check_cron_running() and recent_count == 0 and last_publish:
        hours_ago = (datetime.now(timezone.utc) - last_publish).total_seconds() / 3600
        if hours_ago > 24:
            status["issues"].append(f"No posts in {int(hours_ago)} hours")
    
    # Check cron
    status["metrics"]["cron_configured"] = check_cron_running()
    if not check_cron_running():
        status["issues"].append("Cron jobs not configured")
    
    # Check XRPC indexer
    xrpc_healthy = check_xrpc_indexer()
    status["metrics"]["xrpc_indexer"] = "healthy" if xrpc_healthy else "down"
    if not xrpc_healthy:
        status["issues"].append("XRPC indexer API is down (502/unreachable)")
    
    # Set overall health
    status["healthy"] = len(status["issues"]) == 0
    
    return status


def should_alert() -> bool:
    """Check if enough time has passed since last alert."""
    if not ALERT_STATE_FILE.exists():
        return True
    
    try:
        with open(ALERT_STATE_FILE) as f:
            state = json.load(f)
        last_alert = datetime.fromisoformat(state.get("last_alert", "1970-01-01T00:00:00+00:00"))
        hours_since = (datetime.now(timezone.utc) - last_alert).total_seconds() / 3600
        return hours_since >= ALERT_COOLDOWN_HOURS
    except:
        return True


def record_alert():
    """Record that an alert was sent."""
    ALERT_STATE_FILE.parent.mkdir(exist_ok=True)
    with open(ALERT_STATE_FILE, "w") as f:
        json.dump({"last_alert": datetime.now(timezone.utc).isoformat()}, f)


def post_alert(issues: list[str]):
    """Write alert draft for publishing."""
    draft_path = DRAFTS_DIR / "bluesky" / f"alert-{int(datetime.now().timestamp())}.txt"
    draft_path.parent.mkdir(exist_ok=True)
    
    issues_text = " | ".join(issues[:3])  # Truncate for post length
    content = f"⚠️ Health check alert: {issues_text}"
    
    draft = f"""---
platform: bluesky
type: post
priority: HIGH
drafted_at: {datetime.now(timezone.utc).isoformat()}
---
{content}
"""
    
    with open(draft_path, "w") as f:
        f.write(draft)
    
    print(f"Alert draft written: {draft_path}")
    record_alert()


def main():
    parser = argparse.ArgumentParser(description="Central Health Check")
    parser.add_argument("--alert", action="store_true", help="Post alert if issues found")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    status = run_healthcheck()
    
    if args.json:
        print(json.dumps(status, indent=2))
        return
    
    # Pretty print
    if status["healthy"]:
        print("✓ All systems healthy")
    else:
        print("⚠ Issues detected:")
        for issue in status["issues"]:
            print(f"  - {issue}")
    
    print(f"\nMetrics:")
    print(f"  Queues: {status['metrics']['queues']}")
    print(f"  Published (24h): {status['metrics']['published_24h']}")
    print(f"  Last publish: {status['metrics']['last_publish']}")
    print(f"  Cron: {'configured' if status['metrics']['cron_configured'] else 'NOT configured'}")
    
    if args.alert and not status["healthy"]:
        if should_alert():
            post_alert(status["issues"])
        else:
            print(f"\n[Alert skipped: cooldown period ({ALERT_COOLDOWN_HOURS}h)]")


if __name__ == "__main__":
    main()
