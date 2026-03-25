#!/usr/bin/env python
"""
Connection CLI - Create and manage network.cosmik.connection records.

Uses Semble's connection lexicon for interoperability.

Connection types:
  - related (default)
  - supports
  - opposes
  - addresses
  - helpful
  - explainer
  - leads_to
  - supplements

Usage:
  comind connection create <source> <target> --type supports --note "..."
  comind connection list
  comind connection show <uri>
"""

import os
import click
import httpx
from datetime import datetime, timezone
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv()

console = Console()
DID = os.getenv("ATPROTO_DID", "did:plc:l46arqe6yfgh36h3o554iyvr")
PDS = os.getenv("ATPROTO_PDS", "https://comind.network")
COLLECTION = "network.cosmik.connection"

# Semble connection types
CONNECTION_TYPES = [
    "related",
    "supports",
    "opposes",
    "addresses",
    "helpful",
    "explainer",
    "leads_to",
    "supplements",
]


def get_session():
    """Get authenticated session."""
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


@click.group()
def connection():
    """Manage connections between records (network.cosmik.connection)."""
    pass


@connection.command()
@click.argument("source_uri")
@click.argument("target_uri")
@click.option("--type", "-t", "connection_type", type=click.Choice(CONNECTION_TYPES), default="related", help="Connection type")
@click.option("--note", "-n", default="", help="Note about the connection")
def create(source_uri: str, target_uri: str, connection_type: str, note: str):
    """Create a connection between two records."""
    session = get_session()
    token = session["accessJwt"]
    did = session["did"]

    # Create connection record
    record = {
        "$type": COLLECTION,
        "source": source_uri,
        "target": target_uri,
        "connectionType": connection_type,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }

    if note:
        record["note"] = note

    resp = httpx.post(
        f"{PDS}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {token}"},
        json={"repo": did, "collection": COLLECTION, "record": record},
        timeout=30,
    )

    if resp.status_code == 200:
        data = resp.json()
        console.print(f"[green]Created connection:[/green]")
        console.print(f"  URI: {data['uri']}")
        console.print(f"  {source_uri}")
        console.print(f"  └──[{connection_type}]──> {target_uri}")
        if note:
            console.print(f"  Note: {note}")
    else:
        console.print(f"[red]Failed: {resp.text}[/red]")


@connection.command("list")
@click.option("--source", "-s", default=None, help="Filter by source URI")
@click.option("--target", "-t", default=None, help="Filter by target URI")
@click.option("--type", "connection_type", default=None, help="Filter by connection type")
@click.option("--limit", "-l", default=20, help="Max results")
def list_connections(source: str, target: str, connection_type: str, limit: int):
    """List connections, optionally filtered."""
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
    if source:
        records = [r for r in records if source in r["value"].get("source", "")]
    if target:
        records = [r for r in records if target in r["value"].get("target", "")]
    if connection_type:
        records = [r for r in records if r["value"].get("connectionType") == connection_type]

    if not records:
        console.print("[yellow]No connections found[/yellow]")
        return

    table = Table(title=f"Connections ({len(records)})")
    table.add_column("URI", style="dim")
    table.add_column("Type", style="cyan")
    table.add_column("Source", style="green")
    table.add_column("Target", style="blue")
    table.add_column("Note")

    for r in records:
        v = r["value"]
        src = v.get("source", "?")
        tgt = v.get("target", "?")
        # Truncate URIs for display
        src_short = src.split("/")[-1][:30] if src else "?"
        tgt_short = tgt.split("/")[-1][:30] if tgt else "?"
        table.add_row(
            r["uri"].split("/")[-1],
            v.get("connectionType", "related"),
            src_short,
            tgt_short,
            v.get("note", "")[:30],
        )

    console.print(table)


@connection.command()
@click.argument("connection_uri")
def show(connection_uri: str):
    """Show details of a specific connection."""
    # Parse URI to get rkey
    rkey = connection_uri.split("/")[-1]

    resp = httpx.get(
        f"{PDS}/xrpc/com.atproto.repo.getRecord",
        params={"repo": DID, "collection": COLLECTION, "rkey": rkey},
        timeout=30,
    )

    if resp.status_code != 200:
        console.print(f"[red]Connection not found: {connection_uri}[/red]")
        return

    data = resp.json()
    v = data["value"]

    console.print(f"\n[bold]Connection: {connection_uri}[/bold]\n")
    console.print(f"Type: [cyan]{v.get('connectionType', 'related')}[/cyan]")
    console.print(f"Created: {v.get('createdAt', '?')}")
    console.print(f"\n[green]Source:[/green]")
    console.print(f"  {v.get('source', '?')}")
    console.print(f"\n[blue]Target:[/blue]")
    console.print(f"  {v.get('target', '?')}")
    if v.get("note"):
        console.print(f"\nNote: {v['note']}")


# Legacy compatibility - keep 'links' group as alias
@click.group()
def links():
    """Legacy: Use 'connection' command instead."""
    pass


@links.command()
@click.argument("source_uri")
@click.argument("target_uri")
@click.option("--relationship", "-r", type=click.Choice(["REFERENCES", "SUPPORTS", "CONTRADICTS", "PART_OF", "PRECEDES", "CAUSES", "INSTANCE_OF", "ANSWERS"]), required=True)
@click.option("--note", "-n", default="", help="Note explaining the relationship")
def create(source_uri: str, target_uri: str, relationship: str, note: str):
    """Create a connection (legacy compatibility)."""
    # Map old types to new
    type_map = {
        "REFERENCES": "related",
        "SUPPORTS": "supports",
        "CONTRADICTS": "opposes",
        "ANSWERS": "addresses",
        "PART_OF": "supplements",
        "PRECEDES": "leads_to",
    }
    connection_type = type_map.get(relationship, "related")
    console.print(f"[dim]Legacy: Using network.cosmik.connection with type '{connection_type}'[/dim]")

    session = get_session()
    token = session["accessJwt"]
    did = session["did"]

    record = {
        "$type": COLLECTION,
        "source": source_uri,
        "target": target_uri,
        "connectionType": connection_type,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    if note:
        record["note"] = note

    resp = httpx.post(
        f"{PDS}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {token}"},
        json={"repo": did, "collection": COLLECTION, "record": record},
        timeout=30,
    )

    if resp.status_code == 200:
        data = resp.json()
        console.print(f"[green]Created connection:[/green] {data['uri']}")
    else:
        console.print(f"[red]Failed: {resp.text}[/red]")


if __name__ == "__main__":
    connection()
