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


# Import connection commands
from tools.links import connection as connection_group, links as links_group
cli.add_command(connection_group, name="connection")
cli.add_command(links_group, name="link")  # Legacy compatibility


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
        console.print(f"  [dim]{rkey}[/dim] {text}...")


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


# Semble card commands
@cli.group()
def card():
    """Manage Semble cards (URL bookmarks and notes)."""
    pass


@card.command()
@click.argument("url")
@click.option("--title", "-t", default="", help="Card title")
@click.option("--description", "-d", default="", help="Card description")
def url(url: str, title: str, description: str):
    """Create a URL card."""
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

    # Create URL card
    record = {
        "$type": "network.cosmik.card",
        "type": "URL",
        "content": {
            "$type": "network.cosmik.card#urlContent",
            "url": url,
        },
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }

    if title or description:
        record["content"]["metadata"] = {
            "$type": "network.cosmik.card#urlMetadata",
        }
        if title:
            record["content"]["metadata"]["title"] = title
        if description:
            record["content"]["metadata"]["description"] = description


    resp = httpx.post(f"{pds}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {token}"},
        json={"repo": did, "collection": "network.cosmik.card", "record": record},
        timeout=30)

    if resp.status_code == 200:
        data = resp.json()
        console.print(f"[green]Created URL card:[/green] {data['uri']}")
    else:
        console.print(f"[red]Failed: {resp.text}[/red]")


@card.command()
@click.argument("text")
@click.option("--parent", "-p", required=True, help="Parent card URI (URL card to attach note to)")
def note(text: str, parent: str):
    """Create a NOTE card attached to a URL card."""
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

    # Get parent card CID
    if not parent.startswith("at://"):
        console.print("[red]Parent must be an AT URI (at://...)[/red]")
        return

    parent_rkey = parent.split("/")[-1]
    resp = httpx.get(f"{pds}/xrpc/com.atproto.repo.getRecord",
        params={"repo": did, "collection": "network.cosmik.card", "rkey": parent_rkey}, timeout=30)

    if resp.status_code != 200:
        console.print(f"[red]Parent card not found: {resp.text}[/red]")
        return

    parent_cid = resp.json().get("cid")

    # Create NOTE card
    record = {
        "$type": "network.cosmik.card",
        "type": "NOTE",
        "content": {
            "$type": "network.cosmik.card#noteContent",
            "text": text,
        },
        "parentCard": {
            "uri": parent,
            "cid": parent_cid,
        },
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }

    resp = httpx.post(f"{pds}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {token}"},
        json={"repo": did, "collection": "network.cosmik.card", "record": record},
        timeout=30)

    if resp.status_code == 200:
        data = resp.json()
        console.print(f"[green]Created NOTE card:[/green] {data['uri']}")
        console.print(f"  Attached to: {parent}")
    else:
        console.print(f"[red]Failed: {resp.text}[/red]")


@card.command("list")
@click.option("--limit", "-l", default=10, help="Max results")
def list_cards(limit: int):
    """List recent cards."""
    import httpx
    from tools.links import DID, PDS

    resp = httpx.get(f"{PDS}/xrpc/com.atproto.repo.listRecords",
        params={"repo": DID, "collection": "network.cosmik.card", "limit": limit}, timeout=30)

    if resp.status_code != 200:
        console.print(f"[red]Failed: {resp.text}[/red]")
        return

    records = resp.json().get("records", [])
    if not records:
        console.print("[yellow]No cards found[/yellow]")
        return

    for r in records[:limit]:
        v = r["value"]
        card_type = v.get("type", "?")
        rkey = r["uri"].split("/")[-1]

        if card_type == "URL":
            url = v.get("content", {}).get("url", "?")
            title = v.get("content", {}).get("metadata", {}).get("title", "")
            console.print(f"  [dim]{rkey}[/dim] [cyan]URL[/cyan] {title[:40] or url[:40]}")
        elif card_type == "NOTE":
            text = v.get("content", {}).get("text", "?")[:40]
            parent = v.get("parentCard", {}).get("uri", "")[-12:]
            console.print(f"  [dim]{rkey}[/dim] [yellow]NOTE[/yellow] {text}... → {parent}")
        else:
            console.print(f"  [dim]{rkey}[/dim] {card_type}")


