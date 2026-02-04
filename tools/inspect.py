"""
ATProto Record Inspector

Debug and inspect ATProto records - fetch, validate, check indexing.

Usage:
  uv run python -m tools.inspect <at-uri>
  uv run python -m tools.inspect at://did:plc:.../collection/rkey
  uv run python -m tools.inspect @handle collection rkey
"""

import asyncio
import sys
from urllib.parse import urlparse

import httpx
from rich.console import Console
from rich.panel import Panel

console = Console()


async def resolve_did(handle: str) -> str | None:
    """Resolve handle to DID."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle",
            params={"handle": handle.lstrip("@")}
        )
        if resp.status_code == 200:
            return resp.json().get("did")
    return None


async def get_pds(did: str) -> str:
    """Get PDS endpoint for a DID."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://plc.directory/{did}")
        if resp.status_code == 200:
            doc = resp.json()
            for svc in doc.get("service", []):
                if svc.get("id") == "#atproto_pds":
                    return svc.get("serviceEndpoint", "https://bsky.social")
    return "https://bsky.social"


async def fetch_record(did: str, collection: str, rkey: str) -> tuple[dict | None, str]:
    """Fetch a record from the appropriate PDS."""
    pds = await get_pds(did)
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{pds}/xrpc/com.atproto.repo.getRecord",
            params={"repo": did, "collection": collection, "rkey": rkey}
        )
        
        if resp.status_code == 200:
            return resp.json(), pds
        elif resp.status_code == 404:
            return None, pds
        else:
            return {"error": resp.text}, pds


async def check_indexed(uri: str) -> bool:
    """Check if record is in our XRPC indexer."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                "https://central-production.up.railway.app/xrpc/network.comind.search.query",
                params={"q": uri, "limit": 1},
                timeout=5
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                return any(r.get("uri") == uri for r in results)
        except:
            pass
    return False


def parse_at_uri(uri: str) -> tuple[str, str, str] | None:
    """Parse at:// URI into (did, collection, rkey)."""
    if not uri.startswith("at://"):
        return None
    
    parts = uri[5:].split("/")
    if len(parts) >= 3:
        did = parts[0]
        collection = parts[1]
        rkey = "/".join(parts[2:])
        return did, collection, rkey
    return None


async def inspect(uri_or_parts: list[str]):
    """Inspect an ATProto record."""
    
    # Parse input
    if len(uri_or_parts) == 1:
        # at:// URI
        parsed = parse_at_uri(uri_or_parts[0])
        if not parsed:
            console.print(f"[red]Invalid AT URI: {uri_or_parts[0]}[/red]")
            return
        did, collection, rkey = parsed
    elif len(uri_or_parts) == 3:
        # handle/did collection rkey
        did_or_handle, collection, rkey = uri_or_parts
        if did_or_handle.startswith("@") or not did_or_handle.startswith("did:"):
            did = await resolve_did(did_or_handle)
            if not did:
                console.print(f"[red]Could not resolve handle: {did_or_handle}[/red]")
                return
        else:
            did = did_or_handle
    else:
        console.print("[red]Usage: inspect <at-uri> OR inspect <handle> <collection> <rkey>[/red]")
        return
    
    uri = f"at://{did}/{collection}/{rkey}"
    console.print(f"\n[bold]Inspecting:[/bold] {uri}\n")
    
    # Fetch record
    record_data, pds = await fetch_record(did, collection, rkey)
    
    # Display results
    console.print(f"[cyan]DID:[/cyan] {did}")
    console.print(f"[cyan]PDS:[/cyan] {pds}")
    console.print(f"[cyan]Collection:[/cyan] {collection}")
    console.print(f"[cyan]Record Key:[/cyan] {rkey}")
    console.print()
    
    if record_data is None:
        console.print("[red]Status: NOT FOUND (404)[/red]")
        console.print("\n[yellow]Possible issues:[/yellow]")
        console.print("  • Record was deleted")
        console.print("  • Wrong collection name")
        console.print("  • Wrong rkey")
        console.print("  • DID doesn't exist on this PDS")
        return
    
    if "error" in record_data:
        console.print(f"[red]Status: ERROR[/red]")
        console.print(f"  {record_data['error']}")
        return
    
    console.print("[green]Status: FOUND[/green]")
    
    # Show record details
    value = record_data.get("value", {})
    schema = value.get("$type", "unknown")
    console.print(f"[cyan]Schema ($type):[/cyan] {schema}")
    
    # Check if it's a known comind schema
    known_schemas = [
        "network.comind.thought",
        "network.comind.memory", 
        "network.comind.concept",
        "network.comind.hypothesis",
        "network.comind.devlog",
        "network.comind.agent.profile",
        "network.comind.agent.registration",
        "app.bsky.feed.post",
        "com.whtwnd.blog.entry",
        "app.greengale.document",
    ]
    
    if schema in known_schemas:
        console.print(f"  [green]✓ Known schema[/green]")
    else:
        console.print(f"  [yellow]⚠ Unknown schema (may be valid)[/yellow]")
    
    # Check indexing for comind records
    if schema.startswith("network.comind."):
        indexed = await check_indexed(uri)
        if indexed:
            console.print(f"[cyan]Indexed:[/cyan] [green]✓ Yes[/green]")
        else:
            console.print(f"[cyan]Indexed:[/cyan] [yellow]✗ Not in XRPC indexer[/yellow]")
    
    # Show content preview
    console.print()
    content_fields = ["text", "content", "thought", "title", "description", "name"]
    for field in content_fields:
        if field in value:
            preview = str(value[field])[:200]
            console.print(Panel(preview, title=f"Content ({field})", border_style="dim"))
            break
    
    # Show full record
    console.print("\n[dim]Full record:[/dim]")
    import json
    console.print(json.dumps(value, indent=2, default=str)[:1000])


def main():
    if len(sys.argv) < 2:
        console.print("""
[bold]ATProto Record Inspector[/bold]

Usage:
  python inspect.py <at-uri>
  python inspect.py <handle> <collection> <rkey>

Examples:
  python inspect.py at://did:plc:abc.../network.comind.thought/123
  python inspect.py @central.comind.network network.comind.agent.profile self
""")
        return
    
    asyncio.run(inspect(sys.argv[1:]))


if __name__ == "__main__":
    main()
