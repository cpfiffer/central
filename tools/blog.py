"""
Blog Tool - Manage local blog posts and mirror to greengale.

Commands:
  new <slug>     Create new draft
  list           Show all posts and status
  publish <slug> Post to greengale
  sync           Publish all unpublished posts
"""

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()

BLOG_DIR = Path(__file__).parent.parent / "blog" / "posts"
PUBLISHED_FILE = Path(__file__).parent.parent / "blog" / "published.json"


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown."""
    if not content.startswith("---"):
        return {}, content
    
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    
    frontmatter = {}
    for line in parts[1].strip().split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            value = value.strip().strip('"\'')
            if value == "false":
                value = False
            elif value == "true":
                value = True
            elif value == "null":
                value = None
            frontmatter[key.strip()] = value
    
    return frontmatter, parts[2].strip()


def update_frontmatter(filepath: Path, updates: dict):
    """Update frontmatter values in a markdown file."""
    content = filepath.read_text()
    frontmatter, body = parse_frontmatter(content)
    frontmatter.update(updates)
    
    # Rebuild file
    lines = ["---"]
    for key, value in frontmatter.items():
        if value is None:
            lines.append(f"{key}: null")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif isinstance(value, list):
            lines.append(f"{key}: {value}")
        else:
            lines.append(f'{key}: "{value}"')
    lines.append("---")
    lines.append("")
    lines.append(body)
    
    filepath.write_text("\n".join(lines))


def load_published() -> dict:
    """Load published tracking."""
    if PUBLISHED_FILE.exists():
        return json.loads(PUBLISHED_FILE.read_text())
    return {}


def save_published(data: dict):
    """Save published tracking."""
    PUBLISHED_FILE.parent.mkdir(parents=True, exist_ok=True)
    PUBLISHED_FILE.write_text(json.dumps(data, indent=2))


def cmd_new(slug: str):
    """Create new blog post draft."""
    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    
    date = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date}-{slug}.md"
    filepath = BLOG_DIR / filename
    
    if filepath.exists():
        console.print(f"[red]Already exists: {filepath}[/red]")
        return
    
    template = f'''---
title: "{slug.replace("-", " ").title()}"
date: {date}
tags: []
published: false
greengale_uri: null
---

# {slug.replace("-", " ").title()}

Write your content here.
'''
    filepath.write_text(template)
    console.print(f"[green]Created: {filepath}[/green]")


def cmd_list():
    """List all blog posts."""
    if not BLOG_DIR.exists():
        console.print("[yellow]No blog posts yet.[/yellow]")
        return
    
    table = Table(title="Blog Posts")
    table.add_column("File", style="cyan")
    table.add_column("Title")
    table.add_column("Published", justify="center")
    
    for f in sorted(BLOG_DIR.glob("*.md")):
        content = f.read_text()
        fm, _ = parse_frontmatter(content)
        published = "✓" if fm.get("published") else ""
        table.add_row(f.name, fm.get("title", "?"), published)
    
    console.print(table)


async def cmd_publish(slug: str):
    """Publish a post to greengale."""
    from tools.agent import ComindAgent
    
    # Find the file
    matches = list(BLOG_DIR.glob(f"*{slug}*.md"))
    if not matches:
        console.print(f"[red]No post matching '{slug}'[/red]")
        return
    
    filepath = matches[0]
    content = filepath.read_text()
    fm, body = parse_frontmatter(content)
    
    # Check if already published
    if fm.get("published"):
        console.print(f"[yellow]Already published: {fm.get('greengale_uri')}[/yellow]")
        return
    
    title = fm.get("title", slug)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # Post to greengale
    async with ComindAgent() as agent:
        record = {
            "$type": "app.greengale.blog.entry",
            "content": f"# {title}\n\n{body}",
            "title": title,
            "createdAt": now,
            "visibility": "public"
        }
        
        result = await agent._client.post(
            f"{agent.pds}/xrpc/com.atproto.repo.createRecord",
            headers=agent.auth_headers,
            json={
                "repo": agent.did,
                "collection": "app.greengale.blog.entry",
                "record": record
            }
        )
        
        if result.status_code != 200:
            console.print(f"[red]Failed: {result.text}[/red]")
            return
        
        uri = result.json().get("uri")
        console.print(f"[green]Published: {uri}[/green]")
        
        # Update frontmatter
        update_frontmatter(filepath, {"published": True, "greengale_uri": uri})
        
        # Update tracking
        published = load_published()
        published[filepath.name] = {"uri": uri, "published_at": now}
        save_published(published)


async def cmd_sync():
    """Publish all unpublished posts."""
    if not BLOG_DIR.exists():
        console.print("[yellow]No blog posts yet.[/yellow]")
        return
    
    for f in sorted(BLOG_DIR.glob("*.md")):
        content = f.read_text()
        fm, _ = parse_frontmatter(content)
        if not fm.get("published"):
            slug = f.stem.split("-", 3)[-1] if "-" in f.stem else f.stem
            console.print(f"\nPublishing: {f.name}")
            await cmd_publish(slug)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "new" and len(sys.argv) > 2:
        cmd_new(sys.argv[2])
    elif cmd == "list":
        cmd_list()
    elif cmd == "publish" and len(sys.argv) > 2:
        asyncio.run(cmd_publish(sys.argv[2]))
    elif cmd == "sync":
        asyncio.run(cmd_sync())
    else:
        print(__doc__)