@card.command()
@click.argument("uri")
def show(uri: str):
    """Show card details."""
    import httpx
    from tools.links import DID, PDS

    # Extract rkey if full URI
    if uri.startswith("at://"):
        rkey = uri.split("/")[-1]
    else:
        rkey = uri

    resp = httpx.get(f"{PDS}/xrpc/com.atproto.repo.getRecord",
        params={"repo": DID, "collection": "network.cosmik.card", "rkey": rkey}, timeout=30)

    if resp.status_code != 200:
        console.print(f"[red]Card not found: {resp.text}[/red]")
        return

    data = resp.json()
    v = data["value"]
    card_uri = data["uri"]

    console.print(f"\n[bold cyan]Card: {rkey}[/bold cyan]")
    console.print(f"  URI: {card_uri}")
    console.print(f"  Type: {v.get('type', '?')}")
    console.print(f"  Created: {v.get('createdAt', '?')}")

    if v.get("type") == "URL":
        content = v.get("content", {})
        console.print(f"  URL: {content.get('url', '?')}")
        metadata = content.get("metadata", {})
        if metadata:
            if metadata.get("title"):
                console.print(f"  Title: {metadata['title']}")
            if metadata.get("description"):
                console.print(f"  Description: {metadata['description'][:200]}...")
    elif v.get("type") == "NOTE":
        content = v.get("content", {})
        text = content.get("text", "")
        console.print(f"\n  [yellow]Note:[/yellow]")
        for line in text.split("\n")[:10]:
            console.print(f"    {line}")
        if len(text.split("\n")) > 10:
            lines = text.split('\n')
            console.print(f"    ... ({len(lines) - 10} more lines)")

        parent = v.get("parentCard", {})
        if parent:
            console.print(f"\n  [dim]Attached to: {parent.get('uri', '?')}[/dim]")


@card.command()
@click.argument("rkey")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def delete(rkey: str, force: bool):
    """Delete a card."""
    import os
    import httpx
    from dotenv import load_dotenv

    if not force:
        console.print(f"[yellow]About to delete card: {rkey}[/yellow]")
        console.print("[dim]Use --force to confirm[/dim]")
        return

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

    # Delete
    resp = httpx.post(f"{pds}/xrpc/com.atproto.repo.deleteRecord",
        headers={"Authorization": f"Bearer {token}"},
        json={"repo": did, "collection": "network.cosmik.card", "rkey": rkey},
        timeout=30)

    if resp.status_code == 200:
        console.print(f"[green]Deleted card: {rkey}[/green]")
    else:
        console.print(f"[red]Failed: {resp.text}[/red]")


@card.command()
@click.argument("card_rkey")
@click.argument("collection_rkey")
def link(card_rkey: str, collection_rkey: str):
    """Link a card to a collection."""
    import os
    import httpx
    from dotenv import load_dotenv
    from datetime import datetime, timezone

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

    # Get card CID
    card_uri = f"at://{did}/network.cosmik.card/{card_rkey}"
    resp = httpx.get(
        f"{pds}/xrpc/com.atproto.repo.getRecord",
        params={"repo": did, "collection": "network.cosmik.card", "rkey": card_rkey},
        timeout=30
    )
    if resp.status_code != 200:
        console.print(f"[red]Failed to get card: {resp.text}[/red]")
        return
    card_cid = resp.json().get("cid")
    if not card_cid:
        console.print("[red]Card CID not found[/red]")
        return

    # Get collection CID
    collection_uri = f"at://{did}/network.cosmik.collection/{collection_rkey}"
    resp = httpx.get(
        f"{pds}/xrpc/com.atproto.repo.getRecord",
        params={"repo": did, "collection": "network.cosmik.collection", "rkey": collection_rkey},
        timeout=30
    )
    if resp.status_code != 200:
        console.print(f"[red]Failed to get collection: {resp.text}[/red]")
        return
    collection_cid = resp.json().get("cid")
    if not collection_cid:
        console.print("[red]Collection CID not found[/red]")
        return

    # Create collectionLink with correct format
    # Note: addedBy and addedAt are REQUIRED by Semble's firehose processor
    now = datetime.now(timezone.utc).isoformat()
    link_record = {
        "$type": "network.cosmik.collectionLink",
        "card": {"uri": card_uri, "cid": card_cid},
        "collection": {"uri": collection_uri, "cid": collection_cid},
        "addedBy": did,  # REQUIRED by Semble
        "addedAt": now,  # REQUIRED by Semble
        "createdAt": now,
    }

    resp = httpx.post(
        f"{pds}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "repo": did,
            "collection": "network.cosmik.collectionLink",
            "record": link_record
        },
        timeout=30
    )

    if resp.status_code == 200:
        result = resp.json()
        link_uri = result.get("uri", "")
        console.print(f"[green]Linked card {card_rkey} to collection {collection_rkey}[/green]")
        console.print(f"[dim]URI: {link_uri}[/dim]")
    else:
        console.print(f"[red]Failed: {resp.text}[/red]")


