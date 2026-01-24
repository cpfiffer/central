"""
ATProtocol Identity Resolution Tool

Explore the identity layer of ATProtocol:
- Resolve handles to DIDs
- Resolve DIDs to DID documents
- Understand the relationship between handles, DIDs, and PDS hosts
"""

import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.json import JSON
import json

console = Console()

# Public ATProtocol endpoints
PUBLIC_API = "https://public.api.bsky.app"
PLC_DIRECTORY = "https://plc.directory"


async def resolve_handle(handle: str) -> dict | None:
    """
    Resolve a handle (like @user.bsky.social) to a DID.
    
    Handles are human-readable identifiers that map to DIDs.
    The resolution can happen via:
    1. DNS TXT record (_atproto.handle)
    2. HTTPS well-known endpoint (/.well-known/atproto-did)
    3. The PDS's resolveHandle endpoint
    """
    # Clean handle (remove @ if present)
    handle = handle.lstrip("@")
    
    async with httpx.AsyncClient() as client:
        try:
            # Use the public API's resolveHandle endpoint
            response = await client.get(
                f"{PUBLIC_API}/xrpc/com.atproto.identity.resolveHandle",
                params={"handle": handle}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            console.print(f"[red]Error resolving handle: {e}[/red]")
            return None


async def get_did_document(did: str) -> dict | None:
    """
    Fetch the DID document for a given DID.
    
    DID documents contain:
    - Verification methods (public keys)
    - Service endpoints (PDS location)
    - Also known as (handles)
    
    Supports:
    - did:plc: (PLC directory lookup)
    - did:web: (HTTPS well-known lookup)
    """
    async with httpx.AsyncClient() as client:
        try:
            if did.startswith("did:plc:"):
                # PLC DIDs are resolved via the PLC directory
                response = await client.get(f"{PLC_DIRECTORY}/{did}")
            elif did.startswith("did:web:"):
                # Web DIDs are resolved via HTTPS
                domain = did.replace("did:web:", "").replace("%3A", ":")
                response = await client.get(f"https://{domain}/.well-known/did.json")
            else:
                console.print(f"[red]Unknown DID method: {did}[/red]")
                return None
            
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            console.print(f"[red]Error fetching DID document: {e}[/red]")
            return None


async def get_profile(actor: str) -> dict | None:
    """
    Get the Bluesky profile for an actor (handle or DID).
    
    This returns the social profile data stored in the app.bsky.actor.profile record.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{PUBLIC_API}/xrpc/app.bsky.actor.getProfile",
                params={"actor": actor}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            console.print(f"[red]Error fetching profile: {e}[/red]")
            return None


def display_identity(handle: str, did_data: dict, did_doc: dict, profile: dict | None = None):
    """Display identity information in a rich format."""
    
    console.print(Panel(f"[bold cyan]Identity Analysis: {handle}[/bold cyan]"))
    
    # Basic identity info
    table = Table(title="Identity Mapping")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Handle", handle)
    table.add_row("DID", did_data.get("did", "N/A"))
    
    if did_doc:
        # Extract PDS endpoint
        services = did_doc.get("service", [])
        pds = next((s for s in services if s.get("id") == "#atproto_pds"), None)
        if pds:
            table.add_row("PDS Endpoint", pds.get("serviceEndpoint", "N/A"))
        
        # Extract verification methods
        verification = did_doc.get("verificationMethod", [])
        for vm in verification:
            table.add_row(f"Key ({vm.get('id', 'unknown')})", vm.get("publicKeyMultibase", "N/A")[:32] + "...")
    
    console.print(table)
    
    # Profile info if available
    if profile:
        console.print()
        profile_table = Table(title="Bluesky Profile")
        profile_table.add_column("Property", style="cyan")
        profile_table.add_column("Value", style="green")
        
        profile_table.add_row("Display Name", profile.get("displayName", "N/A"))
        profile_table.add_row("Description", (profile.get("description", "N/A") or "N/A")[:100])
        profile_table.add_row("Followers", str(profile.get("followersCount", 0)))
        profile_table.add_row("Following", str(profile.get("followsCount", 0)))
        profile_table.add_row("Posts", str(profile.get("postsCount", 0)))
        
        console.print(profile_table)
    
    # Raw DID document
    console.print()
    console.print(Panel(JSON(json.dumps(did_doc, indent=2)), title="DID Document (Raw)"))


async def explore_identity(handle_or_did: str):
    """
    Main entry point for identity exploration.
    
    Given a handle or DID, resolve and display all identity information.
    """
    console.print(f"\n[bold]Exploring identity: {handle_or_did}[/bold]\n")
    
    # Determine if input is a handle or DID
    if handle_or_did.startswith("did:"):
        did = handle_or_did
        # Get DID document first to find the handle
        did_doc = await get_did_document(did)
        if did_doc:
            handles = did_doc.get("alsoKnownAs", [])
            handle = handles[0].replace("at://", "") if handles else "unknown"
            did_data = {"did": did}
        else:
            console.print("[red]Could not resolve DID[/red]")
            return
    else:
        handle = handle_or_did.lstrip("@")
        # Resolve handle to DID
        did_data = await resolve_handle(handle)
        if not did_data:
            console.print("[red]Could not resolve handle[/red]")
            return
        
        did = did_data["did"]
        did_doc = await get_did_document(did)
    
    # Get profile
    profile = await get_profile(handle)
    
    # Display everything
    display_identity(handle, did_data, did_doc, profile)
    
    return {
        "handle": handle,
        "did": did,
        "did_document": did_doc,
        "profile": profile
    }


if __name__ == "__main__":
    import asyncio
    import sys
    
    target = sys.argv[1] if len(sys.argv) > 1 else "bsky.app"
    asyncio.run(explore_identity(target))
