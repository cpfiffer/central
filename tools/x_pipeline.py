#!/usr/bin/env python3
"""X Content Pipeline - Generate posts from build artifacts.

Scans git commits, indexer stats, and responder logs to generate
substantive X posts from real work. No fortune cookies.

Usage:
    uv run python -m tools.x_pipeline              # Generate drafts
    uv run python -m tools.x_pipeline --post       # Generate and post
    uv run python -m tools.x_pipeline --since 24h  # Custom time window
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent
POSTED_FILE = PROJECT_ROOT / "data" / "x_pipeline_posted.txt"


def run(cmd: str, cwd: str | None = None) -> str:
    """Run a shell command and return stdout."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=30, cwd=cwd or str(PROJECT_ROOT)
        )
        return result.stdout.strip()
    except Exception:
        return ""


def load_posted() -> set[str]:
    """Load hashes of already-posted content."""
    if POSTED_FILE.exists():
        return set(POSTED_FILE.read_text().strip().split("\n"))
    return set()


def save_posted(content_hash: str):
    """Mark content as posted."""
    POSTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(POSTED_FILE, "a") as f:
        f.write(content_hash + "\n")


# --- Sources ---


def get_recent_commits(since_hours: int = 24) -> list[dict]:
    """Get recent git commits with stats."""
    since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
    log = run(f'git log --since="{since}" --format="%H|%s|%ai" --shortstat')
    if not log:
        return []

    commits = []
    lines = log.strip().split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "|" in line and len(line.split("|")) >= 3:
            parts = line.split("|", 2)
            commit = {
                "hash": parts[0][:7],
                "message": parts[1].strip(),
                "date": parts[2].strip(),
                "stats": "",
            }
            # Next non-empty line might be stats
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and ("file" in next_line or "insertion" in next_line):
                    commit["stats"] = next_line
                    i += 1
            commits.append(commit)
        i += 1

    return commits


def get_indexer_stats() -> dict | None:
    """Get XRPC indexer stats."""
    try:
        import urllib.request
        resp = urllib.request.urlopen(
            "https://comind-indexer.fly.dev/xrpc/network.comind.index.stats",
            timeout=10
        )
        return json.loads(resp.read())
    except Exception:
        return None


def get_responder_activity(since_hours: int = 24) -> dict:
    """Parse responder service logs for activity stats."""
    output = run(
        f'journalctl --user -u comind-responder --since "{since_hours} hours ago" '
        '--no-pager 2>/dev/null'
    )
    if not output:
        return {"mentions": 0, "responses": 0, "skips": 0}

    mentions = output.count("[CRITICAL") + output.count("[HIGH") + output.count("[MEDIUM") + output.count("[LOW")
    responses = output.count("Response:")
    skips = output.count("Skipped @") + output.count("[SKIP]")

    return {"mentions": mentions, "responses": responses, "skips": skips}


# --- Draft Generation ---


def draft_from_commits(commits: list[dict]) -> list[dict]:
    """Generate post drafts from commits."""
    if not commits:
        return []

    drafts = []
    posted = load_posted()

    # Group by theme
    themes = {}
    for c in commits:
        msg = c["message"].lower()
        if any(k in msg for k in ["fix", "bug", "error"]):
            themes.setdefault("fixes", []).append(c)
        elif any(k in msg for k in ["add", "new", "implement", "create"]):
            themes.setdefault("features", []).append(c)
        elif any(k in msg for k in ["refactor", "clean", "remove", "delete"]):
            themes.setdefault("refactors", []).append(c)
        else:
            themes.setdefault("other", []).append(c)

    # Generate a draft per theme if enough substance
    for theme, theme_commits in themes.items():
        if len(theme_commits) == 0:
            continue

        hashes = ", ".join(c["hash"] for c in theme_commits[:5])
        content_hash = f"commits-{hashes}"
        if content_hash in posted:
            continue

        messages = [c["message"] for c in theme_commits[:5]]

        # Build the post text
        if theme == "fixes" and len(theme_commits) >= 2:
            text = f"Fixed {len(theme_commits)} issues: {'; '.join(messages[:3])}. Commits: {hashes}."
        elif theme == "features" and len(theme_commits) >= 1:
            text = f"Shipped: {'; '.join(messages[:3])}. {hashes}."
        elif len(theme_commits) >= 2:
            text = f"{len(theme_commits)} commits: {'; '.join(messages[:3])}. {hashes}."
        else:
            text = f"{messages[0]}. {hashes}."

        # Truncate to 275 chars
        if len(text) > 275:
            text = text[:272] + "..."

        drafts.append({
            "text": text,
            "content_hash": content_hash,
            "source": "commits",
            "theme": theme,
        })

    return drafts


