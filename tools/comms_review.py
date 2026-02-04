"""
Comms Review Tool

Review recent communications drafted by comms subagent.

Usage:
  uv run python -m tools.comms_review             # Show recent published
  uv run python -m tools.comms_review pending     # Show pending drafts
  uv run python -m tools.comms_review stats       # Show statistics
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

DRAFTS_DIR = Path("/home/cameron/central/drafts")
PUBLISHED_DIR = DRAFTS_DIR / "published"
BLUESKY_DIR = DRAFTS_DIR / "bluesky"
REVIEW_DIR = DRAFTS_DIR / "review"
X_DIR = DRAFTS_DIR / "x"


def parse_draft(path: Path) -> dict:
    """Parse a draft file into structured data."""
    content = path.read_text()
    
    # Split frontmatter and body
    parts = content.split("---", 2)
    if len(parts) >= 3:
        import yaml
        try:
            metadata = yaml.safe_load(parts[1])
        except:
            metadata = {}
        body = parts[2].strip()
    else:
        metadata = {}
        body = content
    
    return {
        "path": path,
        "name": path.name,
        "metadata": metadata or {},
        "body": body,
        "mtime": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc),
    }


def show_recent(limit: int = 20):
    """Show recent published communications."""
    if not PUBLISHED_DIR.exists():
        console.print("[dim]No published directory[/dim]")
        return
    
    files = sorted(PUBLISHED_DIR.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    if not files:
        console.print("[dim]No published drafts[/dim]")
        return
    
    console.print(f"[bold]Recent Published ({len(files)} total)[/bold]\n")
    
    for f in files[:limit]:
        draft = parse_draft(f)
        platform = draft["metadata"].get("platform", "?")
        reply_type = draft["metadata"].get("type", "?")
        author = draft["metadata"].get("author", "")
        time_str = draft["mtime"].strftime("%H:%M")
        
        # Truncate body
        body_preview = draft["body"][:80].replace("\n", " ")
        
        style = "cyan" if platform == "bluesky" else "blue"
        console.print(f"[{style}]{time_str}[/] [{reply_type}] {body_preview}...")
        if author:
            console.print(f"  [dim]→ @{author}[/dim]")


def show_pending():
    """Show pending drafts awaiting publish or review."""
    console.print("[bold]Pending Drafts[/bold]\n")
    
    for dir_path, label in [(BLUESKY_DIR, "Bluesky (auto)"), (X_DIR, "X (auto)"), (REVIEW_DIR, "Review (manual)")]:
        if not dir_path.exists():
            continue
        
        files = list(dir_path.glob("*.txt"))
        if files:
            console.print(f"[cyan]{label}:[/cyan] {len(files)} drafts")
            for f in files[:5]:
                draft = parse_draft(f)
                body_preview = draft["body"][:60].replace("\n", " ")
                console.print(f"  • {body_preview}...")
            if len(files) > 5:
                console.print(f"  [dim]... and {len(files) - 5} more[/dim]")
            console.print()


def show_stats():
    """Show communication statistics."""
    console.print("[bold]Comms Statistics[/bold]\n")
    
    # Count published
    published = list(PUBLISHED_DIR.glob("*.txt")) if PUBLISHED_DIR.exists() else []
    
    # Count by platform
    bluesky_count = sum(1 for f in published if "bluesky" in f.name.lower())
    x_count = sum(1 for f in published if f.name.startswith("x-") or "x-reply" in f.name.lower())
    
    # Recent activity (last 24h)
    now = datetime.now(timezone.utc)
    recent = [f for f in published if (now - datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)).total_seconds() < 86400]
    
    table = Table(title="Statistics")
    table.add_column("Metric")
    table.add_column("Value", style="cyan")
    
    table.add_row("Total Published", str(len(published)))
    table.add_row("Bluesky", str(bluesky_count))
    table.add_row("X", str(x_count))
    table.add_row("Last 24h", str(len(recent)))
    table.add_row("Pending (Bluesky)", str(len(list(BLUESKY_DIR.glob("*.txt")))) if BLUESKY_DIR.exists() else "0")
    table.add_row("Pending (Review)", str(len(list(REVIEW_DIR.glob("*.txt")))) if REVIEW_DIR.exists() else "0")
    
    console.print(table)


def main():
    if len(sys.argv) < 2:
        show_recent()
        return
    
    cmd = sys.argv[1]
    
    if cmd == "pending":
        show_pending()
    elif cmd == "stats":
        show_stats()
    elif cmd == "recent":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        show_recent(limit)
    else:
        console.print(f"[red]Unknown command: {cmd}[/red]")
        console.print("Commands: recent, pending, stats")


if __name__ == "__main__":
    main()
