"""
GreenGale Publisher - Publish blog posts to app.greengale.document

Usage:
    uv run python tools/greengale_publish.py <slug>
    uv run python tools/greengale_publish.py --new <slug>
    uv run python tools/greengale_publish.py --list
"""

import os
import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from rich.console import Console

console = Console()

# Paths
BLOG_DIR = Path(__file__).parent.parent / "blog" / "posts"
PUBLISHED_FILE = Path(__file__).parent.parent / "blog" / "greengale_published.json"

# Load credentials
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

HANDLE = os.getenv("ATPROTO_HANDLE")
DID = os.getenv("ATPROTO_DID")
PDS = os.getenv("ATPROTO_PDS")
APP_PASSWORD = os.getenv("ATPROTO_APP_PASSWORD")


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


def load_published() -> dict:
    """Load published tracking."""
    if PUBLISHED_FILE.exists():
        return json.loads(PUBLISHED_FILE.read_text())
    return {}


def save_published(data: dict):
    """Save published tracking."""
    PUBLISHED_FILE.parent.mkdir(parents=True, exist_ok=True)
    PUBLISHED_FILE.write_text(json.dumps(data, indent=2))


def generate_tid() -> str:
    """Generate a timestamp-based ID (TID) for the record key."""
    # TID format: timestamp in microseconds encoded as base32-sortable
    # For simplicity, use a simpler format: YYYYMMDDHHMMSS + random
    import random
    import string
    ts = datetime.now(timezone.utc)
    # Use timestamp microseconds as the TID
    return f"{int(ts.timestamp() * 1_000_000):013d}"


async def create_session(client: httpx.AsyncClient) -> dict:
    """Create an ATProtocol session."""
    response = await client.post(
        f"{PDS}/xrpc/com.atproto.server.createSession",
        json={
            "identifier": HANDLE,
            "password": APP_PASSWORD
        }
    )
    response.raise_for_status()
    return response.json()


async def publish_to_greengale(
    title: str,
    content: str,
    slug: str,
    subtitle: Optional[str] = None,
    tags: Optional[list] = None
) -> dict:
    """Publish a document to GreenGale."""
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Create session
        session = await create_session(client)
        access_jwt = session["accessJwt"]
        
        # Generate record key and timestamp
        now = datetime.now(timezone.utc)
        published_at = now.isoformat().replace("+00:00", "Z")
        rkey = slug  # Use slug as record key for clean URLs
        
        # Build the record
        record = {
            "$type": "app.greengale.document",
            "content": content,  # Plain markdown, no frontmatter
            "title": title,
            "url": f"https://greengale.app/{HANDLE}/{rkey}",
            "path": f"/{HANDLE}/{rkey}",
            "publishedAt": published_at,
            "theme": {"preset": "github-dark"},
            "visibility": "public"
        }
        
        if subtitle:
            record["subtitle"] = subtitle
        if tags:
            record["tags"] = tags
        
        # Publish using putRecord
        response = await client.post(
            f"{PDS}/xrpc/com.atproto.repo.putRecord",
            headers={
                "Authorization": f"Bearer {access_jwt}",
                "Content-Type": "application/json"
            },
            json={
                "repo": DID,
                "collection": "app.greengale.document",
                "rkey": rkey,
                "record": record
            }
        )
        
        if response.status_code != 200:
            return {
                "success": False,
                "error": response.text,
                "status": response.status_code
            }
        
        result = response.json()
        return {
            "success": True,
            "uri": result.get("uri"),
            "cid": result.get("cid"),
            "url": f"https://greengale.app/{HANDLE}/{rkey}"
        }


async def cmd_publish(slug: str):
    """Publish a blog post to GreenGale."""
    # Find the file
    matches = list(BLOG_DIR.glob(f"*{slug}*.md"))
    if not matches:
        console.print(f"[red]No post matching '{slug}'[/red]")
        return
    
    filepath = matches[0]
    content = filepath.read_text()
    fm, body = parse_frontmatter(content)
    
    # Check if already published
    published = load_published()
    if filepath.name in published:
        console.print(f"[yellow]Already published: {published[filepath.name]['url']}[/yellow]")
        return
    
    title = fm.get("title", slug.replace("-", " ").title())
    subtitle = fm.get("subtitle")
    tags = fm.get("tags", [])
    
    console.print(f"Publishing: [cyan]{title}[/cyan]")
    
    # Publish
    result = await publish_to_greengale(
        title=title,
        content=body,  # Just the body, no frontmatter
        slug=slug,
        subtitle=subtitle,
        tags=tags
    )
    
    if result["success"]:
        console.print(f"[green]Published: {result['url']}[/green]")
        console.print(f"  URI: {result['uri']}")
        
        # Track published
        published[filepath.name] = {
            "uri": result["uri"],
            "cid": result["cid"],
            "url": result["url"],
            "published_at": datetime.now(timezone.utc).isoformat()
        }
        save_published(published)
    else:
        console.print(f"[red]Failed: {result['error']}[/red]")


def cmd_new(slug: str):
    """Create a new blog post draft."""
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
    
    published = load_published()
    
    from rich.table import Table
    table = Table(title="Blog Posts")
    table.add_column("File", style="cyan")
    table.add_column("Title")
    table.add_column("GreenGale", justify="center")
    
    for f in sorted(BLOG_DIR.glob("*.md")):
        content = f.read_text()
        fm, _ = parse_frontmatter(content)
        is_published = "✓" if f.name in published else ""
        table.add_row(f.name, fm.get("title", "?"), is_published)
    
    console.print(table)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "--new" and len(sys.argv) > 2:
        cmd_new(sys.argv[2])
    elif cmd == "--list":
        cmd_list()
    elif cmd == "--help":
        print(__doc__)
    elif not cmd.startswith("--"):
        asyncio.run(cmd_publish(cmd))
    else:
        print(__doc__)
