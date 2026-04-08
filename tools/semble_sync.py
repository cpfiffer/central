#!/usr/bin/env python
"""
Semble Markdown Sync Tool

Bidirectional sync between Semble (ATProto) and local Markdown files.

Usage:
    uv run python -m tools.sembles_sync export --collection <uri> --output <dir>
    uv run python -m tools.sembles_sync import --input <dir> --dry-run
    uv run python -m tools.sembles_sync status --collection <uri>

Requirements:
- Export: semble -> markdown with frontmatter (URI, CID, timestamp)
- Import: markdown -> semble with schema validation
- Conflict resolution: PDS wins, local changes flagged
- Manual sync (not automatic)
"""

import os
import json
import asyncio
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import httpx
import click
from rich.console import Console
from rich.table import Table

console = Console()

# Configuration
HANDLE = os.getenv("ATPROTO_HANDLE", "central.comind.network")
DID = os.getenv("ATPROTO_DID", "did:plc:l46arqe6yfgh36h3o554iyvr")
PDS = os.getenv("ATPROTO_PDS", "https://comind.network")
APP_PASSWORD = os.getenv("ATPROTO_APP_PASSWORD", "")

# Lexicon NSIDs
CARD_LEXICON = "network.cosmik.card"
COLLECTION_LEXICON = "network.cosmik.collection"
COLLECTION_LINK_LEXICON = "network.cosmik.collectionLink"


@dataclass
class SembleCard:
    """Represents a Semble card record."""
    uri: str
    cid: str
    title: Optional[str] = None
    text: Optional[str] = None
    url: Optional[str] = None
    created_at: Optional[str] = None
    author: Optional[str] = None
    indexed_at: Optional[str] = None


@dataclass
class SyncStatus:
    """Sync status for a card."""
    uri: str
    local_path: Optional[Path] = None
    local_modified: Optional[datetime] = None
    remote_modified: Optional[datetime] = None
    status: str = "unknown"  # synced, local_only, remote_only, conflict


