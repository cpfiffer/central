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
@click.option("--limit", default=10, help="Number of timeline items")
def timeline(limit: int):
    """Show authenticated Bluesky home timeline."""
    from tools.timeline import timeline as timeline_cmd
    timeline_cmd.main(args=["--limit", str(limit)], standalone_mode=False)


# Import link commands
from tools.links import links as links_group
cli.add_command(links_group, name="link")


# Concept commands
@cli.group()
def concept():
    """Manage concept records."""
    pass


@concept.command()
def sync():
    """Sync concepts from ATProtocol to local cache."""
    from tools.concepts import sync as do_sync
    do_sync()


@concept.command("list")
@click.option("--tag", "-t", help="Filter by tag")
@click.option("--limit", "-l", default=15, help="Max results")
def list_concepts(tag: str, limit: int):
    """List concepts."""
    from tools.concepts import show
    show(tag=tag)


@concept.command()
@click.argument("name")
def show(name: str):
    """Show details of a specific concept."""
    from tools.concepts import show as do_show
    do_show(name=name)


@concept.command()
@click.argument("query")
def search(query: str):
    """Search concepts by keyword."""
    from tools.concepts import search as do_search
    results = do_search(query=query)
    if not results:
        console.print("[yellow]No concepts found[/yellow]")
        return
    for name, data in results[:10]:
        console.print(f"  [cyan]{name}[/cyan] ({data['confidence']}%)")
        if data['summary']:
            console.print(f"    {data['summary'][:60]}...")


@concept.command()
@click.argument("name")
@click.option("--confidence", "-c", default=50, help="Initial confidence (0-100)")
@click.option("--tags", "-t", default="", help="Comma-separated tags")
def create(name: str, confidence: int, tags: str):
    """Create a new concept."""
    import os
    import httpx
    from datetime import datetime, timezone
    from dotenv import load_dotenv

    load_dotenv()
    handle = os.getenv("ATPROTO_HANDLE")
    password = os.getenv("ATPROTO_APP_PASSWORD")
    pds = os.getenv("ATPROTO_PDS", "https://comind.network")

    if not handle or not password:
        console.print("[red]Error: ATPROTO_HANDLE and ATPROTO_APP_PASSWORD required[/red]")
        return

    # Auth
    resp = httpx.post(f"{pds}/xrpc/com.atproto.server.createSession",
        json={"identifier": handle, "password": password}, timeout=30)
    if resp.status_code != 200:
        console.print(f"[red]Auth failed: {resp.text}[/red]")
        return
    session = resp.json()
    token = session["accessJwt"]
    did = session["did"]

    # Create concept
    record = {
        "$type": "network.comind.concept",
        "concept": name,
        "confidence": confidence,
        "tags": [t.strip() for t in tags.split(",")] if tags else [],
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }

    resp = httpx.post(f"{pds}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {token}"},
        json={"repo": did, "collection": "network.comind.concept", "record": record},
        timeout=30)

    if resp.status_code == 200:
        data = resp.json()
        console.print(f"[green]Created concept:[/green] {data['uri']}")
    else:
        console.print(f"[red]Failed: {resp.text}[/red]")


# Query command for link traversal
@cli.command()
@click.argument("uri")
@click.option("--direction", "-d", type=click.Choice(["to", "from", "both"]), default="both")
@click.option("--limit", "-l", default=20, help="Max results")
def query(uri: str, direction: str, limit: int):
    """Query links to/from a record."""
    import httpx
    from tools.links import DID, PDS, COLLECTION

    # Normalize URI
    if not uri.startswith("at://"):
        # Check if it looks like a post rkey (starts with 3)
        if uri.startswith("3"):
            # Post rkey
            uri = f"at://{DID}/app.bsky.feed.post/{uri}"
        else:
            # Assume concept name
            uri = f"at://{DID}/network.comind.concept/{uri.replace(' ', '-')}"

    resp = httpx.get(f"{PDS}/xrpc/com.atproto.repo.listRecords",
        params={"repo": DID, "collection": COLLECTION, "limit": 100}, timeout=30)

    if resp.status_code != 200:
        console.print(f"[red]Failed: {resp.text}[/red]")
        return

    records = resp.json().get("records", [])

    # Filter by direction
    incoming = []  # links TO this URI
    outgoing = []  # links FROM this URI

    for r in records:
        v = r["value"]
        src = v.get("source", "")
        tgt = v.get("target", "")

        if direction in ("to", "both") and tgt == uri:
            incoming.append(r)
        if direction in ("from", "both") and src == uri:
            outgoing.append(r)

    if not incoming and not outgoing:
        console.print(f"[yellow]No links found for {uri}[/yellow]")
        return

    if incoming:
        console.print(f"\n[green]Incoming links ({len(incoming)}):[/green]")
        for r in incoming[:limit]:
            v = r["value"]
            src_short = v.get("source", "").split("/")[-1][:30]
            console.print(f"  {src_short} ──[{v.get('relationship', '?')}]──> [cyan]{uri.split('/')[-1]}[/cyan]")
            if v.get("note"):
                console.print(f"    [dim]{v['note'][:50]}...[/dim]")

    if outgoing:
        console.print(f"\n[blue]Outgoing links ({len(outgoing)}):[/blue]")
        for r in outgoing[:limit]:
            v = r["value"]
            tgt_short = v.get("target", "").split("/")[-1][:30]
            console.print(f"  [cyan]{uri.split('/')[-1]}[/cyan] ──[{v.get('relationship', '?')}]──> {tgt_short}")
            if v.get("note"):
                console.print(f"    [dim]{v['note'][:50]}...[/dim]")


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
    console.print("  link               - Manage relationship links between records")
    console.print("  concept            - Manage concept records")

    console.print("\n[bold]Network Stats (sample):[/bold]")
    console.print("  Public API: https://public.api.bsky.app")
    console.print("  Firehose:   wss://jetstream2.us-east.bsky.network")
    console.print("  PLC Dir:    https://plc.directory")

