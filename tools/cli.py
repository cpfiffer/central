#!/usr/bin/env python
"""
comind - ATProtocol Exploration CLI

Unified interface for all comind exploration tools.
"""

import asyncio
import sys
import click
from rich.console import Console

console = Console()


@click.group()
def cli():
    """comind - Explore the ATProtocol network."""
    pass


@cli.command()
@click.argument("handle_or_did")
def identity(handle_or_did: str):
    """Explore an identity (handle or DID)."""
    from tools.identity import explore_identity
    asyncio.run(explore_identity(handle_or_did))


@cli.command()
@click.argument("handle")
@click.option("--posts", default=5, help="Number of posts to show")
def user(handle: str, posts: int):
    """Explore a user's public data."""
    from tools.explore import explore_user
    asyncio.run(explore_user(handle, show_posts=posts))


@cli.command()
@click.argument("query")
def search(query: str):
    """Search posts and users."""
    from tools.explore import explore_search
    asyncio.run(explore_search(query))


@cli.command()
@click.option("--duration", "-d", default=10, help="Duration in seconds")
@click.option("--posts-only", "-p", is_flag=True, help="Only show posts")
def firehose(duration: int, posts_only: bool):
    """Sample the firehose (real-time event stream)."""
    from tools.firehose import sample_firehose
    asyncio.run(sample_firehose(duration=duration, posts_only=posts_only))


@cli.command()
@click.option("--duration", "-d", default=30, help="Duration in seconds")
def analyze(duration: int):
    """Analyze network activity patterns."""
    from tools.firehose import analyze_network
    asyncio.run(analyze_network(duration=duration))


@cli.command()
@click.argument("did")
@click.option("--duration", "-d", default=60, help="Duration in seconds")
def watch(did: str, duration: int):
    """Watch events from a specific user (by DID)."""
    from tools.firehose import watch_user
    asyncio.run(watch_user(did, duration=duration))


@cli.command()
def status():
    """Show comind status and capabilities."""
    console.print("\n[bold cyan]comind[/bold cyan] - Collective AI on ATProtocol\n")
    
    console.print("[bold]Available Commands:[/bold]")
    console.print("  identity <handle>  - Resolve identity (DID, keys, PDS)")
    console.print("  user <handle>      - View user's posts and data")
    console.print("  search <query>     - Search posts and users")
    console.print("  firehose           - Sample real-time event stream")
    console.print("  analyze            - Analyze network activity")
    console.print("  watch <did>        - Watch specific user's events")
    
    console.print("\n[bold]Network Stats (sample):[/bold]")
    console.print("  Public API: https://public.api.bsky.app")
    console.print("  Firehose:   wss://jetstream2.us-east.bsky.network")
    console.print("  PLC Dir:    https://plc.directory")


if __name__ == "__main__":
    cli()
