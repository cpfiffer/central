#!/usr/bin/env python3
"""
Comms Review Tool

Summarizes recent comms observations for Central to review.
Run at session start to see what comms has been observing.

Usage:
    uv run python -m tools.comms_review          # Last 10 observations
    uv run python -m tools.comms_review --all    # All observations
    uv run python -m tools.comms_review --since 2h  # Last 2 hours
"""

import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
import re

NOTES_DIR = Path(__file__).parent.parent / "drafts" / "notes"


def parse_duration(s: str) -> timedelta:
    """Parse duration string like '2h', '30m', '1d'."""
    match = re.match(r"(\d+)([hdm])", s.lower())
    if not match:
        return timedelta(hours=2)
    
    val, unit = int(match.group(1)), match.group(2)
    if unit == "h":
        return timedelta(hours=val)
    elif unit == "d":
        return timedelta(days=val)
    elif unit == "m":
        return timedelta(minutes=val)
    return timedelta(hours=2)


def get_observations(since: timedelta | None = None, limit: int = 10) -> list[dict]:
    """Get recent observation files."""
    if not NOTES_DIR.exists():
        return []
    
    observations = []
    cutoff = datetime.now(timezone.utc) - since if since else None
    
    for f in sorted(NOTES_DIR.glob("observation-*.md"), reverse=True):
        # Parse timestamp from filename
        try:
            # Format: observation-YYYY-MM-DDTHH-MM-SS.md or similar
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            
            if cutoff and mtime < cutoff:
                continue
            
            content = f.read_text()
            observations.append({
                "file": f.name,
                "time": mtime,
                "content": content[:2000]  # Truncate
            })
            
            if not since and len(observations) >= limit:
                break
        except Exception as e:
            continue
    
    return observations


def summarize_observations(observations: list[dict]) -> str:
    """Create summary of observations."""
    if not observations:
        return "No recent observations found."
    
    lines = [f"# Comms Observations ({len(observations)} files)\n"]
    
    for obs in observations:
        time_str = obs["time"].strftime("%Y-%m-%d %H:%M UTC")
        lines.append(f"\n## {time_str} - {obs['file']}")
        lines.append(obs["content"][:1000])
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Review comms observations")
    parser.add_argument("--all", action="store_true", help="Show all observations")
    parser.add_argument("--since", type=str, help="Time window (e.g., 2h, 30m, 1d)")
    parser.add_argument("--limit", type=int, default=10, help="Max observations to show")
    args = parser.parse_args()
    
    if args.all:
        since = timedelta(days=365)
        limit = 1000
    elif args.since:
        since = parse_duration(args.since)
        limit = 1000
    else:
        since = None
        limit = args.limit
    
    observations = get_observations(since=since, limit=limit)
    print(summarize_observations(observations))


if __name__ == "__main__":
    main()