# Add concept group after it's defined
cli.add_command(concept)


# Thought commands
@cli.group()
def thought():
    """Manage thought records."""
    pass


@thought.command("list")
@click.option("--limit", "-l", default=10, help="Max results")
def list_thoughts(limit: int):
    """List recent thoughts."""
    import httpx
    from tools.links import DID, PDS

    resp = httpx.get(f"{PDS}/xrpc/com.atproto.repo.listRecords",
        params={"repo": DID, "collection": "network.comind.thought", "limit": limit}, timeout=30)

    if resp.status_code != 200:
        console.print(f"[red]Failed: {resp.text}[/red]")
        return

    records = resp.json().get("records", [])
    if not records:
        console.print("[yellow]No thoughts found[/yellow]")
        return

    for r in records[:limit]:
        v = r["value"]
        text = v.get("thought", v.get("content", ""))[:60]
        rkey = r["uri"].split("/")[-1]
        console.print(f"  [dim]{rkey[:12]}[/dim] {text}...")


@thought.command()
@click.argument("text")
@click.option("--context", "-c", default="", help="Context for the thought")
def create(text: str, context: str):
    """Create a new thought."""
    import os
    import httpx
    from datetime import datetime, timezone
    from dotenv import load_dotenv

    load_dotenv()
    handle = os.getenv("ATPROTO_HANDLE")
    password = os.getenv("ATPROTO_APP_PASSWORD")
    pds = os.getenv("ATPROTO_PDS", "https://comind.network")

    if not handle or not password:
        console.print("[red]Error: ATPROTO_HANDLE and ATPROTO_APP_PASSWORD required[/red]")
        return

    # Auth
    resp = httpx.post(f"{pds}/xrpc/com.atproto.server.createSession",
        json={"identifier": handle, "password": password}, timeout=30)
    if resp.status_code != 200:
        console.print(f"[red]Auth failed: {resp.text}[/red]")
        return
    session = resp.json()
    token = session["accessJwt"]
    did = session["did"]

    # Create thought
    record = {
        "$type": "network.comind.thought",
        "thought": text,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    if context:
        record["context"] = context

    resp = httpx.post(f"{pds}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {token}"},
        json={"repo": did, "collection": "network.comind.thought", "record": record},
        timeout=30)

    if resp.status_code == 200:
        data = resp.json()
        console.print(f"[green]Created thought:[/green] {data['uri']}")
    else:
        console.print(f"[red]Failed: {resp.text}[/red]")


# Full-text search across all comind records
@cli.command("search-all")
@click.argument("query")
@click.option("--collection", "-c", default=None, help="Limit to specific collection")
@click.option("--limit", "-l", default=20, help="Max results")
def search_all(query: str, collection: str, limit: int):
    """Search across all comind records."""
    import httpx
    from tools.links import DID, PDS

    # Collections to search
    collections = [
        "network.comind.concept",
        "network.comind.thought",
        "network.comind.observation",
        "network.comind.hypothesis",
        "network.comind.memory",
        "network.comind.reasoning",
        "network.comind.signal",
    ]

    if collection:
        collections = [collection]

    results = []
    for coll in collections:
        resp = httpx.get(f"{PDS}/xrpc/com.atproto.repo.listRecords",
            params={"repo": DID, "collection": coll, "limit": 50}, timeout=30)

        if resp.status_code != 200:
            continue

        for r in resp.json().get("records", []):
            v = r["value"]
            # Search in all text fields
            text_fields = ["concept", "thought", "content", "understanding", "description", "note", "text"]
            full_text = " ".join(str(v.get(f, "")) for f in text_fields)

            if query.lower() in full_text.lower():
                results.append((coll, r["uri"].split("/")[-1], v, full_text[:100]))

    if not results:
        console.print(f"[yellow]No results for '{query}'[/yellow]")
        return

    console.print(f"\n[bold]Results for '{query}' ({len(results)}):[/bold]\n")
    for coll, rkey, v, excerpt in results[:limit]:
        coll_short = coll.split(".")[-1]
        console.print(f"  [dim]{coll_short}[/dim] [cyan]{rkey[:20]}[/cyan]")
        console.print(f"    {excerpt}...")
        console.print()


cli.add_command(thought)


if __name__ == "__main__":
    cli()
