"""
Observations Tool

Read comms observations about public discussions.

Usage:
  uv run python -m tools.observations          # Show recent observations
  uv run python -m tools.observations --all    # Show all observations
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

from rich.console import Console
from rich.markdown import Markdown

console = Console()

NOTES_DIR = Path("/home/cameron/central/drafts/notes")


def show_observations(show_all: bool = False):
    """Show comms observations."""
    if not NOTES_DIR.exists():
        console.print("[dim]No observations directory[/dim]")
        return
    
    files = sorted(NOTES_DIR.glob("observation-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    if not files:
        console.print("[dim]No observations found yet.[/dim]")
        console.print("[dim]Observations are created when comms processes notifications.[/dim]")
        return
    
    # Show recent or all
    to_show = files if show_all else files[:5]
    
    console.print(f"[bold]Comms Observations ({len(files)} total)[/bold]\n")
    
    for f in to_show:
        content = f.read_text()
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        
        console.print(f"[cyan]─── {f.name} ({mtime.strftime('%Y-%m-%d %H:%M')}) ───[/cyan]")
        console.print(Markdown(content))
        console.print()


def main():
    show_all = "--all" in sys.argv
    show_observations(show_all)


if __name__ == "__main__":
    main()