def draft_from_stats(indexer_stats: dict | None, responder_activity: dict) -> list[dict]:
    """Generate a stats post if numbers are interesting."""
    drafts = []
    posted = load_posted()

    if indexer_stats:
        total = indexer_stats.get("total_records", 0)
        agents = indexer_stats.get("total_agents", 0)
        collections = indexer_stats.get("total_collections", 0)

        # Only post stats weekly or on milestones
        milestones = [1000, 5000, 10000, 25000, 50000, 100000]
        for m in milestones:
            content_hash = f"indexer-milestone-{m}"
            if total >= m and content_hash not in posted:
                text = (
                    f"XRPC indexer hit {total:,} records. "
                    f"{agents} agents, {collections} collection types indexed. "
                    f"https://comind-indexer.fly.dev"
                )
                drafts.append({
                    "text": text,
                    "content_hash": content_hash,
                    "source": "indexer",
                })
                break

    if responder_activity["mentions"] >= 5:
        content_hash = f"responder-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        if content_hash not in posted:
            r = responder_activity
            text = (
                f"Live responder: {r['mentions']} mentions, "
                f"{r['responses']} responses, {r['skips']} skipped. "
                f"Running on Jetstream real-time."
            )
            drafts.append({
                "text": text,
                "content_hash": content_hash,
                "source": "responder",
            })

    return drafts


# --- Posting ---


def post_to_x(text: str) -> str | None:
    """Post to X using post.py."""
    try:
        result = subprocess.run(
            ["uv", "run", "python", ".skills/interacting-with-x/scripts/post.py", text],
            capture_output=True, text=True, timeout=30,
            cwd=str(PROJECT_ROOT)
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            print(f"Post failed: {result.stderr}", file=sys.stderr)
            return None
    except Exception as e:
        print(f"Post error: {e}", file=sys.stderr)
        return None


# --- Main ---


def main():
    parser = argparse.ArgumentParser(description="X content pipeline")
    parser.add_argument("--post", action="store_true", help="Actually post (default: dry run)")
    parser.add_argument("--since", default="24h", help="Time window (e.g., 24h, 48h)")
    args = parser.parse_args()

    hours = int(args.since.replace("h", ""))

    # Gather sources
    commits = get_recent_commits(hours)
    indexer_stats = get_indexer_stats()
    responder_activity = get_responder_activity(hours)

    print(f"Sources: {len(commits)} commits, indexer={'up' if indexer_stats else 'down'}, "
          f"{responder_activity['mentions']} mentions")

    # Generate drafts
    drafts = []
    drafts.extend(draft_from_commits(commits))
    drafts.extend(draft_from_stats(indexer_stats, responder_activity))

    if not drafts:
        print("No new content to post.")
        return

    print(f"\n{len(drafts)} draft(s):\n")
    for i, d in enumerate(drafts, 1):
        print(f"  [{i}] ({d['source']}) {d['text']}")
        print(f"      [{len(d['text'])} chars]")
        print()

    if args.post:
        for d in drafts:
            result = post_to_x(d["text"])
            if result:
                save_posted(d["content_hash"])
                print(f"  Posted: {result}")
            else:
                print(f"  Failed to post: {d['text'][:50]}...")
    else:
        print("Dry run. Use --post to publish.")


if __name__ == "__main__":
    main()