cli.add_command(card)


# Semble collection commands
@cli.group()
def collection():
    """Manage Semble collections."""
    pass


@collection.command()
@click.argument("name")
@click.option("--description", "-d", default="", help="Collection description")
def create(name: str, description: str):
    """Create a new collection."""
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

    # Create collection
    record = {
        "$type": "network.cosmik.collection",
        "name": name,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    if description:
        record["description"] = description

    resp = httpx.post(f"{pds}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {token}"},
        json={"repo": did, "collection": "network.cosmik.collection", "record": record},
        timeout=30)

    if resp.status_code == 200:
        data = resp.json()
        console.print(f"[green]Created collection:[/green] {data['uri']}")
        console.print(f"  View: https://semble.so/collection/{data['uri']}")
    else:
        console.print(f"[red]Failed: {resp.text}[/red]")


@collection.command("list")
@click.option("--limit", "-l", default=10, help="Max results")
def list_collections(limit: int):
    """List collections."""
    import httpx
    from tools.links import DID, PDS

    resp = httpx.get(f"{PDS}/xrpc/com.atproto.repo.listRecords",
        params={"repo": DID, "collection": "network.cosmik.collection", "limit": limit}, timeout=30)

    if resp.status_code != 200:
        console.print(f"[red]Failed: {resp.text}[/red]")
        return

    records = resp.json().get("records", [])
    if not records:
        console.print("[yellow]No collections found[/yellow]")
        return

    for r in records[:limit]:
        v = r["value"]
        name = v.get("name", "?")
        rkey = r["uri"].split("/")[-1]
        desc = v.get("description", "")[:40]
        console.print(f"  [dim]{rkey}[/dim] [cyan]{name}[/cyan]")
        if desc:
            console.print(f"    {desc}...")


@collection.command()
@click.argument("uri")
def show(uri: str):
    """Show collection with its cards."""
    import httpx
    from tools.links import DID, PDS

    # Extract rkey if full URI
    if uri.startswith("at://"):
        rkey = uri.split("/")[-1]
    else:
        rkey = uri

    # Get collection
    resp = httpx.get(f"{PDS}/xrpc/com.atproto.repo.getRecord",
        params={"repo": DID, "collection": "network.cosmik.collection", "rkey": rkey}, timeout=30)

    if resp.status_code != 200:
        console.print(f"[red]Collection not found: {resp.text}[/red]")
        return

    data = resp.json()
    v = data["value"]
    coll_uri = data["uri"]

    console.print(f"\n[bold cyan]Collection: {v.get('name', '?')}[/bold cyan]")
    console.print(f"  URI: {coll_uri}")
    if v.get("description"):
        console.print(f"  Description: {v['description']}")
    console.print(f"  Created: {v.get('createdAt', '?')}")

    # Get cards in collection
    resp = httpx.get(f"{PDS}/xrpc/com.atproto.repo.listRecords",
        params={"repo": DID, "collection": "network.cosmik.collectionLink", "limit": 100}, timeout=30)

    if resp.status_code != 200:
        console.print("[yellow]Could not fetch cards[/yellow]")
        return

    links = [r for r in resp.json().get("records", [])
             if r["value"].get("collection", {}).get("uri", "").endswith(rkey)]

    if not links:
        console.print("\n  [dim]No cards in collection[/dim]")
        return

    console.print(f"\n  [bold]Cards ({len(links)}):[/bold]")

    # Get card details
    for link in links[:10]:
        card_uri = link["value"].get("card", {}).get("uri", "")
        card_rkey = card_uri.split("/")[-1]

        card_resp = httpx.get(f"{PDS}/xrpc/com.atproto.repo.getRecord",
            params={"repo": DID, "collection": "network.cosmik.card", "rkey": card_rkey}, timeout=30)

        if card_resp.status_code == 200:
            card_v = card_resp.json()["value"]
            card_type = card_v.get("type", "?")

            if card_type == "URL":
                title = card_v.get("content", {}).get("metadata", {}).get("title", "")
                url = card_v.get("content", {}).get("url", "")
                console.print(f"    [dim]{card_rkey}[/dim] [cyan]URL[/cyan] {title[:30] or url[:30]}")
            elif card_type == "NOTE":
                text = card_v.get("content", {}).get("text", "")[:30]
                console.print(f"    [dim]{card_rkey}[/dim] [yellow]NOTE[/yellow] {text}...")
        else:
            console.print(f"    [dim]{card_rkey}[/dim] [red]not found[/red]")


