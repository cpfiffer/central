"""
Authenticated Bluesky timeline helpers.

Fetches the authenticated home timeline from the agent's own PDS.
Reads credentials from /home/cameron/central/.env:
- ATPROTO_HANDLE or BSKY_HANDLE
- BSKY_PASSWORD or ATPROTO_APP_PASSWORD
- PDS_URI
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import click
import httpx
from rich.console import Console

console = Console()
ENV_PATH = Path("/home/cameron/central/.env")


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip()
    return values


def get_credentials() -> tuple[str, str, str]:
    file_env = load_env_file(ENV_PATH)
    handle = (
        os.getenv("ATPROTO_HANDLE")
        or os.getenv("BSKY_HANDLE")
        or file_env.get("ATPROTO_HANDLE")
        or file_env.get("BSKY_HANDLE")
    )
    password = (
        os.getenv("BSKY_PASSWORD")
        or os.getenv("ATPROTO_APP_PASSWORD")
        or file_env.get("BSKY_PASSWORD")
        or file_env.get("ATPROTO_APP_PASSWORD")
    )
    pds = os.getenv("PDS_URI") or file_env.get("PDS_URI") or "https://bsky.social"

    if not handle or not password:
        raise click.ClickException("Missing Bluesky credentials in env or /home/cameron/central/.env")

    return handle, password, pds.rstrip("/")


def create_session(handle: str, password: str, pds: str) -> str:
    resp = httpx.post(
        f"{pds}/xrpc/com.atproto.server.createSession",
        json={"identifier": handle, "password": password},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("accessJwt")
    if not token:
        raise click.ClickException("Authentication succeeded but no accessJwt returned")
    return token


def fetch_timeline(token: str, pds: str, limit: int = 10) -> dict[str, Any]:
    resp = httpx.get(
        f"{pds}/xrpc/app.bsky.feed.getTimeline",
        params={"limit": limit},
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def render_timeline(data: dict[str, Any]) -> None:
    feed = data.get("feed", [])
    if not feed:
        console.print("[yellow]No posts in timeline[/yellow]")
        return

    for idx, item in enumerate(feed, 1):
        post = item.get("post", {})
        author = post.get("author", {})
        record = post.get("record", {})
        handle = author.get("handle", "?")
        name = author.get("displayName", "")
        text = (record.get("text", "") or "").replace("\n", " ").strip()
        indexed = post.get("indexedAt", "")[:19]
        likes = post.get("likeCount", 0)
        replies = post.get("replyCount", 0)
        reposts = post.get("repostCount", 0)
        console.print(f"[bold]{idx}. @{handle}[/bold] {f'({name})' if name else ''}")
        if indexed:
            console.print(f"   [dim]{indexed}[/dim]")
        console.print(f"   {text[:280]}")
        console.print(f"   [dim]♥ {likes}  ↩ {replies}  🔁 {reposts}[/dim]\n")


@click.group()
def cli() -> None:
    """Authenticated Bluesky feed helpers."""


@cli.command()
@click.option("--limit", default=10, show_default=True, help="Number of timeline items")
def timeline(limit: int) -> None:
    """Show authenticated home timeline from the configured PDS."""
    handle, password, pds = get_credentials()
    console.print(f"[cyan]Authenticating as {handle} via {pds}...[/cyan]")
    token = create_session(handle, password, pds)
    data = fetch_timeline(token, pds, limit=limit)
    render_timeline(data)


if __name__ == "__main__":
    cli()
