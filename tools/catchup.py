"""
comind Catchup Tool

Summarizes what happened while I was offline.
Run this at the start of each attention window.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

LOG_DIR = Path(__file__).parent.parent / "logs"


def load_jsonl(path: Path, since: Optional[datetime] = None) -> list:
    """Load JSONL file, optionally filtering by timestamp."""
    if not path.exists():
        return []
    
    entries = []
    with open(path) as f:
        for line in f:
            if line.strip():
                try:
                    entry = json.loads(line)
                    if since:
                        ts = entry.get("timestamp", "")
                        if ts:
                            entry_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            if entry_time < since:
                                continue
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue
    return entries


def get_last_session_time() -> Optional[datetime]:
    """Get timestamp of last daemon stop (proxy for last session)."""
    daemon_log = LOG_DIR / "daemon.jsonl"
    if not daemon_log.exists():
        return None
    
    last_stop = None
    with open(daemon_log) as f:
        for line in f:
            if line.strip():
                try:
                    entry = json.loads(line)
                    if entry.get("type") == "daemon_stop":
                        last_stop = entry.get("timestamp")
                except:
                    continue
    
    if last_stop:
        return datetime.fromisoformat(last_stop.replace("Z", "+00:00"))
    return None


def summarize_mentions(since: Optional[datetime] = None) -> list:
    """Get mentions since last session."""
    mentions = load_jsonl(LOG_DIR / "mentions.jsonl", since)
    return mentions


def summarize_agent_activity(since: Optional[datetime] = None) -> dict:
    """Summarize agent activity since last session."""
    activity = load_jsonl(LOG_DIR / "agent_activity.jsonl", since)
    
    by_agent = {}
    for entry in activity:
        agent = entry.get("agent", "unknown")
        if agent not in by_agent:
            by_agent[agent] = []
        by_agent[agent].append(entry)
    
    return by_agent


def summarize_pulses(since: Optional[datetime] = None) -> dict:
    """Summarize network pulses since last session."""
    pulses = load_jsonl(LOG_DIR / "network_pulse.jsonl", since)
    
    if not pulses:
        return {"count": 0}
    
    total_posts = sum(p.get("posts", 0) for p in pulses)
    total_likes = sum(p.get("likes", 0) for p in pulses)
    avg_posts_sec = sum(p.get("posts_per_sec", 0) for p in pulses) / len(pulses)
    
    # Aggregate hashtags
    all_tags = {}
    for p in pulses:
        for tag, count in p.get("top_hashtags", []):
            all_tags[tag] = all_tags.get(tag, 0) + count
    
    top_tags = sorted(all_tags.items(), key=lambda x: -x[1])[:10]
    
    return {
        "count": len(pulses),
        "total_posts": total_posts,
        "total_likes": total_likes,
        "avg_posts_sec": round(avg_posts_sec, 2),
        "top_hashtags": top_tags
    }


def catchup(hours: Optional[int] = None):
    """
    Run catchup summary.
    
    Args:
        hours: Look back N hours. If None, uses last daemon stop time.
    """
    if hours:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        console.print(f"[bold]Catching up on last {hours} hours...[/bold]\n")
    else:
        since = get_last_session_time()
        if since:
            delta = datetime.now(timezone.utc) - since
            hours_ago = delta.total_seconds() / 3600
            console.print(f"[bold]Catching up since last session ({hours_ago:.1f} hours ago)...[/bold]\n")
        else:
            console.print("[bold]No previous session found. Showing last 24 hours...[/bold]\n")
            since = datetime.now(timezone.utc) - timedelta(hours=24)
    
    # Mentions
    mentions = summarize_mentions(since)
    if mentions:
        console.print(Panel(f"[bold red]{len(mentions)} mentions[/bold red]", title="📢 Mentions"))
        for m in mentions[-10:]:  # Show last 10
            text = m.get("text", "")[:100]
            console.print(f"  • {text}...")
        if len(mentions) > 10:
            console.print(f"  [dim]...and {len(mentions) - 10} more[/dim]")
        console.print()
    else:
        console.print("[dim]No mentions[/dim]\n")
    
    # Agent activity
    activity = summarize_agent_activity(since)
    if activity:
        console.print(Panel(f"[bold magenta]{sum(len(v) for v in activity.values())} posts from agents[/bold magenta]", title="🤖 Agent Activity"))
        for agent, posts in sorted(activity.items(), key=lambda x: -len(x[1])):
            console.print(f"  [cyan]{agent}[/cyan]: {len(posts)} posts")
            for p in posts[-3:]:  # Show last 3 per agent
                text = p.get("text", "")[:80]
                console.print(f"    • {text}...")
        console.print()
    else:
        console.print("[dim]No agent activity logged[/dim]\n")
    
    # Network pulses
    pulses = summarize_pulses(since)
    if pulses["count"] > 0:
        console.print(Panel(f"[bold blue]{pulses['count']} hourly snapshots[/bold blue]", title="📊 Network"))
        console.print(f"  Posts: {pulses['total_posts']:,}")
        console.print(f"  Likes: {pulses['total_likes']:,}")
        console.print(f"  Avg rate: {pulses['avg_posts_sec']}/sec")
        if pulses["top_hashtags"]:
            tags = " ".join([f"#{t}" for t, _ in pulses["top_hashtags"][:5]])
            console.print(f"  Trending: {tags}")
        console.print()
    else:
        console.print("[dim]No network pulses logged[/dim]\n")
    
    # Concept summary (from local index)
    try:
        from tools.concepts import load
        concepts = load()
        agent_concepts = [n for n, d in concepts.items() if 'agent' in d.get('tags', [])]
        pattern_concepts = [n for n, d in concepts.items() if 'pattern' in d.get('tags', [])]
        console.print(Panel(f"[bold cyan]{len(concepts)} concepts indexed[/bold cyan]", title="🧠 Knowledge"))
        console.print(f"  Agents: {', '.join(agent_concepts[:6])}")
        console.print(f"  Patterns: {', '.join(pattern_concepts)}")
        console.print(f"  [dim]Run: uv run python -m tools.concepts [name|agents|patterns][/dim]")
        console.print()
    except Exception as e:
        console.print(f"[dim]Concept index unavailable: {e}[/dim]\n")
    
    # Summary
    console.print("[bold green]Catchup complete.[/bold green]")
    if mentions:
        console.print(f"[yellow]→ {len(mentions)} mentions need attention[/yellow]")


if __name__ == "__main__":
    import sys
    
    hours = None
    if len(sys.argv) > 1:
        try:
            hours = int(sys.argv[1])
        except ValueError:
            pass
    
    catchup(hours)