@collection.command()
@click.argument("uri")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def delete(uri: str, force: bool):
    """Delete a collection (and its links)."""
    import os
    import httpx
    from dotenv import load_dotenv

    # Extract rkey if full URI
    if uri.startswith("at://"):
        rkey = uri.split("/")[-1]
    else:
        rkey = uri

    if not force:
        console.print(f"[yellow]About to delete collection: {rkey}[/yellow]")
        console.print("[dim]This will also delete all collectionLinks[/dim]")
        console.print("[dim]Use --force to confirm[/dim]")
        return

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

    # Delete collectionLinks first
    resp = httpx.get(f"{pds}/xrpc/com.atproto.repo.listRecords",
        params={"repo": did, "collection": "network.cosmik.collectionLink", "limit": 100}, timeout=30)

    if resp.status_code == 200:
        links = [r for r in resp.json().get("records", [])
                 if r["value"].get("collection", {}).get("uri", "").endswith(rkey)]

        for link in links:
            link_rkey = link["uri"].split("/")[-1]
            httpx.post(f"{pds}/xrpc/com.atproto.repo.deleteRecord",
                headers={"Authorization": f"Bearer {token}"},
                json={"repo": did, "collection": "network.cosmik.collectionLink", "rkey": link_rkey},
                timeout=30)

        console.print(f"  [dim]Deleted {len(links)} collectionLinks[/dim]")

    # Delete collection
    resp = httpx.post(f"{pds}/xrpc/com.atproto.repo.deleteRecord",
        headers={"Authorization": f"Bearer {token}"},
        json={"repo": did, "collection": "network.cosmik.collection", "rkey": rkey},
        timeout=30)

    if resp.status_code == 200:
        console.print(f"[green]Deleted collection: {rkey}[/green]")
    else:
        console.print(f"[red]Failed: {resp.text}[/red]")


@collection.command()
@click.argument("card_uri")
@click.argument("collection_uri")
def add(card_uri: str, collection_uri: str):
    """Add a card to a collection."""
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

    # Get CIDs
    def get_cid(uri):
        if not uri.startswith("at://"):
            return None
        rkey = uri.split("/")[-1]
        coll = uri.split("/")[-2]
        resp = httpx.get(f"{pds}/xrpc/com.atproto.repo.getRecord",
            params={"repo": did, "collection": coll, "rkey": rkey}, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("cid")
        return None

    card_cid = get_cid(card_uri)
    collection_cid = get_cid(collection_uri)

    if not card_cid or not collection_cid:
        console.print(f"[red]Could not find card or collection[/red]")
        return

    # Create collectionLink
    record = {
        "$type": "network.cosmik.collectionLink",
        "card": {"uri": card_uri, "cid": card_cid},
        "collection": {"uri": collection_uri, "cid": collection_cid},
        "addedBy": did,
        "addedAt": datetime.now(timezone.utc).isoformat(),
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }

    resp = httpx.post(f"{pds}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {token}"},
        json={"repo": did, "collection": "network.cosmik.collectionLink", "record": record},
        timeout=30)

    if resp.status_code == 200:
        data = resp.json()
        console.print(f"[green]Added card to collection[/green]")
        console.print(f"  Card: {card_uri[-30:]}")
        console.print(f"  Collection: {collection_uri[-30:]}")
    else:
        console.print(f"[red]Failed: {resp.text}[/red]")


cli.add_command(collection)


if __name__ == "__main__":
    cli()
