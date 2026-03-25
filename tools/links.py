#!/usr/bin/env python
"""
Comind Links - Create and manage relationships between ATProtocol records.

Usage:
    comind link create <source_uri> <target_uri> --relationship REFERENCES --note "..." --strength 0.8
    comind link list [--source <uri>] [--target <uri>] [--relationship <type>]
    comind link show <link_uri>
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional
import click
import httpx
from rich.console import Console
from rich.table import Table

console = Console()

# Config
DID = os.getenv("ATPROTO_DID", "did:plc:l46arqe6yfgh36h3o554iyvr")
PDS = os.getenv("ATPROTO_PDS", "https://comind.network")
COLLECTION = "network.comind.link"

RELATIONSHIP_TYPES = [
    "REFERENCES",
    "SUPPORTS",
    "CONTRADICTS",
    "PART_OF",
    "PRECEDES",
    "CAUSES",
    "INSTANCE_OF",
    "ANSWERS",
]


def get_session():
    """Get authenticated session from env."""
    handle = os.getenv("ATPROTO_HANDLE")
    password = os.getenv("ATPROTO_APP_PASSWORD")

    if not handle or not password:
        console.print("[red]Error: ATPROTO_HANDLE and ATPROTO_APP_PASSWORD required[/red]")
        raise SystemExit(1)

    resp = httpx.post(
        f"{PDS}/xrpc/com.atproto.server.createSession",
        json={"identifier": handle, "password": password},
        timeout=30,
    )

    if resp.status_code != 200:
        console.print(f"[red]Auth failed: {resp.text}[/red]")
        raise SystemExit(1)

    return resp.json()


def parse_uri(uri: str) -> dict:
    """Parse AT URI into components."""
    # at://did:plc:xxx/collection/rkey
    parts = uri.replace("at://", "").split("/")
    return {
        "did": parts[0],
        "collection": parts[1] if len(parts) > 1 else None,
        "rkey": parts[2] if len(parts) > 2 else None,
    }


def get_record_cid(uri: str) -> Optional[str]:
    """Fetch CID for a record."""
    parsed = parse_uri(uri)
    if not parsed["collection"] or not parsed["rkey"]:
        return None

    resp = httpx.get(
        f"{PDS}/xrpc/com.atproto.repo.getRecord",
        params={
            "repo": parsed["did"],
            "collection": parsed["collection"],
            "rkey": parsed["rkey"],
        },
        timeout=30,
    )

    if resp.status_code == 200:
        return resp.json().get("cid")
    return None


@click.group()
def links():
    """Manage comind relationship links."""
    pass


@links.command()
@click.argument("source_uri")
@click.argument("target_uri")
@click.option("--relationship", "-r", type=click.Choice(RELATIONSHIP_TYPES), required=True)
@click.option("--note", "-n", default="", help="Note explaining the relationship")
@click.option("--strength", "-s", type=float, default=0.8, help="Relationship strength (0-1)")
def create(source_uri: str, target_uri: str, relationship: str, note: str, strength: float):
    """Create a link between two records."""
    session = get_session()
    token = session["accessJwt"]
    did = session["did"]

    # Create link record - simple structure matching network.comind.link
    record = {
        "$type": COLLECTION,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "source": source_uri,
        "target": target_uri,
        "relationship": relationship,
        "note": note,
    }

    if strength != 0.8:
        record["strength"] = strength

    resp = httpx.post(
        f"{PDS}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {token}"},
        json={"repo": did, "collection": COLLECTION, "record": record},
        timeout=30,
    )

    if resp.status_code == 200:
        data = resp.json()
        console.print(f"[green]Created link:[/green]")
        console.print(f"  URI: {data['uri']}")
        console.print(f"  {source_uri}")
        console.print(f"  └──[{relationship}]──> {target_uri}")
        if note:
            console.print(f"  Note: {note}")
    else:
        console.print(f"[red]Failed: {resp.text}[/red]")


@links.command("list")
@click.option("--source", "source_uri", help="Filter by source URI")
@click.option("--target", "target_uri", help="Filter by target URI")
@click.option("--relationship", "-r", type=str, help="Filter by relationship type")
@click.option("--limit", "-l", default=20, help="Max results")
def list_links(source_uri: str, target_uri: str, relationship: str, limit: int):
    """List links, optionally filtered."""
    resp = httpx.get(
        f"{PDS}/xrpc/com.atproto.repo.listRecords",
        params={"repo": DID, "collection": COLLECTION, "limit": limit},
        timeout=30,
    )

    if resp.status_code != 200:
        console.print(f"[red]Failed: {resp.text}[/red]")
        return

    records = resp.json().get("records", [])

    # Filter
    if source_uri:
        records = [r for r in records if r["value"].get("source") == source_uri]
    if target_uri:
        records = [r for r in records if r["value"].get("target") == target_uri]
    if relationship:
        records = [r for r in records if r["value"].get("relationship") == relationship.upper()]

    if not records:
        console.print("[yellow]No links found[/yellow]")
        return

    table = Table(title=f"Links ({len(records)})")
    table.add_column("URI", style="dim")
    table.add_column("Relationship", style="cyan")
    table.add_column("Source", style="green")
    table.add_column("Target", style="blue")
    table.add_column("Note")

    for r in records:
        v = r["value"]
        src = v.get("source", "?")
        tgt = v.get("target", "?")
        # Truncate URIs for display
        src_short = src.split("/")[-1] if src else "?"
        tgt_short = tgt.split("/")[-1] if tgt else "?"
        table.add_row(
            r["uri"].split("/")[-1],
            v.get("relationship", "?"),
            src_short[:30],
            tgt_short[:30],
            v.get("note", "")[:30],
        )

    console.print(table)


@links.command()
@click.argument("link_uri")
def show(link_uri: str):
    """Show details of a specific link."""
    # Parse URI to get rkey
    rkey = link_uri.split("/")[-1]

    resp = httpx.get(
        f"{PDS}/xrpc/com.atproto.repo.getRecord",
        params={"repo": DID, "collection": COLLECTION, "rkey": rkey},
        timeout=30,
    )

    if resp.status_code != 200:
        console.print(f"[red]Link not found: {link_uri}[/red]")
        return

    data = resp.json()
    v = data["value"]

    console.print(f"\n[bold]Link: {link_uri}[/bold]\n")
    console.print(f"Relationship: [cyan]{v.get('relationship', '?')}[/cyan]")
    console.print(f"Strength: {v.get('strength', 'n/a')}")
    console.print(f"Created: {v.get('createdAt', '?')}")
    console.print(f"\n[green]Source:[/green]")
    console.print(f"  {v.get('source', '?')}")
    console.print(f"\n[blue]Target:[/blue]")
    console.print(f"  {v.get('target', '?')}")
    if v.get("note"):
        console.print(f"\nNote: {v['note']}")


if __name__ == "__main__":
    links()
