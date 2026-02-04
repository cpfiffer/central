"""
Cognition Daemon

Automated thought/observation recording on a schedule.
Posts to network.comind.thought collection (cognition, not social).

Usage:
  uv run python -m tools.cognition_daemon        # Generate and post thought
  uv run python -m tools.cognition_daemon --dry-run  # Preview without posting
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from rich.console import Console

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.agent import ComindAgent

console = Console()

THOUGHT_COLLECTION = "network.comind.thought"


async def get_recent_activity() -> dict:
    """Gather recent activity for context."""
    activity = {
        "commits": [],
        "posts_24h": 0,
        "mentions": 0,
    }
    
    # Get recent commits
    try:
        import subprocess
        result = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            capture_output=True, text=True, cwd=Path(__file__).parent.parent
        )
        if result.returncode == 0:
            activity["commits"] = result.stdout.strip().split("\n")[:3]
    except:
        pass
    
    # Get published count
    try:
        published_dir = Path(__file__).parent.parent / "drafts" / "published"
        if published_dir.exists():
            recent = [f for f in published_dir.iterdir() 
                     if f.stat().st_mtime > (datetime.now().timestamp() - 86400)]
            activity["posts_24h"] = len(recent)
    except:
        pass
    
    return activity


def generate_thought(activity: dict) -> tuple[str, str]:
    """Generate a thought based on recent activity.
    
    Returns (thought_text, thought_type)
    """
    commits = activity.get("commits", [])
    posts = activity.get("posts_24h", 0)
    
    # Generate based on what's happening
    if commits:
        # Recent development activity
        commit_summary = commits[0].split(" ", 1)[1] if " " in commits[0] else commits[0]
        return (
            f"Recent work: {commit_summary}. {len(commits)} commits in queue. "
            f"Building infrastructure for the agent ecosystem.",
            "progress"
        )
    elif posts > 50:
        return (
            f"High activity: {posts} posts in last 24h. Automation running smoothly. "
            f"Network presence maintained.",
            "observation"
        )
    else:
        return (
            f"Steady state. {posts} posts in 24h. Monitoring network, "
            f"maintaining infrastructure, thinking about next improvements.",
            "status"
        )


async def post_thought(thought: str, thought_type: str, dry_run: bool = False) -> dict | None:
    """Post a thought to network.comind.thought collection."""
    
    console.print(f"\n[cyan]Thought ({thought_type}):[/cyan]")
    console.print(thought)
    
    if dry_run:
        console.print("\n[yellow]Dry run - not posted[/yellow]")
        return None
    
    record = {
        "$type": THOUGHT_COLLECTION,
        "thought": thought,
        "type": thought_type,
        "context": "automated cognition daemon",
        "tags": ["daemon", "automated"],
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    
    async with ComindAgent() as agent:
        rkey = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{agent.pds}/xrpc/com.atproto.repo.createRecord",
                headers=agent.auth_headers,
                json={
                    "repo": agent.did,
                    "collection": THOUGHT_COLLECTION,
                    "rkey": rkey,
                    "record": record
                }
            )
            
            if resp.status_code != 200:
                console.print(f"[red]Failed: {resp.text}[/red]")
                return None
            
            result = resp.json()
            console.print(f"[green]Posted to {THOUGHT_COLLECTION}[/green]")
            console.print(f"URI: {result.get('uri')}")
            return result


async def run_daemon(dry_run: bool = False):
    """Run one cycle of the cognition daemon."""
    console.print("[bold]Cognition Daemon[/bold]")
    console.print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    
    # Gather context
    activity = await get_recent_activity()
    console.print(f"\nActivity: {activity}")
    
    # Generate thought
    thought, thought_type = generate_thought(activity)
    
    # Post it
    await post_thought(thought, thought_type, dry_run)


def main():
    dry_run = "--dry-run" in sys.argv
    asyncio.run(run_daemon(dry_run))


if __name__ == "__main__":
    main()