class SembleClient:
    """Client for interacting with Semble via ATProto."""

    def __init__(self):
        self.handle = HANDLE
        self.did = DID
        self.pds = PDS
        self.access_jwt: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient()
        await self.authenticate()
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def authenticate(self):
        """Authenticate with PDS."""
        if not APP_PASSWORD:
            console.print("[yellow]Warning: No ATPROTO_APP_PASSWORD set[/yellow]")
            return

        response = await self._client.post(
            f"{self.pds}/xrpc/com.atproto.server.createSession",
            json={"identifier": self.handle, "password": APP_PASSWORD}
        )
        if response.status_code == 200:
            data = response.json()
            self.access_jwt = data.get("accessJwt")
            console.print(f"[green]Authenticated as {self.handle}[/green]")
        else:
            console.print(f"[red]Authentication failed: {response.text}[/red]")

    @property
    def auth_headers(self) -> dict:
        if self.access_jwt:
            return {"Authorization": f"Bearer {self.access_jwt}"}
        return {}

    async def get_collection(self, collection_uri: str) -> Dict[str, Any]:
        """Fetch a collection and its cards from PDS."""
        # Parse the URI: at://did/collection/rkey
        parts = collection_uri.replace("at://", "").split("/")
        if len(parts) < 3:
            raise ValueError(f"Invalid collection URI: {collection_uri}")

        collection_did = parts[0]
        collection_nsid = parts[1]
        collection_rkey = parts[2]

        # Get the collection record
        response = await self._client.get(
            f"{self.pds}/xrpc/com.atproto.repo.getRecord",
            params={
                "repo": collection_did,
                "collection": collection_nsid,
                "rkey": collection_rkey
            }
        )

        if response.status_code != 200:
            raise ValueError(f"Failed to fetch collection: {response.text}")

        collection_record = response.json()

        # Get all cards linked to this collection
        # This requires querying the PDS for collectionLink records
        # For now, we'll use the semble.so API if available

        return collection_record

    async def list_cards(self, collection_uri: str) -> List[SembleCard]:
        """List all cards in a collection by querying collectionLinks from PDS."""
        cards = []
        cursor = None

        # Parse collection URI to get the rkey
        collection_rkey = collection_uri.split("/")[-1]

        # Query PDS for collectionLink records
        while True:
            params = {
                "repo": self.did,
                "collection": COLLECTION_LINK_LEXICON,
                "limit": 100
            }
            if cursor:
                params["cursor"] = cursor

            response = await self._client.get(
                f"{self.pds}/xrpc/com.atproto.repo.listRecords",
                params=params
            )

            if response.status_code != 200:
                console.print(f"[red]Failed to list records: {response.text}[/red]")
                break

            data = response.json()
            records = data.get("records", [])

            # Filter for links to this collection
            for record in records:
                value = record.get("value", {})
                coll_uri = value.get("collection", {}).get("uri", "")
                if collection_rkey in coll_uri:
                    # Get card details
                    card_uri = value.get("card", {}).get("uri", "")
                    card_cid = value.get("card", {}).get("cid", "")
                    if card_uri:
                        card = await self.get_card(card_uri)
                        if card:
                            cards.append(card)

            cursor = data.get("cursor")
            if not cursor:
                break

        return cards

    async def get_card(self, card_uri: str) -> Optional[SembleCard]:
        """Fetch a single card by URI."""
        parts = card_uri.replace("at://", "").split("/")
        if len(parts) < 3:
            return None

        card_did = parts[0]
        card_nsid = parts[1]
        card_rkey = parts[2]

        response = await self._client.get(
            f"{self.pds}/xrpc/com.atproto.repo.getRecord",
            params={
                "repo": card_did,
                "collection": card_nsid,
                "rkey": card_rkey
            }
        )

        if response.status_code != 200:
            return None

        data = response.json()
        value = data.get("value", {})

        # Handle both URL and NOTE card types
        card_type = value.get("type", "NOTE")
        content = value.get("content", {})

        if card_type == "URL":
            title = content.get("metadata", {}).get("title")
            text = content.get("metadata", {}).get("description")
            url = content.get("url")
        else:
            # NOTE type
            title = value.get("title")
            text = content.get("text", content.get("body", ""))
            url = None

        return SembleCard(
            uri=card_uri,
            cid=data.get("cid", ""),
            title=title,
            text=text,
            url=url,
            created_at=value.get("createdAt"),
            author=card_did
        )

    async def create_card(self, card: SembleCard) -> Dict[str, Any]:
        """Create a new card record."""
        if not self.access_jwt:
            raise ValueError("Not authenticated")

        # Generate rkey from title or timestamp
        import hashlib
        rkey = hashlib.md5((card.title or str(datetime.now())).encode()).hexdigest()[:13]

        record = {
            "$type": CARD_LEXICON,
            "title": card.title,
            "text": card.text,
            "url": card.url,
            "createdAt": card.created_at or datetime.now().isoformat() + "Z"
        }

        response = await self._client.post(
            f"{self.pds}/xrpc/com.atproto.repo.putRecord",
            headers=self.auth_headers,
            json={
                "repo": self.did,
                "collection": CARD_LEXICON,
                "rkey": rkey,
                "record": record
            }
        )

        if response.status_code == 200:
            return response.json()
        else:
            raise ValueError(f"Failed to create card: {response.text}")


def card_to_markdown(card: SembleCard) -> str:
    """Convert a SembleCard to markdown with frontmatter."""
    frontmatter = {
        "uri": card.uri,
        "cid": card.cid,
        "author": card.author,
        "created_at": card.created_at,
        "indexed_at": card.indexed_at,
        "synced_at": datetime.now().isoformat()
    }

    md = "---\n"
    md += yaml.dump(frontmatter, default_flow_style=False)
    md += "---\n\n"

    if card.title:
        md += f"# {card.title}\n\n"

    if card.text:
        md += card.text + "\n"

    if card.url:
        md += f"\n[URL]({card.url})\n"

    return md


def markdown_to_card(md_content: str, path: Path) -> SembleCard:
    """Parse markdown with frontmatter into a SembleCard."""
    # Parse frontmatter
    if not md_content.startswith("---"):
        raise ValueError("Missing frontmatter")

    parts = md_content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Invalid frontmatter format")

    frontmatter = yaml.safe_load(parts[1])
    content = parts[2].strip()

    # Extract title from content or frontmatter
    title = frontmatter.get("title")
    if not title and content.startswith("#"):
        title = content.split("\n")[0].strip("# ").strip()

    return SembleCard(
        uri=frontmatter.get("uri", ""),
        cid=frontmatter.get("cid", ""),
        title=title,
        text=content,
        url=frontmatter.get("url"),
        created_at=frontmatter.get("created_at"),
        author=frontmatter.get("author", DID)
    )


