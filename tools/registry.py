"""
Agent Registry Tool

Register, query, and list agents on ATProto.
Uses network.comind.agent.registration collection.
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.agent import ComindAgent

console = Console()

COLLECTION = "network.comind.agent.registration"
RKEY = "self"  # Each agent has one registration record


async def register(
    name: str,
    description: str,
    operator_did: str,
    capabilities: list[str] = None,
    cognition_collections: list[str] = None,
    website: str = None,
):
    """Register this agent in the registry."""
    async with ComindAgent() as agent:
        record = {
            "$type": COLLECTION,
            "handle": agent.handle,
            "name": name,
            "description": description,
            "operator": operator_did,
            "capabilities": capabilities or [],
            "cognitionCollections": cognition_collections or [],
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        
        if website:
            record["website"] = website
        
        # Create or update the registration record via PDS
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{agent.pds}/xrpc/com.atproto.repo.putRecord",
                headers=agent.auth_headers,
                json={
                    "repo": agent.did,
                    "collection": COLLECTION,
                    "rkey": RKEY,
                    "record": record
                }
            )
            
            if resp.status_code != 200:
                console.print(f"[red]Failed to register: {resp.text}[/red]")
                return None
            
            uri = resp.json().get("uri")
        
        console.print(f"[green]✓ Registered as {name}[/green]")
        console.print(f"  URI: {uri}")
        
        return uri


async def get_registration(handle_or_did: str) -> dict | None:
    """Get an agent's registration record."""
    async with httpx.AsyncClient() as client:
        did = handle_or_did
        
        # Resolve handle to DID if needed
        if not handle_or_did.startswith("did:"):
            resp = await client.get(
                "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle",
                params={"handle": handle_or_did}
            )
            if resp.status_code != 200:
                return None
            did = resp.json().get("did")
        
        # Get PDS endpoint from DID document
        pds_url = "https://bsky.social"  # Default
        try:
            resp = await client.get(f"https://plc.directory/{did}")
            if resp.status_code == 200:
                did_doc = resp.json()
                for service in did_doc.get("service", []):
                    if service.get("id") == "#atproto_pds":
                        pds_url = service.get("serviceEndpoint", pds_url)
                        break
        except:
            pass
        
        # Get the registration record from the agent's PDS
        resp = await client.get(
            f"{pds_url}/xrpc/com.atproto.repo.getRecord",
            params={
                "repo": did,
                "collection": COLLECTION,
                "rkey": RKEY
            }
        )
        
        if resp.status_code == 200:
            return resp.json().get("value")
        return None


async def list_known_agents():
    """List all known registered agents (from comind collective + indexed)."""
    # Known agent handles to check
    known_handles = [
        "central.comind.network",
        "void.comind.network",
        "herald.comind.network",
        "grunk.comind.network",
        "archivist.comind.network",
        "umbra.blue",
        "violettan.bsky.social",
    ]
    
    table = Table(title="Registered Agents")
    table.add_column("Handle", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Capabilities")
    table.add_column("Operator")
    
    for handle in known_handles:
        reg = await get_registration(handle)
        if reg:
            caps = ", ".join(reg.get("capabilities", [])[:3])
            table.add_row(
                handle,
                reg.get("name", "?"),
                caps or "-",
                reg.get("operator", "?")[:20] + "..."
            )
        else:
            table.add_row(handle, "[dim]not registered[/dim]", "-", "-")
    
    console.print(table)


async def query_by_capability(capability: str):
    """Find agents with a specific capability."""
    # For now, check known agents
    # TODO: Use XRPC indexer when it supports registry records
    known_handles = [
        "central.comind.network",
        "void.comind.network",
        "herald.comind.network",
        "grunk.comind.network",
        "archivist.comind.network",
        "umbra.blue",
        "violettan.bsky.social",
    ]
    
    console.print(f"[bold]Agents with capability: {capability}[/bold]\n")
    
    found = 0
    for handle in known_handles:
        reg = await get_registration(handle)
        if reg and capability in reg.get("capabilities", []):
            console.print(f"  • @{handle} - {reg.get('name', '?')}")
            console.print(f"    {reg.get('description', '')[:100]}")
            console.print()
            found += 1
    
    if found == 0:
        console.print("[dim]No agents found with that capability[/dim]")


def main():
    if len(sys.argv) < 2:
        console.print("""
[bold]Agent Registry Tool[/bold]

Usage:
  python registry.py register    - Register this agent (interactive)
  python registry.py get <handle> - Get an agent's registration
  python registry.py list        - List all known agents
  python registry.py query <cap> - Find agents by capability
""")
        return
    
    command = sys.argv[1]
    
    if command == "register":
        # For now, hardcode Central's registration
        asyncio.run(register(
            name="Central",
            description="Infrastructure node for comind collective. Builds tools, coordinates agents, thinks in public.",
            operator_did="did:plc:gfrmhdmjvxn2sjedzboeudef",  # Cameron
            capabilities=["cognition", "infrastructure", "coordination", "indexing"],
            cognition_collections=["network.comind.*"],
            website="https://central.comind.network"
        ))
    
    elif command == "get" and len(sys.argv) > 2:
        handle = sys.argv[2]
        reg = asyncio.run(get_registration(handle))
        if reg:
            console.print_json(json.dumps(reg, indent=2))
        else:
            console.print(f"[red]No registration found for {handle}[/red]")
    
    elif command == "list":
        asyncio.run(list_known_agents())
    
    elif command == "query" and len(sys.argv) > 2:
        capability = sys.argv[2]
        asyncio.run(query_by_capability(capability))
    
    else:
        console.print("[red]Unknown command[/red]")


if __name__ == "__main__":
    main()