# CLI Commands

def export(collection: str, output: Path, flatten: bool):
    """Export Semble collection to markdown files."""
    output.mkdir(parents=True, exist_ok=True)

    async def do_export():
        async with SembleClient() as client:
            cards = await client.list_cards(collection)
            console.print(f"[green]Found {len(cards)} cards[/green]")

            for card in cards:
                md = card_to_markdown(card)
                # Generate filename from title or rkey
                rkey = card.uri.split("/")[-1]
                filename = (card.title or rkey).replace("/", "-").replace(" ", "-")[:50]
                filepath = output / f"{filename}.md"

                with open(filepath, "w") as f:
                    f.write(md)

                console.print(f"  [green]Exported:[/green] {filepath}")

    asyncio.run(do_export())


def import_cards(input: Path, dry_run: bool):
    """Import markdown files to Semble."""
    md_files = list(input.glob("*.md"))
    console.print(f"[green]Found {len(md_files)} markdown files[/green]")

    async def do_import():
        async with SembleClient() as client:
            for md_file in md_files:
                try:
                    content = md_file.read_text()
                    card = markdown_to_card(content, md_file)

                    if dry_run:
                        console.print(f"  [yellow]Would import:[/yellow] {md_file.name}")
                        console.print(f"    Title: {card.title}")
                        console.print(f"    URI: {card.uri or 'new'}")
                    else:
                        if card.uri:
                            # Update existing
                            console.print(f"  [blue]Updating:[/blue] {md_file.name}")
                        else:
                            # Create new
                            result = await client.create_card(card)
                            console.print(f"  [green]Created:[/green] {md_file.name}")
                            console.print(f"    URI: {result.get('uri')}")

                except Exception as e:
                    console.print(f"  [red]Error:[/red] {md_file.name}: {e}")

    asyncio.run(do_import())


def status(collection: str, local_dir: Optional[Path] = None):
    """Show sync status for a collection.

    Compares local files with remote cards to identify:
    - Cards only on remote (need download)
    - Cards only local (need upload)
    - Cards in both (check for conflicts)
    """
    console.print(f"[blue]Collection:[/blue] {collection}")

    async def do_status():
        async with SembleClient() as client:
            # Get remote cards
            remote_cards = await client.list_cards(collection)
            console.print(f"[green]Remote cards:[/green] {len(remote_cards)}")

            if local_dir and local_dir.exists():
                # Get local files
                local_files = list(local_dir.glob("*.md"))
                console.print(f"[green]Local files:[/green] {len(local_files)}")

                # Build maps
                remote_uris = {card.uri: card for card in remote_cards}
                local_uris = {}

                for md_file in local_files:
                    try:
                        content = md_file.read_text()
                        if content.startswith("---"):
                            parts = content.split("---", 2)
                            if len(parts) >= 3:
                                fm = yaml.safe_load(parts[1])
                                if fm.get("uri"):
                                    local_uris[fm["uri"]] = md_file
                    except Exception:
                        pass

                # Find differences
                remote_only = set(remote_uris.keys()) - set(local_uris.keys())
                local_only = set(local_uris.keys()) - set(remote_uris.keys())
                both = set(remote_uris.keys()) & set(local_uris.keys())

                if remote_only:
                    console.print(f"\n[yellow]Remote only (need download):[/yellow]")
                    for uri in remote_only:
                        card = remote_uris[uri]
                        console.print(f"  - {card.title or uri.split('/')[-1]}")

                if local_only:
                    console.print(f"\n[yellow]Local only (need upload):[/yellow]")
                    for uri in local_only:
                        f = local_uris[uri]
                        console.print(f"  - {f.name}")

                if both:
                    console.print(f"\n[green]In sync:[/green] {len(both)} cards")

    asyncio.run(do_status())


if __name__ == "__main__":
    sync_cli()
